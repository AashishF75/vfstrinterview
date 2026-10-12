import pytest
import pymongo
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.models.interview_session import (
    QuestionDifficulty,
    SessionStatus,
    EvaluatorMode,
    utc_now,
    SessionQuestionResponse,
)
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.user import UserInDB, UserRole
from app.services.interview_session_service import InterviewSessionService, _ensure_utc


def make_student(reg_no="241FA04001"):
    return UserInDB(
        id=f"user-{reg_no}",
        email=f"stu.{reg_no.lower()}@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="hashed_pw",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


# ==============================================================================
# 1. Starting an interview creates a valid, unexpired session
# ==============================================================================

@pytest.mark.anyio
async def test_start_session_creates_valid_unexpired_session():
    """Verify that starting an interview creates a valid, unexpired session with Question 1."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()
    mock_sessions = AsyncMock()
    mock_questions = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
        "interview_sessions": mock_sessions,
        "interview_questions": mock_questions,
    }[name]

    student = make_student("241FA04001")
    now = utc_now()

    mock_assignments.find_one.return_value = {
        "assignment_id": "asgn-valid-1",
        "interview_id": "int-valid-1",
        "student_registration_number": "241FA04001",
        "selected_role": "Software Development Engineer",
        "status": "accepted",
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-valid-1",
        "title": "Adaptive Technical Interview — Software Development Engineer",
        "status": "scheduled",
        "duration_minutes": 45,
    }
    # No active session
    mock_sessions.find_one.return_value = None
    mock_sessions.insert_one = AsyncMock()

    mock_questions.find_one.return_value = {
        "question_text": "Explain the time complexity of quicksort and worst-case avoidance.",
        "topic": "Algorithms",
        "question_type": "conceptual",
        "expected_answer": "Average O(n log n), worst case O(n^2) avoided by randomized pivot.",
        "keywords": ["quicksort", "pivot", "complexity"],
    }

    res = await InterviewSessionService.start_session(
        mock_db,
        assignment_id="asgn-valid-1",
        student_user=student,
    )

    assert isinstance(res, SessionQuestionResponse)
    assert res.session_id is not None
    assert res.assignment_id == "asgn-valid-1"
    assert res.question_index == 1
    assert res.total_questions == 5
    assert res.question_text == "Explain the time complexity of quicksort and worst-case avoidance."
    assert res.expires_at is not None
    assert res.expires_at > now
    assert res.time_remaining_seconds > 0
    # Expected duration is 45 + 5 = 50 minutes = 3000 seconds
    assert 2900 <= res.time_remaining_seconds <= 3000

    # Verify session document inserted in MongoDB
    assert mock_sessions.insert_one.called
    inserted_doc = mock_sessions.insert_one.call_args[0][0]
    assert inserted_doc["session_status"] == SessionStatus.IN_PROGRESS.value
    assert inserted_doc["expires_at"] == res.expires_at


# ==============================================================================
# 2. First question loads successfully after session creation
# ==============================================================================

@pytest.mark.anyio
async def test_first_question_loads_after_session_creation():
    """Verify that get_current_question successfully loads Question 1 for an active session."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "university_interviews": mock_interviews,
    }[name]

    student = make_student("241FA04001")
    now = utc_now()
    future_exp = now + timedelta(minutes=45)

    mock_sessions.find_one.return_value = {
        "session_id": "session-active-1",
        "assignment_id": "asgn-active-1",
        "interview_id": "int-active-1",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "current_question_index": 1,
        "total_questions_target": 5,
        "current_difficulty": "medium",
        "expires_at": future_exp,
        "active_question": {
            "question_text": "What is the difference between TCP and UDP?",
            "topic": "Networking",
            "question_type": "conceptual",
        },
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-active-1",
        "title": "Adaptive Technical Assessment",
    }

    q_res = await InterviewSessionService.get_current_question(
        mock_db,
        session_id="session-active-1",
        student_user=student,
    )

    assert q_res.session_id == "session-active-1"
    assert q_res.question_index == 1
    assert q_res.question_text == "What is the difference between TCP and UDP?"
    assert q_res.time_remaining_seconds > 0
    assert q_res.expires_at == future_exp


# ==============================================================================
# 3. Genuinely expired session is rejected across all operational endpoints
# ==============================================================================

@pytest.mark.anyio
async def test_genuinely_expired_session_rejected_in_get_current_question():
    """Verify get_current_question rejects expired session and marks it timed_out."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("241FA04001")
    past_exp = utc_now() - timedelta(minutes=10)

    mock_sessions.find_one.return_value = {
        "session_id": "session-exp-1",
        "assignment_id": "asgn-exp-1",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "expires_at": past_exp,
    }

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.get_current_question(
            mock_db,
            session_id="session-exp-1",
            student_user=student,
        )

    assert exc.value.status_code == 400
    assert "timed out" in exc.value.detail.lower()
    # Verifies both session and assignment updated
    assert mock_sessions.update_one.called
    assert mock_assignments.update_one.called


@pytest.mark.anyio
async def test_genuinely_expired_session_rejected_in_run_code():
    """Verify run_code rejects expired session and marks it timed_out."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_assignments = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("241FA04001")
    past_exp = utc_now() - timedelta(minutes=5)

    mock_sessions.find_one.return_value = {
        "session_id": "session-exp-2",
        "assignment_id": "asgn-exp-2",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "expires_at": past_exp,
    }

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.run_code(
            mock_db,
            session_id="session-exp-2",
            student_user=student,
            language="python",
            source_code="print('hello')",
        )

    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()
    assert mock_sessions.update_one.called
    assert mock_assignments.update_one.called


