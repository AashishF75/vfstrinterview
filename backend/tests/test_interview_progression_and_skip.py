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
    StudentPerformanceReportResponse,
    utc_now,
)
from app.services.interview_session_service import InterviewSessionService


def make_student(uid: str, reg_no: str) -> UserInDB:
    return UserInDB(
        id=uid,
        email=f"{reg_no.lower()}@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="hashed_password",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


@pytest.mark.anyio
async def test_skip_question_advances_to_next_question():
    """
    Verifies that InterviewSessionService.skip_question:
    1. Records skipped response with is_skipped=True, status="skipped", evaluation_score=None.
    2. Does not assign an answer score.
    3. Advances current_question_index in session.
    4. Automatically generates/selects next question.
    5. Returns next_question in SubmitAnswerResponse with is_session_completed=False.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock()
    mock_sessions.update_one = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value=None)
    mock_responses.insert_one = AsyncMock()
    mock_interviews = MagicMock()
    mock_interviews.find_one = AsyncMock(return_value={"interview_id": "int-1", "title": "Software Engineering"})
    mock_questions = MagicMock()
    mock_questions.find_one = AsyncMock(return_value={
        "question_text": "Describe the principles of RESTful architecture.",
        "topic": "Software Engineering",
        "question_type": "conceptual",
        "difficulty": "medium",
    })

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
        "interview_questions": mock_questions,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-skip-1"
    now = utc_now()

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
            "question_text": "What is normalization in relational databases?",
            "topic": "Databases",
            "difficulty": "medium",
            "question_type": "conceptual",
        },
    }

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.skip_question(
            db=mock_db,
            session_id=session_id,
            student_user=student,
        )

    # 1. Assert response structure
    assert response.session_id == session_id
    assert response.question_index == 1
    assert response.is_skipped is True
    assert response.evaluated_score is None
    assert response.is_session_completed is False
    assert response.next_question is not None
    assert response.next_question.question_index == 2
    assert response.next_question.question_text == "Describe the principles of RESTful architecture."

    # 2. Assert response document persisted in DB
    resp_doc = mock_responses.insert_one.call_args[0][0]
    assert resp_doc["session_id"] == session_id
    assert resp_doc["question_index"] == 1
    assert resp_doc["is_skipped"] is True
    assert resp_doc["status"] == "skipped"
    assert resp_doc["evaluation_score"] is None

    # 3. Assert session updated to question 2
    sess_update = mock_sessions.update_one.call_args[0][1]
    assert sess_update["$set"]["current_question_index"] == 2
    assert sess_update["$set"]["active_question"]["question_text"] == "Describe the principles of RESTful architecture."


@pytest.mark.anyio
async def test_skip_final_question_completes_interview():
    """
    Verifies that skipping the final question (e.g. Q5 of 5):
    1. Records skipped response for Q5.
    2. Marks session and assignment as COMPLETED.
    3. Generates scorecard with accurate accounting of answered vs skipped questions.
    4. Returns is_session_completed=True, next_question=None.
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

    # Prior responses: Q1-Q4 answered
    prior_responses = [
        {"question_index": 1, "topic": "Databases", "difficulty": "medium", "evaluation_score": 8.0, "is_skipped": False, "status": "answered"},
        {"question_index": 2, "topic": "Databases", "difficulty": "medium", "evaluation_score": 7.5, "is_skipped": False, "status": "answered"},
        {"question_index": 3, "topic": "OS", "difficulty": "hard", "evaluation_score": 8.5, "is_skipped": False, "status": "answered"},
        {"question_index": 4, "topic": "OS", "difficulty": "hard", "evaluation_score": 9.0, "is_skipped": False, "status": "answered"},
    ]
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=prior_responses)
    mock_responses.find = MagicMock(return_value=cursor)

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-skip-final"
    now = utc_now()

    # Session on Question 5 of 5
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
            "question_text": "Write a deadlock detection algorithm.",
            "topic": "OS",
            "difficulty": "hard",
            "question_type": "coding",
        },
    }

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    mock_provider.generate_scorecard_summary.return_value = {
        "overall_score": 8.2,
        "percentage_score": 82.0,
        "performance_level": "Proficient",
        "summary_feedback": "Evaluated across 4 answered questions. 1 question skipped.",
        "strengths": ["Database concepts", "Operating systems"],
        "areas_for_growth": ["Coding challenges under time constraints"],
    }

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.skip_question(
            db=mock_db,
            session_id=session_id,
            student_user=student,
        )

    assert response.is_session_completed is True
    assert response.is_skipped is True
    assert response.evaluated_score is None
    assert response.next_question is None
    assert response.scorecard_id is not None

    # Assert scorecard accounting
    scorecard_doc = mock_scorecards.insert_one.call_args[0][0]
    assert scorecard_doc["total_questions_assigned"] == 5
    assert scorecard_doc["questions_answered"] == 4
    assert scorecard_doc["questions_skipped"] == 1
    assert scorecard_doc["questions_evaluated"] == 4

    # Assert session marked completed
    sess_update = mock_sessions.update_one.call_args[0][1]
    assert sess_update["$set"]["session_status"] == SessionStatus.COMPLETED.value


