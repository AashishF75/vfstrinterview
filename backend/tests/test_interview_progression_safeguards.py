import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.models.user import UserInDB, UserRole
from app.models.interview import AssignmentStatus
from app.models.interview_session import (
    SessionStatus,
    QuestionDifficulty,
    EvaluatorMode,
    SessionQuestionResponse,
    SubmitAnswerResponse,
    utc_now,
)
from app.services.interview_session_service import InterviewSessionService


def make_student_user(uid: str, reg_no: str) -> UserInDB:
    return UserInDB(
        id=uid,
        email=f"{reg_no.lower()}@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="hashed_password",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


@pytest.mark.anyio
async def test_session_submission_and_next_question_progression():
    """
    Verifies that InterviewSessionService.submit_answer:
    1. Evaluates candidate response using the AI provider.
    2. Persists response in interview_responses.
    3. Advances current_question_index in session state.
    4. Updates active_question with next question.
    5. Returns next_question in SubmitAnswerResponse without marking session completed.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock()
    mock_sessions.update_one = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value=None)  # No prior duplicate
    mock_responses.insert_one = AsyncMock()
    mock_interviews = MagicMock()
    mock_interviews.find_one = AsyncMock(return_value={"interview_id": "int-1", "title": "Networks Assessment"})
    mock_questions = MagicMock()
    mock_questions.find_one = AsyncMock(return_value={
        "question_text": "Explain OSPF link-state routing algorithm.",
        "topic": "Networks Assessment",
        "question_type": "conceptual",
        "difficulty": "hard",
    })

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
        "interview_questions": mock_questions,
    }[name]

    student = make_student_user("stu-1", "241FA04001")
    session_id = "test-session-prog-1"
    now = utc_now()

    # Active session doc (on question 1, total 5 questions)
    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "asgn-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 5,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=45),
        "active_question": {
            "question_text": "What is the function of the ARP protocol?",
            "topic": "Networks",
            "difficulty": "medium",
            "question_type": "conceptual",
        },
    }

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.GEMINI)
    mock_provider.evaluate_answer.return_value = {
        "score": 8.5,
        "feedback": "Accurate explanation of IP to MAC address resolution.",
        "strengths": ["Clear definition", "Correct layer placement"],
        "improvements": ["Mention ARP cache timeout"],
    }

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="ARP maps an IPv4 address to its associated physical MAC address on local LAN.",
            student_user=student,
        )

    # Verifications
    assert response.session_id == session_id
    assert response.question_index == 1
    assert response.evaluated_score == 8.5
    assert response.is_session_completed is False
    assert response.next_question is not None
    assert response.next_question.question_index == 2
    assert response.next_question.total_questions == 5
    assert response.next_question.question_text == "Explain OSPF link-state routing algorithm."

    # Verify session update in DB advanced question index
    update_call = mock_sessions.update_one.call_args
    assert update_call is not None
    update_filter, update_payload = update_call[0]
    assert update_filter == {"session_id": session_id}
    assert update_payload["$set"]["current_question_index"] == 2
    assert update_payload["$set"]["active_question"]["question_text"] == "Explain OSPF link-state routing algorithm."


@pytest.mark.anyio
async def test_duplicate_submission_conflict_rejection():
    """
    Verifies that submitting the same question twice raises HTTP 409 Conflict.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    now = utc_now()
    session_id = "test-session-dup-1"

    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": session_id,
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "expires_at": now + timedelta(minutes=45),
        "active_question": {"question_text": "Sample question", "topic": "Networking"},
    })

    # Response already exists in DB for (session_id, question_index=1)
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value={"response_id": "existing-resp-1"})

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
    }[name]

    student = make_student_user("stu-1", "241FA04001")

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="Attempting duplicate submission.",
            student_user=student,
        )

    assert exc_info.value.status_code == 409
    assert "already been submitted" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_final_question_completion_scorecard_generation():
    """
    Verifies that submitting the final question marks session completed,
    generates a scorecard, and returns is_session_completed=True with next_question=None.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock()
    mock_sessions.update_one = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value=None)
    mock_responses.insert_one = AsyncMock()
    mock_scorecards = MagicMock()
    mock_scorecards.insert_one = AsyncMock()
    mock_assignments = MagicMock()
    mock_assignments.update_one = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student_user("stu-1", "241FA04001")
    session_id = "test-session-final-1"
    now = utc_now()

    # Active session is on final question (question 5 of 5)
    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "asgn-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 5,
        "total_questions_target": 5,
        "current_difficulty": "hard",
        "expires_at": now + timedelta(minutes=45),
        "active_question": {
            "question_text": "Explain zero-copy networking using sendfile system call.",
            "topic": "Advanced Networks",
            "difficulty": "hard",
            "question_type": "conceptual",
        },
    }

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.GEMINI)
    mock_provider.evaluate_answer.return_value = {
        "score": 9.0,
        "feedback": "Thorough architectural breakdown.",
        "strengths": ["Kernel bypass understanding"],
        "improvements": [],
    }
    mock_provider.generate_scorecard_summary.return_value = {
        "overall_score": 8.7,
        "percentage_score": 87.0,
        "performance_level": "Distinction",
        "summary_feedback": "Strong candidate demonstration across protocol stack.",
        "strengths": ["Networking foundations", "Performance optimization"],
        "areas_for_growth": ["Distributed synchronization"],
    }

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="sendfile avoids copying data into user space buffers, transferring directly between descriptors in kernel mode.",
            student_user=student,
        )

    # Verifications
    assert response.is_session_completed is True
    assert response.next_question is None
    assert response.scorecard_id is not None

    # Verify session status update to completed
    update_session = mock_sessions.update_one.call_args[0][1]
    assert update_session["$set"]["session_status"] == SessionStatus.COMPLETED.value
    assert update_session["$set"]["final_scorecard_id"] == response.scorecard_id

    # Verify scorecard persisted
    scorecard_doc = mock_scorecards.insert_one.call_args[0][0]
    assert scorecard_doc["overall_score"] == 8.7
    assert scorecard_doc["performance_level"] == "Distinction"