@pytest.mark.anyio
async def test_get_session_by_assignment_detects_and_marks_expiry():
    """Verify get_session_by_assignment detects passed expiry and updates session and assignment."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "university_interviews": mock_interviews,
    }[name]

    student = make_student("241FA04001")
    past_exp = utc_now() - timedelta(minutes=15)

    mock_assignments.find_one.return_value = {
        "assignment_id": "asgn-exp-3",
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "status": "in_progress",
    }
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[{
        "session_id": "session-exp-3",
        "assignment_id": "asgn-exp-3",
        "session_status": "in_progress",
        "expires_at": past_exp,
        "active_question": {"question_text": "Explain DNS", "topic": "DNS"},
    }])
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "Adaptive Technical Assessment",
    }
    mock_sessions.update_one = AsyncMock()
    mock_assignments.update_one = AsyncMock()

    res = await InterviewSessionService.get_session_by_assignment(
        mock_db,
        assignment_id="asgn-exp-3",
        student_user=student,
    )

    assert res["has_session"] is True
    assert res["session_status"] == SessionStatus.TIMED_OUT.value
    assert res["time_remaining_seconds"] == 0
    assert mock_sessions.update_one.called
    assert mock_assignments.update_one.called


# ==============================================================================
# 4. Session with invalid or missing expiry data fails safely
# ==============================================================================

def test_ensure_utc_handles_all_datatypes_safely():
    """Verify _ensure_utc normalizes naive datetimes, aware datetimes, ISO strings, timestamps, and missing values."""
    now = datetime.now(timezone.utc)

    # 1. None
    assert _ensure_utc(None).tzinfo == timezone.utc

    # 2. Offset-naive datetime
    naive = datetime(2026, 10, 12, 12, 0, 0)
    aware = _ensure_utc(naive)
    assert aware.tzinfo == timezone.utc
    assert aware.year == 2026 and aware.month == 10 and aware.day == 12

    # 3. Timezone-aware datetime
    already_aware = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)
    assert _ensure_utc(already_aware) == already_aware

    # 4. ISO string with Z
    iso_z = "2026-10-12T12:00:00Z"
    parsed_z = _ensure_utc(iso_z)
    assert parsed_z.tzinfo == timezone.utc
    assert parsed_z.hour == 12

    # 5. ISO string with offset
    iso_offset = "2026-10-12T17:30:00+05:30"
    parsed_offset = _ensure_utc(iso_offset)
    assert parsed_offset.tzinfo == timezone.utc
    assert parsed_offset.hour == 12  # 17:30 IST is 12:00 UTC

    # 6. Numeric epoch timestamp in seconds
    epoch_sec = 1791806400  # valid future timestamp
    parsed_sec = _ensure_utc(epoch_sec)
    assert parsed_sec.tzinfo == timezone.utc

    # 7. Numeric epoch timestamp in milliseconds
    epoch_ms = 1791806400 * 1000
    parsed_ms = _ensure_utc(epoch_ms)
    assert parsed_ms.tzinfo == timezone.utc
    assert parsed_ms == parsed_sec

    # 8. Malformed string falls back safely to utc_now without exception
    malformed = "invalid-date-string"
    parsed_fallback = _ensure_utc(malformed)
    assert parsed_fallback.tzinfo == timezone.utc


# ==============================================================================
# 5. Duplicate-session and duplicate-submission safeguards
# ==============================================================================

@pytest.mark.anyio
async def test_start_session_when_active_session_is_expired_creates_new():
    """Verify that if an active session document in DB is actually expired, start_session finalizes it and creates a new one."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()
    mock_sessions = AsyncMock()
    mock_questions = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
        "interview_sessions": mock_sessions,
        "interview_questions": mock_questions,
    }[name]

    student = make_student("241FA04001")
    past_exp = utc_now() - timedelta(minutes=20)

    mock_assignments.find_one.return_value = {
        "assignment_id": "asgn-recover-1",
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "selected_role": "Product Engineer",
        "status": "in_progress",
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "Adaptive Technical Assessment",
        "status": "scheduled",
        "duration_minutes": 45,
    }
    # Existing session was in_progress, but its expires_at has passed!
    mock_sessions.find_one.return_value = {
        "session_id": "old-expired-session",
        "assignment_id": "asgn-recover-1",
        "session_status": "in_progress",
        "expires_at": past_exp,
    }
    mock_sessions.update_one = AsyncMock()
    mock_sessions.insert_one = AsyncMock()

    mock_questions.find_one.return_value = {
        "question_text": "Explain system scalability patterns.",
        "topic": "Architecture",
        "question_type": "conceptual",
    }

    # Should NOT raise 409 Conflict because the old session expired!
    res = await InterviewSessionService.start_session(
        mock_db,
        assignment_id="asgn-recover-1",
        student_user=student,
    )

    assert res.session_id is not None
    assert res.session_id != "old-expired-session"
    assert res.time_remaining_seconds > 0
    # Verified old session was updated to timed_out
    assert mock_sessions.update_one.called
