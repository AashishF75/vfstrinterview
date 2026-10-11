import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserInDB, UserRole
from app.models.proctoring import (
    ProctoringEventType,
    ProctoringReviewStatus,
    SingleProctoringEventInput,
    RecordProctoringEventsRequest,
    utc_now,
)
from app.services.proctoring_service import ProctoringService
from app.api.deps import get_current_active_user
from app.core.database import get_interview_database


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Pydantic Schema Validation Tests
# ==============================================================================

def test_proctoring_event_schema_valid():
    """Verify that valid proctoring events are accepted."""
    now = utc_now()
    evt = SingleProctoringEventInput(
        event_type=ProctoringEventType.TAB_HIDDEN,
        client_timestamp=now,
        duration_seconds=None,
        metadata={"screen_resolution": "1920x1080"},
    )
    assert evt.event_type == ProctoringEventType.TAB_HIDDEN
    assert evt.duration_seconds is None
    assert evt.metadata["screen_resolution"] == "1920x1080"


def test_proctoring_batch_rejects_empty():
    """Verify that an empty batch of events is rejected."""
    with pytest.raises(Exception):
        RecordProctoringEventsRequest(events=[])


def test_proctoring_batch_rejects_over_50_items():
    """Verify that batches exceeding 50 items are rejected by Pydantic."""
    now = utc_now()
    events = [
        SingleProctoringEventInput(
            event_type=ProctoringEventType.FACE_NORMAL,
            client_timestamp=now,
        )
        for _ in range(51)
    ]
    with pytest.raises(Exception):
        RecordProctoringEventsRequest(events=events)


# ==============================================================================
# 2. Service-Level Unit & Authorization Tests
# ==============================================================================

@pytest.mark.anyio
async def test_record_events_rejects_unverified_student():
    """Verify that a student without a verified registration number is rejected with 403."""
    db = AsyncMock()
    unverified_student = UserInDB(
        id="stu-1",
        email="unverified@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number=None,
    )
    events = [
        SingleProctoringEventInput(
            event_type=ProctoringEventType.CAMERA_STREAM_CONNECTED,
            client_timestamp=utc_now(),
        )
    ]

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.record_events(
            db=db,
            session_id="sess-1",
            events=events,
            student_user=unverified_student,
        )
    assert exc_info.value.status_code == 403
    assert "not linked to a verified registration number" in exc_info.value.detail