@pytest.mark.anyio
async def test_skip_all_questions_score_calculation():
    """
    Verifies that if a candidate skips every single question in the interview:
    1. Overall score is 0.0 and percentage is 0.0.
    2. Performance level is 'Needs Improvement'.
    3. No fabricated scores are generated.
    4. Accounting accurately reflects 0 answered, 5 skipped.
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

    # Prior responses: Q1-Q4 all skipped
    prior_responses = [
        {"question_index": 1, "topic": "Networking", "difficulty": "medium", "evaluation_score": None, "is_skipped": True, "status": "skipped"},
        {"question_index": 2, "topic": "Networking", "difficulty": "medium", "evaluation_score": None, "is_skipped": True, "status": "skipped"},
        {"question_index": 3, "topic": "Networking", "difficulty": "medium", "evaluation_score": None, "is_skipped": True, "status": "skipped"},
        {"question_index": 4, "topic": "Networking", "difficulty": "medium", "evaluation_score": None, "is_skipped": True, "status": "skipped"},
    ]
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=prior_responses)
    mock_responses.find = MagicMock(return_value=cursor)

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-skip-all"
    now = utc_now()

    # Session on Question 5 of 5
    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "asgn-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 5,
        "total_questions_target": 5,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=45),
        "active_question": {
            "question_text": "Explain TCP congestion control window.",
            "topic": "Networking",
            "difficulty": "medium",
            "question_type": "conceptual",
        },
    }

    from app.services.ai_provider import MockRuleEngineProvider
    real_mock_provider = MockRuleEngineProvider()

    with patch("app.services.interview_session_service.get_ai_provider", return_value=real_mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.skip_question(
            db=mock_db,
            session_id=session_id,
            student_user=student,
        )

    assert response.is_session_completed is True

    scorecard_doc = mock_scorecards.insert_one.call_args[0][0]
    assert scorecard_doc["overall_score"] == 0.0
    assert scorecard_doc["percentage_score"] == 0.0
    assert scorecard_doc["performance_level"] == "Needs Improvement"
    assert scorecard_doc["questions_answered"] == 0
    assert scorecard_doc["questions_skipped"] == 5
    assert scorecard_doc["questions_evaluated"] == 0
    assert "all questions" in scorecard_doc["summary_feedback"].lower()
    assert "skipped" in scorecard_doc["summary_feedback"].lower()


@pytest.mark.anyio
async def test_duplicate_skip_rejected_with_409():
    """
    Verifies that calling skip_question twice on the same question index raises HTTP 409 Conflict.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    now = utc_now()
    session_id = "test-session-dup-skip"

    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": session_id,
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 2,
        "expires_at": now + timedelta(minutes=45),
        "active_question": {"question_text": "Sample question", "topic": "Networking"},
    })

    # Response already exists in DB for question 2
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value={"response_id": "existing-resp-skip-2"})

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
    }[name]

    student = make_student("stu-1", "241FA04001")

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.skip_question(
            db=mock_db,
            session_id=session_id,
            student_user=student,
        )

    assert exc_info.value.status_code == 409
    assert "already been submitted or skipped" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_skip_cross_student_access_rejected_with_403():
    """
    Verifies that Candidate A cannot skip questions in Candidate B's interview session.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    session_id = "test-session-cross-skip"

    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": session_id,
        "student_registration_number": "241FA04999",  # Belongs to candidate 241FA04999
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
    })

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
    }[name]

    # Attacker candidate
    student_attacker = make_student("stu-1", "241FA04001")

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.skip_question(
            db=mock_db,
            session_id=session_id,
            student_user=student_attacker,
        )

    assert exc_info.value.status_code == 403
    assert "access denied" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_report_accounting_distinguishes_skipped_and_answered():
    """
    Verifies that get_performance_report correctly calculates:
    - total_questions_assigned
    - questions_answered
    - questions_skipped
    - questions_evaluated
    - labels skipped items accurately in response summaries
    """
    mock_db = MagicMock()
    mock_assignments = MagicMock()
    mock_sessions = MagicMock()
    mock_scorecards = MagicMock()
    mock_responses = MagicMock()
    mock_interviews = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "interview_scorecards": mock_scorecards,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
    }[name]

    assignment_id = "asgn-rep-test"
    session_id = "sess-rep-test"
    student = make_student("stu-1", "241FA04001")
    now = utc_now()

    mock_assignments.find_one = AsyncMock(return_value={
        "assignment_id": assignment_id,
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.COMPLETED.value,
    })

    sess_doc = {
        "session_id": session_id,
        "assignment_id": assignment_id,
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.COMPLETED.value,
        "total_questions_target": 5,
        "completed_at": now,
        "created_at": now,
    }
    cursor_sess = MagicMock()
    cursor_sess.sort = MagicMock(return_value=cursor_sess)
    cursor_sess.to_list = AsyncMock(return_value=[sess_doc])
    mock_sessions.find = MagicMock(return_value=cursor_sess)
    mock_sessions.find_one = AsyncMock(return_value=sess_doc)

    mock_scorecards.find_one = AsyncMock(return_value={
        "scorecard_id": "sc-1",
        "session_id": session_id,
        "overall_score": 8.0,
        "percentage_score": 80.0,
        "performance_level": "Proficient",
        "summary_feedback": "Demonstrated strong knowledge with 2 skipped questions.",
        "difficulty_progression": ["medium", "medium", "hard", "hard", "hard"],
        "total_questions_assigned": 5,
        "questions_answered": 3,
        "questions_skipped": 2,
        "questions_evaluated": 3,
        "evaluator_mode": "mock_rule_engine",
        "disclaimer": "Evaluations reflect algorithmic rubrics.",
        "created_at": now,
    })

    raw_responses = [
        {"question_index": 1, "question_text": "Q1", "topic": "SQL", "difficulty": "medium", "answer_text": "Answer 1", "evaluation_score": 8.0, "is_skipped": False, "status": "answered", "evaluation_feedback": "Good"},
        {"question_index": 2, "question_text": "Q2", "topic": "SQL", "difficulty": "medium", "answer_text": "(Skipped)", "evaluation_score": None, "is_skipped": True, "status": "skipped", "evaluation_feedback": "Skipped by candidate."},
        {"question_index": 3, "question_text": "Q3", "topic": "OOP", "difficulty": "hard", "answer_text": "Answer 3", "evaluation_score": 7.5, "is_skipped": False, "status": "answered", "evaluation_feedback": "Solid"},
        {"question_index": 4, "question_text": "Q4", "topic": "OOP", "difficulty": "hard", "answer_text": "(Skipped)", "evaluation_score": None, "is_skipped": True, "status": "skipped", "evaluation_feedback": "Skipped by candidate."},
        {"question_index": 5, "question_text": "Q5", "topic": "TCP/IP", "difficulty": "hard", "answer_text": "Answer 5", "evaluation_score": 8.5, "is_skipped": False, "status": "answered", "evaluation_feedback": "Great"},
    ]
    cursor_resp = MagicMock()
    cursor_resp.sort = MagicMock(return_value=cursor_resp)
    cursor_resp.to_list = AsyncMock(return_value=raw_responses)
    mock_responses.find = MagicMock(return_value=cursor_resp)

    mock_interviews.find_one = AsyncMock(return_value={"interview_id": "int-1", "title": "Technical Assessment"})

    report = await InterviewSessionService.get_performance_report(
        db=mock_db,
        assignment_id=assignment_id,
        user=student,
    )

    assert report.total_questions_assigned == 5
    assert report.questions_answered == 3
    assert report.questions_skipped == 2
    assert report.questions_evaluated == 3
    assert len(report.responses) == 5

    # Check skipped question properties
    skipped_items = [r for r in report.responses if r.is_skipped]
    assert len(skipped_items) == 2
    for s in skipped_items:
        assert s.status == "skipped"
        assert s.evaluation_score is None
        assert s.score is None


@pytest.mark.anyio
async def test_submit_non_final_answer_advances_to_next_question():
    """
    Verifies that InterviewSessionService.submit_answer:
    1. Evaluates candidate answer via the configured provider.
    2. Persists response with is_skipped=False, status="answered", and numeric evaluation_score.
    3. Advances current_question_index in session state.
    4. Automatically selects/generates next question.
    5. Returns next_question in SubmitAnswerResponse with is_session_completed=False.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock()
    mock_sessions.update_one = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value=None)
    mock_responses.insert_one = AsyncMock()
    mock_interviews = MagicMock()
    mock_interviews.find_one = AsyncMock(return_value={"interview_id": "int-1", "title": "Software Engineering"})
    mock_questions = MagicMock()
    mock_questions.find_one = AsyncMock(return_value={
        "question_text": "Describe the principles of RESTful architecture.",
        "topic": "Software Engineering",
        "question_type": "conceptual",
        "difficulty": "medium",
    })

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
        "interview_questions": mock_questions,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-submit-1"
    now = utc_now()

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
            "question_text": "What is normalization in relational databases?",
            "topic": "Databases",
            "difficulty": "medium",
            "question_type": "conceptual",
        },
    }

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    mock_provider.evaluate_answer = AsyncMock(return_value={
        "score": 8.5,
        "feedback": "Clear explanation of 1NF, 2NF, and 3NF.",
        "strengths": ["Comprehensive coverage of anomaly elimination."],
        "improvements": ["Could briefly mention BCNF."],
    })

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="Normalization organizes data to reduce redundancy and improve data integrity across 1NF, 2NF, and 3NF.",
            student_user=student,
        )

    # 1. Assert response properties
    assert response.session_id == session_id
    assert response.question_index == 1
    assert response.is_skipped is False
    assert response.is_session_completed is False
    assert response.evaluated_score == 8.5
    assert response.next_question is not None
    assert response.next_question.question_index == 2
    assert response.next_question.question_text == "Describe the principles of RESTful architecture."
    assert response.scorecard_id is None

    # 2. Assert response persisted
    mock_responses.insert_one.assert_called_once()
    saved_resp = mock_responses.insert_one.call_args[0][0]
    assert saved_resp["session_id"] == session_id
    assert saved_resp["question_index"] == 1
    assert saved_resp["evaluation_score"] == 8.5
    assert saved_resp["is_skipped"] is False
    assert saved_resp["status"] == "answered"

    # 3. Assert session updated to question 2
    mock_sessions.update_one.assert_called_once()
    update_filter, update_payload = mock_sessions.update_one.call_args[0]
    assert update_filter == {"session_id": session_id}
    assert update_payload["$set"]["current_question_index"] == 2
    assert update_payload["$set"]["active_question"]["question_text"] == "Describe the principles of RESTful architecture."


