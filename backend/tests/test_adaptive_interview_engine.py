import pytest
import pymongo
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.models.interview_session import (
    QuestionDifficulty,
    SessionStatus,
    EvaluatorMode,
    InterviewSessionInDB,
    utc_now,
)
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.user import UserInDB, UserRole
from app.services.ai_provider import (
    AdaptiveDifficultyPolicy,
    MockRuleEngineProvider,
    get_ai_provider,
    AIProviderUnavailableError,
)
from app.services.interview_session_service import InterviewSessionService
from app.core.config import settings


# ==============================================================================
# 1. Adaptive Difficulty Policy Tests
# ==============================================================================

def test_adaptive_difficulty_escalation():
    """Verify difficulty escalates when candidate scores >= 7.5."""
    # easy -> medium
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.EASY, 8.0)
    assert next_diff == QuestionDifficulty.MEDIUM
    assert "escalating from easy to medium" in rationale

    # medium -> hard
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.MEDIUM, 9.2)
    assert next_diff == QuestionDifficulty.HARD
    assert "escalating from medium to hard" in rationale

    # hard -> hard (reaches maximum ceiling)
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.HARD, 9.5)
    assert next_diff == QuestionDifficulty.HARD
    assert "maintaining hard tier" in rationale


def test_adaptive_difficulty_de_escalation():
    """Verify difficulty de-escalates when candidate scores < 5.0."""
    # hard -> medium
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.HARD, 4.0)
    assert next_diff == QuestionDifficulty.MEDIUM
    assert "de-escalating to medium tier" in rationale

    # medium -> easy
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.MEDIUM, 3.5)
    assert next_diff == QuestionDifficulty.EASY
    assert "adjusting to foundational easy tier" in rationale

    # easy -> easy (reaches floor)
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.EASY, 2.0)
    assert next_diff == QuestionDifficulty.EASY
    assert "maintaining easy tier" in rationale


def test_adaptive_difficulty_maintenance():
    """Verify difficulty is maintained when score is between 5.0 and 7.4."""
    next_diff, rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(QuestionDifficulty.MEDIUM, 6.5)
    assert next_diff == QuestionDifficulty.MEDIUM
    assert "maintaining current medium" in rationale


# ==============================================================================
# 2. Provider Interface & Unconfigured Fallback Tests
# ==============================================================================

@pytest.mark.anyio
async def test_mock_rule_engine_provider_generation_and_evaluation():
    """Verify MockRuleEngineProvider evaluates responses with explicit mock_rule_engine mode."""
    provider = MockRuleEngineProvider()
    assert provider.get_mode() == EvaluatorMode.MOCK_RULE_ENGINE

    # Question generation
    q = await provider.generate_question(
        topic="Computer Networking",
        instructions="Answer clearly",
        difficulty=QuestionDifficulty.MEDIUM,
        question_index=1,
        previous_questions=[],
    )
    assert "question_text" in q
    assert q["difficulty"] == QuestionDifficulty.MEDIUM

    # Evaluation with keyword match
    eval_res = await provider.evaluate_answer(
        question="Describe VLANs and 802.1Q trunking",
        answer="VLANs divide broadcast domains. An 802.1Q trunk tag enables frame tagging across switches.",
        difficulty=QuestionDifficulty.MEDIUM,
        topic="VLANs & Trunking",
    )
    assert eval_res["score"] >= 6.0
    assert len(eval_res["strengths"]) > 0
    assert "feedback" in eval_res


def test_unconfigured_ai_provider_raises_unavailable():
    """Verify unconfigured cloud AI provider explicitly raises AIProviderUnavailableError."""
    with patch.object(settings, "AI_PROVIDER", "gemini"):
        with patch.object(settings, "GEMINI_API_KEY", None):
            with pytest.raises(AIProviderUnavailableError, match="GEMINI_API_KEY is not configured"):
                get_ai_provider()


# ==============================================================================
# 3. Session Lifecycle & Ownership Tests
# ==============================================================================

