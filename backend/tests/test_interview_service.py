import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from app.models.interview import (
    UniversityInterviewCreate,
    UniversityInterviewUpdate,
    InterviewStatus,
    AssignmentStatus,
    BulkAssignmentRequest,
    utc_now,
)
from app.models.user import UserInDB, UserRole
from app.services.interview_service import InterviewService


def make_test_admin():
    return UserInDB(
        id="admin-uuid-1",
        email="admin@vfstr.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="hashed_secret",
        institution_id="VFSTR",
    )


def make_test_faculty():
    return UserInDB(
        id="faculty-uuid-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="hashed_secret",
        institution_id="VFSTR",
    )


def make_test_student(reg_no="241FA04001"):
    return UserInDB(
        id="student-uuid-1",
        email=f"student.{reg_no.lower()}@gmail.com",
        role=UserRole.STUDENT,
        hashed_password="hashed_secret",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


# ==============================================================================
# 1. Schedule & Model Validation Tests
# ==============================================================================

def test_interview_create_valid():
    now = utc_now()
    start = now + timedelta(days=2)
    end = start + timedelta(hours=3)

    data = UniversityInterviewCreate(
        title="Cisco NetAcad Interview Round 1",
        instructions="Please ensure your camera is enabled throughout the assessment.",
        scheduled_start_time=start,
        scheduled_end_time=end,
        duration_minutes=45,
    )
    assert data.title == "Cisco NetAcad Interview Round 1"
    assert data.duration_minutes == 45


def test_interview_rejects_past_time():
    now = utc_now()
    past_start = now - timedelta(days=1)
    end = now + timedelta(hours=1)

    with pytest.raises(ValueError, match="scheduled_start_time cannot be in the past"):
        UniversityInterviewCreate(
            title="Past Interview",
            instructions="Test instructions for past interview",
            scheduled_start_time=past_start,
            scheduled_end_time=end,
            duration_minutes=30,
        )


def test_interview_rejects_end_before_start():
    now = utc_now()
    start = now + timedelta(days=1)
    end = start - timedelta(hours=1)

    with pytest.raises(ValueError, match="scheduled_end_time must be strictly after scheduled_start_time"):
        UniversityInterviewCreate(
            title="Inverted Times",
            instructions="Test instructions with invalid window",
            scheduled_start_time=start,
            scheduled_end_time=end,
            duration_minutes=30,
        )


def test_interview_rejects_duration_exceeding_window():
    now = utc_now()
    start = now + timedelta(days=1)
    end = start + timedelta(minutes=30)  # 30 minute window

    with pytest.raises(ValueError, match="cannot exceed scheduled time window"):
        UniversityInterviewCreate(
            title="Oversized Duration",
            instructions="Duration is 60 minutes but window is only 30 minutes",
            scheduled_start_time=start,
            scheduled_end_time=end,
            duration_minutes=60,
        )


# ==============================================================================
# 2. Candidate Assignment & Eligibility Verification Tests
# ==============================================================================

@pytest.mark.anyio
async def test_assign_candidates_eligible_vs_quarantined():
    """Verify that eligible candidates are assigned, while quarantined/missing candidates are rejected."""
    mock_db = MagicMock()
    mock_interviews = AsyncMock()
    mock_assignments = AsyncMock()
    mock_registry = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "university_interviews": mock_interviews,
        "student_interview_assignments": mock_assignments,
        "interview_eligibility_registry": mock_registry,
    }[name]

    # Interview exists in SCHEDULED state
    mock_interviews.find_one.return_value = {
        "interview_id": "test-int-123",
        "title": "Interview 1",
        "status": "scheduled",
    }

    # Registry mock behavior
    async def mock_reg_lookup(query):
        reg = query.get("registration_number")
        if reg == "241FA04001":
            return {
                "_id": "id-1",
                "registration_number": "241FA04001",
                "email": "vu.241fa04001@gmail.com",
                "section": "1",
                "review_status": "approved",
                "interview_eligible": True,
            }
        elif reg == "231FA04941":  # Senior quarantined batch
            return {
                "_id": "id-2",
                "registration_number": "231FA04941",
                "email": "alokamneeraj01@gmail.com",
                "section": "2",
                "review_status": "needs_review",
                "interview_eligible": False,
                "review_reasons": ["UNEXPECTED_BATCH_2023"],
            }
        return None  # Missing candidate

    mock_registry.find_one.side_effect = mock_reg_lookup
    mock_assignments.find_one.return_value = None  # No prior assignment
    mock_assignments.insert_one = AsyncMock()

    admin = make_test_admin()
    req_regs = ["241FA04001", "231FA04941", "999FA99999"]
    res = await InterviewService.assign_candidates(mock_db, "test-int-123", req_regs, admin)

    assert res.total_requested == 3
    assert res.assigned_count == 1
    assert res.failed_count == 2

    # Check per-candidate results
    results_map = {r.registration_number: r for r in res.results}
    assert results_map["241FA04001"].success is True
    assert results_map["241FA04001"].status == "assigned"

    assert results_map["231FA04941"].success is False
    assert "INELIGIBLE_CANDIDATE" in results_map["231FA04941"].reason

    assert results_map["999FA99999"].success is False
    assert "STUDENT_NOT_FOUND_IN_REGISTRY" in results_map["999FA99999"].reason


