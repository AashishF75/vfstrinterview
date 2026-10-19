import json
import logging
import pytest
import httpx
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.core.config import settings
from app.models.interview_session import (
    QuestionDifficulty,
    SessionStatus,
    EvaluatorMode,
    utc_now,
)
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.user import UserInDB, UserRole
from app.services.ai_provider import (
    BaseInterviewAIProvider,
    GeminiInterviewAIProvider,
    MockRuleEngineProvider,
    get_ai_provider,
    AIProviderError,
    AIProviderUnavailableError,
    AdaptiveDifficultyPolicy,
)
from app.services.interview_session_service import InterviewSessionService


def make_student(reg_no="241FA04001"):
    return UserInDB(
        email=f"test_{reg_no.lower()}@vignan.ac.in",
        full_name="Test Student",
        role=UserRole.STUDENT,
        registration_number=reg_no,
        hashed_password="mock_hash_test_123",
        is_active=True,
    )


def build_gemini_mock_response(status_code: int, content_dict_or_text, usage_metadata=None, headers=None):
    """Builds a mock httpx.Response simulating Google Gemini API."""
    if isinstance(content_dict_or_text, dict):
        gemini_payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps(content_dict_or_text)}
                        ],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ]
        }
        if usage_metadata:
            gemini_payload["usageMetadata"] = usage_metadata
        raw_text = json.dumps(gemini_payload)
    elif isinstance(content_dict_or_text, str):
        raw_text = content_dict_or_text
    else:
        raw_text = ""

    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent")
    return httpx.Response(status_code=status_code, text=raw_text, headers=headers or {}, request=req)


# ==============================================================================
# 1. Gemini Provider Construction & Missing API Key Tests
# ==============================================================================

def test_gemini_provider_requires_api_key():
    """Verify Gemini provider raises AIProviderUnavailableError if key is missing or blank."""
    with pytest.raises(AIProviderUnavailableError, match="GEMINI_API_KEY must not be empty"):
        GeminiInterviewAIProvider(api_key="")

    with pytest.raises(AIProviderUnavailableError):
        GeminiInterviewAIProvider(api_key="   ")


def test_factory_fails_closed_when_gemini_key_missing():
    """Verify get_ai_provider fails closed when AI_PROVIDER='gemini' but key is missing, even if fallback is True."""
    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", ""):
            with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", True):
                with pytest.raises(AIProviderUnavailableError, match="GEMINI_API_KEY is not configured"):
                    get_ai_provider()


def test_factory_returns_gemini_provider_when_configured():
    """Verify get_ai_provider constructs GeminiInterviewAIProvider when configured."""
    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", "mock-test-key-12345"):
            provider = get_ai_provider()
            assert isinstance(provider, GeminiInterviewAIProvider)
            assert provider.get_mode() == EvaluatorMode.GEMINI


# ==============================================================================
# 2. Valid Structured Output Generation
# ==============================================================================

@pytest.mark.anyio
async def test_gemini_generate_question_valid():
    """Verify Gemini question generation with structured JSON."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    expected_q = {
        "question_text": "Explain how the TCP 3-way handshake handles synchronization and sequence numbers.",
        "topic": "TCP Protocol",
        "difficulty": "medium",
    }
    mock_resp = build_gemini_mock_response(200, expected_q)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.generate_question(
            topic="Networking Essentials",
            instructions="Focus on transport layer",
            difficulty=QuestionDifficulty.MEDIUM,
            question_index=1,
            previous_questions=[],
        )

        assert res["question_text"] == expected_q["question_text"]
        assert res["topic"] == expected_q["topic"]
        assert res["difficulty"] == QuestionDifficulty.MEDIUM
        # Ensure API key is sent via header and NOT in URL
        sent_call = mock_post.call_args
        assert sent_call.kwargs["headers"]["x-goog-api-key"] == "test-key"
        assert "key=" not in sent_call.args[0]


@pytest.mark.anyio
async def test_gemini_evaluate_answer_valid():
    """Verify Gemini answer evaluation with structured rubric."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    expected_eval = {
        "score": 8.5,
        "feedback": "Strong explanation of SYN, SYN-ACK, and sequence number assignment.",
        "strengths": ["Precise handshake steps", "Correct flag usage"],
        "improvements": ["Mention window scaling options"],
        "rationale": "High relevance and technical correctness.",
    }
    mock_resp = build_gemini_mock_response(200, expected_eval)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        eval_res = await provider.evaluate_answer(
            question="Describe the TCP handshake.",
            answer="Host A sends SYN with ISN, Host B replies with SYN-ACK, Host A sends ACK.",
            difficulty=QuestionDifficulty.MEDIUM,
            topic="TCP Transport",
        )

        assert eval_res["score"] == 8.5
        assert "Strong explanation" in eval_res["feedback"]
        assert len(eval_res["strengths"]) == 2
        assert len(eval_res["improvements"]) == 1
        assert eval_res["rationale"] is not None