def make_student(reg_no="241FA04001"):
    return UserInDB(
        id=f"user-{reg_no}",
        email=f"stu.{reg_no.lower()}@gmail.com",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


@pytest.mark.anyio
async def test_student_cannot_start_other_student_assignment():
    """Verify student A is forbidden from starting student B's assignment."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()
    mock_sessions = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
        "interview_sessions": mock_sessions,
    }[name]

    # Assignment belongs to 241FA04002
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-b",
        "interview_id": "int-1",
        "student_registration_number": "241FA04002",
        "status": "assigned",
    }

    student_a = make_student("241FA04001")

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.start_session(
            mock_db,
            assignment_id="assign-b",
            student_user=student_a,
        )
    assert exc.value.status_code == 403
    assert "Access denied" in exc.value.detail


@pytest.mark.anyio
async def test_duplicate_session_start_rejected():
    """Verify starting an assignment that already has an in-progress session raises 409 Conflict."""
    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()
    mock_sessions = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
        "interview_sessions": mock_sessions,
    }[name]

    student = make_student("241FA04001")
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-1",
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "status": "in_progress",
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "NetAcad Technical",
        "status": "scheduled",
        "duration_minutes": 45,
    }
    # An active session already exists!
    mock_sessions.find_one.return_value = {
        "session_id": "session-active-1",
        "session_status": "in_progress",
    }

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.start_session(
            mock_db,
            assignment_id="assign-1",
            student_user=student,
        )
    assert exc.value.status_code == 409
    assert "already in progress" in exc.value.detail


@pytest.mark.anyio
async def test_question_progression_and_scorecard_generation():
    """Verify question submission progresses through questions and generates a scorecard on completion."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.insert_one = AsyncMock()
    mock_scorecards = AsyncMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "interview_scorecards": mock_scorecards,
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
    }[name]

    student = make_student("241FA04001")
    session_id = "session-progress-1"

    # Step 1: Submitting question 1 (out of 2 for this test)
    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "assign-1",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "current_question_index": 1,
        "total_questions_target": 2,
        "current_difficulty": "medium",
        "expires_at": utc_now() + timedelta(minutes=30),
        "active_question": {
            "question_text": "What is the function of Layer 3 IP addressing?",
            "topic": "IP Addressing",
            "difficulty": "medium",
        },
    }
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "Networking Exam",
        "instructions": "Be thorough",
    }
    mock_responses.find.return_value.to_list = AsyncMock(return_value=[])

    # Submit answer to question 1
    res1 = await InterviewSessionService.submit_answer(
        mock_db,
        session_id=session_id,
        answer_text="IP addresses provide logical addressing for packets across router boundaries.",
        student_user=student,
    )
    assert res1.is_session_completed is False
    assert res1.next_question is not None
    assert res1.next_question.question_index == 2

    # Step 2: Submitting final question 2
    mock_sessions.find_one.return_value = {
        "session_id": session_id,
        "interview_id": "int-1",
        "assignment_id": "assign-1",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "current_question_index": 2,
        "total_questions_target": 2,
        "current_difficulty": "medium",
        "expires_at": utc_now() + timedelta(minutes=30),
        "active_question": {
            "question_text": "Describe the TCP three-way handshake.",
            "topic": "TCP Protocol",
            "difficulty": "medium",
        },
    }

    # Responses list returns 2 responses
    mock_responses.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[
        {"question_index": 1, "score": 8.0, "difficulty": "medium", "strengths": ["Clear terminology"], "improvements": []},
        {"question_index": 2, "score": 8.5, "difficulty": "medium", "strengths": ["Detailed"], "improvements": []},
    ])

    res2 = await InterviewSessionService.submit_answer(
        mock_db,
        session_id=session_id,
        answer_text="SYN, SYN-ACK, ACK establish the sequence numbers and initial window size.",
        student_user=student,
    )
    assert res2.is_session_completed is True
    assert res2.scorecard_id is not None
    assert mock_scorecards.insert_one.called
    assert mock_assignments.update_one.called


