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
    TopicPerformanceItem,
    ActionablePriorityItem,
    VideoRecommendationItem,
    StudentPerformanceReportResponse,
    utc_now,
)
from app.services.learning_resources import match_video_recommendations
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.user import UserInDB, UserRole
from app.services.ai_provider import (
    get_ai_provider,
    AdaptiveDifficultyPolicy,
    AIProviderUnavailableError,
    AIProviderError,
)
from app.models.code_execution import (
    SupportedLanguage,
    ExecutionStatus,
    RunCodeResponse,
    normalize_language_name,
)
from app.services.coding_challenge_service import CodingChallengeService
from app.services.code_execution_service import (
    CodeExecutionService,
    ExecutionServiceUnavailableError,
)

logger = logging.getLogger(__name__)

SESSIONS_COLLECTION = "interview_sessions"
RESPONSES_COLLECTION = "interview_responses"
SCORECARDS_COLLECTION = "interview_scorecards"
ASSIGNMENTS_COLLECTION = "student_interview_assignments"
INTERVIEWS_COLLECTION = "university_interviews"
QUESTIONS_COLLECTION = "interview_questions"


def _ensure_utc(dt: Any) -> datetime:
    """
    Ensures datetime is timezone-aware UTC, safely normalizing:
    - Offset-naive datetime (safely assumes UTC from MongoDB storage)
    - Timezone-aware datetime (converted to UTC)
    - ISO format strings (with or without Z / offset)
    - Integer/float unix timestamps (seconds or milliseconds)
    """
    if dt is None:
        return utc_now()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(dt, (int, float)):
        try:
            val = float(dt)
            ts = val / 1000.0 if val > 1e11 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return utc_now()
    if isinstance(dt, str):
        clean_str = dt.strip()
        if not clean_str:
            return utc_now()
        # Handle numeric string timestamp
        try:
            val = float(clean_str)
            ts = val / 1000.0 if val > 1e11 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except ValueError:
            pass
        # Handle ISO formatted string
        try:
            iso_str = clean_str.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(iso_str)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            logger.warning("Failed to parse datetime string '%s', falling back to utc_now", dt)
            return utc_now()
    return utc_now()


COMMON_TECH_ACRONYMS: Dict[str, str] = {
    "SQL": "SQL",
    "OS": "OS",
    "OOP": "OOP",
    "DBMS": "DBMS",
    "TCP/IP": "TCP/IP",
    "TCP": "TCP",
    "IP": "IP",
    "UDP": "UDP",
    "DSA": "DSA",
    "API": "API",
    "REST": "REST",
    "QA": "QA",
    "CPU": "CPU",
    "HTML": "HTML",
    "CSS": "CSS",
    "AI": "AI",
    "ML": "ML",
    "CI/CD": "CI/CD",
}


def _format_topic_name(raw_topic: Optional[str]) -> str:
    """
    Normalizes topic names preserving common industry acronyms (e.g. SQL, OS, OOP, DBMS, TCP/IP, DSA, API, REST, QA).
    Avoids indiscriminate .title() mutations that transform 'SQL' into 'Sql'.
    """
    cleaned = (raw_topic or "Technical Assessment").strip()
    if not cleaned:
        return "Technical Assessment"

    upper_cleaned = cleaned.upper()
    if upper_cleaned in COMMON_TECH_ACRONYMS:
        return COMMON_TECH_ACRONYMS[upper_cleaned]

    # Process multi-word topics word-by-word
    words = cleaned.split()
    formatted_words: List[str] = []
    for w in words:
        clean_w = w.strip()
        upper_w = clean_w.upper()
        if upper_w in COMMON_TECH_ACRONYMS:
            formatted_words.append(COMMON_TECH_ACRONYMS[upper_w])
        elif clean_w.isupper() and len(clean_w) <= 4:
            formatted_words.append(clean_w)
        elif clean_w.islower():
            formatted_words.append(clean_w.capitalize())
        else:
            formatted_words.append(clean_w)

    return " ".join(formatted_words)


