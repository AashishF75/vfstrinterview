import logging
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from app.core.config import settings
from app.models.user import UserInDB, UserRole
from app.models.interview_session import SessionStatus, QuestionDifficulty
from app.models.performance_tracking import (
    RecommendationLevel,
    RecommendationStatus,
    EvidenceSufficiency,
    PerformanceTrend,
    StudentProfileUpdate,
    StudentProfileInfo,
    InterviewHistorySummaryItem,
    TopicMasterySummaryItem,
    PracticePriorityItem,
    LevelRecommendation,
    StudentPerformanceSummaryResponse,
    PaginatedInterviewHistoryResponse,
    StudentTrackingAdminItem,
    PaginatedStudentTrackingResponse,
    utc_now,
)

logger = logging.getLogger(__name__)

SCORECARDS_COLLECTION = "interview_scorecards"
SESSIONS_COLLECTION = "interview_sessions"
ASSIGNMENTS_COLLECTION = "student_interview_assignments"
INTERVIEWS_COLLECTION = "university_interviews"
RESPONSES_COLLECTION = "interview_responses"
PROFILES_COLLECTION = "student_profiles"
USERS_COLLECTION = "users"

# Mapping between recommendation levels and underlying question bank difficulty
LEVEL_TO_DIFFICULTY_MAP = {
    RecommendationLevel.BEGINNER: "easy",
    RecommendationLevel.INTERMEDIATE: "medium",
    RecommendationLevel.ADVANCED: "hard",
}

DIFFICULTY_TO_LEVEL_MAP = {
    "easy": RecommendationLevel.BEGINNER,
    "medium": RecommendationLevel.INTERMEDIATE,
    "hard": RecommendationLevel.ADVANCED,
}


def _clean_str(val: Optional[str]) -> str:
    return (val or "").strip()


def _clean_reg(val: Optional[str]) -> str:
    return _clean_str(val).upper()


def _format_topic_name(raw: Optional[str]) -> str:
    if not raw or not raw.strip():
        return "General Technical Assessment"
    cleaned = raw.strip().replace("_", " ")
    return " ".join(word.capitalize() for word in cleaned.split())


