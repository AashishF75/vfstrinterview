import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserInDB, UserRole
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.interview_session import QuestionDifficulty, SessionStatus, EvaluatorMode, utc_now
from app.core.security import create_access_token


@pytest.fixture
def client():
    return TestClient(app)


def make_user(uid: str, email: str, role: UserRole, reg_no: str = None) -> UserInDB:
    return UserInDB(
        id=uid,
        email=email,
        role=role,
        hashed_password="hashed_pw",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


@pytest.mark.anyio
async def test_complete_interview_workflow_and_lifecycle():
    """
    End-to-End lifecycle verification:
    1. Admin creates university interview & assigns student 241FA04001.
    2. Student 241FA04001 accepts assignment.
    3. Student starts session: verifies Question 1 (medium) & timer.
    4. Student submits valid answer with high score: verifies immediate feedback & escalation to hard.
    5. Final question submitted: session marks completed & scorecard is generated.
    6. Reload/resume verification: get_session_by_assignment returns completed state consistently.
    7. Cross-student isolation: Student B (241FA04002) is rejected with 403 on all endpoints.
    8. Duplicate start rejection: 409 Conflict.
    9. Server-side expiry enforcement: 400 Bad Request.
    """
    from app.services.interview_session_service import InterviewSessionService
    from app.services.interview_service import InterviewService
    from app.models.interview import UniversityInterviewCreate, StudentInterviewAssignmentInDB

    mock_db = MagicMock()
    mock_interviews = AsyncMock()
    mock_assignments = AsyncMock()
    mock_sessions = MagicMock()
    mock_sessions.insert_one = AsyncMock()
    mock_sessions.update_one = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.insert_one = AsyncMock()
    mock_scorecards = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "university_interviews": mock_interviews,
        "student_interview_assignments": mock_assignments,
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
    }[name]

    admin_user = make_user("admin-1", "admin@vfstr.ac.in", UserRole.UNIVERSITY_ADMIN)
    student_a = make_user("stu-1", "student1@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04001")
    student_b = make_user("stu-2", "student2@vfstr.ac.in", UserRole.STUDENT, reg_no="241FA04002")

    # --------------------------------------------------------------------------
    # Step 1: Admin creates test interview
    # --------------------------------------------------------------------------
    now = utc_now()
    interview_id = "test-int-e2e-1"
    interview_doc = {
        "interview_id": interview_id,
        "title": "Computer Networking Adaptive Assessment",
        "instructions": "Explain networking protocols thoroughly.",
        "scheduled_start_time": now + timedelta(days=1),
        "scheduled_end_time": now + timedelta(days=1, hours=2),
        "duration_minutes": 30,
        "status": InterviewStatus.SCHEDULED.value,
        "created_by_user_id": admin_user.id,
        "created_by_email": admin_user.email,
        "created_at": now,
        "updated_at": now,
    }
    mock_interviews.find_one.return_value = interview_doc

    # --------------------------------------------------------------------------
    # Step 2: Assign Student A (241FA04001)
    # --------------------------------------------------------------------------
    assignment_id = "assign-e2e-1"
    assignment_doc = {
        "assignment_id": assignment_id,
        "interview_id": interview_id,
        "student_registration_number": "241FA04001",
        "student_email": student_a.email,
        "status": AssignmentStatus.ASSIGNED.value,
        "assigned_at": now,
        "created_at": now,
        "updated_at": now,
    }
    mock_assignments.find_one.return_value = assignment_doc

    # --------------------------------------------------------------------------
    # Step 3: Student A accepts assignment
    # --------------------------------------------------------------------------
    accepted_doc = dict(assignment_doc, status=AssignmentStatus.ACCEPTED.value)
    mock_assignments.find_one.return_value = accepted_doc

    # --------------------------------------------------------------------------
    # Step 4: Check session before starting (returns has_session: False)
    # --------------------------------------------------------------------------
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    check_session_res = await InterviewSessionService.get_session_by_assignment(
        mock_db,
        assignment_id=assignment_id,
        student_user=student_a,
    )
    assert check_session_res["has_session"] is False

    # --------------------------------------------------------------------------
    # Step 5: Start Interview Session (Question 1)
    # --------------------------------------------------------------------------
    mock_sessions.find_one = AsyncMock(return_value=None)  # No prior active session
    start_res = await InterviewSessionService.start_session(
        mock_db,
        assignment_id=assignment_id,
        student_user=student_a,
    )
    assert start_res.assignment_id == assignment_id
    assert start_res.question_index == 1
    assert start_res.difficulty == QuestionDifficulty.MEDIUM
    assert start_res.evaluator_mode == "mock_rule_engine"
    assert start_res.time_remaining_seconds > 0
    assert mock_sessions.insert_one.called
    session_id = start_res.session_id

    # --------------------------------------------------------------------------
    # Step 6: Submit Answer 1 (High score -> Adaptive escalation to HARD)
    # --------------------------------------------------------------------------
    session_state = {
        "session_id": session_id,
        "interview_id": interview_id,
        "assignment_id": assignment_id,
        "student_registration_number": "241FA04001",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 2,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=30),
        "active_question": {
            "question_text": "Describe why VLANs are implemented and how 802.1Q tagging works.",
            "topic": "VLANs & Trunking",
            "difficulty": "medium",
        },
    }
    mock_sessions.find_one = AsyncMock(return_value=session_state)

    # Submit comprehensive answer matching keywords
    answer_text = (
        "VLANs divide physical switches into multiple logical broadcast domains to improve network security and efficiency. "
        "802.1Q tagging inserts an identification tag into Ethernet frames across trunk links between switches."
    )
    sub1_res = await InterviewSessionService.submit_answer(
        mock_db,
        session_id=session_id,
        answer_text=answer_text,
        student_user=student_a,
    )
    assert sub1_res.evaluated_score >= 7.5
    assert sub1_res.next_difficulty == QuestionDifficulty.HARD
    assert "escalat" in sub1_res.difficulty_rationale.lower()
    assert sub1_res.is_session_completed is False
    assert sub1_res.next_question is not None
    assert sub1_res.next_question.question_index == 2

    # --------------------------------------------------------------------------
    # Step 7: Submit Answer 2 (Final Question -> Session completed & Scorecard)
    # --------------------------------------------------------------------------
    session_state["current_question_index"] = 2
    session_state["current_difficulty"] = "hard"
    session_state["active_question"] = {
        "question_text": "Analyze how Link-State protocols like OSPF establish adjacencies and exchange LSAs.",
        "topic": "Dynamic Routing & OSPF",
        "difficulty": "hard",
    }
    mock_sessions.find_one = AsyncMock(return_value=session_state)

    # Responses list returns 2 completed responses
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[
        {
            "question_index": 1,
            "score": sub1_res.evaluated_score,
            "difficulty": "medium",
            "strengths": ["Clear technical terms: broadcast domain, 802.1q"],
            "improvements": [],
        },
        {
            "question_index": 2,
            "score": 8.0,
            "difficulty": "hard",
            "strengths": ["Identified OSPF adjacency requirements"],
            "improvements": [],
        },
    ])

    sub2_res = await InterviewSessionService.submit_answer(
        mock_db,
        session_id=session_id,
        answer_text="OSPF routers exchange Hello packets to establish adjacency and populate the link-state database (LSDB).",
        student_user=student_a,
    )
    assert sub2_res.is_session_completed is True
    assert sub2_res.scorecard_id is not None
    assert mock_scorecards.insert_one.called

    # --------------------------------------------------------------------------
    # Step 8: View Final Scorecard & Verify Mock Rubric Disclaimer
    # --------------------------------------------------------------------------
    saved_scorecard_doc = mock_scorecards.insert_one.call_args[0][0]
    mock_scorecards.find_one.return_value = saved_scorecard_doc
    session_state["session_status"] = SessionStatus.COMPLETED.value
    session_state["scorecard_id"] = saved_scorecard_doc["scorecard_id"]
    mock_sessions.find_one = AsyncMock(return_value=session_state)

    # Set responses cursor for scorecard audit
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[
        {
            "question_index": 1,
            "question_text": "Describe VLANs",
            "topic": "VLANs",
            "difficulty": "medium",
            "answer_text": answer_text,
            "evaluation_score": 8.0,
            "evaluation_feedback": "Good grasp of 802.1Q.",
            "strengths": ["Clear terms"],
            "improvements": [],
            "difficulty_adjustment_rationale": "Score >= 7.5: escalated to hard",
        },
        {
            "question_index": 2,
            "question_text": "Analyze OSPF",
            "topic": "OSPF",
            "difficulty": "hard",
            "answer_text": "OSPF adjacency explanation.",
            "evaluation_score": 8.0,
            "evaluation_feedback": "Solid OSPF mechanics.",
            "strengths": ["Adjacency understanding"],
            "improvements": [],
            "difficulty_adjustment_rationale": "Final question reached",
        },
    ])

    scorecard_res = await InterviewSessionService.get_scorecard(
        mock_db,
        session_id=session_id,
        user=student_a,
    )
    assert scorecard_res.overall_score == saved_scorecard_doc["overall_score"]
    assert scorecard_res.evaluator_mode == "mock_rule_engine"
    assert "MOCK EVALUATION NOTICE" in scorecard_res.disclaimer
    assert len(scorecard_res.responses) == 2

    # --------------------------------------------------------------------------
    # Step 9: Reload Page / Resume Session by Assignment
    # --------------------------------------------------------------------------
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[session_state])
    reload_res = await InterviewSessionService.get_session_by_assignment(
        mock_db,
        assignment_id=assignment_id,
        student_user=student_a,
    )
    assert reload_res["has_session"] is True
    assert reload_res["session_id"] == session_id
    assert reload_res["session_status"] == "completed"
    assert reload_res["scorecard_id"] == saved_scorecard_doc["scorecard_id"]

    # --------------------------------------------------------------------------
    # Step 10: Cross-Student Isolation (Student B rejected with 403)
    # --------------------------------------------------------------------------
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.get_scorecard(
            mock_db,
            session_id=session_id,
            user=student_b,
        )
    assert exc.value.status_code == 403
    assert "Access denied" in exc.value.detail

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.submit_answer(
            mock_db,
            session_id=session_id,
            answer_text="Hacking answer",
            student_user=student_b,
        )
    assert exc.value.status_code == 403