@pytest.mark.anyio
async def test_submit_final_answer_completes_interview():
    """
    Verifies that InterviewSessionService.submit_answer on the final question:
    1. Evaluates candidate answer.
    2. Persists response with status="answered".
    3. Generates scorecard with overall score.
    4. Marks session and assignment as COMPLETED.
    5. Returns is_session_completed=True, next_question=None, and scorecard_id.
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

    prior_responses = [
        {"question_index": 1, "question_text": "Q1", "topic": "Databases", "difficulty": "medium", "score": 8.0, "is_skipped": False, "status": "answered"},
        {"question_index": 2, "question_text": "Q2", "topic": "Databases", "difficulty": "medium", "score": 7.5, "is_skipped": False, "status": "answered"},
        {"question_index": 3, "question_text": "Q3", "topic": "Databases", "difficulty": "hard", "score": 9.0, "is_skipped": False, "status": "answered"},
        {"question_index": 4, "question_text": "Q4", "topic": "Databases", "difficulty": "hard", "score": 8.5, "is_skipped": False, "status": "answered"},
    ]
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=prior_responses)
    mock_responses.find = MagicMock(return_value=cursor)

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-submit-final"
    now = utc_now()

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
            "question_text": "Explain ACID properties and transaction isolation levels.",
            "topic": "Databases",
            "difficulty": "hard",
            "question_type": "conceptual",
        },
    }

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    mock_provider.evaluate_answer = AsyncMock(return_value={
        "score": 9.0,
        "feedback": "Excellent breakdown of atomicity, consistency, isolation, and durability.",
        "strengths": ["Thorough explanation of dirty reads and phantom reads."],
        "improvements": [],
    })
    mock_provider.generate_scorecard_summary = AsyncMock(return_value={
        "overall_score": 8.4,
        "percentage_score": 84.0,
        "performance_level": "Advanced",
        "summary_feedback": "Demonstrated advanced database expertise across all 5 evaluated questions.",
        "strengths": ["Database fundamentals", "Transaction isolation"],
        "areas_for_growth": ["Distributed concurrency"],
    })

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="ACID guarantees atomicity, consistency, isolation, and durability in DBMS transactions.",
            student_user=student,
        )

    # 1. Assert completed response
    assert response.is_session_completed is True
    assert response.next_question is None
    assert response.scorecard_id is not None
    assert response.evaluated_score == 9.0

    # 2. Assert scorecard saved
    mock_scorecards.insert_one.assert_called_once()
    saved_sc = mock_scorecards.insert_one.call_args[0][0]
    assert saved_sc["session_id"] == session_id
    assert saved_sc["questions_answered"] == 5
    assert saved_sc["questions_skipped"] == 0
    assert saved_sc["overall_score"] == 8.4

    # 3. Assert session marked COMPLETED
    mock_sessions.update_one.assert_called_once()
    update_filter, update_payload = mock_sessions.update_one.call_args[0]
    assert update_filter == {"session_id": session_id}
    assert update_payload["$set"]["session_status"] == SessionStatus.COMPLETED.value


@pytest.mark.anyio
async def test_submit_duplicate_rejected_with_409():
    """
    Verifies that attempting to submit an answer for an already answered or skipped
    question index raises HTTP 409 Conflict.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value={"response_id": "resp-existing", "question_index": 2})

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-submit-dup"
    now = utc_now()

    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "asgn-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 2,
        "total_questions_target": 5,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=45),
        "active_question": {"question_text": "Q2", "topic": "Networking", "difficulty": "medium", "question_type": "conceptual"},
    })

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="Some answer text",
            student_user=student,
        )

    assert exc_info.value.status_code == 409
    assert "already been submitted or skipped" in exc_info.value.detail