@pytest.mark.anyio
async def test_assign_candidates_prevents_duplicates():
    """Verify that duplicate candidate assignments are rejected."""
    mock_db = MagicMock()
    mock_interviews = AsyncMock()
    mock_assignments = AsyncMock()
    mock_registry = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "university_interviews": mock_interviews,
        "student_interview_assignments": mock_assignments,
        "interview_eligibility_registry": mock_registry,
    }[name]

    mock_interviews.find_one.return_value = {
        "interview_id": "test-int-123",
        "title": "Interview 1",
        "status": "scheduled",
    }
    mock_registry.find_one.return_value = {
        "_id": "id-1",
        "registration_number": "241FA04001",
        "email": "vu.241fa04001@gmail.com",
        "review_status": "approved",
        "interview_eligible": True,
    }
    # Candidate already assigned!
    mock_assignments.find_one.return_value = {
        "assignment_id": "existing-assign-1",
        "status": "assigned",
    }

    admin = make_test_admin()
    res = await InterviewService.assign_candidates(mock_db, "test-int-123", ["241FA04001"], admin)

    assert res.assigned_count == 0
    assert res.failed_count == 1
    assert res.results[0].success is False
    assert "DUPLICATE_ASSIGNMENT" in res.results[0].reason


# ==============================================================================
# 3. Student Cross-Account Isolation & Lifecycle State Transitions
# ==============================================================================

@pytest.mark.anyio
async def test_student_cannot_access_other_student_assignment():
    """Verify that student A is strictly forbidden from accessing student B's assignment."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
    }[name]

    # Assignment belongs to 241FA04002
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-999",
        "interview_id": "test-int-1",
        "student_registration_number": "241FA04002",
        "status": "assigned",
    }

    # Student 241FA04001 attempts to access it
    with pytest.raises(HTTPException) as exc:
        await InterviewService.get_student_assignment_detail(
            mock_db,
            assignment_id="assign-999",
            student_reg_no="241FA04001",
        )
    assert exc.value.status_code == 403
    assert "Access denied" in exc.value.detail


@pytest.mark.anyio
async def test_student_lifecycle_transitions():
    """Verify valid transitions: assigned -> accepted -> in_progress -> completed."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
    }[name]

    student_reg = "241FA04001"

    # 1. Accept assignment
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-1",
        "interview_id": "int-1",
        "student_registration_number": student_reg,
        "status": "assigned",
        "assigned_at": utc_now(),
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "Interview 1",
        "instructions": "Instructions",
    }

    res_accepted = await InterviewService.transition_assignment_status(
        mock_db, "assign-1", AssignmentStatus.ACCEPTED, student_reg
    )
    assert mock_assignments.update_one.called
    update_call = mock_assignments.update_one.call_args[0][1]["$set"]
    assert update_call["status"] == "accepted"
    assert "accepted_at" in update_call

    # 2. Reject invalid jump: assigned cannot jump directly to completed
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-1",
        "interview_id": "int-1",
        "student_registration_number": student_reg,
        "status": "assigned",
        "assigned_at": utc_now(),
    }
    with pytest.raises(HTTPException) as exc:
        await InterviewService.transition_assignment_status(
            mock_db, "assign-1", AssignmentStatus.COMPLETED, student_reg
        )
    assert exc.value.status_code == 400
    assert "Cannot complete interview" in exc.value.detail


@pytest.mark.anyio
async def test_update_interview_cascade_cancellation():
    """Verify cancelling an interview cascades cancellation to active assignments."""
    mock_db = MagicMock()
    mock_interviews = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "university_interviews": mock_interviews,
        "student_interview_assignments": mock_assignments,
    }[name]

    now = utc_now()
    mock_interviews.find_one.return_value = {
        "interview_id": "int-cancel-1",
        "title": "Test Interview",
        "instructions": "Standard instructions for test",
        "scheduled_start_time": now + timedelta(days=1),
        "scheduled_end_time": now + timedelta(days=1, hours=2),
        "duration_minutes": 60,
        "status": "scheduled",
        "created_by_user_id": "admin-1",
        "created_by_email": "admin@vfstr.ac.in",
        "created_at": now,
        "updated_at": now,
    }
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_assignments.aggregate.return_value = mock_cursor

    update_in = UniversityInterviewUpdate(status=InterviewStatus.CANCELLED)
    await InterviewService.update_interview(mock_db, "int-cancel-1", update_in)

    # Verify update_many was called on assignments
    assert mock_assignments.update_many.called
    update_call = mock_assignments.update_many.call_args[0]
    filter_query = update_call[0]
    set_fields = update_call[1]["$set"]

    assert filter_query["interview_id"] == "int-cancel-1"
    assert set_fields["status"] == "cancelled"
    assert "cancelled_at" in set_fields