@pytest.mark.anyio
async def test_gemini_generate_scorecard_summary_valid():
    """Verify Gemini scorecard summary generation."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    expected_summary = {
        "overall_score": 8.0,
        "percentage_score": 80.0,
        "performance_level": "Proficient",
        "summary_feedback": "Consistently strong understanding of networking protocols.",
        "strengths": ["Clear TCP handshake explanation", "Accurate subnetting"],
        "areas_for_growth": ["Deepen OSPF LSA understanding"],
    }
    mock_resp = build_gemini_mock_response(200, expected_summary)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        responses = [
            {"question_index": 1, "question_text": "What is ARP?", "difficulty": "medium", "evaluation_score": 8.0, "evaluation_feedback": "Good"},
            {"question_index": 2, "question_text": "What is TCP?", "difficulty": "medium", "evaluation_score": 8.0, "evaluation_feedback": "Great"},
        ]
        res = await provider.generate_scorecard_summary(responses=responses, interview_title="Networking Assessment")

        assert res["overall_score"] == 8.0
        assert res["percentage_score"] == 80.0
        assert res["performance_level"] == "Proficient"
        assert len(res["strengths"]) == 2


# ==============================================================================
# 3. Code Fences and Clamping Protections
# ==============================================================================

@pytest.mark.anyio
async def test_gemini_handles_markdown_code_fences():
    """Verify markdown ```json code fences returned by model are stripped cleanly."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    raw_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "```json\n{\"question_text\": \"Explain 802.1Q trunking tags.\", \"topic\": \"VLANs\", \"difficulty\": \"medium\"}\n```"}
                    ]
                }
            }
        ]
    }
    mock_resp = httpx.Response(status_code=200, text=json.dumps(raw_payload), request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.generate_question(
            topic="VLANs", instructions="", difficulty=QuestionDifficulty.MEDIUM, question_index=1, previous_questions=[]
        )
        assert res["question_text"] == "Explain 802.1Q trunking tags."
        assert res["topic"] == "VLANs"


@pytest.mark.anyio
async def test_gemini_clamps_score_to_ten():
    """Verify score is clamped within [0.0, 10.0]."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    mock_resp = build_gemini_mock_response(200, {
        "score": 11.5,  # Exceeds 10
        "feedback": "Exceptional answer that exceeded expectations.",
        "strengths": ["Flawless"],
        "improvements": [],
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.evaluate_answer("What is IP?", "IP is ...", QuestionDifficulty.EASY, "IP")
        assert res["score"] == 10.0


# ==============================================================================
# 4. Error Handling: Malformed JSON, Missing Fields, HTTP Errors, Timeouts
# ==============================================================================

@pytest.mark.anyio
async def test_gemini_handles_malformed_json():
    """Verify malformed JSON from Gemini raises AIProviderError."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    raw_payload = {
        "candidates": [
            {"content": {"parts": [{"text": "{ not valid json here ..."}]}}
        ]
    }
    mock_resp = httpx.Response(status_code=200, text=json.dumps(raw_payload), request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="valid JSON"):
            await provider.evaluate_answer("Q?", "A", QuestionDifficulty.MEDIUM, "T")


@pytest.mark.anyio
async def test_gemini_handles_missing_schema_fields():
    """Verify missing required fields in JSON raises AIProviderError."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    # Missing 'score' field
    mock_resp = build_gemini_mock_response(200, {
        "feedback": "Good answer but missing score.",
        "strengths": [],
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="required evaluation schema"):
            await provider.evaluate_answer("Q?", "A", QuestionDifficulty.MEDIUM, "T")


@pytest.mark.anyio
async def test_gemini_handles_auth_failure_401_403():
    """Verify HTTP 401 or 403 raises AIProviderError without exposing keys."""
    provider = GeminiInterviewAIProvider(api_key="secret-key")
    mock_resp = httpx.Response(status_code=401, text='{"error": "API_KEY_INVALID"}', request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="authentication failed"):
            await provider.generate_question("T", "", QuestionDifficulty.EASY, 1, [])


@pytest.mark.anyio
async def test_gemini_handles_rate_limit_and_quota_429():
    """Verify HTTP 429 raises AIProviderError with rate limit detail."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    mock_resp = httpx.Response(status_code=429, text='{"error": "RESOURCE_EXHAUSTED"}', request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="quota or rate limit exceeded"):
            await provider.evaluate_answer("Q?", "A", QuestionDifficulty.MEDIUM, "T")


