import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from app.core.config import settings
from app.models.interview_session import (
    SessionStatus,
    QuestionDifficulty,
    EvaluatorMode,
    InterviewSessionInDB,
    InterviewResponseInDB,
    InterviewScorecardInDB,
    SessionQuestionResponse,
    SubmitAnswerResponse,
    ScorecardResponse,
    ResponseSummary,
    utc_now,
)
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.user import UserInDB, UserRole
from app.services.ai_provider import (
    get_ai_provider,
    AdaptiveDifficultyPolicy,
    AIProviderUnavailableError,
    AIProviderError,
)

logger = logging.getLogger(__name__)

SESSIONS_COLLECTION = "interview_sessions"
RESPONSES_COLLECTION = "interview_responses"
SCORECARDS_COLLECTION = "interview_scorecards"
ASSIGNMENTS_COLLECTION = "student_interview_assignments"
INTERVIEWS_COLLECTION = "university_interviews"


def _ensure_utc(dt: Any) -> datetime:
    """Ensures datetime is timezone-aware UTC, safely normalizing offset-naive MongoDB datetimes."""
    if dt is None:
        return utc_now()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    return utc_now()


class InterviewSessionService:
    @staticmethod
    async def start_session(
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        student_user: UserInDB,
    ) -> SessionQuestionResponse:
        """
        Starts an assigned interview session:
        - Validates student ownership of assignment.
        - Enforces that no concurrent active attempt exists for the same assignment.
        - Generates initial question and records session.
        - Updates assignment lifecycle status to in_progress.
        """
        student_reg = student_user.registration_number
        if not student_reg or student_reg.strip().upper() in ["#N/A", "NA", "N/A", ""]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student account is not linked to a verified university registration number",
            )
        clean_reg = student_reg.strip().upper()

        # 1. Fetch and verify assignment
        assignment = await db[ASSIGNMENTS_COLLECTION].find_one({"assignment_id": assignment_id})
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview assignment '{assignment_id}' was not found",
            )

        # Cross-student isolation barrier
        if assignment.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to start another student's assignment",
            )

        if assignment.get("status") in [AssignmentStatus.COMPLETED.value, AssignmentStatus.CANCELLED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot start assignment with status '{assignment.get('status')}'. Assignment is already finalized.",
            )

        # 2. Fetch parent interview
        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": assignment["interview_id"]})
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Associated university interview definition was not found",
            )

        if interview.get("status") in [InterviewStatus.CANCELLED.value, InterviewStatus.COMPLETED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot start session: University interview is '{interview.get('status')}'.",
            )

        # 3. Prevent duplicate concurrent active attempts for the same assignment
        active_session = await db[SESSIONS_COLLECTION].find_one(
            {"assignment_id": assignment_id, "session_status": SessionStatus.IN_PROGRESS.value}
        )
        if active_session:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active interview session is already in progress for this assignment.",
            )

        # 4. Initialize session
        now = utc_now()
        duration_mins = interview.get("duration_minutes", 45)
        expires_at = now + timedelta(minutes=duration_mins + 5)  # 5 min grace period
        session_id = str(uuid.uuid4())
        total_questions = settings.INTERVIEW_TOTAL_QUESTIONS_DEFAULT

        # 5. Resolve AI Provider and generate initial question
        provider = get_ai_provider()
        initial_diff = QuestionDifficulty.MEDIUM

        try:
            gen_q = await provider.generate_question(
                topic=interview.get("title", "Networking Assessment"),
                instructions=interview.get("instructions", ""),
                difficulty=initial_diff,
                question_index=1,
                previous_questions=[],
            )
        except (AIProviderUnavailableError, AIProviderError) as exc:
            logger.error("AI provider failure during session start: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Interview AI evaluator is unavailable: {str(exc)}",
            )

        session_doc = {
            "session_id": session_id,
            "interview_id": assignment["interview_id"],
            "assignment_id": assignment_id,
            "student_registration_number": clean_reg,
            "student_user_id": str(student_user.id),
            "session_status": SessionStatus.IN_PROGRESS.value,
            "current_question_index": 1,
            "total_questions_target": total_questions,
            "current_difficulty": initial_diff.value,
            "started_at": now,
            "completed_at": None,
            "expires_at": expires_at,
            "final_scorecard_id": None,
            "created_at": now,
            "updated_at": now,
            # Cache active question in session state
            "active_question": {
                "question_text": gen_q["question_text"],
                "topic": gen_q["topic"],
                "difficulty": initial_diff.value,
            },
        }

        try:
            await db[SESSIONS_COLLECTION].insert_one(session_doc)
        except pymongo.errors.DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate active session conflict encountered.",
            )

        # 6. Update assignment status to in_progress
        await db[ASSIGNMENTS_COLLECTION].update_one(
            {"assignment_id": assignment_id},
            {
                "$set": {
                    "status": AssignmentStatus.IN_PROGRESS.value,
                    "started_at": now,
                    "updated_at": now,
                }
            },
        )

        time_remaining = max(0, int((expires_at - now).total_seconds()))

        return SessionQuestionResponse(
            session_id=session_id,
            assignment_id=assignment_id,
            interview_title=interview.get("title", "University Interview"),
            question_index=1,
            total_questions=total_questions,
            difficulty=initial_diff,
            question_text=gen_q["question_text"],
            topic=gen_q["topic"],
            time_remaining_seconds=time_remaining,
            evaluator_mode=provider.get_mode().value,
        )

    @staticmethod
    async def get_current_question(
        db: AsyncIOMotorDatabase,
        session_id: str,
        student_user: UserInDB,
    ) -> SessionQuestionResponse:
        """Retrieves the active question for an in-progress session with ownership verification."""
        clean_reg = (student_user.registration_number or "").strip().upper()
        session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )

        if session.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to access another student's session",
            )

        if session.get("session_status") != SessionStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session is already {session.get('session_status')}. No active question available.",
            )

        now = utc_now()
        expires_at = _ensure_utc(session.get("expires_at", now))
        if now > expires_at:
            await db[SESSIONS_COLLECTION].update_one(
                {"session_id": session_id},
                {"$set": {"session_status": SessionStatus.TIMED_OUT.value, "updated_at": now}},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Interview session has timed out. Duration limit exceeded.",
            )

        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": session["interview_id"]})
        interview_title = interview.get("title", "University Interview") if interview else "University Interview"

        active_q = session.get("active_question", {})
        time_remaining = max(0, int((expires_at - now).total_seconds()))
        provider = get_ai_provider()

        return SessionQuestionResponse(
            session_id=session_id,
            assignment_id=session["assignment_id"],
            interview_title=interview_title,
            question_index=session.get("current_question_index", 1),
            total_questions=session.get("total_questions_target", 5),
            difficulty=QuestionDifficulty(session.get("current_difficulty", "medium")),
            question_text=active_q.get("question_text", "Explain key networking concepts."),
            topic=active_q.get("topic", "Networking"),
            time_remaining_seconds=time_remaining,
            evaluator_mode=provider.get_mode().value,
        )

    @staticmethod
    async def submit_answer(
        db: AsyncIOMotorDatabase,
        session_id: str,
        answer_text: str,
        student_user: UserInDB,
    ) -> SubmitAnswerResponse:
        """
        Submits candidate answer, evaluates response, adjusts difficulty adaptively,
        and either advances to next question or generates final scorecard.
        """
        clean_reg = (student_user.registration_number or "").strip().upper()
        if not answer_text or not answer_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Answer text cannot be blank or whitespace only",
            )
        session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )

        if session.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You cannot submit answers to another student's session",
            )

        if session.get("session_status") != SessionStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot submit answer: Session is already {session.get('session_status')}.",
            )

        now = utc_now()
        expires_at = _ensure_utc(session.get("expires_at", now))
        if now > expires_at:
            await db[SESSIONS_COLLECTION].update_one(
                {"session_id": session_id},
                {"$set": {"session_status": SessionStatus.TIMED_OUT.value, "updated_at": now}},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot submit answer: Interview session duration has expired.",
            )

        active_q = session.get("active_question", {})
        curr_q_index = session.get("current_question_index", 1)
        curr_diff = QuestionDifficulty(session.get("current_difficulty", "medium"))
        topic = active_q.get("topic", "Networking")
        question_text = active_q.get("question_text", "")

        # Concurrency barrier: Check if this question was already submitted
        find_one_call = db[RESPONSES_COLLECTION].find_one(
            {"session_id": session_id, "question_index": curr_q_index}
        )
        existing_resp = await find_one_call if hasattr(find_one_call, "__await__") else find_one_call
        if isinstance(existing_resp, dict) and existing_resp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Question {curr_q_index} has already been submitted for this session.",
            )

        # 1. Evaluate answer using active provider
        provider = get_ai_provider()
        try:
            eval_result = await provider.evaluate_answer(
                question=question_text,
                answer=answer_text,
                difficulty=curr_diff,
                topic=topic,
            )
        except (AIProviderUnavailableError, AIProviderError) as exc:
            logger.error("AI provider failure during answer evaluation: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI evaluation service is temporarily unavailable: {str(exc)}",
            )

        score = eval_result["score"]

        # 2. Compute next difficulty adaptively
        next_diff, diff_rationale = AdaptiveDifficultyPolicy.determine_next_difficulty(
            current_difficulty=curr_diff,
            score=score,
        )

        response_id = str(uuid.uuid4())
        response_doc = {
            "response_id": response_id,
            "session_id": session_id,
            "question_index": curr_q_index,
            "question_text": question_text,
            "difficulty": curr_diff.value,
            "topic": topic,
            "answer_text": answer_text,
            "evaluation_score": score,
            "evaluation_feedback": eval_result["feedback"],
            "strengths": eval_result.get("strengths", []),
            "improvements": eval_result.get("improvements", []),
            "difficulty_adjustment_rationale": diff_rationale,
            "evaluator_mode": provider.get_mode().value,
            "evaluated_at": now,
            "created_at": now,
        }

        total_target = session.get("total_questions_target", 5)

        # 3. Check if session has reached final question
        if curr_q_index >= total_target:
            # Query prior responses
            cursor = db[RESPONSES_COLLECTION].find({"session_id": session_id})
            if hasattr(cursor, "sort") and callable(cursor.sort):
                cursor = cursor.sort("question_index", pymongo.ASCENDING)
            if hasattr(cursor, "to_list"):
                res = cursor.to_list(length=100)
                prior_responses = await res if hasattr(res, "__await__") else res
            elif hasattr(cursor, "__await__"):
                prior_responses = await cursor
            else:
                prior_responses = cursor

            if not isinstance(prior_responses, list):
                prior_responses = []

            # Include current response in summary input
            current_summary_item = {
                "question_index": curr_q_index,
                "question_text": question_text,
                "difficulty": curr_diff.value,
                "topic": topic,
                "score": score,
                "evaluation_score": score,
                "feedback": eval_result["feedback"],
                "evaluation_feedback": eval_result["feedback"],
                "strengths": eval_result.get("strengths", []),
                "improvements": eval_result.get("improvements", []),
            }
            all_responses = prior_responses + [current_summary_item]

            try:
                scorecard_summary = await provider.generate_scorecard_summary(
                    responses=all_responses,
                    interview_title=topic,
                )
            except (AIProviderUnavailableError, AIProviderError) as exc:
                logger.error("AI provider failure during scorecard generation: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Scorecard generation service is temporarily unavailable: {str(exc)}",
                )

            scorecard_id = str(uuid.uuid4())
            difficulty_progression = [r.get("difficulty", "medium") for r in all_responses if isinstance(r, dict)]

            if provider.get_mode() == EvaluatorMode.MOCK_RULE_ENGINE:
                disclaimer_text = (
                    "MOCK EVALUATION NOTICE: Questions and evaluations were generated by a local deterministic "
                    "rule engine (mock rubric mode) without external cloud AI models. Evaluations reflect "
                    "keyword heuristics and rule rubrics, and do not claim objective or bias-free scoring."
                )
            elif provider.get_mode() == EvaluatorMode.GEMINI:
                disclaimer_text = (
                    "AI EVALUATION NOTICE: Questions and evaluations were generated using Google Gemini "
                    "cloud AI models. Evaluations reflect automated language model rubrics based on candidate responses, "
                    "and do not claim objective or bias-free scoring."
                )
            else:
                disclaimer_text = (
                    "AI EVALUATION NOTICE: Evaluations reflect automated algorithmic rubrics based "
                    "on candidate responses, and do not claim objective or bias-free scoring."
                )

            scorecard_doc = {
                "scorecard_id": scorecard_id,
                "session_id": session_id,
                "interview_id": session.get("interview_id", ""),
                "student_registration_number": clean_reg,
                "overall_score": scorecard_summary["overall_score"],
                "percentage_score": scorecard_summary["percentage_score"],
                "performance_level": scorecard_summary["performance_level"],
                "summary_feedback": scorecard_summary["summary_feedback"],
                "difficulty_progression": difficulty_progression,
                "strengths_summary": scorecard_summary.get("strengths", []),
                "areas_for_growth": scorecard_summary.get("areas_for_growth", []),
                "evaluator_mode": provider.get_mode().value,
                "disclaimer": disclaimer_text,
                "created_at": now,
            }

            # Persist response and scorecard atomically
            try:
                await db[RESPONSES_COLLECTION].insert_one(response_doc)
            except pymongo.errors.DuplicateKeyError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Question {curr_q_index} has already been submitted for this session.",
                )

            await db[SCORECARDS_COLLECTION].insert_one(scorecard_doc)

            # Mark session completed
            await db[SESSIONS_COLLECTION].update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "session_status": SessionStatus.COMPLETED.value,
                        "completed_at": now,
                        "final_scorecard_id": scorecard_id,
                        "updated_at": now,
                    }
                },
            )

            # Mark assignment completed
            await db[ASSIGNMENTS_COLLECTION].update_one(
                {"assignment_id": session["assignment_id"]},
                {
                    "$set": {
                        "status": AssignmentStatus.COMPLETED.value,
                        "completed_at": now,
                        "updated_at": now,
                    }
                },
            )

            return SubmitAnswerResponse(
                session_id=session_id,
                question_index=curr_q_index,
                evaluated_score=score,
                feedback=eval_result["feedback"],
                strengths=eval_result.get("strengths", []),
                improvements=eval_result.get("improvements", []),
                next_difficulty=next_diff,
                difficulty_rationale=diff_rationale,
                is_session_completed=True,
                next_question=None,
                scorecard_id=scorecard_id,
                evaluator_mode=provider.get_mode().value,
            )

        # 4. Advance to next question
        next_q_index = curr_q_index + 1
        int_id = session.get("interview_id")
        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": int_id}) if int_id else None
        interview_title = interview.get("title", "Networking Assessment") if interview else "Networking Assessment"

        # Collect previous questions to avoid repetition
        cursor = db[RESPONSES_COLLECTION].find({"session_id": session_id}, {"question_text": 1})
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(length=100)
            prev_docs = await res if hasattr(res, "__await__") else res
        elif hasattr(cursor, "__await__"):
            prev_docs = await cursor
        else:
            prev_docs = cursor
        if not isinstance(prev_docs, list):
            prev_docs = []
        prev_questions = [p.get("question_text", "") for p in prev_docs if isinstance(p, dict)]

        try:
            next_q_gen = await provider.generate_question(
                topic=interview_title,
                instructions=interview.get("instructions", "") if interview else "",
                difficulty=next_diff,
                question_index=next_q_index,
                previous_questions=prev_questions + [question_text],
            )
        except (AIProviderUnavailableError, AIProviderError) as exc:
            logger.error("AI provider failure generating next question: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Question generation service is temporarily unavailable: {str(exc)}",
            )

        # Persist response and advance session state
        try:
            await db[RESPONSES_COLLECTION].insert_one(response_doc)
        except pymongo.errors.DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Question {curr_q_index} has already been submitted for this session.",
            )

        await db[SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "current_question_index": next_q_index,
                    "current_difficulty": next_diff.value,
                    "active_question": {
                        "question_text": next_q_gen["question_text"],
                        "topic": next_q_gen["topic"],
                        "difficulty": next_diff.value,
                    },
                    "updated_at": now,
                }
            },
        )

        time_remaining = max(0, int((expires_at - now).total_seconds()))

        next_question_resp = SessionQuestionResponse(
            session_id=session_id,
            assignment_id=session["assignment_id"],
            interview_title=interview_title,
            question_index=next_q_index,
            total_questions=total_target,
            difficulty=next_diff,
            question_text=next_q_gen["question_text"],
            topic=next_q_gen["topic"],
            time_remaining_seconds=time_remaining,
            evaluator_mode=provider.get_mode().value,
        )

        return SubmitAnswerResponse(
            session_id=session_id,
            question_index=curr_q_index,
            evaluated_score=score,
            feedback=eval_result["feedback"],
            strengths=eval_result.get("strengths", []),
            improvements=eval_result.get("improvements", []),
            next_difficulty=next_diff,
            difficulty_rationale=diff_rationale,
            is_session_completed=False,
            next_question=next_question_resp,
            scorecard_id=None,
            evaluator_mode=provider.get_mode().value,
        )

    @staticmethod
    async def get_scorecard(
        db: AsyncIOMotorDatabase,
        session_id: str,
        user: UserInDB,
    ) -> ScorecardResponse:
        """Retrieves completed session scorecard with role-based access control and isolation."""
        session = await db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )

        # Authorization check
        if user.role == UserRole.STUDENT:
            clean_reg = (user.registration_number or "").strip().upper()
            if session.get("student_registration_number") != clean_reg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You are not authorized to view another student's scorecard",
                )
        elif user.role not in [UserRole.PLATFORM_ADMIN, UserRole.UNIVERSITY_ADMIN, UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to access interview scorecard",
            )

        scorecard = await db[SCORECARDS_COLLECTION].find_one({"session_id": session_id}, {"_id": 0})
        if not scorecard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scorecard for this interview session is not yet generated or session is incomplete",
            )

        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": session["interview_id"]})
        interview_title = interview.get("title") if interview else None

        # Fetch responses
        cursor = db[RESPONSES_COLLECTION].find({"session_id": session_id}, {"_id": 0})
        if hasattr(cursor, "sort") and callable(cursor.sort):
            cursor = cursor.sort("question_index", pymongo.ASCENDING)
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(length=100)
            raw_responses = await res if hasattr(res, "__await__") else res
        elif hasattr(cursor, "__await__"):
            raw_responses = await cursor
        else:
            raw_responses = cursor
        if not isinstance(raw_responses, list):
            raw_responses = []

        response_summaries = [
            ResponseSummary(
                question_index=r["question_index"],
                question_text=r["question_text"],
                difficulty=QuestionDifficulty(r["difficulty"]),
                answer_text=r["answer_text"],
                evaluation_score=r["evaluation_score"],
                feedback=r["evaluation_feedback"],
                strengths=r.get("strengths", []),
                improvements=r.get("improvements", []),
                difficulty_adjustment_rationale=r.get("difficulty_adjustment_rationale", ""),
            )
            for r in raw_responses
        ]

        return ScorecardResponse(
            scorecard_id=scorecard["scorecard_id"],
            session_id=session_id,
            interview_id=scorecard["interview_id"],
            interview_title=interview_title,
            student_registration_number=scorecard["student_registration_number"],
            overall_score=scorecard["overall_score"],
            percentage_score=scorecard["percentage_score"],
            performance_level=scorecard["performance_level"],
            summary_feedback=scorecard["summary_feedback"],
            difficulty_progression=scorecard.get("difficulty_progression", []),
            strengths_summary=scorecard.get("strengths_summary", []),
            areas_for_growth=scorecard.get("areas_for_growth", []),
            evaluator_mode=scorecard.get("evaluator_mode", "mock_rule_engine"),
            disclaimer=scorecard.get("disclaimer", ""),
            completed_at=session.get("completed_at", session.get("updated_at", utc_now())),
            responses=response_summaries,
        )

    @staticmethod
    async def get_session_by_assignment(
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        student_user: UserInDB,
    ) -> Dict[str, Any]:
        """
        Retrieves active or completed session associated with a student assignment.
        Used to resume active sessions, review scorecards, and avoid duplicate start attempts.
        """
        clean_reg = (student_user.registration_number or "").strip().upper()
        if not clean_reg and student_user.role == UserRole.STUDENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student account does not have a verified registration number linked.",
            )

        assignment = await db[ASSIGNMENTS_COLLECTION].find_one({"assignment_id": assignment_id})
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assignment '{assignment_id}' not found",
            )

        if student_user.role == UserRole.STUDENT and assignment.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You cannot access another student's assignment session",
            )

        # Find latest session for this assignment
        cursor = db[SESSIONS_COLLECTION].find({"assignment_id": assignment_id})
        if hasattr(cursor, "sort") and callable(cursor.sort):
            cursor = cursor.sort("created_at", pymongo.DESCENDING)
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(length=5)
            sessions_list = await res if hasattr(res, "__await__") else res
        elif hasattr(cursor, "__await__"):
            sessions_list = await cursor
        else:
            sessions_list = cursor

        if not sessions_list or not isinstance(sessions_list, list):
            return {
                "has_session": False,
                "assignment_id": assignment_id,
                "assignment_status": assignment.get("status"),
            }

        session = sessions_list[0]
        now = utc_now()
        expires_at = _ensure_utc(session.get("expires_at", now))
        if session.get("session_status") == SessionStatus.IN_PROGRESS.value and now > expires_at:
            await db[SESSIONS_COLLECTION].update_one(
                {"session_id": session["session_id"]},
                {"$set": {"session_status": SessionStatus.TIMED_OUT.value, "updated_at": now}},
            )
            session["session_status"] = SessionStatus.TIMED_OUT.value

        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": assignment["interview_id"]})
        interview_title = interview.get("title", "University Interview") if interview else "University Interview"

        provider = get_ai_provider()
        time_remaining = max(0, int((expires_at - now).total_seconds()))

        return {
            "has_session": True,
            "session_id": session["session_id"],
            "assignment_id": assignment_id,
            "interview_title": interview_title,
            "session_status": session["session_status"],
            "current_question_index": session.get("current_question_index", 1),
            "total_questions_target": session.get("total_questions_target", 5),
            "current_difficulty": session.get("current_difficulty", "medium"),
            "active_question": session.get("active_question"),
            "expires_at": session.get("expires_at").isoformat() if session.get("expires_at") else None,
            "time_remaining_seconds": time_remaining,
            "scorecard_id": session.get("scorecard_id") or session.get("final_scorecard_id"),
            "evaluator_mode": provider.get_mode().value,
        }