@pytest.mark.anyio
async def test_record_events_rejects_nonexistent_session():
    """Verify that submitting events for a missing session returns 404."""
    db = AsyncMock()
    db["interview_sessions"].find_one.return_value = None

    student = UserInDB(
        id="stu-1",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )
    events = [
        SingleProctoringEventInput(
            event_type=ProctoringEventType.CAMERA_STREAM_CONNECTED,
            client_timestamp=utc_now(),
        )
    ]

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.record_events(
            db=db,
            session_id="missing-sess",
            events=events,
            student_user=student,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_record_events_cross_student_isolation():
    """Verify that a student cannot inject proctoring events into another student's session."""
    db = AsyncMock()
    # Session belongs to student 241FA04002
    db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-target",
        "student_registration_number": "241FA04002",
        "assignment_id": "assign-1",
        "interview_id": "interview-1",
    }

    # Calling student is 241FA04001
    attacker = UserInDB(
        id="stu-attacker",
        email="attacker@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )
    events = [
        SingleProctoringEventInput(
            event_type=ProctoringEventType.FACE_ABSENT,
            client_timestamp=utc_now(),
        )
    ]

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.record_events(
            db=db,
            session_id="sess-target",
            events=events,
            student_user=attacker,
        )
    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail


@pytest.mark.anyio
async def test_record_events_success_and_metrics_calculation():
    """Verify successful insertion of proctoring events and summary metrics aggregation."""
    db = AsyncMock()
    db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-valid",
        "student_registration_number": "241FA04001",
        "assignment_id": "assign-valid",
        "interview_id": "int-valid",
    }
    db["proctoring_events"].insert_many.return_value = AsyncMock()

    student = UserInDB(
        id="stu-valid",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )
    now = utc_now()
    events = [
        SingleProctoringEventInput(
            event_type=ProctoringEventType.CAMERA_STREAM_CONNECTED,
            client_timestamp=now,
        ),
        SingleProctoringEventInput(
            event_type=ProctoringEventType.TAB_HIDDEN,
            client_timestamp=now + timedelta(seconds=10),
        ),
        SingleProctoringEventInput(
            event_type=ProctoringEventType.TAB_VISIBLE,
            client_timestamp=now + timedelta(seconds=15),
            duration_seconds=5.0,
        ),
        SingleProctoringEventInput(
            event_type=ProctoringEventType.FACE_ABSENT,
            client_timestamp=now + timedelta(seconds=30),
            duration_seconds=4.0,
        ),
    ]

    res = await ProctoringService.record_events(
        db=db,
        session_id="sess-valid",
        events=events,
        student_user=student,
    )
    assert res.success is True
    assert res.persisted_count == 4
    assert res.session_id == "sess-valid"

    # Verify timeline calculation
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(
        return_value=[
            {
                "event_id": "e-1",
                "event_type": ProctoringEventType.CAMERA_STREAM_CONNECTED.value,
                "client_timestamp": now,
                "server_timestamp": now,
                "duration_seconds": None,
                "metadata": {},
            },
            {
                "event_id": "e-2",
                "event_type": ProctoringEventType.TAB_HIDDEN.value,
                "client_timestamp": now + timedelta(seconds=10),
                "server_timestamp": now + timedelta(seconds=10),
                "duration_seconds": None,
                "metadata": {},
            },
            {
                "event_id": "e-3",
                "event_type": ProctoringEventType.TAB_VISIBLE.value,
                "client_timestamp": now + timedelta(seconds=15),
                "server_timestamp": now + timedelta(seconds=15),
                "duration_seconds": 5.0,
                "metadata": {},
            },
            {
                "event_id": "e-4",
                "event_type": ProctoringEventType.FACE_ABSENT.value,
                "client_timestamp": now + timedelta(seconds=30),
                "server_timestamp": now + timedelta(seconds=30),
                "duration_seconds": 4.0,
                "metadata": {},
            },
        ]
    )
    db["proctoring_events"].find.return_value = mock_cursor

    timeline_res = await ProctoringService.get_session_timeline(
        db=db,
        session_id="sess-valid",
        current_user=student,
    )

    assert timeline_res.session_id == "sess-valid"
    assert timeline_res.summary.total_tab_hidden_count == 1
    assert timeline_res.summary.total_tab_hidden_duration_seconds == 5.0
    assert timeline_res.summary.total_face_absent_count == 1
    assert timeline_res.summary.total_face_absent_duration_seconds == 4.0
    assert timeline_res.summary.integrity_status == "notice"
    assert len(timeline_res.timeline) == 4


# ==============================================================================
# 3. HTTP API Route Integration Tests
# ==============================================================================

def test_proctoring_routes_reject_unauthenticated(client):
    """Verify that unauthenticated proctoring requests are rejected with 401."""
    resp = client.post("/api/interview-rooms/sessions/any-session/proctoring-events", json={"events": []})
    assert resp.status_code == 401


def test_proctoring_admin_routes_reject_student(client):
    """Verify that student role cannot call admin proctoring review routes."""
    student = UserInDB(
        id="stu-1",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )
    app.dependency_overrides[get_current_active_user] = lambda: student

    try:
        resp = client.get("/api/admin/interviews/sessions/any-session/proctoring-events")
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

        patch_resp = client.patch(
            "/api/admin/interviews/sessions/any-session/proctoring-review",
            json={"review_status": "cleared"},
        )
        assert patch_resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_proctoring_admin_routes_accept_university_admin(client):
    """Verify that university_admin can access the proctoring timeline and review endpoints."""
    admin = UserInDB(
        id="admin-1",
        email="admin@vfstr.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
    )
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-adm",
        "student_registration_number": "241FA04001",
        "assignment_id": "assign-adm",
    }
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db["proctoring_events"].find.return_value = mock_cursor

    app.dependency_overrides[get_current_active_user] = lambda: admin
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    try:
        resp = client.get("/api/admin/interviews/sessions/sess-adm/proctoring-events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-adm"
        assert data["summary"]["integrity_status"] == "normal"
    finally:
        app.dependency_overrides.clear()