@pytest.mark.anyio
async def test_scorecard_cross_student_isolation():
    """Verify that student A cannot view student B's scorecard."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_scorecards = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_scorecards": mock_scorecards,
    }[name]

    mock_sessions.find_one.return_value = {
        "session_id": "session-b-1",
        "student_registration_number": "241FA04002",
        "session_status": "completed",
        "interview_id": "int-1",
    }

    student_a = make_student("241FA04001")

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.get_scorecard(
            mock_db,
            session_id="session-b-1",
            user=student_a,
        )
    assert exc.value.status_code == 403
    assert "Access denied" in exc.value.detail


@pytest.mark.anyio
async def test_invalid_answer_submission_empty_rejected():
    """Verify that submitting an empty or whitespace-only answer is rejected."""
    mock_db = MagicMock()
    student = make_student("241FA04001")

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.submit_answer(
            mock_db,
            session_id="session-1",
            answer_text="   \n   ",
            student_user=student,
        )
    assert exc.value.status_code == 422
    assert "cannot be blank" in exc.value.detail


@pytest.mark.anyio
async def test_answer_submission_rejected_for_expired_session():
    """Verify that attempting to submit an answer to an expired session updates status to timed_out and returns 400."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_db.__getitem__.side_effect = lambda name: {"interview_sessions": mock_sessions}[name]

    student = make_student("241FA04001")
    expired_time = utc_now() - timedelta(minutes=5)

    mock_sessions.find_one.return_value = {
        "session_id": "session-expired-1",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "expires_at": expired_time,
    }

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.submit_answer(
            mock_db,
            session_id="session-expired-1",
            answer_text="This is an answer submitted too late.",
            student_user=student,
        )
    assert exc.value.status_code == 400
    assert "duration has expired" in exc.value.detail
    assert mock_sessions.update_one.called


@pytest.mark.anyio
async def test_concurrent_duplicate_question_submission_raises_409():
    """Verify concurrent submission of the same question triggers DuplicateKeyError handling and returns 409."""
    mock_db = MagicMock()
    mock_sessions = AsyncMock()
    mock_responses = MagicMock()
    mock_responses.insert_one = AsyncMock(side_effect=pymongo.errors.DuplicateKeyError("E11000 duplicate key"))
    mock_interviews = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "interview_sessions": mock_sessions,
        "interview_responses": mock_responses,
        "university_interviews": mock_interviews,
    }[name]

    student = make_student("241FA04001")
    mock_sessions.find_one.return_value = {
        "session_id": "session-concurrent-1",
        "student_registration_number": "241FA04001",
        "session_status": "in_progress",
        "current_question_index": 1,
        "total_questions_target": 3,
        "expires_at": utc_now() + timedelta(minutes=30),
        "active_question": {"question_text": "Q1", "topic": "Networking", "difficulty": "medium"},
    }

    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.submit_answer(
            mock_db,
            session_id="session-concurrent-1",
            answer_text="Valid answer submitted concurrently.",
            student_user=student,
        )
    assert exc.value.status_code == 409
    assert "already been submitted" in exc.value.detail


@pytest.mark.anyio
async def test_get_session_by_assignment_retrieves_active_and_enforces_isolation():
    """Verify get_session_by_assignment returns active session and rejects cross-student access."""
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
    mock_assignments.find_one.return_value = {
        "assignment_id": "assign-1",
        "interview_id": "int-1",
        "student_registration_number": "241FA04001",
        "status": "in_progress",
    }
    mock_sessions.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[{
        "session_id": "session-1",
        "assignment_id": "assign-1",
        "session_status": "in_progress",
        "current_question_index": 2,
        "total_questions_target": 5,
        "current_difficulty": "medium",
        "active_question": {"question_text": "What is ARP?", "topic": "ARP", "difficulty": "medium"},
        "expires_at": utc_now() + timedelta(minutes=25),
    }])
    mock_interviews.find_one.return_value = {
        "interview_id": "int-1",
        "title": "Technical Interview",
    }

    # 1. Successful lookup
    res = await InterviewSessionService.get_session_by_assignment(
        mock_db,
        assignment_id="assign-1",
        student_user=student,
    )
    assert res["has_session"] is True
    assert res["session_id"] == "session-1"
    assert res["current_question_index"] == 2

    # 2. Cross-student isolation (student B attempting to access student A's assignment)
    student_b = make_student("241FA04002")
    with pytest.raises(HTTPException) as exc:
        await InterviewSessionService.get_session_by_assignment(
            mock_db,
            assignment_id="assign-1",
            student_user=student_b,
        )
    assert exc.value.status_code == 403
    assert "Access denied" in exc.value.detail


def test_unconfigured_fallback_disabled_raises():
    """Verify that when AI_PROVIDER is unset and ALLOW_MOCK_EVALUATOR_FALLBACK is False, an error is raised."""
    with patch.object(settings, "AI_PROVIDER", None):
        with patch.object(settings, "ALLOW_MOCK_EVALUATOR_FALLBACK", False):
            with pytest.raises(AIProviderUnavailableError, match="No AI provider is configured and ALLOW_MOCK_EVALUATOR_FALLBACK is disabled"):
                get_ai_provider()