class InterviewSessionService:
    @staticmethod
    def _resolve_interview_role(assignment: Optional[Dict[str, Any]], interview: Optional[Dict[str, Any]]) -> Optional[str]:
        """Resolves target role for strict role-based question bank isolation."""
        canon_map = {
            "associate software engineer": "Associate Software Engineer",
            "software development engineer": "Software Development Engineer",
            "product engineer": "Product Engineer",
            "system engineer": "System Engineer",
            "testing engineer": "Testing Engineer",
        }
        role = (assignment or {}).get("selected_role") or (interview or {}).get("role") or (interview or {}).get("target_role")
        if role and isinstance(role, str):
            clean_role = role.strip().lower()
            if clean_role in canon_map:
                return canon_map[clean_role]
            return role.strip()
        title = (interview or {}).get("title", "")
        for canon_clean, canon in canon_map.items():
            if canon_clean in title.lower():
                return canon
        return None

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
        now = utc_now()
        if active_session:
            has_raw_exp = active_session.get("expires_at") is not None
            if has_raw_exp:
                active_exp = _ensure_utc(active_session.get("expires_at"))
                if now > active_exp:
                    # Active session has genuinely expired - mark timed out and allow fresh session creation
                    await db[SESSIONS_COLLECTION].update_one(
                        {"session_id": active_session["session_id"]},
                        {"$set": {"session_status": SessionStatus.TIMED_OUT.value, "updated_at": now}},
                    )
                    active_session = None
            if active_session:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An active interview session is already in progress for this assignment.",
                )

        # 4. Initialize session
        raw_duration = interview.get("duration_minutes") or 45
        try:
            duration_mins = int(raw_duration)
            if duration_mins <= 0:
                duration_mins = 45
        except (ValueError, TypeError):
            duration_mins = 45

        expires_at = now + timedelta(minutes=duration_mins + 5)  # 5 min grace period
        session_id = str(uuid.uuid4())
        total_questions = settings.INTERVIEW_TOTAL_QUESTIONS_DEFAULT

        # 5. Resolve Question: Check stored question bank first, fallback to AI provider
        provider = get_ai_provider()
        initial_diff = QuestionDifficulty.MEDIUM

        target_role = InterviewSessionService._resolve_interview_role(assignment, interview)

        interview_or = [{"interview_id": assignment["interview_id"]}, {"interview_id": None}]
        diff_or = [{"difficulty": initial_diff.value}, {"difficulty": None}, {"difficulty": {"$exists": False}}]

        stored_q = None
        try:
            # 1. Prefer target role, conceptual, matching difficulty
            q1_filter: Dict[str, Any] = {
                "$and": [
                    {"$or": interview_or},
                    {"$or": diff_or},
                ],
                "question_type": "conceptual",
            }
            if target_role:
                q1_filter["role"] = target_role
            stored_q = await db[QUESTIONS_COLLECTION].find_one(q1_filter)

            # 2. Prefer target role, conceptual (any difficulty in bank)
            if not stored_q:
                q2_filter = {
                    "$or": interview_or,
                    "question_type": "conceptual",
                }
                if target_role:
                    q2_filter["role"] = target_role
                stored_q = await db[QUESTIONS_COLLECTION].find_one(q2_filter)

            # 3. Target role (any question type / any difficulty)
            if not stored_q:
                q3_filter = {"$or": interview_or}
                if target_role:
                    q3_filter["role"] = target_role
                stored_q = await db[QUESTIONS_COLLECTION].find_one(q3_filter)
        except Exception as e:
            logger.warning("Error checking stored questions: %s", e)

        if stored_q and stored_q.get("question_text"):
            gen_q = {
                "question_text": stored_q["question_text"],
                "topic": stored_q.get("topic", interview.get("title", "Technical Assessment")),
                "question_type": stored_q.get("question_type", "conceptual"),
                "expected_answer": stored_q.get("expected_answer"),
                "keywords": stored_q.get("keywords") or [],
            }
        else:
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

        coding_spec = None
        if gen_q.get("question_type") == "coding":
            coding_spec = CodingChallengeService.get_candidate_challenge_spec(gen_q["question_text"])

        session_doc = {
            "session_id": session_id,
            "interview_id": assignment["interview_id"],
            "assignment_id": assignment_id,
            "selected_role": target_role,
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
            # Cache active question in session state (internal expected_answer retained for rubric grounding)
            "active_question": {
                "question_text": gen_q["question_text"],
                "topic": gen_q["topic"],
                "difficulty": initial_diff.value,
                "question_type": gen_q.get("question_type", "conceptual"),
                "coding_spec": coding_spec,
                "expected_answer": gen_q.get("expected_answer"),
                "keywords": gen_q.get("keywords") or [],
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
            question_type=gen_q.get("question_type", "conceptual"),
            coding_spec=coding_spec,
            time_remaining_seconds=time_remaining,
            evaluator_mode=provider.get_mode().value,
            expires_at=expires_at,
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
            asgn_id = session.get("assignment_id")
            if asgn_id:
                try:
                    await db[ASSIGNMENTS_COLLECTION].update_one(
                        {"assignment_id": asgn_id},
                        {"$set": {"status": AssignmentStatus.COMPLETED.value, "completed_at": now, "updated_at": now}},
                    )
                except KeyError:
                    pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Interview session has timed out. Duration limit exceeded.",
            )

        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": session["interview_id"]})
        interview_title = interview.get("title", "University Interview") if interview else "University Interview"

        active_q = session.get("active_question", {})
        coding_spec = active_q.get("coding_spec")
        if active_q.get("question_type") == "coding" and not coding_spec:
            coding_spec = CodingChallengeService.get_candidate_challenge_spec(active_q.get("question_text", ""))

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
            question_type=active_q.get("question_type", "conceptual"),
            coding_spec=coding_spec,
            time_remaining_seconds=time_remaining,
            evaluator_mode=provider.get_mode().value,
            expires_at=expires_at,
        )

    @staticmethod
    async def run_code(
        db: AsyncIOMotorDatabase,
        session_id: str,
        student_user: UserInDB,
        language: str,
        source_code: str,
        custom_input: Optional[str] = None,
    ) -> RunCodeResponse:
        """
        Executes code within isolated sandbox against custom input or sample visible test cases.
        Hidden test cases are NEVER exposed.
        """
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
                detail="Access denied: You cannot run code in another student's session",
            )

        if session.get("session_status") != SessionStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot run code: Session is already {session.get('session_status')}.",
            )

        now = utc_now()
        expires_at = _ensure_utc(session.get("expires_at", now))
        if now > expires_at:
            await db[SESSIONS_COLLECTION].update_one(
                {"session_id": session_id},
                {"$set": {"session_status": SessionStatus.TIMED_OUT.value, "updated_at": now}},
            )
            asgn_id = session.get("assignment_id")
            if asgn_id:
                try:
                    await db[ASSIGNMENTS_COLLECTION].update_one(
                        {"assignment_id": asgn_id},
                        {"$set": {"status": AssignmentStatus.COMPLETED.value, "completed_at": now, "updated_at": now}},
                    )
                except KeyError:
                    pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Interview session duration has expired.",
            )

        active_q = session.get("active_question", {})
        if active_q.get("question_type") != "coding":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active question is not a coding question.",
            )

        challenge = CodingChallengeService.resolve_challenge(active_q.get("question_text", ""))
        sample_cases = challenge.get("sample_cases", [])

        try:
            return await CodeExecutionService.run_single_or_custom(
                session_id=session_id,
                language_str=language,
                source_code=source_code,
                custom_input=custom_input,
                sample_test_cases=sample_cases,
            )
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(err),
            )
        except ExecutionServiceUnavailableError as exc:
            logger.error("Execution service error during run_code: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )

    @staticmethod
    async def submit_answer(
        db: AsyncIOMotorDatabase,
        session_id: str,
        answer_text: str,
        student_user: UserInDB,
        language: Optional[str] = None,
        source_code: Optional[str] = None,
    ) -> SubmitAnswerResponse:
        """
        Submits candidate answer or coding solution, evaluates response, adjusts difficulty adaptively,
        and either advances to next question or generates final scorecard.
        """
        clean_reg = (student_user.registration_number or "").strip().upper()
        if not (answer_text and answer_text.strip()) and not (source_code and source_code.strip()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Answer text or code cannot be blank or whitespace only",
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
            asgn_id = session.get("assignment_id")
            if asgn_id:
                try:
                    await db[ASSIGNMENTS_COLLECTION].update_one(
                        {"assignment_id": asgn_id},
                        {"$set": {"status": AssignmentStatus.COMPLETED.value, "completed_at": now, "updated_at": now}},
                    )
                except KeyError:
                    pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot submit answer: Interview session duration has expired.",
            )

        active_q = session.get("active_question", {})
        curr_q_index = session.get("current_question_index", 1)
        curr_diff = QuestionDifficulty(session.get("current_difficulty", "medium"))
        topic = active_q.get("topic", "Networking")
        question_text = active_q.get("question_text", "")
        is_coding = active_q.get("question_type") == "coding"
        code_to_eval = source_code or answer_text
        code_execution_summary = None

        # Concurrency barrier: Check if this question was already answered or skipped
        find_one_call = db[RESPONSES_COLLECTION].find_one(
            {"session_id": session_id, "question_index": curr_q_index}
        )
        existing_resp = await find_one_call if hasattr(find_one_call, "__await__") else find_one_call
        if isinstance(existing_resp, dict) and existing_resp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Question {curr_q_index} has already been submitted or skipped for this session.",
            )

        # 1. Evaluate answer
        provider = get_ai_provider()
        if is_coding:
            try:
                lang = normalize_language_name(language or "python")
            except ValueError as err:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))

            eval_cases = CodingChallengeService.get_all_evaluation_cases(question_text)
            try:
                exec_status, passed_cnt, total_cnt, masked_results, compile_err = await CodeExecutionService.evaluate_full_test_suite(
                    language=lang,
                    source_code=code_to_eval,
                    test_cases=eval_cases,
                )
            except ExecutionServiceUnavailableError as exc:
                logger.error("Execution sandbox unavailable during solution submit: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Code execution sandbox is unavailable: {str(exc)}",
                )

            pass_rate = (passed_cnt / total_cnt) if total_cnt > 0 else 0.0
            score = round(pass_rate * 10.0, 1)

            if exec_status == ExecutionStatus.COMPILATION_ERROR:
                feedback = f"Compilation failed: {compile_err or 'Syntax or build error'}. 0 of {total_cnt} test cases passed."
                strengths = []
                improvements = ["Fix compiler/syntax errors before resubmitting.", "Verify class declarations and imports."]
            elif exec_status == ExecutionStatus.SUCCESS and passed_cnt == total_cnt:
                feedback = f"All {total_cnt} evaluation test cases passed successfully! Algorithmic logic and constraints satisfied."
                strengths = [f"Language: {lang.value.title()}", "Passed all boundary and edge test scenarios."]
                improvements = ["Consider further optimizing space complexity if applicable."]
            else:
                feedback = f"{passed_cnt} of {total_cnt} evaluation test cases passed ({round(pass_rate * 100)}%). Partial solution."
                strengths = [f"Language: {lang.value.title()}", f"Successfully resolved {passed_cnt} test scenarios."]
                improvements = [f"{total_cnt - passed_cnt} test cases failed due to edge cases or incorrect output format."]

            eval_result = {
                "score": score,
                "feedback": feedback,
                "strengths": strengths,
                "improvements": improvements,
            }
            code_execution_summary = {
                "language": lang.value,
                "status": exec_status.value,
                "tests_passed": passed_cnt,
                "tests_total": total_cnt,
                "passed_test_cases": passed_cnt,
                "total_test_cases": total_cnt,
                "pass_percentage": round(pass_rate * 100.0, 1),
                "pass_rate_percent": round(pass_rate * 100.0, 1),
                "results": [r.model_dump() for r in masked_results],
                "test_case_results": [r.model_dump() for r in masked_results],
            }
            evaluator_mode_str = "sandboxed_compiler"
        else:
            try:
                eval_result = await provider.evaluate_answer(
                    question=question_text,
                    answer=answer_text,
                    difficulty=curr_diff,
                    topic=topic,
                    expected_answer=active_q.get("expected_answer"),
                    keywords=active_q.get("keywords") or [],
                )
            except (AIProviderUnavailableError, AIProviderError) as exc:
                logger.error("AI provider failure during answer evaluation: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"AI evaluation service is temporarily unavailable: {str(exc)}",
                )
            score = eval_result["score"]
            evaluator_mode_str = provider.get_mode().value

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
            "question_type": "coding" if is_coding else "conceptual",
            "language": language if is_coding else None,
            "source_code": source_code if is_coding else None,
            "code_execution_summary": code_execution_summary,
            "evaluation_score": score,
            "evaluation_feedback": eval_result["feedback"],
            "strengths": eval_result.get("strengths", []),
            "improvements": eval_result.get("improvements", []),
            "difficulty_adjustment_rationale": diff_rationale,
            "evaluator_mode": evaluator_mode_str,
            "status": "answered",
            "is_skipped": False,
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
                "status": "answered",
                "is_skipped": False,
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

            answered_cnt = len([r for r in all_responses if isinstance(r, dict) and not r.get("is_skipped") and r.get("status") != "skipped"])
            skipped_cnt = len([r for r in all_responses if isinstance(r, dict) and (r.get("is_skipped") or r.get("status") == "skipped")])

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
            elif provider.get_mode() == EvaluatorMode.NEMOTRON:
                disclaimer_text = (
                    "AI EVALUATION NOTICE: Questions and evaluations were generated using NVIDIA Nemotron "
                    "cloud AI models. Evaluations reflect automated language model rubrics based on candidate responses, "
                    "and do not claim objective or bias-free scoring."
                )
            else:
                disclaimer_text = (
                    "AI EVALUATION NOTICE: Evaluations reflect automated algorithmic rubrics based "
                    "on candidate responses, and do not claim objective or bias-free scoring."
                )

            if skipped_cnt > 0:
                disclaimer_text += f" Score is calculated across {answered_cnt} evaluated question(s). {skipped_cnt} of {total_target} assigned questions were skipped."

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
                "total_questions_assigned": total_target,
                "questions_answered": answered_cnt,
                "questions_skipped": skipped_cnt,
                "questions_evaluated": answered_cnt,
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
                evaluator_mode=evaluator_mode_str,
                code_execution_summary=code_execution_summary,
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

        all_asked = prev_questions + [question_text]

        # Check stored question bank first for the next question with strict role isolation
        target_role = session.get("selected_role") or InterviewSessionService._resolve_interview_role({}, interview)
        interview_or = [{"interview_id": int_id}, {"interview_id": None}]
        target_type = "coding" if next_q_index >= total_target else "conceptual"
        diff_or = [{"difficulty": next_diff.value}, {"difficulty": None}, {"difficulty": {"$exists": False}}]

        stored_next_q = None
        try:
            # 1. Matching role, target_type, unasked, matching difficulty
            query_tier1 = {
                "$and": [
                    {"$or": interview_or},
                    {"$or": diff_or},
                ],
                "question_text": {"$nin": all_asked},
                "question_type": target_type,
            }
            if target_role:
                query_tier1["role"] = target_role
            stored_next_q = await db[QUESTIONS_COLLECTION].find_one(query_tier1)

            # 2. Matching role, target_type, unasked (any difficulty in bank)
            if not stored_next_q:
                query_tier2 = {
                    "$or": interview_or,
                    "question_text": {"$nin": all_asked},
                    "question_type": target_type,
                }
                if target_role:
                    query_tier2["role"] = target_role
                stored_next_q = await db[QUESTIONS_COLLECTION].find_one(query_tier2)

            # 3. Matching role, unasked (any type, any difficulty)
            if not stored_next_q:
                query_tier3 = {
                    "$or": interview_or,
                    "question_text": {"$nin": all_asked},
                }
                if target_role:
                    query_tier3["role"] = target_role
                stored_next_q = await db[QUESTIONS_COLLECTION].find_one(query_tier3)
        except Exception as e:
            logger.warning("Error querying stored question bank for progression: %s", e)

        if stored_next_q and stored_next_q.get("question_text"):
            next_q_gen = {
                "question_text": stored_next_q["question_text"],
                "topic": stored_next_q.get("topic", interview_title),
                "question_type": stored_next_q.get("question_type", target_type),
                "expected_answer": stored_next_q.get("expected_answer"),
                "keywords": stored_next_q.get("keywords") or [],
            }
        else:
            try:
                next_q_gen = await provider.generate_question(
                    topic=interview_title,
                    instructions=interview.get("instructions", "") if interview else "",
                    difficulty=next_diff,
                    question_index=next_q_index,
                    previous_questions=all_asked,
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

        coding_spec_next = None
        if next_q_gen.get("question_type") == "coding":
            coding_spec_next = CodingChallengeService.get_candidate_challenge_spec(next_q_gen["question_text"])

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
                        "question_type": next_q_gen.get("question_type", target_type),
                        "coding_spec": coding_spec_next,
                        "expected_answer": next_q_gen.get("expected_answer"),
                        "keywords": next_q_gen.get("keywords") or [],
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
            question_type=next_q_gen.get("question_type", target_type),
            coding_spec=coding_spec_next,
            time_remaining_seconds=time_remaining,
            evaluator_mode=evaluator_mode_str,
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
            is_skipped=False,
            next_question=next_question_resp,
            scorecard_id=None,
            evaluator_mode=evaluator_mode_str,
            code_execution_summary=code_execution_summary,
        )

    @staticmethod
    async def skip_question(
        db: AsyncIOMotorDatabase,
        session_id: str,
        student_user: UserInDB,
    ) -> SubmitAnswerResponse:
        """
        Skips the active question without assigning an answer score.
        Advances session state to the next question or completes the interview if on the final question.
        Ensures idempotent completion and strict ownership validation.
        """
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
                detail="Access denied: You cannot skip questions in another student's session",
            )

        if session.get("session_status") != SessionStatus.IN_PROGRESS.value:
            if session.get("session_status") == SessionStatus.COMPLETED.value:
                existing_sc_call = db[SCORECARDS_COLLECTION].find_one({"session_id": session_id})
                existing_scorecard = await existing_sc_call if hasattr(existing_sc_call, "__await__") else existing_sc_call
                return SubmitAnswerResponse(
                    session_id=session_id,
                    question_index=session.get("current_question_index", 1),
                    evaluated_score=None,
                    feedback="Interview session is already completed.",
                    strengths=[],
                    improvements=[],
                    next_difficulty=QuestionDifficulty(session.get("current_difficulty", "medium")),
                    difficulty_rationale="Session already completed.",
                    is_session_completed=True,
                    is_skipped=True,
                    next_question=None,
                    scorecard_id=session.get("final_scorecard_id") or (existing_scorecard.get("scorecard_id") if existing_scorecard else None),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot skip question: Session is already {session.get('session_status')}.",
            )

        now = utc_now()
        expires_at = _ensure_utc(session.get("expires_at", now))
        if now > expires_at:
            await db[SESSIONS_COLLECTION].update_one(
                {"session_id": session_id},
                {"$set": {"session_status": SessionStatus.TIMED_OUT.value, "updated_at": now}},
            )
            asgn_id = session.get("assignment_id")
            if asgn_id:
                try:
                    await db[ASSIGNMENTS_COLLECTION].update_one(
                        {"assignment_id": asgn_id},
                        {"$set": {"status": AssignmentStatus.COMPLETED.value, "completed_at": now, "updated_at": now}},
                    )
                except KeyError:
                    pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot skip question: Interview session duration has expired.",
            )

        active_q = session.get("active_question", {})
        curr_q_index = session.get("current_question_index", 1)
        curr_diff = QuestionDifficulty(session.get("current_difficulty", "medium"))
        topic = active_q.get("topic", "Networking")
        question_text = active_q.get("question_text", "")
        is_coding = active_q.get("question_type") == "coding"
        total_target = session.get("total_questions_target", 5)

        # Concurrency barrier: Check if this question was already answered or skipped
        find_one_call = db[RESPONSES_COLLECTION].find_one(
            {"session_id": session_id, "question_index": curr_q_index}
        )
        existing_resp = await find_one_call if hasattr(find_one_call, "__await__") else find_one_call
        if isinstance(existing_resp, dict) and existing_resp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Question {curr_q_index} has already been submitted or skipped for this session.",
            )

        provider = get_ai_provider()
        evaluator_mode_str = provider.get_mode().value

        response_id = str(uuid.uuid4())
        response_doc = {
            "response_id": response_id,
            "session_id": session_id,
            "question_index": curr_q_index,
            "question_text": question_text,
            "difficulty": curr_diff.value,
            "topic": topic,
            "answer_text": "(Question skipped by candidate)",
            "question_type": "coding" if is_coding else "conceptual",
            "language": None,
            "source_code": None,
            "code_execution_summary": None,
            "evaluation_score": None,
            "evaluation_feedback": "Question was skipped by candidate during the interview.",
            "strengths": [],
            "improvements": [],
            "difficulty_adjustment_rationale": "Question skipped by candidate; maintaining current difficulty level.",
            "evaluator_mode": evaluator_mode_str,
            "status": "skipped",
            "is_skipped": True,
            "evaluated_at": now,
            "created_at": now,
        }

        # Check if reached final question
        if curr_q_index >= total_target:
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

            all_responses = prior_responses + [response_doc]

            try:
                scorecard_summary = await provider.generate_scorecard_summary(
                    responses=all_responses,
                    interview_title=topic,
                )
            except (AIProviderUnavailableError, AIProviderError) as exc:
                logger.error("AI provider failure during scorecard generation on skip: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Scorecard generation service is temporarily unavailable: {str(exc)}",
                )

            scorecard_id = str(uuid.uuid4())
            difficulty_progression = [r.get("difficulty", "medium") for r in all_responses if isinstance(r, dict)]

            answered_cnt = len([r for r in all_responses if isinstance(r, dict) and not r.get("is_skipped") and r.get("status") != "skipped"])
            skipped_cnt = len([r for r in all_responses if isinstance(r, dict) and (r.get("is_skipped") or r.get("status") == "skipped")])

            disclaimer_text = (
                f"Evaluations reflect automated technical rubrics. "
                f"Report based on {answered_cnt} evaluated question(s) and {skipped_cnt} skipped question(s) "
                f"out of {total_target} assigned questions."
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
                "evaluator_mode": evaluator_mode_str,
                "disclaimer": disclaimer_text,
                "total_questions_assigned": total_target,
                "questions_answered": answered_cnt,
                "questions_skipped": skipped_cnt,
                "questions_evaluated": answered_cnt,
                "created_at": now,
            }

            try:
                await db[RESPONSES_COLLECTION].insert_one(response_doc)
            except pymongo.errors.DuplicateKeyError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Question {curr_q_index} has already been answered or skipped for this session.",
                )

            await db[SCORECARDS_COLLECTION].insert_one(scorecard_doc)

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
                evaluated_score=None,
                feedback="Question skipped by candidate.",
                strengths=[],
                improvements=[],
                next_difficulty=curr_diff,
                difficulty_rationale="Question skipped by candidate; interview completed.",
                is_session_completed=True,
                is_skipped=True,
                next_question=None,
                scorecard_id=scorecard_id,
                evaluator_mode=evaluator_mode_str,
            )

        # Advance to next question
        next_q_index = curr_q_index + 1
        int_id = session.get("interview_id")
        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": int_id}) if int_id else None
        interview_title = interview.get("title", "Technical Assessment") if interview else "Technical Assessment"

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
        all_asked = prev_questions + [question_text]

        target_role = session.get("selected_role") or InterviewSessionService._resolve_interview_role({}, interview)
        interview_or = [{"interview_id": int_id}, {"interview_id": None}]
        target_type = "coding" if next_q_index >= total_target else "conceptual"
        diff_or = [{"difficulty": curr_diff.value}, {"difficulty": None}, {"difficulty": {"$exists": False}}]

        stored_next_q = None
        try:
            query_tier1 = {
                "$and": [
                    {"$or": interview_or},
                    {"$or": diff_or},
                ],
                "question_text": {"$nin": all_asked},
                "question_type": target_type,
            }
            if target_role:
                query_tier1["role"] = target_role
            stored_next_q = await db[QUESTIONS_COLLECTION].find_one(query_tier1)

            if not stored_next_q:
                query_tier2 = {
                    "$or": interview_or,
                    "question_text": {"$nin": all_asked},
                    "question_type": target_type,
                }
                if target_role:
                    query_tier2["role"] = target_role
                stored_next_q = await db[QUESTIONS_COLLECTION].find_one(query_tier2)

            if not stored_next_q:
                query_tier3 = {
                    "$or": interview_or,
                    "question_text": {"$nin": all_asked},
                }
                if target_role:
                    query_tier3["role"] = target_role
                stored_next_q = await db[QUESTIONS_COLLECTION].find_one(query_tier3)
        except Exception as e:
            logger.warning("Error querying stored question bank on skip progression: %s", e)

        if stored_next_q and stored_next_q.get("question_text"):
            next_q_gen = {
                "question_text": stored_next_q["question_text"],
                "topic": stored_next_q.get("topic", interview_title),
                "question_type": stored_next_q.get("question_type", target_type),
                "expected_answer": stored_next_q.get("expected_answer"),
                "keywords": stored_next_q.get("keywords") or [],
            }
        else:
            try:
                next_q_gen = await provider.generate_question(
                    topic=interview_title,
                    instructions=interview.get("instructions", "") if interview else "",
                    difficulty=curr_diff,
                    question_index=next_q_index,
                    previous_questions=all_asked,
                )
            except (AIProviderUnavailableError, AIProviderError) as exc:
                logger.error("AI provider failure generating next question on skip: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Question generation service is temporarily unavailable: {str(exc)}",
                )

        try:
            await db[RESPONSES_COLLECTION].insert_one(response_doc)
        except pymongo.errors.DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Question {curr_q_index} has already been answered or skipped for this session.",
            )

        coding_spec_next = None
        if next_q_gen.get("question_type") == "coding":
            coding_spec_next = CodingChallengeService.get_candidate_challenge_spec(next_q_gen["question_text"])

        await db[SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "current_question_index": next_q_index,
                    "current_difficulty": curr_diff.value,
                    "active_question": {
                        "question_text": next_q_gen["question_text"],
                        "topic": next_q_gen["topic"],
                        "difficulty": curr_diff.value,
                        "question_type": next_q_gen.get("question_type", target_type),
                        "coding_spec": coding_spec_next,
                        "expected_answer": next_q_gen.get("expected_answer"),
                        "keywords": next_q_gen.get("keywords") or [],
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
            difficulty=curr_diff,
            question_text=next_q_gen["question_text"],
            topic=next_q_gen["topic"],
            question_type=next_q_gen.get("question_type", target_type),
            coding_spec=coding_spec_next,
            time_remaining_seconds=time_remaining,
            evaluator_mode=evaluator_mode_str,
        )

        return SubmitAnswerResponse(
            session_id=session_id,
            question_index=curr_q_index,
            evaluated_score=None,
            feedback="Question skipped by candidate.",
            strengths=[],
            improvements=[],
            next_difficulty=curr_diff,
            difficulty_rationale="Question skipped by candidate; maintaining current difficulty level.",
            is_session_completed=False,
            is_skipped=True,
            next_question=next_question_resp,
            scorecard_id=None,
            evaluator_mode=evaluator_mode_str,
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
                topic=r.get("topic", "Technical Assessment"),
                answer_text=r["answer_text"],
                evaluation_score=r["evaluation_score"],
                score=r["evaluation_score"],
                feedback=r["evaluation_feedback"],
                strengths=r.get("strengths", []),
                improvements=r.get("improvements", []),
                difficulty_adjustment_rationale=r.get("difficulty_adjustment_rationale", ""),
                question_type=r.get("question_type", "conceptual"),
                language=r.get("language"),
                code_execution_summary=r.get("code_execution_summary"),
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
            strengths=scorecard.get("strengths_summary", []),
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
            if assignment_id:
                try:
                    await db[ASSIGNMENTS_COLLECTION].update_one(
                        {"assignment_id": assignment_id},
                        {"$set": {"status": AssignmentStatus.COMPLETED.value, "completed_at": now, "updated_at": now}},
                    )
                except KeyError:
                    pass
            session["session_status"] = SessionStatus.TIMED_OUT.value

        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": assignment["interview_id"]})
        interview_title = interview.get("title", "University Interview") if interview else "University Interview"

        provider = get_ai_provider()
        time_remaining = max(0, int((expires_at - now).total_seconds()))

        active_q = session.get("active_question") or {}
        coding_spec = active_q.get("coding_spec")
        if active_q.get("question_type") == "coding" and not coding_spec:
            coding_spec = CodingChallengeService.get_candidate_challenge_spec(active_q.get("question_text", ""))

        # Strip internal rubric fields (expected_answer, keywords) before returning to student client
        safe_active_q = {
            k: v for k, v in active_q.items()
            if k not in ("expected_answer", "keywords")
        }

        return {
            "has_session": True,
            "session_id": session["session_id"],
            "assignment_id": assignment_id,
            "interview_title": interview_title,
            "session_status": session["session_status"],
            "current_question_index": session.get("current_question_index", 1),
            "question_index": session.get("current_question_index", 1),
            "total_questions_target": session.get("total_questions_target", 5),
            "total_questions": session.get("total_questions_target", 5),
            "current_difficulty": session.get("current_difficulty", "medium"),
            "difficulty": session.get("current_difficulty", "medium"),
            "question_text": active_q.get("question_text", ""),
            "question": active_q.get("question_text", ""),
            "topic": active_q.get("topic", interview_title),
            "question_type": active_q.get("question_type", "conceptual"),
            "coding_spec": coding_spec,
            "active_question": safe_active_q,
            "expires_at": expires_at.isoformat() if session.get("expires_at") else None,
            "time_remaining_seconds": time_remaining,
            "scorecard_id": session.get("scorecard_id") or session.get("final_scorecard_id"),
            "evaluator_mode": provider.get_mode().value,
        }

    @staticmethod
    async def get_performance_report(
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        user: UserInDB,
        target_session_id: Optional[str] = None,
    ) -> StudentPerformanceReportResponse:
        """
        Retrieves a comprehensive, evidence-grounded performance report for a completed assignment:
        - Strictly enforces student ownership (cross-student access blocked with 403 Forbidden).
        - Allows faculty and administrators institutional access.
        - Calculates topic-wise scores and question counts.
        - Labels single-question topics honestly as limited evidence.
        - Generates actionable preparation priorities.
        - Recommends verified educational videos mapped directly to demonstrated deficits.
        """
        clean_reg = (user.registration_number or "").strip().upper()
        asgn_call = db[ASSIGNMENTS_COLLECTION].find_one({"assignment_id": assignment_id})
        assignment = await asgn_call if hasattr(asgn_call, "__await__") else asgn_call
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview assignment '{assignment_id}' was not found",
            )

        if user.role == UserRole.STUDENT:
            if not clean_reg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Student account does not have a verified registration number linked.",
                )
            if assignment.get("student_registration_number") != clean_reg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You are not authorized to view another student's performance report",
                )
        elif user.role not in [
            UserRole.PLATFORM_ADMIN,
            UserRole.UNIVERSITY_ADMIN,
            UserRole.DEPARTMENT_ADMIN,
            UserRole.FACULTY,
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to access interview performance report",
            )

        if target_session_id:
            sess_call = db[SESSIONS_COLLECTION].find_one({"session_id": target_session_id})
            session = await sess_call if hasattr(sess_call, "__await__") else sess_call
            if not session or session.get("assignment_id") != assignment_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Interview session '{target_session_id}' not found for assignment '{assignment_id}'",
                )
            if session.get("session_status") != SessionStatus.COMPLETED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Interview session '{target_session_id}' is still in progress. The performance report is available upon interview completion.",
                )
        else:
            # Query all sessions for this assignment to inspect current session lifecycle
            all_sess_cursor = db[SESSIONS_COLLECTION].find({"assignment_id": assignment_id})
            if hasattr(all_sess_cursor, "sort") and callable(all_sess_cursor.sort):
                all_sess_cursor = all_sess_cursor.sort("created_at", pymongo.DESCENDING)
            if hasattr(all_sess_cursor, "to_list"):
                res = all_sess_cursor.to_list(length=10)
                all_sessions = await res if hasattr(res, "__await__") else res
            elif hasattr(all_sess_cursor, "__await__"):
                all_sessions = await all_sess_cursor
            else:
                all_sessions = all_sess_cursor
            if not isinstance(all_sessions, list):
                all_sessions = []

            if not all_sessions:
                any_sess_call = db[SESSIONS_COLLECTION].find_one({"assignment_id": assignment_id})
                any_sess = await any_sess_call if hasattr(any_sess_call, "__await__") else any_sess_call
                if any_sess and any_sess.get("session_status") == SessionStatus.IN_PROGRESS.value:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Interview session is still in progress. The performance report is available upon interview completion.",
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No completed interview session found for assignment '{assignment_id}'.",
                )

            # Prevent returning stale report from an older session if the assignment has an in-progress session
            latest_session = all_sessions[0]
            if latest_session.get("session_status") == SessionStatus.IN_PROGRESS.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Interview session is still in progress. The performance report is available upon interview completion.",
                )

            completed_sessions = [
                s for s in all_sessions if s.get("session_status") == SessionStatus.COMPLETED.value
            ]
            if not completed_sessions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No completed interview session found for assignment '{assignment_id}'.",
                )

            session = completed_sessions[0]

        session_id = session["session_id"]

        sc_call = db[SCORECARDS_COLLECTION].find_one({"session_id": session_id}, {"_id": 0})
        scorecard = await sc_call if hasattr(sc_call, "__await__") else sc_call
        if not scorecard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Final scorecard for this interview session has not yet been generated.",
            )

        int_call = db[INTERVIEWS_COLLECTION].find_one({"interview_id": assignment["interview_id"]})
        interview = await int_call if hasattr(int_call, "__await__") else int_call
        interview_title = interview.get("title") if interview else "Adaptive Placement Mock Interview"
        selected_role = assignment.get("selected_role") or session.get("selected_role")

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

        total_questions_target = session.get("total_questions_target", len(raw_responses) or 5)
        answered_count = len([r for r in raw_responses if not r.get("is_skipped") and r.get("status") != "skipped"])
        skipped_count = len([r for r in raw_responses if r.get("is_skipped") or r.get("status") == "skipped"])
        evaluated_count = len([r for r in raw_responses if not r.get("is_skipped") and r.get("status") != "skipped" and r.get("evaluation_score") is not None])

        response_summaries = []
        for r in raw_responses:
            is_skp = bool(r.get("is_skipped") or r.get("status") == "skipped")
            stat_val = "skipped" if is_skp else r.get("status", "answered")
            eval_score_val = float(r["evaluation_score"]) if r.get("evaluation_score") is not None else None
            response_summaries.append(
                ResponseSummary(
                    question_index=r["question_index"],
                    question_text=r["question_text"],
                    difficulty=QuestionDifficulty(r["difficulty"]),
                    topic=r.get("topic", "Technical Assessment"),
                    answer_text=r.get("answer_text", "(Question skipped by candidate)" if is_skp else ""),
                    evaluation_score=eval_score_val,
                    score=eval_score_val,
                    feedback=r.get("evaluation_feedback", "Question was skipped by candidate." if is_skp else ""),
                    strengths=r.get("strengths", []),
                    improvements=r.get("improvements", []),
                    difficulty_adjustment_rationale=r.get("difficulty_adjustment_rationale", ""),
                    question_type=r.get("question_type", "conceptual"),
                    language=r.get("language"),
                    code_execution_summary=r.get("code_execution_summary"),
                    status=stat_val,
                    is_skipped=is_skp,
                )
            )

        # Aggregate topic-wise performance
        topic_scores: Dict[str, List[float]] = {}
        topic_all_questions: Dict[str, List[Dict[str, Any]]] = {}
        topic_feedback: Dict[str, List[str]] = {}
        for r in raw_responses:
            topic_name = _format_topic_name(r.get("topic"))
            topic_all_questions.setdefault(topic_name, []).append(r)
            if not r.get("is_skipped") and r.get("status") != "skipped" and r.get("evaluation_score") is not None:
                topic_scores.setdefault(topic_name, []).append(float(r["evaluation_score"]))
            if r.get("improvements"):
                topic_feedback.setdefault(topic_name, []).extend(r["improvements"])

        topic_items: List[TopicPerformanceItem] = []
        actionable_priorities: List[ActionablePriorityItem] = []

        for t_name, all_q in topic_all_questions.items():
            scores = topic_scores.get(t_name, [])
            total_tested = len(all_q)
            eval_tested = len(scores)

            if eval_tested > 0:
                avg = round(sum(scores) / eval_tested, 1)
                min_s = round(min(scores), 1)
                max_s = round(max(scores), 1)

                is_limited = eval_tested < 2
                if is_limited:
                    evidence_lvl = "limited"
                    note = f"Limited evidence: Evaluated on 1 question ({total_tested - eval_tested} skipped). Consider this an initial practice indicator."
                elif eval_tested == 2:
                    evidence_lvl = "moderate"
                    note = "Evaluated across 2 questions. Representative sample."
                else:
                    evidence_lvl = "sufficient"
                    note = f"Evaluated across {eval_tested} questions. Strong evidence basis."

                if avg >= 7.0:
                    cat = "strength"
                elif avg >= 5.0:
                    cat = "moderate"
                else:
                    cat = "weakness"
            else:
                avg = 0.0
                min_s = 0.0
                max_s = 0.0
                cat = "weakness"
                is_limited = True
                evidence_lvl = "limited"
                note = f"All {total_tested} question(s) in this topic were skipped by candidate. No evaluation score recorded."

            topic_items.append(
                TopicPerformanceItem(
                    topic=t_name,
                    questions_tested=total_tested,
                    average_score=avg,
                    min_score=min_s,
                    max_score=max_s,
                    category=cat,
                    is_limited_evidence=is_limited,
                    evidence_level=evidence_lvl,
                    evidence_note=note,
                )
            )

            # Build actionable priorities for weak topics (< 6.5) or topics where questions were skipped
            if eval_tested == 0 or avg < 6.5 or topic_feedback.get(t_name):
                priority_lvl = "high" if (eval_tested == 0 or avg < 5.0) else "medium"
                if eval_tested == 0:
                    reason_text = f"Questions in '{t_name}' were skipped during the interview. Revision recommended to build baseline confidence."
                else:
                    specific_gap = f" Evaluator notes: '{topic_feedback[t_name][0]}'" if topic_feedback.get(t_name) else ""
                    reason_text = f"Average score of {avg}/10 across {eval_tested} evaluated question(s).{specific_gap}"

                steps = [
                    f"Review core technical principles and standard architecture definitions for {t_name}.",
                    "Practice structured answers focusing on system trade-offs, protocols, and implementation constraints.",
                    "Simulate timed scenario-based interview questions to reinforce recall under pressure.",
                ]
                actionable_priorities.append(
                    ActionablePriorityItem(
                        topic=t_name,
                        priority=priority_lvl,
                        average_score=avg,
                        reason=reason_text,
                        actionable_steps=steps,
                    )
                )

        topic_items.sort(key=lambda x: x.average_score)
        actionable_priorities.sort(key=lambda x: (0 if x.priority == "high" else 1, x.average_score))

        # Match verified learning video recommendations
        topic_dicts = [t.model_dump() for t in topic_items]
        matched_videos_raw = match_video_recommendations(
            topic_breakdown=topic_dicts,
            selected_role=selected_role,
            responses=raw_responses,
            max_recommendations=4,
        )
        video_items = [VideoRecommendationItem(**v) for v in matched_videos_raw]

        completed_timestamp = session.get("completed_at", session.get("updated_at", utc_now()))

        return StudentPerformanceReportResponse(
            report_id=f"rep-{session_id[:12]}",
            assignment_id=assignment_id,
            session_id=session_id,
            interview_id=assignment["interview_id"],
            interview_title=interview_title,
            selected_role=selected_role,
            student_registration_number=assignment["student_registration_number"],
            student_email=assignment.get("student_email"),
            overall_score=scorecard["overall_score"],
            percentage_score=scorecard["percentage_score"],
            performance_level=scorecard["performance_level"],
            summary_feedback=scorecard["summary_feedback"],
            evaluator_mode=scorecard.get("evaluator_mode", "mock_rule_engine"),
            difficulty_progression=scorecard.get("difficulty_progression", []),
            completed_at=completed_timestamp,
            total_questions_assigned=total_questions_target,
            questions_answered=answered_count,
            questions_skipped=skipped_count,
            questions_evaluated=evaluated_count,
            topic_breakdown=topic_items,
            actionable_priorities=actionable_priorities,
            video_recommendations=video_items,
            responses=response_summaries,
            disclaimer=scorecard.get(
                "disclaimer",
                "Evaluations reflect automated technical rubrics and adaptive difficulty thresholds. Recommendations are tailored based on demonstrated performance evidence and do not imply automated viewing history."
            ),
        )

    @staticmethod
    async def get_performance_report_by_session(
        db: AsyncIOMotorDatabase,
        session_id: str,
        user: UserInDB,
    ) -> StudentPerformanceReportResponse:
        """
        Helper retrieving a performance report using session_id.
        Strictly verifies that the requested session is completed before delegating,
        preventing an in-progress session from returning an earlier completed session's report.
        """
        sess_call = db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
        session = await sess_call if hasattr(sess_call, "__await__") else sess_call
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview session '{session_id}' not found",
            )
        if session.get("session_status") != SessionStatus.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Interview session '{session_id}' is still in progress. The performance report is available upon interview completion.",
            )
        return await InterviewSessionService.get_performance_report(
            db=db,
            assignment_id=session["assignment_id"],
            user=user,
            target_session_id=session_id,
        )
