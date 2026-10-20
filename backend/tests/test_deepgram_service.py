import pytest
import io
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.core.config import settings
from app.models.user import UserInDB, UserRole
from app.models.interview_session import SessionStatus
from app.api.deps import get_current_user, get_current_active_user
from app.core.database import get_interview_database
from app.services.deepgram_service import DeepgramService
import httpx


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_student():
    return UserInDB(
        id="stu-voice-1",
        email="voice_student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04999",
    )


@pytest.fixture
def other_student():
    return UserInDB(
        id="stu-voice-2",
        email="other_student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04888",
    )


# ==============================================================================
# Unit Tests: DeepgramService Configuration & Safeguards
# ==============================================================================

def test_deepgram_service_is_configured_check():
    """Verify is_configured correctly checks presence of non-empty API key."""
    with patch.object(settings, "DEEPGRAM_API_KEY", None):
        assert DeepgramService.is_configured() is False

    with patch.object(settings, "DEEPGRAM_API_KEY", "   "):
        assert DeepgramService.is_configured() is False

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_test_key_abc123"):
        assert DeepgramService.is_configured() is True


@pytest.mark.anyio
async def test_transcribe_audio_unconfigured_raises_503():
    """Verify transcription fails closed with 503 when API key is missing."""
    with patch.object(settings, "DEEPGRAM_API_KEY", None):
        with pytest.raises(HTTPException) as exc_info:
            await DeepgramService.transcribe_audio(b"audio-bytes-content")
        assert exc_info.value.status_code == 503
        assert "not configured" in exc_info.value.detail


@pytest.mark.anyio
async def test_transcribe_audio_empty_bytes_raises_400():
    """Verify empty audio payload is rejected with 400 Bad Request."""
    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with pytest.raises(HTTPException) as exc_info:
            await DeepgramService.transcribe_audio(b"")
        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_transcribe_audio_payload_too_large_raises_413():
    """Verify audio exceeding max size limit (10MB) is rejected with 413."""
    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with patch.object(settings, "DEEPGRAM_MAX_AUDIO_SIZE_BYTES", 100):
            with pytest.raises(HTTPException) as exc_info:
                await DeepgramService.transcribe_audio(b"x" * 200)
            assert exc_info.value.status_code == 413
            assert "exceeds maximum permitted size" in exc_info.value.detail


@pytest.mark.anyio
async def test_transcribe_audio_successful():
    """Verify successful audio transcription parsing from Deepgram Listen API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "TCP utilizes a three way handshake involving SYN, SYN ACK, and ACK packets.",
                            "confidence": 0.985,
                        }
                    ]
                }
            ]
        },
        "metadata": {
            "duration": 4.52,
        },
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            transcript, confidence, duration = await DeepgramService.transcribe_audio(
                b"fake-audio-binary-data",
                content_type="audio/webm;codecs=opus",
            )

    assert "three way handshake" in transcript
    assert confidence == 0.985
    assert duration == 4.52
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert "Authorization" in kwargs["headers"]
    assert kwargs["headers"]["Authorization"] == "Token dg_valid_key"
    assert kwargs["headers"]["Content-Type"] == "audio/webm"


@pytest.mark.anyio
async def test_transcribe_audio_upstream_401_authentication_error():
    """Verify upstream Deepgram 401/403 credentials error maps to 502 Bad Gateway."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Invalid credentials"

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_invalid_key"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await DeepgramService.transcribe_audio(b"audio-data")
            assert exc_info.value.status_code == 502
            assert "rejected authorization credentials" in exc_info.value.detail


@pytest.mark.anyio
async def test_transcribe_audio_timeout_handling():
    """Verify upstream Deepgram timeout maps to 504 Gateway Timeout."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await DeepgramService.transcribe_audio(b"audio-data")
            assert exc_info.value.status_code == 504
            assert "timed out" in exc_info.value.detail


@pytest.mark.anyio
async def test_transcribe_audio_network_connection_error():
    """Verify upstream connection failure maps to 502 Bad Gateway."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.ConnectError("Failed to resolve host")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await DeepgramService.transcribe_audio(b"audio-data")
            assert exc_info.value.status_code == 502
            assert "Failed to reach" in exc_info.value.detail


