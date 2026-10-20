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
        "institution_id": "VFSTR",
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


# ==============================================================================
# 4. Phase 6 Faculty Review & Institutional Scoping Tests
# ==============================================================================

@pytest.mark.anyio
async def test_proctoring_review_faculty_success_and_audit():
    """Verify that a faculty reviewer can update review status and audit metadata is recorded."""
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-fac-1",
        "student_registration_number": "241FA04001",
        "assignment_id": "assign-1",
        "interview_id": "int-1",
        "institution_id": "VFSTR",
        "department": "CSE",
    }
    mock_db["students"].find_one.return_value = {
        "registration_number": "241FA04001",
        "department": "CSE",
        "institution_id": "VFSTR",
    }
    mock_db["interview_sessions"].update_one.return_value = AsyncMock(modified_count=1)

    faculty = UserInDB(
        id="fac-1",
        email="faculty.cse@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )

    res = await ProctoringService.update_review_status(
        db=mock_db,
        session_id="sess-fac-1",
        review_status=ProctoringReviewStatus.CLEARED,
        review_notes="Candidate explained camera tilt. No infractions detected.",
        admin_user=faculty,
    )

    assert res["success"] is True
    assert res["session_id"] == "sess-fac-1"
    assert res["review_status"] == "cleared"
    assert res["reviewed_by_email"] == "faculty.cse@vfstr.ac.in"
    assert res["reviewed_at"] is not None

    call_args = mock_db["interview_sessions"].update_one.call_args[0]
    filter_arg = call_args[0]
    update_arg = call_args[1]["$set"]
    assert filter_arg == {"session_id": "sess-fac-1"}
    assert update_arg["proctoring_review_status"] == "cleared"
    assert update_arg["proctoring_reviewed_by_email"] == "faculty.cse@vfstr.ac.in"
    assert update_arg["proctoring_review_notes"] == "Candidate explained camera tilt. No infractions detected."


@pytest.mark.anyio
async def test_proctoring_review_department_isolation_denies_cross_dept():
    """Verify that an ECE faculty reviewer is rejected (403) from reviewing a CSE session."""
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-cse-1",
        "student_registration_number": "241FA04001",
        "institution_id": "VFSTR",
    }
    mock_db["students"].find_one.return_value = {
        "registration_number": "241FA04001",
        "department": "CSE",
        "institution_id": "VFSTR",
    }

    ece_faculty = UserInDB(
        id="fac-ece",
        email="faculty.ece@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="ECE",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.update_review_status(
            db=mock_db,
            session_id="sess-cse-1",
            review_status=ProctoringReviewStatus.FLAGGED,
            review_notes="Unauthorized attempt",
            admin_user=ece_faculty,
        )
    assert exc_info.value.status_code == 403
    assert "department" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_review_institution_isolation_denies_cross_univ():
    """Verify that a reviewer from another institution is rejected (403)."""
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-vfstr-1",
        "student_registration_number": "241FA04001",
        "institution_id": "VFSTR",
    }

    other_admin = UserInDB(
        id="admin-other",
        email="admin@otheruniv.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="OTHER_UNIV",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.get_session_timeline(
            db=mock_db,
            session_id="sess-vfstr-1",
            current_user=other_admin,
        )
    assert exc_info.value.status_code == 403
    assert "institution" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_review_rejects_student_direct():
    """Verify that a student calling update_review_status directly is rejected with 403."""
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-stu-1",
        "student_registration_number": "241FA04001",
    }

    student = UserInDB(
        id="stu-1",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.update_review_status(
            db=mock_db,
            session_id="sess-stu-1",
            review_status=ProctoringReviewStatus.CLEARED,
            review_notes="Self clear",
            admin_user=student,
        )
    assert exc_info.value.status_code == 403
    assert "insufficient permissions" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_review_rejects_excessive_note_length():
    """Verify that a review note exceeding 2000 characters is rejected with 422."""
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-1",
        "student_registration_number": "241FA04001",
    }
    mock_db["students"].find_one.return_value = {
        "registration_number": "241FA04001",
        "department": "CSE",
    }

    faculty = UserInDB(
        id="fac-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.update_review_status(
            db=mock_db,
            session_id="sess-1",
            review_status=ProctoringReviewStatus.FLAGGED,
            review_notes="X" * 2001,
            admin_user=faculty,
        )
    assert exc_info.value.status_code == 422
    assert "2000 characters" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_timeline_empty_events_handling():
    """Verify that an interview session with zero proctoring events returns normal status and neutral disclaimer."""
    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one.return_value = {
        "session_id": "sess-clean",
        "student_registration_number": "241FA04001",
        "assignment_id": "assign-clean",
        "proctoring_review_status": "unreviewed",
        "institution_id": "VFSTR",
    }
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db["proctoring_events"].find.return_value = mock_cursor
    mock_db["students"].find_one.return_value = {
        "registration_number": "241FA04001",
        "department": "CSE",
        "institution_id": "VFSTR",
    }

    faculty = UserInDB(
        id="fac-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )

    timeline = await ProctoringService.get_session_timeline(
        db=mock_db,
        session_id="sess-clean",
        current_user=faculty,
    )

    assert timeline.session_id == "sess-clean"
    assert timeline.summary.integrity_status == "normal"
    assert timeline.summary.total_tab_hidden_count == 0
    assert timeline.summary.total_face_absent_count == 0
    assert timeline.summary.total_multiple_faces_count == 0
    assert timeline.summary.stream_disruptions_count == 0
    assert len(timeline.timeline) == 0
    assert "automated evidence" in timeline.summary.disclaimer.lower()


@pytest.mark.anyio
async def test_proctoring_review_missing_institution_metadata_denied():
    """Verify that if a session lacks institution metadata across records, university_admin is denied (403 fail-closed)."""
    cols = {
        "interview_sessions": AsyncMock(find_one=AsyncMock(return_value={
            "session_id": "sess-no-inst",
            "student_registration_number": "EXT_STU_NO_INST",
        })),
        "student_interview_assignments": AsyncMock(find_one=AsyncMock(return_value=None)),
        "interviews": AsyncMock(find_one=AsyncMock(return_value=None)),
        "students": AsyncMock(find_one=AsyncMock(return_value=None)),
    }
    mock_db = MagicMock()
    mock_db.__getitem__.side_effect = lambda k: cols.get(k, AsyncMock())

    admin = UserInDB(
        id="admin-1",
        email="admin@vfstr.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.get_session_timeline(
            db=mock_db,
            session_id="sess-no-inst",
            current_user=admin,
        )
    assert exc_info.value.status_code == 403
    assert "institutional scope" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_review_missing_department_metadata_denied():
    """Verify that if a session lacks department metadata, faculty reviewer is denied (403 fail-closed)."""
    cols = {
        "interview_sessions": AsyncMock(find_one=AsyncMock(return_value={
            "session_id": "sess-no-dept",
            "student_registration_number": "EXT_STU_NO_DEPT",
            "institution_id": "VFSTR",
        })),
        "student_interview_assignments": AsyncMock(find_one=AsyncMock(return_value={"institution_id": "VFSTR"})),
        "interviews": AsyncMock(find_one=AsyncMock(return_value=None)),
        "students": AsyncMock(find_one=AsyncMock(return_value={"institution_id": "VFSTR", "department": None})),
    }
    mock_db = MagicMock()
    mock_db.__getitem__.side_effect = lambda k: cols.get(k, AsyncMock())

    faculty = UserInDB(
        id="fac-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.update_review_status(
            db=mock_db,
            session_id="sess-no-dept",
            review_status=ProctoringReviewStatus.CLEARED,
            review_notes="Notes",
            admin_user=faculty,
        )
    assert exc_info.value.status_code == 403
    assert "department scope" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_review_missing_reviewer_scope_denied():
    """Verify that a reviewer lacking department or institution is denied access (403)."""
    cols = {
        "interview_sessions": AsyncMock(find_one=AsyncMock(return_value={
            "session_id": "sess-valid-scope",
            "student_registration_number": "241FA04001",
            "institution_id": "VFSTR",
            "department": "CSE",
        })),
    }
    mock_db = MagicMock()
    mock_db.__getitem__.side_effect = lambda k: cols.get(k, AsyncMock())

    # Department admin with missing department
    dept_admin_no_dept = UserInDB(
        id="dept-no-dept",
        email="dept_admin@vfstr.ac.in",
        role=UserRole.DEPARTMENT_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
        department=None,
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.update_review_status(
            db=mock_db,
            session_id="sess-valid-scope",
            review_status=ProctoringReviewStatus.CLEARED,
            review_notes="Notes",
            admin_user=dept_admin_no_dept,
        )
    assert exc_info.value.status_code == 403
    assert "department identity" in exc_info.value.detail.lower()

    # Reviewer with missing institution
    admin_no_inst = UserInDB(
        id="admin-no-inst",
        email="admin@vfstr.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="",
    )

    with pytest.raises(Exception) as exc_info2:
        await ProctoringService.get_session_timeline(
            db=mock_db,
            session_id="sess-valid-scope",
            current_user=admin_no_inst,
        )
    assert exc_info2.value.status_code == 403
    assert "institutional identity" in exc_info2.value.detail.lower()


@pytest.mark.anyio
async def test_proctoring_review_platform_admin_cross_tenant_allowed():
    """Verify that platform_admin can access and review sessions across tenants."""
    mock_sessions = AsyncMock()
    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": "sess-any-tenant",
        "student_registration_number": "241FA04001",
        "institution_id": "OTHER_UNIV",
        "department": "MECH",
    })
    mock_sessions.update_one = AsyncMock(return_value=AsyncMock(modified_count=1))

    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_sessions

    platform_admin = UserInDB(
        id="super-admin",
        email="platform@vfstr.ac.in",
        role=UserRole.PLATFORM_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
        department=None,
    )

    res = await ProctoringService.update_review_status(
        db=mock_db,
        session_id="sess-any-tenant",
        review_status=ProctoringReviewStatus.CLEARED,
        review_notes="Platform admin override review.",
        admin_user=platform_admin,
    )
    assert res["success"] is True
    assert res["session_id"] == "sess-any-tenant"
    assert res["review_status"] == "cleared"


@pytest.mark.anyio
async def test_proctoring_review_unrecognized_branch_code_inference_denied():
    """Verify that an unrecognized branch code (e.g. 99) in registration number does NOT default to CSE and fails closed (403)."""
    cols = {
        "interview_sessions": AsyncMock(find_one=AsyncMock(return_value={
            "session_id": "sess-unknown-branch",
            "student_registration_number": "241FA99001",
        })),
        "student_interview_assignments": AsyncMock(find_one=AsyncMock(return_value=None)),
        "interviews": AsyncMock(find_one=AsyncMock(return_value=None)),
        "students": AsyncMock(find_one=AsyncMock(return_value=None)),
    }
    mock_db = MagicMock()
    mock_db.__getitem__.side_effect = lambda k: cols.get(k, AsyncMock())

    cse_faculty = UserInDB(
        id="fac-cse-1",
        email="faculty.cse@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )

    with pytest.raises(Exception) as exc_info:
        await ProctoringService.get_session_timeline(
            db=mock_db,
            session_id="sess-unknown-branch",
            current_user=cse_faculty,
        )
    assert exc_info.value.status_code == 403