@pytest.mark.anyio
async def test_gemini_handles_service_unavailable_503():
    """Verify HTTP 503 raises AIProviderError."""
    provider = GeminiInterviewAIProvider(api_key="test-key")
    mock_resp = httpx.Response(status_code=503, text='{"error": "Service Unavailable"}', request=httpx.Request("POST", "http://test"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="temporarily unavailable"):
            await provider.evaluate_answer("Q?", "A", QuestionDifficulty.MEDIUM, "T")


@pytest.mark.anyio
async def test_gemini_handles_timeout():
    """Verify httpx.TimeoutException raises AIProviderError."""
    provider = GeminiInterviewAIProvider(api_key="test-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ReadTimeout("Connection timed out")
        with pytest.raises(AIProviderError, match="timed out"):
            await provider.evaluate_answer("Q?", "A", QuestionDifficulty.MEDIUM, "T")


# ==============================================================================
# 5. Fail-Closed Protection (No Silent Mock Fallback)
# ==============================================================================

@pytest.mark.anyio
async def test_no_silent_mock_fallback_on_gemini_failure():
    """
    Verify that when AI_PROVIDER is 'gemini', an error from Gemini raises HTTP 503
    and does NOT silently substitute MockRuleEngineProvider results.
    """
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("241FA04001")
    session_id = "session-gemini-fail-1"
    now = utc_now()

    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "assignment_id": "assign-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 3,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=30),
        "active_question": {
            "question_text": "What is ARP?",
            "topic": "ARP",
            "difficulty": "medium",
        },
    }
    mock_responses.find_one.return_value = None  # No existing duplicate response

    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", "test-key"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                # Simulate Gemini 429 Quota Exhaustion
                mock_post.return_value = httpx.Response(status_code=429, text="Quota exceeded", request=httpx.Request("POST", "http://test"))

                with pytest.raises(HTTPException) as exc:
                    await InterviewSessionService.submit_answer(
                        mock_db,
                        session_id=session_id,
                        answer_text="ARP resolves IP addresses to MAC addresses.",
                        student_user=student,
                    )

                # Must fail-closed with 503 and NOT silently return mock evaluation
                assert exc.value.status_code == 503
                assert "AI evaluation service is temporarily unavailable" in exc.value.detail
                # Crucial reliability check: DB must not have inserted response
                assert not mock_responses.insert_one.called
                assert not mock_sessions.update_one.called


# ==============================================================================
# 6. Session Lifecycle & Duplicate Submission Protections
# ==============================================================================

@pytest.mark.anyio
async def test_duplicate_submission_rejected_before_ai_provider():
    """Verify duplicate submission check halts immediately without invoking AI."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
    }[name]

    student = make_student("241FA04001")
    now = utc_now()
    mock_sessions.find_one.return_value = {
        "session_id": "session-dup-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 3,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=20),
        "active_question": {"question_text": "Q?", "topic": "T", "difficulty": "medium"},
    }
    # Response already exists in DB
    mock_responses.find_one.return_value = {"response_id": "resp-already-1", "question_index": 1}

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.submit_answer(
            mock_db,
            session_id="session-dup-1",
            answer_text="Second attempt to answer question 1.",
            student_user=student,
        )

    assert exc.value.status_code == 409
    assert "already been submitted" in exc.value.detail


@pytest.mark.anyio
async def test_submission_to_completed_or_expired_session_rejected():
    """Verify answers cannot be submitted to completed or expired sessions."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_db.__getitem__.side_effect = lambda name: {"interview_sessions": mock_sessions}[name]

    student = make_student("241FA04001")

    # 1. Completed session
    mock_sessions.find_one.return_value = {
        "session_id": "session-comp-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.COMPLETED.value,
        "expires_at": utc_now() + timedelta(minutes=20),
    }
    with pytest.raises(HTTPException) as exc1:
        await InterviewSessionService.submit_answer(
            mock_db, session_id="session-comp-1", answer_text="Late answer", student_user=student
        )
    assert exc1.value.status_code == 400
    assert "already completed" in exc1.value.detail

    # 2. Expired session
    mock_sessions.find_one.return_value = {
        "session_id": "session-exp-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "expires_at": utc_now() - timedelta(minutes=5),  # Expired
    }
    with pytest.raises(HTTPException) as exc2:
        await InterviewSessionService.submit_answer(
            mock_db, session_id="session-exp-1", answer_text="Late answer", student_user=student
        )
    assert exc2.value.status_code == 400
    assert "duration has expired" in exc2.value.detail


# ==============================================================================
# 7. Scorecard Persistence, Provider Mode Labelling, & Disclaimer Verifications
# ==============================================================================

@pytest.mark.anyio
async def test_gemini_scorecard_persistence_and_provider_mode_labelling():
    """
    Verify complete session completed under Gemini mode:
    - Persists responses with evaluator_mode='gemini'
    - Persists scorecard with evaluator_mode='gemini'
    - Disclaimer contains explicit AI notice and does not claim objective/bias-free scoring
    """
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = AsyncMock()
    mock_scorecards = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("241FA04001")
    session_id = "sess-gemini-final-1"
    now = utc_now()

    # Session is at Question 2 of 2 (Final Question)
    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-101",
        "assignment_id": "assign-101",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 2,
        "total_questions_target": 2,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=30),
        "active_question": {
            "question_text": "Explain OSPF link-state database synchronization.",
            "topic": "OSPF Routing",
            "difficulty": "medium",
        },
    }
    mock_responses.find_one.return_value = None  # No duplicate for Q2

    # Prior Q1 response in DB
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[
        {
            "question_index": 1,
            "question_text": "What is ARP?",
            "difficulty": "medium",
            "evaluation_score": 8.0,
            "evaluation_feedback": "Strong",
            "strengths": ["Clear"],
            "improvements": [],
        }
    ])

    eval_json = {
        "score": 9.0,
        "feedback": "Flawless explanation of LSAs and Dijkstra algorithm.",
        "strengths": ["Accurate Dijkstra reference", "LSA flood explanation"],
        "improvements": [],
        "rationale": "High technical depth.",
    }
    summary_json = {
        "overall_score": 8.5,
        "percentage_score": 85.0,
        "performance_level": "Exceptional",
        "summary_feedback": "Mastery of routing protocols demonstrated.",
        "strengths": ["OSPF LSAs", "ARP"],
        "areas_for_growth": ["Continue maintaining precision"],
    }

    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", "valid-key"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                # 1st call for evaluate_answer, 2nd call for generate_scorecard_summary
                mock_post.side_effect = [
                    build_gemini_mock_response(200, eval_json),
                    build_gemini_mock_response(200, summary_json),
                ]

                sub_res = await InterviewSessionService.submit_answer(
                    mock_db,
                    session_id=session_id,
                    answer_text="Routers exchange Link State Advertisements to build identical LSDBs and calculate the shortest path tree using Dijkstra.",
                    student_user=student,
                )

                assert sub_res.is_session_completed is True
                assert sub_res.scorecard_id is not None

                # Verify response doc persisted with evaluator_mode='gemini'
                assert mock_responses.insert_one.called
                saved_resp = mock_responses.insert_one.call_args[0][0]
                assert saved_resp["evaluator_mode"] == "gemini"
                assert saved_resp["evaluation_score"] == 9.0

                # Verify scorecard persisted with evaluator_mode='gemini'
                assert mock_scorecards.insert_one.called
                saved_scorecard = mock_scorecards.insert_one.call_args[0][0]
                assert saved_scorecard["evaluator_mode"] == "gemini"
                assert saved_scorecard["overall_score"] == 8.5
                assert "AI EVALUATION NOTICE" in saved_scorecard["disclaimer"]
                assert "Google Gemini" in saved_scorecard["disclaimer"]
                assert "bias-free" in saved_scorecard["disclaimer"]