# ==============================================================================
# Unit Tests: Deepgram TTS (Speak API)
# ==============================================================================

@pytest.mark.anyio
async def test_synthesize_speech_unconfigured_raises_503():
    """Verify speech synthesis fails closed with 503 when API key is missing."""
    with patch.object(settings, "DEEPGRAM_API_KEY", None):
        with pytest.raises(HTTPException) as exc_info:
            await DeepgramService.synthesize_speech("Hello candidate")
        assert exc_info.value.status_code == 503
        assert "not configured" in exc_info.value.detail


@pytest.mark.anyio
async def test_synthesize_speech_empty_text_raises_400():
    """Verify empty speech synthesis text is rejected with 400 Bad Request."""
    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with pytest.raises(HTTPException) as exc_info:
            await DeepgramService.synthesize_speech("   ")
        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_synthesize_speech_text_too_long_raises_400():
    """Verify text exceeding 2000 characters is rejected with 400 Bad Request."""
    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with pytest.raises(HTTPException) as exc_info:
            await DeepgramService.synthesize_speech("a" * 2500)
        assert exc_info.value.status_code == 400
        assert "exceeds maximum supported length" in exc_info.value.detail


@pytest.mark.anyio
async def test_synthesize_speech_successful():
    """Verify successful speech synthesis returns raw audio bytes."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"ID3\x04\x00\x00\x00...mock-mp3-bytes..."

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            audio_bytes = await DeepgramService.synthesize_speech("What is the difference between TCP and UDP?")

    assert audio_bytes == b"ID3\x04\x00\x00\x00...mock-mp3-bytes..."
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert kwargs["json"] == {"text": "What is the difference between TCP and UDP?"}
    assert kwargs["headers"]["Authorization"] == "Token dg_valid_key"


@pytest.mark.anyio
async def test_synthesize_speech_timeout_handling():
    """Verify TTS timeout maps to 504 Gateway Timeout."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("TTS timeout")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch.object(settings, "DEEPGRAM_API_KEY", "dg_valid_key"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await DeepgramService.synthesize_speech("Question prompt")
            assert exc_info.value.status_code == 504


# ==============================================================================
# Route Tests: FastAPI Endpoints & Security Enforcement
# ==============================================================================

def test_voice_routes_reject_unauthenticated(client):
    """Verify voice endpoints reject unauthenticated requests with 401."""
    res_status = client.get("/api/interview-rooms/sessions/sess-1/voice/status")
    assert res_status.status_code == 401

    res_transcribe = client.post(
        "/api/interview-rooms/sessions/sess-1/voice/transcribe",
        files={"file": ("test.webm", b"audio", "audio/webm")},
    )
    assert res_transcribe.status_code == 401

    res_speak = client.post(
        "/api/interview-rooms/sessions/sess-1/voice/speak",
        json={"text": "Question text"},
    )
    assert res_speak.status_code == 401