def safe_parse_score(
    value: Any,
    min_val: float = 0.0,
    max_val: float = 10.0,
) -> Optional[float]:
    """
    Safely parses a numeric score value:
    - Rejects None, missing, non-numeric strings, NaN, and infinity.
    - Rejects values strictly outside [min_val, max_val].
    - Preserves exact 0.0 without conflating it with None/missing.
    - Returns None if invalid or out of range.
    """
    if value is None:
        return None
    try:
        val = float(value)
    except (ValueError, TypeError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    if val < min_val or val > max_val:
        return None
    return val


class InterviewRecommendationService:
    """
    Dedicated, explainable backend service for student performance tracking
    and personalized interview level recommendation.
    """

    @classmethod
    async def get_or_create_student_profile(
        cls,
        db: AsyncIOMotorDatabase,
        user: UserInDB,
        target_reg_no: Optional[str] = None,
    ) -> StudentProfileInfo:
        """
        Retrieves the student's profile information, merging official institutional
        account records with any student-updated preferences (target role, skills, etc.).
        """
        reg_no = target_reg_no or user.registration_number
        clean_registration = _clean_reg(reg_no)

        # 1. Fetch profile customizations from student_profiles collection
        profile_doc = await db[PROFILES_COLLECTION].find_one({"registration_number": clean_registration})
        profile_doc = profile_doc or {}

        # 2. Derive base user details (if target is different, query user account)
        user_doc = None
        is_target_different = bool(target_reg_no and clean_registration != _clean_reg(user.registration_number))
        if is_target_different:
            # Check in users collection (auth db or interview db if combined)
            auth_db = db.client[settings.MONGODB_DB_NAME]
            user_doc = await auth_db[USERS_COLLECTION].find_one({"registration_number": clean_registration})

        if is_target_different:
            full_name = profile_doc.get("full_name") or (user_doc.get("full_name") if user_doc else None)
            email = profile_doc.get("email") or (user_doc.get("email") if user_doc else None)
            institution_id = profile_doc.get("institution_id") or (user_doc.get("institution_id") if user_doc else None) or "VFSTR"
            department = profile_doc.get("department") or (user_doc.get("department") if user_doc else None)
            batch_cohort = profile_doc.get("batch_cohort") or (user_doc.get("batch_cohort") if user_doc else None)
            section = profile_doc.get("section") or (user_doc.get("section") if user_doc else None)
        else:
            full_name = profile_doc.get("full_name") or (user_doc.get("full_name") if user_doc else user.full_name)
            email = profile_doc.get("email") or (user_doc.get("email") if user_doc else user.email)
            institution_id = profile_doc.get("institution_id") or (user_doc.get("institution_id") if user_doc else user.institution_id) or "VFSTR"
            department = profile_doc.get("department") or (user_doc.get("department") if user_doc else user.department)
            batch_cohort = profile_doc.get("batch_cohort") or (user_doc.get("batch_cohort") if user_doc else user.batch_cohort)
            section = profile_doc.get("section") or (user_doc.get("section") if user_doc else user.section)

        return StudentProfileInfo(
            registration_number=clean_registration,
            full_name=full_name,
            email=email,
            institution_id=institution_id,
            department=department,
            batch_cohort=batch_cohort,
            section=section,
            target_role=profile_doc.get("target_role") or "Associate Software Engineer",
            technical_skills=profile_doc.get("technical_skills") or ["Python", "DSA", "Problem Solving"],
            preferred_languages=profile_doc.get("preferred_languages") or ["Python", "Java", "C++"],
            experience_level=profile_doc.get("experience_level") or "Entry Level",
            areas_of_interest=profile_doc.get("areas_of_interest") or ["Software Engineering", "Algorithms"],
            updated_at=profile_doc.get("updated_at"),
        )

    @classmethod
    async def update_student_profile(
        cls,
        db: AsyncIOMotorDatabase,
        current_user: UserInDB,
        payload: StudentProfileUpdate,
    ) -> StudentProfileInfo:
        """
        Updates student's optional profile fields (target role, technical skills, etc.).
        Guarantees that official registration and eligibility records remain immutable.
        """
        clean_reg_no = _clean_reg(current_user.registration_number)
        if not clean_reg_no:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student account is not linked to a verified registration number.",
            )

        update_fields: Dict[str, Any] = {
            "registration_number": clean_reg_no,
            "email": current_user.email,
            "institution_id": current_user.institution_id,
            "updated_at": utc_now(),
        }

        if payload.target_role is not None:
            update_fields["target_role"] = payload.target_role.strip()
        if payload.technical_skills is not None:
            update_fields["technical_skills"] = [s.strip() for s in payload.technical_skills if s and s.strip()]
        if payload.preferred_languages is not None:
            update_fields["preferred_languages"] = [l.strip() for l in payload.preferred_languages if l and l.strip()]
        if payload.experience_level is not None:
            update_fields["experience_level"] = payload.experience_level.strip()
        if payload.areas_of_interest is not None:
            update_fields["areas_of_interest"] = [a.strip() for a in payload.areas_of_interest if a and a.strip()]

        await db[PROFILES_COLLECTION].update_one(
            {"registration_number": clean_reg_no},
            {"$set": update_fields},
            upsert=True,
        )

        return await cls.get_or_create_student_profile(db=db, user=current_user)

    @classmethod
    async def get_student_completed_evaluations(
        cls,
        db: AsyncIOMotorDatabase,
        student_reg_no: str,
    ) -> List[Dict[str, Any]]:
        """
        Queries all authoritative completed interviews and scorecards for the student.
        Deduplicates multiple scorecards by underlying session_id using authoritative
        final_scorecard_id, explicit finalization markers, or latest timestamps.
        Sorts chronologically ascending by completion time for trend analysis.
        """
        clean_reg_no = _clean_reg(student_reg_no)
        if not clean_reg_no:
            return []

        cursor = db[SCORECARDS_COLLECTION].find({"student_registration_number": clean_reg_no})
        if hasattr(cursor, "sort") and callable(cursor.sort):
            cursor = cursor.sort("created_at", pymongo.ASCENDING)
        if hasattr(cursor, "to_list"):
            res = cursor.to_list(length=200)
            scorecards = await res if hasattr(res, "__await__") else res
        elif hasattr(cursor, "__await__"):
            scorecards = await cursor
        else:
            scorecards = cursor

        if not isinstance(scorecards, list):
            scorecards = []

        # Group scorecards by session_id to identify duplicates
        session_scorecards_map: Dict[str, List[Dict[str, Any]]] = {}
        for sc in scorecards:
            sid = sc.get("session_id")
            if not sid:
                continue
            session_scorecards_map.setdefault(sid, []).append(sc)

        completed_records = []
        for session_id, sc_list in session_scorecards_map.items():
            # Verify associated session is genuinely completed
            sess_call = db[SESSIONS_COLLECTION].find_one({"session_id": session_id})
            session = await sess_call if hasattr(sess_call, "__await__") else sess_call
            if not session or session.get("session_status") != SessionStatus.COMPLETED.value:
                continue

            chosen_sc: Optional[Dict[str, Any]] = None

            if len(sc_list) == 1:
                chosen_sc = sc_list[0]
            else:
                # Multiple scorecards exist for the same session_id (Fix 5: Authoritative resolution)
                # 1. Authoritative final_scorecard_id on the session document
                final_sc_id = session.get("final_scorecard_id")
                if final_sc_id:
                    for sc in sc_list:
                        if sc.get("scorecard_id") == final_sc_id:
                            chosen_sc = sc
                            break

                # 2. Check for explicit is_final flag
                if not chosen_sc:
                    final_marked = [sc for sc in sc_list if sc.get("is_final") is True]
                    if len(final_marked) == 1:
                        chosen_sc = final_marked[0]

                # 3. Check for non-conflicting duplicates (identical overall scores)
                if not chosen_sc:
                    valid_scores = [
                        safe_parse_score(sc.get("overall_score"), 0.0, 10.0)
                        for sc in sc_list
                    ]
                    all_scores_agree = (
                        len(valid_scores) == len(sc_list)
                        and all(s is not None for s in valid_scores)
                        and len(set(valid_scores)) == 1
                    )
                    if all_scores_agree:
                        chosen_sc = max(
                            sc_list,
                            key=lambda s: s.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
                        )
                    else:
                        # Conflicting scores: check if there are distinct created_at timestamps
                        timestamps = [s.get("created_at") for s in sc_list]
                        has_distinct_timestamps = (
                            all(ts is not None for ts in timestamps)
                            and len(set(timestamps)) == len(timestamps)
                        )
                        if has_distinct_timestamps:
                            chosen_sc = max(sc_list, key=lambda s: s.get("created_at"))
                        else:
                            logger.warning(
                                "Ambiguous conflicting duplicate scorecards detected for session %s "
                                "without authoritative resolution; excluding session from calculations.",
                                session_id,
                            )
                            continue

            if not chosen_sc:
                continue

            # Safe numeric validation on chosen scorecard
            if safe_parse_score(chosen_sc.get("overall_score"), 0.0, 10.0) is None:
                logger.warning(
                    "Scorecard %s for session %s has invalid/missing overall_score; excluding.",
                    chosen_sc.get("scorecard_id"),
                    session_id,
                )
                continue

            assignment_id = session.get("assignment_id")
            assignment = None
            if assignment_id:
                assignment = await db[ASSIGNMENTS_COLLECTION].find_one({"assignment_id": assignment_id})

            # Get interview metadata
            interview_id = chosen_sc.get("interview_id") or (session.get("interview_id") if session else None)
            interview = None
            if interview_id:
                interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": interview_id})

            selected_role = (
                (assignment.get("selected_role") if assignment else None)
                or session.get("selected_role")
                or (interview.get("role") if interview else None)
                or "Associate Software Engineer"
            )

            completed_at = chosen_sc.get("created_at") or session.get("completed_at") or utc_now()

            # Retrieve question responses to inspect topic performance and difficulty progression
            resp_cursor = db[RESPONSES_COLLECTION].find({"session_id": session_id})
            if hasattr(resp_cursor, "sort") and callable(resp_cursor.sort):
                resp_cursor = resp_cursor.sort("question_index", pymongo.ASCENDING)
            if hasattr(resp_cursor, "to_list"):
                r_res = resp_cursor.to_list(length=50)
                responses = await r_res if hasattr(r_res, "__await__") else r_res
            elif hasattr(resp_cursor, "__await__"):
                responses = await resp_cursor
            else:
                responses = resp_cursor

            if not isinstance(responses, list):
                responses = []

            completed_records.append({
                "scorecard": chosen_sc,
                "session": session,
                "assignment": assignment,
                "interview": interview,
                "selected_role": selected_role,
                "completed_at": completed_at,
                "responses": responses,
            })

        # Sort completed_records chronologically ascending by completed_at
        completed_records.sort(
            key=lambda r: r.get("completed_at") or datetime.min.replace(tzinfo=timezone.utc)
        )
        return completed_records

    @classmethod
    def calculate_trend_and_consistency(
        cls,
        scores: List[float],
    ) -> Tuple[PerformanceTrend, Optional[float]]:
        """
        Calculates performance trend and consistency score from chronological score history.
        """
        if len(scores) < 2:
            return PerformanceTrend.INSUFFICIENT_DATA, None

        n = len(scores)
        # Calculate standard deviation
        avg = sum(scores) / n
        variance = sum((x - avg) ** 2 for x in scores) / n
        stdev = math.sqrt(variance)
        consistency = round(max(0.0, min(10.0, 10.0 - (stdev * 2.0))), 1)

        # Calculate slope or recent comparison
        if n >= 3:
            recent_avg = sum(scores[-2:]) / 2.0
            earlier_avg = sum(scores[:-2]) / float(n - 2)
            delta = recent_avg - earlier_avg
        else:
            delta = scores[-1] - scores[0]

        if delta >= 0.5:
            trend = PerformanceTrend.IMPROVING
        elif delta <= -0.5:
            trend = PerformanceTrend.DECLINING
        else:
            trend = PerformanceTrend.STABLE

        return trend, consistency

    @classmethod
    def aggregate_topic_mastery(
        cls,
        records: List[Dict[str, Any]],
    ) -> List[TopicMasterySummaryItem]:
        """
        Aggregates question-level scores across all completed interviews to determine topic mastery.
        """
        topic_scores: Dict[str, List[float]] = {}
        topic_total_q: Dict[str, int] = {}

        for rec in records:
            responses = rec.get("responses", [])
            for r in responses:
                t_name = _format_topic_name(r.get("topic"))
                topic_total_q[t_name] = topic_total_q.get(t_name, 0) + 1
                if not r.get("is_skipped") and r.get("status") != "skipped":
                    score_val = safe_parse_score(r.get("evaluation_score"), 0.0, 10.0)
                    if score_val is not None:
                        topic_scores.setdefault(t_name, []).append(score_val)

        mastery_items: List[TopicMasterySummaryItem] = []
        for t_name, total_q in topic_total_q.items():
            scores = topic_scores.get(t_name, [])
            if not scores:
                continue

            avg_score = round(sum(scores) / len(scores), 1)
            min_score = round(min(scores), 1)
            max_score = round(max(scores), 1)

            if avg_score >= 7.5:
                category = "strength"
                mastery_level = "Proficient"
            elif avg_score >= 5.0:
                category = "moderate"
                mastery_level = "Developing"
            else:
                category = "weakness"
                mastery_level = "Foundational Gap"

            if total_q >= 5:
                evidence_level = "sufficient"
            elif total_q >= 2:
                evidence_level = "moderate"
            else:
                evidence_level = "limited"

            mastery_items.append(
                TopicMasterySummaryItem(
                    topic=t_name,
                    questions_tested=total_q,
                    average_score=avg_score,
                    min_score=min_score,
                    max_score=max_score,
                    category=category,
                    mastery_level=mastery_level,
                    evidence_level=evidence_level,
                )
            )

        # Sort by average score ascending (so weaknesses are visible first)
        mastery_items.sort(key=lambda item: item.average_score)
        return mastery_items

    @classmethod
    def calculate_level_recommendation(
        cls,
        records: List[Dict[str, Any]],
        profile: StudentProfileInfo,
    ) -> LevelRecommendation:
        """
        Deterministic, explainable recommendation logic conforming to policy:
        - Beginner: foundational gaps (< 5.0/10) or insufficient history
        - Intermediate: solid fundamentals (5.0–7.4/10) or single strong score (provisional)
        - Advanced: repeated strong performance (>= 7.5/10) across at least 2 interviews without critical gaps
        - Never promote to Advanced on single interview (provisional).
        """
        scores: List[float] = []
        for r in records:
            sc = r.get("scorecard")
            if isinstance(sc, dict):
                s = safe_parse_score(sc.get("overall_score"), 0.0, 10.0)
                if s is not None:
                    scores.append(s)

        valid_count = len(scores)
        count = valid_count
        avg_score = round(sum(scores) / valid_count, 1) if scores else None
        latest_score = round(scores[-1], 1) if scores else None

        trend, consistency = cls.calculate_trend_and_consistency(scores)
        topic_mastery = cls.aggregate_topic_mastery(records)

        # Identify strengths & weaknesses
        strongest = [t.topic for t in topic_mastery if t.category == "strength"][:3]
        weakest = [t.topic for t in topic_mastery if t.category == "weakness"][:3]

        # Generate practice priorities for topics with scores < 6.0
        practice_priorities: List[PracticePriorityItem] = []
        for t in topic_mastery:
            if t.average_score < 6.0:
                p_level = "high" if t.average_score < 5.0 else "medium"
                practice_priorities.append(
                    PracticePriorityItem(
                        topic=t.topic,
                        priority=p_level,
                        average_score=t.average_score,
                        reason=f"Average demonstrated score ({t.average_score}/10) reflects actionable comprehension gaps.",
                        recommended_focus=f"Targeted review of core {t.topic} principles, standard patterns, and implementation problems.",
                    )
                )

        # CASE 1: ZERO INTERVIEWS
        if count == 0:
            return LevelRecommendation(
                recommended_level=RecommendationLevel.BEGINNER,
                underlying_difficulty="easy",
                status=RecommendationStatus.PROVISIONAL,
                evidence_sufficiency=EvidenceSufficiency.LIMITED,
                completed_interviews_count=0,
                average_score=None,
                latest_score=None,
                score_trend=PerformanceTrend.INSUFFICIENT_DATA,
                consistency_score=None,
                explanation=(
                    "No completed interview sessions on record yet. A foundational Beginner interview "
                    "is recommended to establish your baseline technical competencies."
                ),
                progression_requirements="Complete an initial interview with an overall score >= 5.0/10 to unlock Intermediate level.",
                suggested_focus="Foundational programming syntax, basic object-oriented principles, and standard problem solving.",
                strongest_topics=[],
                weakest_topics=[],
                practice_priorities=[],
                calculated_at=utc_now(),
            )

        # CASE 2: EXACTLY 1 INTERVIEW (PROVISIONAL)
        if count == 1:
            first_score = scores[0]
            if first_score < 5.0:
                rec_level = RecommendationLevel.BEGINNER
                underlying = "easy"
                expl = (
                    f"Initial interview score of {first_score}/10 indicates foundational gaps. "
                    "Beginner difficulty is recommended to strengthen core concepts before advancing."
                )
                prog_req = "Score >= 5.0/10 on foundational technical interviews to progress to Intermediate difficulty."
                focus = "Core language fundamentals, data type properties, and basic algorithmic problem solving."
            else:
                rec_level = RecommendationLevel.INTERMEDIATE
                underlying = "medium"
                expl = (
                    f"Solid initial performance ({first_score}/10) demonstrated good technical fundamentals. "
                    "Provisional recommendation to attempt Intermediate difficulty to evaluate conceptual application under moderate pressure."
                )
                prog_req = (
                    "Complete a second completed interview with consistent >= 7.5/10 performance "
                    "to corroborate readiness for Advanced difficulty."
                )
                focus = "Application of data structures, algorithmic efficiency, and structured problem solving."

            return LevelRecommendation(
                recommended_level=rec_level,
                underlying_difficulty=underlying,
                status=RecommendationStatus.PROVISIONAL,
                evidence_sufficiency=EvidenceSufficiency.LIMITED,
                completed_interviews_count=1,
                average_score=avg_score,
                latest_score=latest_score,
                score_trend=PerformanceTrend.INSUFFICIENT_DATA,
                consistency_score=None,
                explanation=expl,
                progression_requirements=prog_req,
                suggested_focus=focus,
                strongest_topics=strongest,
                weakest_topics=weakest,
                practice_priorities=practice_priorities,
                calculated_at=utc_now(),
            )

        # CASE 3: 2 OR MORE COMPLETED INTERVIEWS (EVIDENCE-SUPPORTED)
        has_incomplete_evidence = len(records) > valid_count
        if has_incomplete_evidence:
            sufficiency = EvidenceSufficiency.LIMITED if count < 3 else EvidenceSufficiency.MODERATE
        else:
            sufficiency = EvidenceSufficiency.STRONG if count >= 3 else EvidenceSufficiency.MODERATE

        recent_scores = scores[-2:]
        recent_avg = sum(recent_scores) / len(recent_scores)
        has_critical_topic_gap = any(t.average_score < 4.5 for t in topic_mastery)
        recent_collapse = latest_score < 5.0

        # Sub-case 3A: ADVANCED
        # Requires: count >= 2, recent_avg >= 7.5, historical avg >= 7.0, latest >= 6.5, no critical core gap
        if recent_avg >= 7.5 and avg_score >= 7.0 and latest_score >= 6.5 and not has_critical_topic_gap:
            return LevelRecommendation(
                recommended_level=RecommendationLevel.ADVANCED,
                underlying_difficulty="hard",
                status=RecommendationStatus.EVIDENCE_SUPPORTED,
                evidence_sufficiency=sufficiency,
                completed_interviews_count=count,
                average_score=avg_score,
                latest_score=latest_score,
                score_trend=trend,
                consistency_score=consistency,
                explanation=(
                    f"Consistently strong technical performance across {count} verified interviews "
                    f"(recent avg: {round(recent_avg, 1)}/10, overall avg: {avg_score}/10) with verified mastery "
                    "across evaluated engineering competencies."
                ),
                progression_requirements=(
                    "Maintain high performance on complex system architecture, edge-case optimization, "
                    "and multi-variable technical reasoning questions."
                ),
                suggested_focus="Advanced system design, optimal time/space complexity trade-offs, and multi-tier concurrency.",
                strongest_topics=strongest,
                weakest_topics=weakest,
                practice_priorities=practice_priorities,
                calculated_at=utc_now(),
            )

        # Sub-case 3B: BEGINNER
        # Foundational gaps: recent average < 5.0 or latest collapse < 4.5 with low overall average
        if recent_avg < 5.0 or (recent_collapse and avg_score < 5.5):
            return LevelRecommendation(
                recommended_level=RecommendationLevel.BEGINNER,
                underlying_difficulty="easy",
                status=RecommendationStatus.EVIDENCE_SUPPORTED,
                evidence_sufficiency=sufficiency,
                completed_interviews_count=count,
                average_score=avg_score,
                latest_score=latest_score,
                score_trend=trend,
                consistency_score=consistency,
                explanation=(
                    f"Recent performance ({round(recent_avg, 1)}/10) indicates foundational comprehension challenges. "
                    "Beginner level is recommended to solidify essential concepts before attempting complex questions."
                ),
                progression_requirements="Achieve consistent scores >= 5.0/10 across foundational sessions to qualify for Intermediate.",
                suggested_focus="Core syntax, foundational data structures, and direct concept definitions.",
                strongest_topics=strongest,
                weakest_topics=weakest,
                practice_priorities=practice_priorities,
                calculated_at=utc_now(),
            )

        # Sub-case 3C: INTERMEDIATE
        # Solid fundamentals (5.0 - 7.4) or strong aggregate with topic gaps
        if has_critical_topic_gap:
            gap_note = f" Identified gaps in {', '.join(weakest[:2])} require reinforcement."
        else:
            gap_note = ""

        return LevelRecommendation(
            recommended_level=RecommendationLevel.INTERMEDIATE,
            underlying_difficulty="medium",
            status=RecommendationStatus.EVIDENCE_SUPPORTED,
            evidence_sufficiency=sufficiency,
            completed_interviews_count=count,
            average_score=avg_score,
            latest_score=latest_score,
            score_trend=trend,
            consistency_score=consistency,
            explanation=(
                f"Demonstrated solid competency across {count} interviews (average {avg_score}/10).{gap_note} "
                "Intermediate difficulty provides the optimal challenge to bridge theory and applied engineering."
            ),
            progression_requirements=(
                "Achieve >= 7.5/10 in consecutive Intermediate assessments and resolve identified topic gaps "
                "to advance to Advanced difficulty."
            ),
            suggested_focus="Data structure implementation, database indexing/normalization, and moderate algorithmic problems.",
            strongest_topics=strongest,
            weakest_topics=weakest,
            practice_priorities=practice_priorities,
            calculated_at=utc_now(),
        )

    @classmethod
    async def get_student_performance_summary(
        cls,
        db: AsyncIOMotorDatabase,
        current_user: UserInDB,
        target_registration_number: Optional[str] = None,
    ) -> StudentPerformanceSummaryResponse:
        """
        Main entry point for student progress and recommendation summary.
        Enforces strict RBAC and multi-tenant scoping.
        """
        clean_user_reg = _clean_reg(current_user.registration_number)
        target_reg = _clean_reg(target_registration_number) if target_registration_number else clean_user_reg

        # Authorization Guard
        if current_user.role == UserRole.STUDENT:
            if not clean_user_reg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Student account is not linked to a verified registration number.",
                )
            if target_reg != clean_user_reg:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Students are strictly restricted to their own performance record.",
                )
        elif current_user.role in [
            UserRole.FACULTY,
            UserRole.DEPARTMENT_ADMIN,
            UserRole.UNIVERSITY_ADMIN,
            UserRole.PLATFORM_ADMIN,
        ]:
            if not target_reg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Target student registration number is required for administrative lookup.",
                )

            # Resolve target student tenant evidence across authoritative collections
            auth_db = db.client[settings.MONGODB_DB_NAME]
            u_call = auth_db[USERS_COLLECTION].find_one({"registration_number": target_reg})
            student_user = await u_call if hasattr(u_call, "__await__") else (u_call if isinstance(u_call, dict) else None)

            p_call = db[PROFILES_COLLECTION].find_one({"registration_number": target_reg})
            student_profile = await p_call if hasattr(p_call, "__await__") else (p_call if isinstance(p_call, dict) else None)

            student_asgn = None
            if not student_user and not student_profile:
                a_call = db[ASSIGNMENTS_COLLECTION].find_one({"student_registration_number": target_reg})
                student_asgn = await a_call if hasattr(a_call, "__await__") else (a_call if isinstance(a_call, dict) else None)
                if not student_asgn:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Student registration number '{target_reg}' not found.",
                    )

            if current_user.role != UserRole.PLATFORM_ADMIN:
                inst_sources = []
                dept_sources = []

                if student_user:
                    if student_user.get("institution_id"):
                        inst_sources.append(("users", _clean_str(student_user.get("institution_id")).upper()))
                    if student_user.get("department"):
                        dept_sources.append(("users", _clean_str(student_user.get("department")).lower()))

                if student_profile:
                    if student_profile.get("institution_id"):
                        inst_sources.append(("student_profiles", _clean_str(student_profile.get("institution_id")).upper()))
                    if student_profile.get("department"):
                        dept_sources.append(("student_profiles", _clean_str(student_profile.get("department")).lower()))

                if student_asgn:
                    if student_asgn.get("institution_id"):
                        inst_sources.append(("assignments", _clean_str(student_asgn.get("institution_id")).upper()))
                    if student_asgn.get("department"):
                        dept_sources.append(("assignments", _clean_str(student_asgn.get("department")).lower()))

                # Fail closed if authoritative sources conflict on institution
                distinct_insts = {val for _, val in inst_sources if val}
                if len(distinct_insts) > 1:
                    logger.warning("Conflicting institution evidence for student %s: %s", target_reg, distinct_insts)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: Conflicting institution records for student.",
                    )

                target_inst = next(iter(distinct_insts), None)
                if not target_inst:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: Target student institution cannot be verified.",
                    )

                admin_inst = _clean_str(current_user.institution_id or "VFSTR").upper()
                if admin_inst != target_inst:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: Cross-institution access is strictly prohibited.",
                    )

                # Department-level isolation for DEPARTMENT_ADMIN and FACULTY
                if current_user.role in [UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY]:
                    distinct_depts = {val for _, val in dept_sources if val}
                    if len(distinct_depts) > 1:
                        logger.warning("Conflicting department evidence for student %s: %s", target_reg, distinct_depts)
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: Conflicting department records for student.",
                        )

                    target_dept = next(iter(distinct_depts), None)
                    if not target_dept:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: Target student department cannot be verified.",
                        )

                    admin_dept = _clean_str(current_user.department).lower()
                    if admin_dept and admin_dept != target_dept:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: Student belongs to another department.",
                        )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )

        # 1. Fetch Profile Info
        profile = await cls.get_or_create_student_profile(db=db, user=current_user, target_reg_no=target_reg)

        # 2. Fetch Completed Evaluations
        records = await cls.get_student_completed_evaluations(db=db, student_reg_no=target_reg)

        # 3. Derive Recommendation
        recommendation = cls.calculate_level_recommendation(records=records, profile=profile)

        # 4. Derive Topic Mastery
        topic_mastery = cls.aggregate_topic_mastery(records=records)

        # 5. Build Recent History Summary with safe parsing
        scores: List[float] = []
        for r in records:
            sc = r.get("scorecard")
            if isinstance(sc, dict):
                s = safe_parse_score(sc.get("overall_score"), 0.0, 10.0)
                if s is not None:
                    scores.append(s)

        trend, _ = cls.calculate_trend_and_consistency(scores)

        recent_history: List[InterviewHistorySummaryItem] = []
        for r in reversed(records[-10:]):  # Most recent first
            sc = r.get("scorecard") or {}
            sess = r.get("session") or {}
            asgn = r.get("assignment") or {}
            int_doc = r.get("interview") or {}
            asgn_id = asgn.get("assignment_id") or sess.get("assignment_id") or sc.get("session_id") or "mock-asgn"

            parsed_overall = safe_parse_score(sc.get("overall_score"), 0.0, 10.0)
            if parsed_overall is None:
                continue

            parsed_pct = safe_parse_score(sc.get("percentage_score"), 0.0, 100.0)
            if parsed_pct is None:
                parsed_pct = round(parsed_overall * 10.0, 1)

            # Derive dominant difficulty for this interview
            diff_prog = sc.get("difficulty_progression") or [sess.get("current_difficulty") or "medium"]
            dominant_diff = diff_prog[-1] if diff_prog else "medium"
            level_label = DIFFICULTY_TO_LEVEL_MAP.get(dominant_diff, RecommendationLevel.INTERMEDIATE).value

            responses = r.get("responses", [])
            answered = len([x for x in responses if not x.get("is_skipped") and x.get("status") != "skipped"])
            skipped = len([x for x in responses if x.get("is_skipped") or x.get("status") == "skipped"])

            recent_history.append(
                InterviewHistorySummaryItem(
                    assignment_id=asgn_id,
                    session_id=sess.get("session_id") or asgn_id,
                    interview_id=sc.get("interview_id") or sess.get("interview_id") or "int-mock",
                    interview_title=int_doc.get("title") or f"Technical Mock Interview — {r['selected_role']}",
                    selected_role=r["selected_role"],
                    completed_at=r["completed_at"],
                    overall_score=round(parsed_overall, 1),
                    percentage_score=round(parsed_pct, 1),
                    performance_level=sc.get("performance_level") or "Competent",
                    difficulty_level=level_label,
                    difficulty_progression=diff_prog,
                    total_questions=len(responses) or 5,
                    answered_questions=answered or len(responses),
                    skipped_questions=skipped,
                    report_url=f"/report/{asgn_id}",
                )
            )

        highest = max(scores) if scores else None
        lowest = min(scores) if scores else None

        return StudentPerformanceSummaryResponse(
            profile=profile,
            recommendation=recommendation,
            total_completed_interviews=len(records),
            latest_score=recommendation.latest_score,
            historical_average_score=recommendation.average_score,
            highest_score=highest,
            lowest_score=lowest,
            trend=trend,
            topic_mastery=topic_mastery,
            recent_history=recent_history,
        )

    @classmethod
    async def get_student_interview_history(
        cls,
        db: AsyncIOMotorDatabase,
        current_user: UserInDB,
        target_registration_number: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> PaginatedInterviewHistoryResponse:
        """
        Retrieves paginated completed interview history for a student.
        """
        summary = await cls.get_student_performance_summary(
            db=db,
            current_user=current_user,
            target_registration_number=target_registration_number,
        )
        all_items = summary.recent_history
        total = len(all_items)
        paginated_items = all_items[skip : skip + limit]

        return PaginatedInterviewHistoryResponse(
            items=paginated_items,
            total=total,
            skip=skip,
            limit=limit,
        )

    @classmethod
    async def get_faculty_student_tracking(
        cls,
        db: AsyncIOMotorDatabase,
        current_reviewer: UserInDB,
        department: Optional[str] = None,
        batch_cohort: Optional[str] = None,
        role: Optional[str] = None,
        recommended_level: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> PaginatedStudentTrackingResponse:
        """
        Provides authorized faculty and administrators with multi-tenant filtered
        student performance and level recommendation tracking.
        Optimized with bounded base pagination and batch queries to eliminate N+1 latency.
        """
        if current_reviewer.role not in [
            UserRole.PLATFORM_ADMIN,
            UserRole.UNIVERSITY_ADMIN,
            UserRole.DEPARTMENT_ADMIN,
            UserRole.FACULTY,
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for student tracking.",
            )

        # Validate pagination bounds
        safe_skip = max(0, skip)
        safe_limit = max(1, min(limit, 50))

        auth_db = db.client[settings.MONGODB_DB_NAME]

        # Base query for student accounts
        query: Dict[str, Any] = {"role": UserRole.STUDENT.value}

        # Multi-tenancy Scoping:
        if current_reviewer.role in [UserRole.UNIVERSITY_ADMIN, UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY]:
            query["institution_id"] = current_reviewer.institution_id or "VFSTR"

        if current_reviewer.role in [UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY]:
            if current_reviewer.department:
                query["department"] = current_reviewer.department

        # Additional query filters
        if department and current_reviewer.role in [UserRole.PLATFORM_ADMIN, UserRole.UNIVERSITY_ADMIN]:
            query["department"] = department
        if batch_cohort:
            query["batch_cohort"] = batch_cohort

        if search and search.strip():
            s = search.strip()
            query["$or"] = [
                {"registration_number": {"$regex": s, "$options": "i"}},
                {"full_name": {"$regex": s, "$options": "i"}},
                {"email": {"$regex": s, "$options": "i"}},
            ]

        # Total count for pagination metadata (fast count query)
        count_call = auth_db[USERS_COLLECTION].count_documents(query)
        total = await count_call if hasattr(count_call, "__await__") else count_call

        # Fetch only the paginated slice of students using database skip and limit
        cursor = auth_db[USERS_COLLECTION].find(query)
        if hasattr(cursor, "sort") and callable(cursor.sort):
            cursor = cursor.sort("registration_number", pymongo.ASCENDING)
        if hasattr(cursor, "skip") and callable(cursor.skip):
            cursor = cursor.skip(safe_skip)
        if hasattr(cursor, "limit") and callable(cursor.limit):
            cursor = cursor.limit(safe_limit)

        if hasattr(cursor, "to_list"):
            res = cursor.to_list(length=safe_limit)
            students = await res if hasattr(res, "__await__") else res
        elif hasattr(cursor, "__await__"):
            students = await cursor
        else:
            students = cursor

        if not isinstance(students, list):
            students = []

        if not students:
            return PaginatedStudentTrackingResponse(
                items=[],
                total=total,
                skip=safe_skip,
                limit=safe_limit,
                filters_applied={
                    "department": department or (current_reviewer.department if current_reviewer.role in [UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY] else None),
                    "batch_cohort": batch_cohort,
                    "role": role,
                    "recommended_level": recommended_level,
                    "search": search,
                },
            )

        # Collect registration numbers for this paginated slice
        page_regs = [_clean_reg(st.get("registration_number")) for st in students if st.get("registration_number")]
        page_regs = [r for r in page_regs if r]

        # BATCH 1: Fetch profiles for this page in a single query
        profiles_by_reg: Dict[str, Dict[str, Any]] = {}
        if page_regs:
            p_cursor = db[PROFILES_COLLECTION].find({"registration_number": {"$in": page_regs}})
            if hasattr(p_cursor, "to_list"):
                p_res = p_cursor.to_list(length=len(page_regs))
                profiles = await p_res if hasattr(p_res, "__await__") else p_res
            elif hasattr(p_cursor, "__await__"):
                profiles = await p_cursor
            else:
                profiles = p_cursor
            if isinstance(profiles, list):
                profiles_by_reg = {
                    _clean_reg(p.get("registration_number")): p
                    for p in profiles if p.get("registration_number")
                }

        # BATCH 2: Fetch scorecards for this page's students in a single query
        scorecards: List[Dict[str, Any]] = []
        if page_regs:
            sc_cursor = db[SCORECARDS_COLLECTION].find({"student_registration_number": {"$in": page_regs}})
            if hasattr(sc_cursor, "sort") and callable(sc_cursor.sort):
                sc_cursor = sc_cursor.sort("created_at", pymongo.ASCENDING)
            if hasattr(sc_cursor, "to_list"):
                sc_res = sc_cursor.to_list(length=len(page_regs) * 50)
                scorecards = await sc_res if hasattr(sc_res, "__await__") else sc_res
            elif hasattr(sc_cursor, "__await__"):
                scorecards = await sc_cursor
            else:
                scorecards = sc_cursor
        if not isinstance(scorecards, list):
            scorecards = []

        # Collect session_ids from scorecards
        page_session_ids = list({sc["session_id"] for sc in scorecards if sc.get("session_id")})

        # BATCH 3: Fetch sessions for these scorecards
        sessions_by_id: Dict[str, Dict[str, Any]] = {}
        if page_session_ids:
            sess_cursor = db[SESSIONS_COLLECTION].find({"session_id": {"$in": page_session_ids}})
            if hasattr(sess_cursor, "to_list"):
                sess_res = sess_cursor.to_list(length=len(page_session_ids))
                sessions_list = await sess_res if hasattr(sess_res, "__await__") else sess_res
            elif hasattr(sess_cursor, "__await__"):
                sessions_list = await sess_cursor
            else:
                sessions_list = sess_cursor
            if isinstance(sessions_list, list):
                sessions_by_id = {s["session_id"]: s for s in sessions_list if s.get("session_id")}

        completed_session_ids = {
            sid for sid, s in sessions_by_id.items()
            if s.get("session_status") == SessionStatus.COMPLETED.value
        }

        # BATCH 4 & 5: Fetch assignments and interviews for completed sessions
        assignment_ids = list({
            sessions_by_id[sid].get("assignment_id")
            for sid in completed_session_ids if sessions_by_id[sid].get("assignment_id")
        })
        assignments_by_id: Dict[str, Dict[str, Any]] = {}
        if assignment_ids:
            asgn_cursor = db[ASSIGNMENTS_COLLECTION].find({"assignment_id": {"$in": assignment_ids}})
            if hasattr(asgn_cursor, "to_list"):
                asgn_res = asgn_cursor.to_list(length=len(assignment_ids))
                asgns_list = await asgn_res if hasattr(asgn_res, "__await__") else asgn_res
            elif hasattr(asgn_cursor, "__await__"):
                asgns_list = await asgn_cursor
            else:
                asgns_list = asgn_cursor
            if isinstance(asgns_list, list):
                assignments_by_id = {a["assignment_id"]: a for a in asgns_list if a.get("assignment_id")}

        interview_ids = list({
            sessions_by_id[sid].get("interview_id")
            for sid in completed_session_ids if sessions_by_id[sid].get("interview_id")
        })
        interviews_by_id: Dict[str, Dict[str, Any]] = {}
        if interview_ids:
            int_cursor = db[INTERVIEWS_COLLECTION].find({"interview_id": {"$in": interview_ids}})
            if hasattr(int_cursor, "to_list"):
                int_res = int_cursor.to_list(length=len(interview_ids))
                ints_list = await int_res if hasattr(int_res, "__await__") else int_res
            elif hasattr(int_cursor, "__await__"):
                ints_list = await int_cursor
            else:
                ints_list = int_cursor
            if isinstance(ints_list, list):
                interviews_by_id = {i["interview_id"]: i for i in ints_list if i.get("interview_id")}

        # BATCH 6: Fetch responses for completed sessions
        responses_by_session: Dict[str, List[Dict[str, Any]]] = {}
        if completed_session_ids:
            resp_cursor = db[RESPONSES_COLLECTION].find({"session_id": {"$in": list(completed_session_ids)}})
            if hasattr(resp_cursor, "sort") and callable(resp_cursor.sort):
                resp_cursor = resp_cursor.sort("question_index", pymongo.ASCENDING)
            if hasattr(resp_cursor, "to_list"):
                resp_res = resp_cursor.to_list(length=len(completed_session_ids) * 50)
                resps_list = await resp_res if hasattr(resp_res, "__await__") else resp_res
            elif hasattr(resp_cursor, "__await__"):
                resps_list = await resp_cursor
            else:
                resps_list = resp_cursor
            if isinstance(resps_list, list):
                for r in resps_list:
                    sid = r.get("session_id")
                    if sid:
                        responses_by_session.setdefault(sid, []).append(r)

        # Group scorecards: student_reg -> session_id -> list of scorecards
        student_session_sc: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for sc in scorecards:
            reg = _clean_reg(sc.get("student_registration_number"))
            sid = sc.get("session_id")
            if reg and sid and sid in completed_session_ids:
                student_session_sc.setdefault(reg, {}).setdefault(sid, []).append(sc)

        # Assemble evaluations and recommendations per student on page
        tracking_items: List[StudentTrackingAdminItem] = []

        for st in students:
            reg_no = _clean_reg(st.get("registration_number"))
            if not reg_no:
                continue

            p_doc = profiles_by_reg.get(reg_no, {})
            target_role = p_doc.get("target_role") or "Associate Software Engineer"
            if role and role.strip() and target_role.lower() != role.strip().lower():
                continue

            # Build deduplicated completed evaluations for this student
            sessions_map = student_session_sc.get(reg_no, {})
            student_records: List[Dict[str, Any]] = []

            for sid, sc_list in sessions_map.items():
                sess = sessions_by_id.get(sid)
                if not sess:
                    continue

                chosen_sc: Optional[Dict[str, Any]] = None
                if len(sc_list) == 1:
                    chosen_sc = sc_list[0]
                else:
                    final_sc_id = sess.get("final_scorecard_id")
                    if final_sc_id:
                        for sc in sc_list:
                            if sc.get("scorecard_id") == final_sc_id:
                                chosen_sc = sc
                                break
                    if not chosen_sc:
                        final_marked = [sc for sc in sc_list if sc.get("is_final") is True]
                        if len(final_marked) == 1:
                            chosen_sc = final_marked[0]
                    if not chosen_sc:
                        valid_scores = [safe_parse_score(sc.get("overall_score"), 0.0, 10.0) for sc in sc_list]
                        all_scores_agree = (
                            len(valid_scores) == len(sc_list)
                            and all(s is not None for s in valid_scores)
                            and len(set(valid_scores)) == 1
                        )
                        if all_scores_agree:
                            chosen_sc = max(
                                sc_list,
                                key=lambda s: s.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
                            )
                        else:
                            timestamps = [s.get("created_at") for s in sc_list]
                            if all(ts is not None for ts in timestamps) and len(set(timestamps)) == len(timestamps):
                                chosen_sc = max(sc_list, key=lambda s: s.get("created_at"))
                            else:
                                logger.warning(
                                    "Ambiguous conflicting duplicate scorecards for session %s; excluding.", sid
                                )
                                continue

                if not chosen_sc:
                    continue

                if safe_parse_score(chosen_sc.get("overall_score"), 0.0, 10.0) is None:
                    continue

                asgn = assignments_by_id.get(sess.get("assignment_id"))
                int_doc = interviews_by_id.get(chosen_sc.get("interview_id") or sess.get("interview_id"))

                sel_role = (
                    (asgn.get("selected_role") if asgn else None)
                    or sess.get("selected_role")
                    or (int_doc.get("role") if int_doc else None)
                    or "Associate Software Engineer"
                )
                comp_at = chosen_sc.get("created_at") or sess.get("completed_at") or utc_now()

                student_records.append({
                    "scorecard": chosen_sc,
                    "session": sess,
                    "assignment": asgn,
                    "interview": int_doc,
                    "selected_role": sel_role,
                    "completed_at": comp_at,
                    "responses": responses_by_session.get(sid, []),
                })

            student_records.sort(
                key=lambda r: r.get("completed_at") or datetime.min.replace(tzinfo=timezone.utc)
            )

            profile_info = StudentProfileInfo(
                registration_number=reg_no,
                full_name=st.get("full_name") or "Student",
                email=st.get("email") or f"{reg_no.lower()}@vignan.ac.in",
                institution_id=st.get("institution_id", "VFSTR"),
                department=st.get("department"),
                batch_cohort=st.get("batch_cohort"),
                section=st.get("section"),
                target_role=target_role,
            )

            rec = cls.calculate_level_recommendation(records=student_records, profile=profile_info)

            if recommended_level and recommended_level.strip():
                if rec.recommended_level.value.lower() != recommended_level.strip().lower():
                    continue

            last_interview_at = student_records[-1]["completed_at"] if student_records else None

            tracking_items.append(
                StudentTrackingAdminItem(
                    registration_number=reg_no,
                    full_name=st.get("full_name") or "Student",
                    email=st.get("email") or f"{reg_no.lower()}@vignan.ac.in",
                    institution_id=st.get("institution_id", "VFSTR"),
                    department=st.get("department"),
                    batch_cohort=st.get("batch_cohort"),
                    section=st.get("section"),
                    target_role=target_role,
                    completed_interviews_count=len(student_records),
                    latest_score=rec.latest_score,
                    average_score=rec.average_score,
                    trend=rec.score_trend,
                    recommended_level=rec.recommended_level,
                    recommendation_status=rec.status,
                    evidence_sufficiency=rec.evidence_sufficiency,
                    last_interview_at=last_interview_at,
                )
            )

        return PaginatedStudentTrackingResponse(
            items=tracking_items,
            total=total,
            skip=safe_skip,
            limit=safe_limit,
            filters_applied={
                "department": department or (current_reviewer.department if current_reviewer.role in [UserRole.DEPARTMENT_ADMIN, UserRole.FACULTY] else None),
                "batch_cohort": batch_cohort,
                "role": role,
                "recommended_level": recommended_level,
                "search": search,
            },
        )