@pytest.mark.anyio
async def test_mock_evaluator_regression_and_mode_labelling():
    """Verify mock rule engine continues to produce clear mock_rule_engine labelling."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = AsyncMock()
    mock_scorecards = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("241FA04001")
    session_id = "sess-mock-1"
    now = utc_now()

    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-102",
        "assignment_id": "assign-102",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 1,  # Single question session
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=30),
        "active_question": {
            "question_text": "Walk through the complete ARP process when Host A wants to communicate with Host B on the local subnet.",
            "topic": "Address Resolution Protocol (ARP)",
            "difficulty": "medium",
        },
    }
    mock_responses.find_one.return_value = None
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

    with patch.object(settings, "AI_PROVIDER", None):
        with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", True):
            sub_res = await InterviewSessionService.submit_answer(
                mock_db,
                session_id=session_id,
                answer_text="Host A broadcasts an ARP request containing Host B's IP address. Host B replies with a unicast ARP reply containing its MAC address.",
                student_user=student,
            )

            assert sub_res.is_session_completed is True
            assert mock_scorecards.insert_one.called
            saved_scorecard = mock_scorecards.insert_one.call_args[0][0]
            assert saved_scorecard["evaluator_mode"] == "mock_rule_engine"
            assert "MOCK EVALUATION NOTICE" in saved_scorecard["disclaimer"]
            assert "deterministic" in saved_scorecard["disclaimer"]


@pytest.mark.anyio
async def test_adaptive_difficulty_progression_with_gemini_evaluations():
    """Verify adaptive difficulty escalates on high Gemini scores and de-escalates on low scores."""
    # Escalation
    high_diff, r_high = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.MEDIUM, 8.5)
    assert high_diff == QuestionDifficulty.HARD
    assert "escalating from medium to hard" in r_high

    # De-escalation
    low_diff, r_low = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.MEDIUM, 4.0)
    assert low_diff == QuestionDifficulty.EASY
    assert "adjusting to foundational easy tier" in r_low

    # Maintenance
    mid_diff, r_mid = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.MEDIUM, 6.5)
    assert mid_diff == QuestionDifficulty.MEDIUM
    assert "maintaining current medium" in r_mid


@pytest.mark.anyio
async def test_provider_failure_allows_clean_session_retry():
    """
    Verify that when Gemini fails on question submission:
    1. HTTP 503 is returned.
    2. No response record was inserted into the database.
    3. The student can retry and succeed once Gemini recovers.
    """
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = AsyncMock()
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
    }[name]

    student = make_student("241FA04001")
    session_id = "sess-retry-1"
    now = utc_now()

    session_state = {
        "session_id": session_id,
        "interview_id": "int-103",
        "assignment_id": "assign-103",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 3,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=30),
        "active_question": {
            "question_text": "What is DHCP?",
            "topic": "DHCP",
            "difficulty": "medium",
        },
    }
    mock_sessions.find_one.return_value = session_state
    mock_interviews.find_one.return_value = {"title": "Networking Assessment", "instructions": ""}
    # Simulated responses collection storage
    stored_responses = []

    def mock_responses_find_one(query):
        for r in stored_responses:
            if r.get("session_id") == query.get("session_id") and r.get("question_index") == query.get("question_index"):
                return r
        return None

    mock_responses.find_one.side_effect = mock_responses_find_one
    mock_responses.insert_one.side_effect = lambda doc: stored_responses.append(doc)
    mock_responses.find.return_value.to_list = AsyncMock(return_value=[])

    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", "test-key"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                # 1. First attempt fails due to timeout
                mock_post.side_effect = httpx.ReadTimeout("Timeout")
                with pytest.raises(HTTPException) as exc:
                    await InterviewSessionService.submit_answer(
                        mock_db,
                        session_id=session_id,
                        answer_text="DHCP allocates dynamic IP addresses via DORA.",
                        student_user=student,
                    )
                assert exc.value.status_code == 503
                # Verify NOTHING was inserted into stored_responses
                assert len(stored_responses) == 0

                # 2. Second attempt succeeds once provider recovers
                eval_json = {
                    "score": 8.0,
                    "feedback": "Accurate description of DORA.",
                    "strengths": ["DORA mentioned"],
                    "improvements": [],
                    "rationale": "Clear answer.",
                }
                next_q_json = {
                    "question_text": "Explain the difference between TCP and UDP.",
                    "topic": "Transport Layer",
                    "difficulty": "hard",
                }
                mock_post.side_effect = [
                    build_gemini_mock_response(200, eval_json),
                    build_gemini_mock_response(200, next_q_json),
                ]

                sub_res = await InterviewSessionService.submit_answer(
                    mock_db,
                    session_id=session_id,
                    answer_text="DHCP allocates dynamic IP addresses via DORA.",
                    student_user=student,
                )

                assert sub_res.evaluated_score == 8.0
                assert sub_res.is_session_completed is False
                assert sub_res.next_question is not None
                assert len(stored_responses) == 1
                assert stored_responses[0]["evaluation_score"] == 8.0


# ==============================================================================
# Phase 1: Reliability, Telemetry, Bounded Retries & Grounding Tests
# ==============================================================================

@pytest.mark.anyio
async def test_gemini_usage_metadata_extraction_success(caplog):
    """Verify successful Gemini response extracts usageMetadata and logs telemetry."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key")
    expected_q = {
        "question_text": "Explain the TCP handshake mechanism.",
        "topic": "Transport Protocols",
        "difficulty": "medium",
    }
    usage_meta = {
        "promptTokenCount": 142,
        "candidatesTokenCount": 58,
        "totalTokenCount": 200,
    }
    mock_resp = build_gemini_mock_response(200, expected_q, usage_metadata=usage_meta)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.generate_question(
            topic="Transport Protocols",
            instructions="",
            difficulty=QuestionDifficulty.MEDIUM,
            question_index=1,
            previous_questions=[],
        )

        assert res["question_text"] == expected_q["question_text"]

    telemetry_logs = [r.message for r in caplog.records if "ai_request_telemetry" in r.message]
    assert len(telemetry_logs) >= 1
    raw_log = telemetry_logs[-1]
    data = json.loads(raw_log.split("AI Request Telemetry: ")[1])
    assert data["task"] == "generate_question"
    assert data["outcome"] == "success"
    assert data["prompt_tokens"] == 142
    assert data["candidates_tokens"] == 58
    assert data["total_tokens"] == 200
    assert data["http_status"] == 200
    assert data["latency_ms"] >= 0