@pytest.mark.anyio
async def test_submit_to_completed_session_rejected_with_400():
    """
    Verifies that submitting an answer to an already completed session raises HTTP 400.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": "sess-completed",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.COMPLETED.value,
    })

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
    }[name]

    student = make_student("stu-1", "241FA04001")

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id="sess-completed",
            answer_text="Some answer text",
            student_user=student,
        )

    assert exc_info.value.status_code == 400
    assert "already completed" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_submit_blank_answer_rejected_with_422():
    """
    Verifies that submitting a blank or whitespace-only answer raises HTTP 422.
    """
    mock_db = MagicMock()
    student = make_student("stu-1", "241FA04001")

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id="sess-1",
            answer_text="   \n\t  ",
            student_user=student,
        )

    assert exc_info.value.status_code == 422
    assert "cannot be blank" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_submit_cross_student_access_rejected_with_403():
    """
    Verifies that Candidate A cannot submit answers to Candidate B's interview session.
    """
    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": "sess-cross-submit",
        "student_registration_number": "241FA04999",  # Belongs to candidate 241FA04999
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
    })

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
    }[name]

    student_attacker = make_student("stu-1", "241FA04001")

    with pytest.raises(HTTPException) as exc_info:
        await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id="sess-cross-submit",
            answer_text="Attempting to submit answer to another candidate session",
            student_user=student_attacker,
        )

    assert exc_info.value.status_code == 403
    assert "access denied" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_submit_provider_failure_preserves_session_unmodified():
    """
    Verifies that when AI provider evaluation fails (HTTP 503):
    1. An HTTP 503 exception is raised.
    2. No response record is inserted into interview_responses.
    3. The session state is not advanced or marked completed.
    """
    from app.services.ai_provider import AIProviderError

    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_responses = MagicMock()
    mock_responses.find_one = AsyncMock(return_value=None)
    mock_responses.insert_one = AsyncMock()
    mock_interviews = MagicMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
    }[name]

    student = make_student("stu-1", "241FA04001")
    session_id = "test-session-provider-fail"
    now = utc_now()

    mock_sessions.find_one = AsyncMock(return_value={
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "asgn-1",
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 5,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=45),
        "active_question": {"question_text": "What is DNS?", "topic": "Networking", "difficulty": "medium", "question_type": "conceptual"},
    })

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.GEMINI)
    mock_provider.evaluate_answer = AsyncMock(side_effect=AIProviderError("Upstream evaluation service unavailable"))

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        with pytest.raises(HTTPException) as exc_info:
            await InterviewSessionService.submit_answer(
                db=mock_db,
                session_id=session_id,
                answer_text="DNS resolves domain names to IP addresses.",
                student_user=student,
            )

    assert exc_info.value.status_code == 503
    assert "temporarily unavailable" in exc_info.value.detail.lower()

    # Verify no response was saved
    mock_responses.insert_one.assert_not_called()
    # Verify session was NOT updated
    mock_sessions.update_one.assert_not_called()