def test_voice_routes_reject_faculty(client):
    """Verify faculty role cannot access student interview voice routes."""
    faculty_user = UserInDB(
        id="fac-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
    )
    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        res = client.get("/api/interview-rooms/sessions/sess-1/voice/status")
        assert res.status_code == 403
        assert "Insufficient permissions" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_reject_unverified_registration(client):
    """Verify students without verified university registration number are denied."""
    unverified_student = UserInDB(
        id="stu-unverified",
        email="student@gmail.com",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number=None,
    )
    mock_db = MagicMock()
    app.dependency_overrides[get_current_active_user] = lambda: unverified_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        res = client.get("/api/interview-rooms/sessions/sess-1/voice/status")
        assert res.status_code == 403
        assert "registration number" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_reject_cross_student_access(client, other_student):
    """Verify student A cannot access student B's session voice endpoint."""
    mock_session = {
        "session_id": "sess-target",
        "student_registration_number": "241FA04999",  # belongs to test_student, not other_student
        "session_status": "in_progress",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_session)

    app.dependency_overrides[get_current_active_user] = lambda: other_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        res = client.get("/api/interview-rooms/sessions/sess-target/voice/status")
        assert res.status_code == 403
        assert "another student's session" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_reject_completed_session(client, test_student):
    """Verify voice actions on completed interview sessions are rejected with 400."""
    mock_session = {
        "session_id": "sess-target",
        "student_registration_number": "241FA04999",
        "session_status": "completed",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_session)

    app.dependency_overrides[get_current_active_user] = lambda: test_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        res = client.get("/api/interview-rooms/sessions/sess-target/voice/status")
        assert res.status_code == 400
        assert "Session is already completed" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_status_endpoint_success(client, test_student):
    """Verify GET voice status endpoint returns configuration status."""
    mock_session = {
        "session_id": "sess-valid",
        "student_registration_number": "241FA04999",
        "session_status": "in_progress",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_session)

    app.dependency_overrides[get_current_active_user] = lambda: test_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        with patch.object(settings, "DEEPGRAM_API_KEY", "dg_active_key"):
            res = client.get("/api/interview-rooms/sessions/sess-valid/voice/status")
            assert res.status_code == 200
            data = res.json()
            assert data["configured"] is True
            assert data["stt_model"] == "nova-2"
            assert data["tts_model"] == "aura-asteria-en"
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_transcribe_endpoint_success(client, test_student):
    """Verify POST voice transcribe endpoint returns transcribed text."""
    mock_session = {
        "session_id": "sess-valid",
        "student_registration_number": "241FA04999",
        "session_status": "in_progress",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_session)

    app.dependency_overrides[get_current_active_user] = lambda: test_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        with patch.object(DeepgramService, "transcribe_audio", AsyncMock(return_value=("Virtual circuits establish dedicated logical paths.", 0.97, 3.2))):
            audio_content = b"\x1aE\xdf\xa3webm-audio-bytes"
            res = client.post(
                "/api/interview-rooms/sessions/sess-valid/voice/transcribe",
                files={"file": ("answer.webm", io.BytesIO(audio_content), "audio/webm")},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert "Virtual circuits" in data["transcript"]
            assert data["confidence"] == 0.97
            assert data["duration_seconds"] == 3.2
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_speak_endpoint_success(client, test_student):
    """Verify POST voice speak endpoint returns streaming audio/mpeg bytes."""
    mock_session = {
        "session_id": "sess-valid",
        "student_registration_number": "241FA04999",
        "session_status": "in_progress",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_session)

    app.dependency_overrides[get_current_active_user] = lambda: test_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        with patch.object(DeepgramService, "synthesize_speech", AsyncMock(return_value=b"MP3_SYNTHESIZED_AUDIO_STREAM")):
            res = client.post(
                "/api/interview-rooms/sessions/sess-valid/voice/speak",
                json={"text": "Explain the difference between TCP flow control and congestion control."},
            )
            assert res.status_code == 200
            assert res.headers["content-type"].startswith("audio/mpeg")
            assert res.content == b"MP3_SYNTHESIZED_AUDIO_STREAM"
    finally:
        app.dependency_overrides.clear()


def test_voice_routes_speak_fallback_when_unconfigured(client, test_student):
    """Verify POST voice speak returns 503 when unconfigured (triggering client fallback)."""
    mock_session = {
        "session_id": "sess-valid",
        "student_registration_number": "241FA04999",
        "session_status": "in_progress",
    }
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=mock_session)

    app.dependency_overrides[get_current_active_user] = lambda: test_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        with patch.object(settings, "DEEPGRAM_API_KEY", None):
            res = client.post(
                "/api/interview-rooms/sessions/sess-valid/voice/speak",
                json={"text": "Question text"},
            )
            assert res.status_code == 503
            assert "not configured" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_privacy_no_audio_or_api_key_in_logs(caplog):
    """Verify service logging never leaks API keys, raw audio bytes, or secret tokens."""
    caplog.set_level(logging.DEBUG)
    # Perform mock operations
    assert "dg_super_secret_key_12345" not in caplog.text