@pytest.mark.anyio
async def test_gemini_missing_usage_metadata_recorded_as_none(caplog):
    """Verify missing usageMetadata records token counts as None without errors."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key")
    expected_eval = {
        "score": 9.0,
        "feedback": "Excellent response.",
        "strengths": ["Clarity"],
        "improvements": [],
        "rationale": "Solid technical foundation.",
    }
    mock_resp = build_gemini_mock_response(200, expected_eval, usage_metadata=None)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await provider.evaluate_answer(
            question="What is DNS?",
            answer="DNS translates domain names to IP addresses.",
            difficulty=QuestionDifficulty.EASY,
            topic="DNS",
        )
        assert res["score"] == 9.0

    telemetry_logs = [r.message for r in caplog.records if "ai_request_telemetry" in r.message]
    assert len(telemetry_logs) >= 1
    data = json.loads(telemetry_logs[-1].split("AI Request Telemetry: ")[1])
    assert data["task"] == "evaluate_answer"
    assert data["outcome"] == "success"
    assert data["prompt_tokens"] is None
    assert data["candidates_tokens"] is None
    assert data["total_tokens"] is None


def test_gemini_token_counts_not_fabricated():
    """Assert that when usageMetadata is missing or null, token counts are strictly None and never fabricated."""
    from app.services.ai_provider import AITelemetryRecord
    rec = AITelemetryRecord(
        task="evaluate_answer",
        provider="gemini",
        model="gemini-1.5-flash",
        outcome="success",
        latency_ms=125.0,
        attempts=1,
        prompt_tokens=None,
        candidates_tokens=None,
        total_tokens=None,
        http_status=200,
    )
    assert rec.prompt_tokens is None
    assert rec.candidates_tokens is None
    assert rec.total_tokens is None
    assert not isinstance(rec.prompt_tokens, int)


@pytest.mark.anyio
async def test_gemini_retry_after_valid_header():
    """Verify HTTP 429 with valid Retry-After header respects the delay value."""
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=2)
    resp_429 = build_gemini_mock_response(429, "Rate limited", headers={"Retry-After": "2"})
    resp_200 = build_gemini_mock_response(200, {
        "question_text": "Valid question after 429.",
        "topic": "OS",
        "difficulty": "medium",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [resp_429, resp_200]
            res = await provider.generate_question("OS", "", QuestionDifficulty.MEDIUM, 1, [])
            assert res["question_text"] == "Valid question after 429."
            assert mock_post.call_count == 2
            mock_sleep.assert_called_once_with(2.0)


@pytest.mark.anyio
async def test_gemini_retry_after_missing_or_malformed():
    """Verify HTTP 429 with malformed or missing Retry-After header falls back to exponential backoff."""
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=1)
    resp_429 = build_gemini_mock_response(429, "Rate limited", headers={"Retry-After": "malformed_value"})
    resp_200 = build_gemini_mock_response(200, {
        "question_text": "Recovered question.",
        "topic": "Net",
        "difficulty": "easy",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [resp_429, resp_200]
            res = await provider.generate_question("Net", "", QuestionDifficulty.EASY, 1, [])
            assert res["question_text"] == "Recovered question."
            assert mock_post.call_count == 2
            assert mock_sleep.call_count == 1
            sleep_arg = mock_sleep.call_args[0][0]
            assert 1.0 <= sleep_arg <= 2.0


@pytest.mark.anyio
async def test_gemini_503_followed_by_successful_retry():
    """Verify HTTP 503 transient error retries and succeeds within retry budget."""
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=2)
    resp_503 = build_gemini_mock_response(503, "Service temporarily unavailable")
    resp_200 = build_gemini_mock_response(200, {
        "score": 7.5,
        "feedback": "Solid answer.",
        "strengths": ["Clear"],
        "improvements": [],
        "rationale": "Good",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [resp_503, resp_200]
            res = await provider.evaluate_answer("Q", "A", QuestionDifficulty.MEDIUM, "T")
            assert res["score"] == 7.5
            assert mock_post.call_count == 2
            assert mock_sleep.call_count == 1


@pytest.mark.anyio
async def test_gemini_timeout_followed_by_successful_retry():
    """Verify httpx.TimeoutException retries within budget and succeeds on subsequent attempt."""
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=2)
    resp_200 = build_gemini_mock_response(200, {
        "score": 8.0,
        "feedback": "Great recovery.",
        "strengths": ["Solid"],
        "improvements": [],
        "rationale": "Good",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [httpx.ReadTimeout("Timeout error"), resp_200]
            res = await provider.evaluate_answer("Q", "A", QuestionDifficulty.MEDIUM, "T")
            assert res["score"] == 8.0
            assert mock_post.call_count == 2
            assert mock_sleep.call_count == 1


@pytest.mark.anyio
async def test_gemini_retry_budget_exhausted():
    """Verify retry budget exhaustion raises AIProviderError after maximum attempts."""
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=2)
    resp_503 = build_gemini_mock_response(503, "Unavailable")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.side_effect = [resp_503, resp_503, resp_503]
            with pytest.raises(AIProviderError, match="temporarily unavailable \\(HTTP 503\\)"):
                await provider.generate_question("T", "", QuestionDifficulty.MEDIUM, 1, [])
            assert mock_post.call_count == 3
            assert mock_sleep.call_count == 2


@pytest.mark.anyio
async def test_gemini_auth_error_not_retried():
    """Verify HTTP 401/403 permanent authentication errors fail immediately without retry."""
    provider = GeminiInterviewAIProvider(api_key="secret-key", max_retries=3)
    resp_401 = build_gemini_mock_response(401, "API Key Invalid")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.return_value = resp_401
            with pytest.raises(AIProviderError, match="authentication failed"):
                await provider.generate_question("T", "", QuestionDifficulty.EASY, 1, [])
            assert mock_post.call_count == 1
            assert mock_sleep.call_count == 0


@pytest.mark.anyio
async def test_gemini_total_deadline_respected(caplog):
    """Verify that when remaining deadline is smaller than required delay, retry is halted immediately."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=2, total_deadline_seconds=5.0)
    resp_429 = build_gemini_mock_response(429, "Rate limited", headers={"Retry-After": "15"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.return_value = resp_429
            with pytest.raises(AIProviderError, match="exceeds remaining request deadline"):
                await provider.generate_question("T", "", QuestionDifficulty.MEDIUM, 1, [])
            assert mock_post.call_count == 1
            assert mock_sleep.call_count == 0

    deadline_logs = [r.message for r in caplog.records if "deadline_exceeded" in r.message]
    assert len(deadline_logs) >= 1


@pytest.mark.anyio
async def test_telemetry_does_not_log_secrets_prompts_or_answers(caplog):
    """Verify telemetry log entries never contain API keys, full prompts, or candidate answers."""
    caplog.set_level(logging.INFO)
    secret_api_key = "AIzaSyTestSecret12345"
    candidate_secret_answer = "SuperSecretCandidateProprietaryAnswer"
    provider = GeminiInterviewAIProvider(api_key=secret_api_key)
    mock_resp = build_gemini_mock_response(200, {
        "score": 8.0,
        "feedback": "Good answer.",
        "strengths": ["Clear"],
        "improvements": [],
        "rationale": "Ok",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        await provider.evaluate_answer(
            question="What is HTTP?",
            answer=candidate_secret_answer,
            difficulty=QuestionDifficulty.EASY,
            topic="Web",
        )

    telemetry_logs = [r.message for r in caplog.records if "ai_request_telemetry" in r.message]
    assert len(telemetry_logs) >= 1
    for log_entry in telemetry_logs:
        assert secret_api_key not in log_entry
        assert candidate_secret_answer not in log_entry
        assert "What is HTTP?" not in log_entry


@pytest.mark.anyio
async def test_existing_question_bank_selection_preferred_over_llm():
    """Verify that when the question bank has an unasked question, Gemini is NOT called."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_interviews = AsyncMock()
    mock_assignments = AsyncMock()
    mock_questions = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "university_interviews": mock_interviews,
        "interviews": mock_interviews,
        "student_interview_assignments": mock_assignments,
        "interview_questions": mock_questions,
        "questions": mock_questions,
    }.get(name, AsyncMock())

    student = make_student("241FA04001")
    assignment_id = "assign-bank-1"
    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "student_registration_number": "241FA04001",
        "interview_id": "interview-1",
        "target_role": "Software Engineer",
        "status": AssignmentStatus.ASSIGNED.value,
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "interview-1",
        "title": "SE Assessment",
        "instructions": "",
        "status": InterviewStatus.SCHEDULED.value,
        "duration_minutes": 45,
    }
    mock_sessions.find_one.return_value = None

    mock_questions.find_one.return_value = {
        "question_id": "q-bank-01",
        "question_text": "Explain the difference between a process and a thread.",
        "topic": "Operating Systems",
        "question_type": "conceptual",
        "expected_answer": "A process has its own address space, while threads share it.",
        "keywords": ["process", "thread", "address space"],
    }

    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", "test-key"):
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                session_res = await InterviewSessionService.start_session(
                    mock_db,
                    assignment_id=assignment_id,
                    student_user=student,
                )

                assert session_res.question_text == "Explain the difference between a process and a thread."
                assert session_res.topic == "Operating Systems"
                assert mock_post.call_count == 0


@pytest.mark.anyio
async def test_expected_answer_grounding_without_leaking_hidden_rubric():
    """Verify expected_answer is passed to evaluate_answer for grounding but stripped from student endpoints."""
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock()
    mock_sessions.update_one = AsyncMock()
    mock_sessions.insert_one = AsyncMock()
    mock_responses = AsyncMock()
    mock_interviews = AsyncMock()
    mock_questions = AsyncMock()
    mock_scorecards = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
        "interviews": mock_interviews,
        "student_interview_assignments": mock_assignments,
        "interview_questions": mock_questions,
        "questions": mock_questions,
        "interview_scorecards": mock_scorecards,
    }.get(name, AsyncMock())

    student = make_student("241FA04001")
    session_id = "session-ground-1"
    now = utc_now()

    session_state = {
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "assign-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 2,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=30),
        "active_question": {
            "question_text": "What is the function of the ARP protocol?",
            "topic": "Networking",
            "difficulty": "medium",
            "question_type": "conceptual",
            "expected_answer": "ARP resolves IP addresses to physical MAC addresses on a local network.",
            "keywords": ["arp", "mac", "ip", "broadcast"],
        },
    }
    mock_sessions.find_one.return_value = session_state
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[session_state])
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-1",
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.IN_PROGRESS.value,
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "Networking Assessment",
    }
    mock_responses.find_one.return_value = None
    mock_questions.find_one.return_value = {
        "question_id": "q-bank-02",
        "question_text": "Explain TCP 3-way handshake.",
        "topic": "Networking",
        "difficulty": "hard",
        "question_type": "conceptual",
    }

    provider = GeminiInterviewAIProvider(api_key="test-key")

    with patch("app.services.interview_session_service.get_ai_provider", return_value=provider):
        with patch.object(provider, "evaluate_answer", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = {
                "score": 9.0,
                "feedback": "Accurate explanation matching ARP specifications.",
                "strengths": ["Correct layer"],
                "improvements": [],
                "rationale": "High relevance",
            }

            await InterviewSessionService.submit_answer(
                mock_db,
                session_id=session_id,
                answer_text="ARP resolves IP to MAC address on the ethernet link.",
                student_user=student,
            )

            mock_eval.assert_called_once()
            kwargs = mock_eval.call_args.kwargs
            assert kwargs["expected_answer"] == "ARP resolves IP addresses to physical MAC addresses on a local network."
            assert kwargs["keywords"] == ["arp", "mac", "ip", "broadcast"]

    assignment_view = await InterviewSessionService.get_session_by_assignment(
        mock_db,
        assignment_id="assign-1",
        student_user=student,
    )
    assert "active_question" in assignment_view
    assert "expected_answer" not in assignment_view["active_question"]
    assert "keywords" not in assignment_view["active_question"]
    assert "expected_answer" not in assignment_view


def test_compute_backoff_delay_never_exceeds_max_delay():
    """Verify that compute_backoff_delay strictly caps backoff at max_delay even with high attempts and jitter."""
    from app.services.ai_provider import compute_backoff_delay
    max_delay = 10.0
    for attempt in range(20):
        for _ in range(10):
            delay = compute_backoff_delay(attempt, base_delay=1.0, factor=1.5, max_delay=max_delay, jitter_range=1.0)
            assert delay <= max_delay
            assert delay >= 0.0


@pytest.mark.anyio
async def test_gemini_retry_abandoned_due_to_deadline_raises_controlled_error(caplog):
    """Verify that when backoff on 503 exceeds remaining deadline, it aborts cleanly with controlled deadline error."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key", max_retries=2, total_deadline_seconds=0.5)
    resp_503 = build_gemini_mock_response(503, "Service Unavailable")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_post.return_value = resp_503
            with pytest.raises(AIProviderError, match="exceeds remaining request deadline"):
                await provider.generate_question("T", "", QuestionDifficulty.MEDIUM, 1, [])
            assert mock_post.call_count == 1
            assert mock_sleep.call_count == 0

    deadline_logs = [r.message for r in caplog.records if "deadline_exceeded" in r.message]
    assert len(deadline_logs) >= 1


@pytest.mark.anyio
async def test_gemini_200_empty_candidates_records_failure_telemetry(caplog):
    """Verify HTTP 200 with empty candidates logs outcome=empty_candidates and preserves usage tokens."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key")
    raw_payload = {
        "candidates": [],
        "promptFeedback": {"blockReason": "SAFETY"},
        "usageMetadata": {
            "promptTokenCount": 25,
            "candidatesTokenCount": 0,
            "totalTokenCount": 25,
        },
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(raw_payload).encode("utf-8"),
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="Gemini returned no candidates"):
            await provider.generate_question("T", "", QuestionDifficulty.EASY, 1, [])

    failure_logs = [r.message for r in caplog.records if "empty_candidates" in r.message]
    assert len(failure_logs) >= 1
    assert '"prompt_tokens": 25' in failure_logs[0]
    success_logs = [r.message for r in caplog.records if '"outcome": "success"' in r.message]
    assert len(success_logs) == 0


@pytest.mark.anyio
async def test_gemini_200_empty_content_parts_records_failure_telemetry(caplog):
    """Verify HTTP 200 with empty content parts logs outcome=empty_content, not success."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key")
    raw_payload = {
        "candidates": [
            {"content": {"parts": [{"text": ""}]}}
        ],
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(raw_payload).encode("utf-8"),
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="empty content parts"):
            await provider.generate_question("T", "", QuestionDifficulty.EASY, 1, [])

    failure_logs = [r.message for r in caplog.records if "empty_content" in r.message]
    assert len(failure_logs) >= 1
    success_logs = [r.message for r in caplog.records if '"outcome": "success"' in r.message]
    assert len(success_logs) == 0


@pytest.mark.anyio
async def test_gemini_200_invalid_content_json_records_failure_telemetry(caplog):
    """Verify HTTP 200 with non-JSON text logs outcome=invalid_content_json, not success."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key")
    raw_payload = {
        "candidates": [
            {"content": {"parts": [{"text": "Sorry, I am not able to generate JSON."}]}}
        ],
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(raw_payload).encode("utf-8"),
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="could not be parsed as valid JSON"):
            await provider.generate_question("T", "", QuestionDifficulty.EASY, 1, [])

    failure_logs = [r.message for r in caplog.records if "invalid_content_json" in r.message]
    assert len(failure_logs) >= 1
    success_logs = [r.message for r in caplog.records if '"outcome": "success"' in r.message]
    assert len(success_logs) == 0


@pytest.mark.anyio
async def test_gemini_200_schema_validation_error_records_failure_telemetry(caplog):
    """Verify HTTP 200 with invalid schema fields logs outcome=validation_error, not success."""
    caplog.set_level(logging.INFO)
    provider = GeminiInterviewAIProvider(api_key="test-key")
    raw_payload = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps({"wrong_field": "some data"})}]}}
        ],
        "usageMetadata": {
            "promptTokenCount": 50,
            "candidatesTokenCount": 10,
            "totalTokenCount": 60,
        },
    }
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(raw_payload).encode("utf-8"),
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(AIProviderError, match="did not match the required question schema"):
            await provider.generate_question("T", "", QuestionDifficulty.EASY, 1, [])

    failure_logs = [r.message for r in caplog.records if "validation_error" in r.message]
    assert len(failure_logs) >= 1
    assert '"prompt_tokens": 50' in failure_logs[0]
    assert '"total_tokens": 60' in failure_logs[0]
    success_logs = [r.message for r in caplog.records if '"outcome": "success"' in r.message]
    assert len(success_logs) == 0


def test_gemini_model_resolution_priority_and_prefix_stripping():
    """Verify Gemini model resolution respects AI_MODEL_NAME override, defaults to verified model, and strips models/ prefix."""
    # 1. Default when neither AI_MODEL_NAME nor custom default set
    with patch.object(settings, "AI_MODEL_NAME", None):
        with patch.object(settings, "GEMINI_DEFAULT_MODEL", "gemini-3.5-flash-lite"):
            assert settings.resolved_gemini_model == "gemini-3.5-flash-lite"

    # 2. GEMINI_DEFAULT_MODEL override
    with patch.object(settings, "AI_MODEL_NAME", None):
        with patch.object(settings, "GEMINI_DEFAULT_MODEL", "gemini-3.8-flash"):
            assert settings.resolved_gemini_model == "gemini-3.8-flash"

    # 3. AI_MODEL_NAME has higher priority than GEMINI_DEFAULT_MODEL
    with patch.object(settings, "AI_MODEL_NAME", "custom-gemini-model"):
        with patch.object(settings, "GEMINI_DEFAULT_MODEL", "gemini-3.5-flash-lite"):
            assert settings.resolved_gemini_model == "custom-gemini-model"

    # 4. Leading 'models/' prefix is safely stripped to prevent duplicate URL segments
    with patch.object(settings, "AI_MODEL_NAME", "models/gemini-3.5-flash-lite"):
        assert settings.resolved_gemini_model == "gemini-3.5-flash-lite"

    # 5. Verify factory injects resolved model into provider
    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", "test-key-mock-123"):
            with patch.object(settings, "AI_MODEL_NAME", "gemini-3.5-flash-lite"):
                provider = get_ai_provider()
                assert isinstance(provider, GeminiInterviewAIProvider)
                assert provider.model_name == "gemini-3.5-flash-lite"
