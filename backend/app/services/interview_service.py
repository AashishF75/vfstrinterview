import logging
import uuid
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

from app.models.interview import (
    UniversityInterviewCreate,
    UniversityInterviewUpdate,
    UniversityInterviewResponse,
    UniversityInterviewInDB,
    StudentInterviewAssignmentInDB,
    StudentAssignmentResponse,
    CandidateSummaryResponse,
    BulkAssignmentRequest,
    BulkAssignmentResponse,
    CandidateAssignmentResult,
    InterviewStatus,
    AssignmentStatus,
    utc_now,
)
from app.models.user import UserInDB, UserRole
from app.services.question_bank_service import QuestionBankService

logger = logging.getLogger(__name__)

INTERVIEWS_COLLECTION = "university_interviews"
ASSIGNMENTS_COLLECTION = "student_interview_assignments"
ELIGIBILITY_COLLECTION = "interview_eligibility_registry"


class InterviewService:
    @staticmethod
    async def create_interview(
        db: AsyncIOMotorDatabase,
        data: UniversityInterviewCreate,
        creator: UserInDB,
    ) -> UniversityInterviewResponse:
        """Creates a university-wide interview definition in interview_db."""
        now = utc_now()
        interview_id = str(uuid.uuid4())

        # Revalidate question set access if selected
        if data.question_set_id:
            await QuestionBankService.validate_question_set_access(
                db=db,
                set_id=data.question_set_id,
                current_user=creator,
            )

        doc = {
            "interview_id": interview_id,
            "title": data.title.strip(),
            "description": data.description.strip() if data.description else None,
            "instructions": data.instructions.strip(),
            "scheduled_start_time": data.scheduled_start_time,
            "scheduled_end_time": data.scheduled_end_time,
            "duration_minutes": data.duration_minutes,
            "status": InterviewStatus.SCHEDULED.value,
            "created_by_user_id": str(creator.id),
            "created_by_email": str(creator.email),
            "target_cohort": data.target_cohort,
            "target_department": data.target_department,
            "question_set_id": data.question_set_id,
            "question_set_name": data.question_set_name,
            "created_at": now,
            "updated_at": now,
        }

        await db[INTERVIEWS_COLLECTION].insert_one(doc)
        logger.info(f"Created interview '{interview_id}' by {creator.email} (question_set: {data.question_set_id})")

        return UniversityInterviewResponse(
            **doc,
            total_assignments_count=0,
            status_counts={},
        )

    @staticmethod
    async def list_interviews(
        db: AsyncIOMotorDatabase,
    ) -> List[UniversityInterviewResponse]:
        """Lists all interviews with live assignment counts and status breakdown."""
        cursor = db[INTERVIEWS_COLLECTION].find({}, {"_id": 0}).sort("scheduled_start_time", pymongo.DESCENDING)
        interviews = await cursor.to_list(length=1000)

        results = []
        for doc in interviews:
            interview_id = doc["interview_id"]

            # Aggregate assignment counts
            counts_pipeline = [
                {"$match": {"interview_id": interview_id}},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]
            agg = await db[ASSIGNMENTS_COLLECTION].aggregate(counts_pipeline).to_list(length=20)
            status_counts = {item["_id"]: item["count"] for item in agg}
            total_count = sum(status_counts.values())

            results.append(
                UniversityInterviewResponse(
                    **doc,
                    total_assignments_count=total_count,
                    status_counts=status_counts,
                )
            )

        return results

    @staticmethod
    async def get_interview_detail(
        db: AsyncIOMotorDatabase,
        interview_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves interview details along with assigned student roster."""
        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": interview_id}, {"_id": 0})
        if not interview:
            return None

        # Fetch assigned students
        cursor = db[ASSIGNMENTS_COLLECTION].find({"interview_id": interview_id}, {"_id": 0}).sort("assigned_at", pymongo.ASCENDING)
        assignments = await cursor.to_list(length=2000)

        status_counts = {}
        for a in assignments:
            st = a.get("status")
            status_counts[st] = status_counts.get(st, 0) + 1

        return {
            "interview": UniversityInterviewResponse(
                **interview,
                total_assignments_count=len(assignments),
                status_counts=status_counts,
            ),
            "assignments": assignments,
        }

    @staticmethod
    async def update_interview(
        db: AsyncIOMotorDatabase,
        interview_id: str,
        update_data: UniversityInterviewUpdate,
    ) -> Optional[UniversityInterviewResponse]:
        """Updates interview details or status (e.g. cancellation)."""
        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": interview_id})
        if not interview:
            return None

        now = utc_now()
        update_fields: Dict[str, Any] = {"updated_at": now}

        if update_data.title is not None:
            update_fields["title"] = update_data.title.strip()
        if update_data.description is not None:
            update_fields["description"] = update_data.description.strip()
        if update_data.instructions is not None:
            update_fields["instructions"] = update_data.instructions.strip()
        if update_data.scheduled_start_time is not None:
            update_fields["scheduled_start_time"] = update_data.scheduled_start_time
        if update_data.scheduled_end_time is not None:
            update_fields["scheduled_end_time"] = update_data.scheduled_end_time
        if update_data.duration_minutes is not None:
            update_fields["duration_minutes"] = update_data.duration_minutes
        if update_data.status is not None:
            update_fields["status"] = update_data.status.value

            # If cancelling the interview, cascade cancellation to active assignments
            if update_data.status == InterviewStatus.CANCELLED:
                await db[ASSIGNMENTS_COLLECTION].update_many(
                    {
                        "interview_id": interview_id,
                        "status": {"$in": [AssignmentStatus.ASSIGNED.value, AssignmentStatus.ACCEPTED.value]},
                    },
                    {
                        "$set": {
                            "status": AssignmentStatus.CANCELLED.value,
                            "cancelled_at": now,
                            "cancellation_reason": "Interview cancelled by university administrator",
                            "updated_at": now,
                        }
                    },
                )

        await db[INTERVIEWS_COLLECTION].update_one({"interview_id": interview_id}, {"$set": update_fields})
        updated = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": interview_id}, {"_id": 0})

        # Aggregated counts
        agg_cursor = db[ASSIGNMENTS_COLLECTION].aggregate([
            {"$match": {"interview_id": interview_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ])
        if hasattr(agg_cursor, "to_list"):
            agg = await agg_cursor.to_list(length=20)
        else:
            agg = await agg_cursor
        status_counts = {item["_id"]: item["count"] for item in agg}

        return UniversityInterviewResponse(
            **updated,
            total_assignments_count=sum(status_counts.values()),
            status_counts=status_counts,
        )

    @staticmethod
    async def search_eligible_candidates(
        db: AsyncIOMotorDatabase,
        interview_id: Optional[str] = None,
        section: Optional[str] = None,
        department: Optional[str] = None,
        batch_cohort: Optional[str] = None,
        eligibility: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 300,
        current_admin: Optional[UserInDB] = None,
    ) -> List[CandidateSummaryResponse]:
        """
        Searches candidates from interview_eligibility_registry with multi-tenant scoping:
        - Filters by section, department, cohort, and eligibility status.
        - Restricts non-platform administrators to their institution and department.
        - Searches across registration_number, student_name, and email.
        """
        query: Dict[str, Any] = {}

        # Eligibility filter
        clean_elig = (eligibility or "eligible").strip().lower()
        if clean_elig == "eligible":
            query["review_status"] = "approved"
            query["interview_eligible"] = True
        elif clean_elig == "ineligible":
            query["$or"] = [
                {"review_status": {"$ne": "approved"}},
                {"interview_eligible": False},
            ]
        # if "all", no review_status / interview_eligible restriction

        # Multi-tenant institutional scoping
        if current_admin and current_admin.role != UserRole.PLATFORM_ADMIN:
            inst = (current_admin.institution_id or "VFSTR").strip().upper()
            query["institution_id"] = inst
            if current_admin.role == UserRole.DEPARTMENT_ADMIN and current_admin.department:
                query["department"] = current_admin.department

        if section and section.strip() and section.strip().upper() not in ["ALL", ""]:
            query["section"] = section.strip()

        if department and department.strip() and department.strip().upper() not in ["ALL", ""]:
            query["department"] = department.strip()

        if batch_cohort and batch_cohort.strip() and batch_cohort.strip().upper() not in ["ALL", ""]:
            query["batch_cohort"] = batch_cohort.strip()

        if search and search.strip():
            term = search.strip()
            regex_clause = {"$regex": re.escape(term), "$options": "i"}
            search_clause = [
                {"registration_number": regex_clause},
                {"student_name": regex_clause},
                {"student_name_raw": regex_clause},
                {"email": regex_clause},
            ]
            if "$or" in query:
                query["$and"] = [{"$or": query.pop("$or")}, {"$or": search_clause}]
            else:
                query["$or"] = search_clause

        cursor = db[ELIGIBILITY_COLLECTION].find(
            query,
            {
                "_id": 0,
                "s_no": 1,
                "registration_number": 1,
                "student_name": 1,
                "student_name_raw": 1,
                "email": 1,
                "section": 1,
                "review_status": 1,
                "interview_eligible": 1,
                "batch_cohort": 1,
                "department": 1,
                "institution_id": 1,
            },
        ).sort("s_no", pymongo.ASCENDING).limit(limit)

        candidates = await cursor.to_list(length=limit)

        # Cross-reference existing assignments if interview_id provided
        assigned_regs = set()
        if interview_id:
            assigned_cursor = db[ASSIGNMENTS_COLLECTION].find(
                {"interview_id": interview_id},
                {"student_registration_number": 1},
            )
            assigned_docs = await assigned_cursor.to_list(length=2000)
            assigned_regs = {d["student_registration_number"] for d in assigned_docs}

        results = []
        for c in candidates:
            reg = c["registration_number"]
            results.append(
                CandidateSummaryResponse(
                    s_no=c.get("s_no", 0),
                    registration_number=reg,
                    student_name=c.get("student_name") or c.get("student_name_raw") or None,
                    email=c.get("email", ""),
                    section=c.get("section", ""),
                    review_status=c.get("review_status", ""),
                    interview_eligible=bool(c.get("interview_eligible", True)),
                    batch_cohort=c.get("batch_cohort"),
                    department=c.get("department"),
                    institution_id=c.get("institution_id") or "VFSTR",
                    already_assigned=reg in assigned_regs,
                )
            )

        return results

    @staticmethod
    async def assign_candidates(
        db: AsyncIOMotorDatabase,
        interview_id: str,
        reg_numbers: List[str],
        assigner: UserInDB,
    ) -> BulkAssignmentResponse:
        """
        Assigns candidates to an interview with atomic verification:
        1. Interview must exist and not be cancelled/completed.
        2. Candidate must exist in interview_eligibility_registry with review_status='approved' and interview_eligible=True.
        3. Rejects missing, quarantined, or lateral/senior candidates.
        4. Rejects duplicates already assigned to this interview.
        5. Returns clear per-candidate results.
        """
        interview = await db[INTERVIEWS_COLLECTION].find_one({"interview_id": interview_id})
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Interview '{interview_id}' not found",
            )

        if interview["status"] in [InterviewStatus.CANCELLED.value, InterviewStatus.COMPLETED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot assign candidates to an interview with status '{interview['status']}'",
            )

        if not reg_numbers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No candidate registration numbers provided",
            )

        now = utc_now()
        results: List[CandidateAssignmentResult] = []
        assigned_count = 0
        failed_count = 0

        # Deduplicate incoming list preserving order
        unique_req_regs = []
        seen = set()
        for r in reg_numbers:
            clean = r.strip().upper()
            if clean not in seen:
                seen.add(clean)
                unique_req_regs.append(clean)

        for reg in unique_req_regs:
            # 1. Lookup student in eligibility registry
            reg_doc = await db[ELIGIBILITY_COLLECTION].find_one({"registration_number": reg})
            if not reg_doc:
                results.append(
                    CandidateAssignmentResult(
                        registration_number=reg,
                        success=False,
                        reason="STUDENT_NOT_FOUND_IN_REGISTRY",
                    )
                )
                failed_count += 1
                continue

            # 1b. Multi-tenant institutional isolation check
            user_inst = (assigner.institution_id or "VFSTR").strip().upper()
            student_inst = (reg_doc.get("institution_id") or "VFSTR").strip().upper()
            if assigner.role != UserRole.PLATFORM_ADMIN and student_inst != user_inst:
                results.append(
                    CandidateAssignmentResult(
                        registration_number=reg,
                        success=False,
                        reason=f"CROSS_INSTITUTION_UNAUTHORIZED: Student belongs to '{student_inst}', not authorized for '{user_inst}'",
                    )
                )
                failed_count += 1
                continue

            # 1c. Department-scoping check for department_admin
            if assigner.role == UserRole.DEPARTMENT_ADMIN and assigner.department:
                student_dept = reg_doc.get("department")
                if student_dept and student_dept.strip().upper() != assigner.department.strip().upper():
                    results.append(
                        CandidateAssignmentResult(
                            registration_number=reg,
                            success=False,
                            reason=f"DEPARTMENT_MISMATCH: Student belongs to '{student_dept}', not authorized for department '{assigner.department}'",
                        )
                    )
                    failed_count += 1
                    continue

            # 2. Check approval and eligibility
            if reg_doc.get("review_status") != "approved" or not reg_doc.get("interview_eligible"):
                review_reasons = reg_doc.get("review_reasons", [])
                reasons_str = ", ".join(review_reasons) if review_reasons else "QUARANTINED_OR_INELIGIBLE"
                results.append(
                    CandidateAssignmentResult(
                        registration_number=reg,
                        success=False,
                        reason=f"INELIGIBLE_CANDIDATE: {reasons_str}",
                    )
                )
                failed_count += 1
                continue

            # 3. Check duplicate assignment
            existing = await db[ASSIGNMENTS_COLLECTION].find_one(
                {"interview_id": interview_id, "student_registration_number": reg}
            )
            if existing:
                results.append(
                    CandidateAssignmentResult(
                        registration_number=reg,
                        success=False,
                        status=existing.get("status"),
                        reason="DUPLICATE_ASSIGNMENT: Student is already assigned to this interview",
                    )
                )
                failed_count += 1
                continue

            # 4. Create assignment
            assignment_id = str(uuid.uuid4())
            new_assignment = {
                "assignment_id": assignment_id,
                "interview_id": interview_id,
                "student_registration_number": reg,
                "student_email": reg_doc.get("email", ""),
                "section": reg_doc.get("section"),
                "eligibility_registry_id": str(reg_doc.get("_id", "")),
                "status": AssignmentStatus.ASSIGNED.value,
                "assigned_by_user_id": str(assigner.id),
                "assigned_at": now,
                "accepted_at": None,
                "started_at": None,
                "completed_at": None,
                "cancelled_at": None,
                "cancellation_reason": None,
                "updated_at": now,
            }

            try:
                await db[ASSIGNMENTS_COLLECTION].insert_one(new_assignment)
                results.append(
                    CandidateAssignmentResult(
                        registration_number=reg,
                        success=True,
                        status=AssignmentStatus.ASSIGNED.value,
                    )
                )
                assigned_count += 1
            except pymongo.errors.DuplicateKeyError:
                results.append(
                    CandidateAssignmentResult(
                        registration_number=reg,
                        success=False,
                        reason="DUPLICATE_ASSIGNMENT_COLLISION",
                    )
                )
                failed_count += 1

        return BulkAssignmentResponse(
            interview_id=interview_id,
            total_requested=len(reg_numbers),
            assigned_count=assigned_count,
            failed_count=failed_count,
            results=results,
        )

    @staticmethod
    async def list_student_assignments(
        db: AsyncIOMotorDatabase,
        student_reg_no: str,
    ) -> List[StudentAssignmentResponse]:
        """Lists assignments exclusively for the verified authenticated student registration number."""
        clean_reg = student_reg_no.strip().upper()
        cursor = db[ASSIGNMENTS_COLLECTION].find(
            {"student_registration_number": clean_reg},
            {"_id": 0},
        ).sort("assigned_at", pymongo.DESCENDING)
        assignments = await cursor.to_list(length=100)

        # Collect unique interview IDs to fetch parent interview details in one batch
        interview_ids = list({a["interview_id"] for a in assignments})
        interviews_cursor = db[INTERVIEWS_COLLECTION].find(
            {"interview_id": {"$in": interview_ids}},
            {"_id": 0},
        )
        interviews_list = await interviews_cursor.to_list(length=len(interview_ids))
        interviews_map = {i["interview_id"]: i for i in interviews_list}

        results = []
        for a in assignments:
            parent = interviews_map.get(a["interview_id"], {})
            results.append(
                StudentAssignmentResponse(
                    assignment_id=a["assignment_id"],
                    interview_id=a["interview_id"],
                    interview_title=parent.get("title", "Untitled Interview"),
                    interview_instructions=parent.get("instructions", "No instructions provided"),
                    scheduled_start_time=parent.get("scheduled_start_time", utc_now()),
                    scheduled_end_time=parent.get("scheduled_end_time", utc_now()),
                    duration_minutes=parent.get("duration_minutes", 60),
                    student_registration_number=a["student_registration_number"],
                    student_email=a["student_email"],
                    selected_role=a.get("selected_role"),
                    section=a.get("section"),
                    status=AssignmentStatus(a["status"]),
                    assigned_at=a["assigned_at"],
                    accepted_at=a.get("accepted_at"),
                    started_at=a.get("started_at"),
                    completed_at=a.get("completed_at"),
                    cancelled_at=a.get("cancelled_at"),
                    cancellation_reason=a.get("cancellation_reason"),
                )
            )

        return results

    @staticmethod
    async def get_student_assignment_detail(
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        student_reg_no: str,
    ) -> StudentAssignmentResponse:
        """Retrieves an assignment guaranteeing strict cross-student isolation."""
        clean_reg = student_reg_no.strip().upper()
        assignment = await db[ASSIGNMENTS_COLLECTION].find_one({"assignment_id": assignment_id}, {"_id": 0})
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview assignment not found",
            )

        # Cross-student isolation barrier
        if assignment.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view or access another student's assignment",
            )

        parent = await db[INTERVIEWS_COLLECTION].find_one(
            {"interview_id": assignment["interview_id"]},
            {"_id": 0},
        )
        parent = parent or {}

        return StudentAssignmentResponse(
            assignment_id=assignment["assignment_id"],
            interview_id=assignment["interview_id"],
            interview_title=parent.get("title", "Untitled Interview"),
            interview_instructions=parent.get("instructions", ""),
            scheduled_start_time=parent.get("scheduled_start_time", utc_now()),
            scheduled_end_time=parent.get("scheduled_end_time", utc_now()),
            duration_minutes=parent.get("duration_minutes", 60),
            student_registration_number=assignment["student_registration_number"],
            student_email=assignment.get("student_email", ""),
            selected_role=assignment.get("selected_role"),
            section=assignment.get("section"),
            status=AssignmentStatus(assignment["status"]),
            assigned_at=assignment["assigned_at"],
            accepted_at=assignment.get("accepted_at"),
            started_at=assignment.get("started_at"),
            completed_at=assignment.get("completed_at"),
            cancelled_at=assignment.get("cancelled_at"),
            cancellation_reason=assignment.get("cancellation_reason"),
        )

    @staticmethod
    async def transition_assignment_status(
        db: AsyncIOMotorDatabase,
        assignment_id: str,
        target_status: AssignmentStatus,
        student_reg_no: str,
    ) -> StudentAssignmentResponse:
        """
        Validates and transitions student assignment state:
        - ASSIGNED -> ACCEPTED
        - ACCEPTED -> IN_PROGRESS
        - IN_PROGRESS -> COMPLETED
        Rejects invalid transitions or attempts to access another student's assignment.
        """
        clean_reg = student_reg_no.strip().upper()
        assignment = await db[ASSIGNMENTS_COLLECTION].find_one({"assignment_id": assignment_id})
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

        if assignment.get("student_registration_number") != clean_reg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You cannot modify another student's assignment",
            )

        current_status = AssignmentStatus(assignment["status"])
        now = utc_now()
        update_fields: Dict[str, Any] = {"status": target_status.value, "updated_at": now}

        # Valid transitions
        if target_status == AssignmentStatus.ACCEPTED:
            if current_status != AssignmentStatus.ASSIGNED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot accept assignment in state '{current_status.value}'. Must be 'assigned'.",
                )
            update_fields["accepted_at"] = now

        elif target_status == AssignmentStatus.IN_PROGRESS:
            if current_status not in [AssignmentStatus.ACCEPTED, AssignmentStatus.ASSIGNED]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot start interview in state '{current_status.value}'.",
                )
            update_fields["started_at"] = now
            if not assignment.get("accepted_at"):
                update_fields["accepted_at"] = now

        elif target_status == AssignmentStatus.COMPLETED:
            if current_status != AssignmentStatus.IN_PROGRESS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot complete interview in state '{current_status.value}'. Must be 'in_progress'.",
                )
            update_fields["completed_at"] = now

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid student transition to state '{target_status.value}'.",
            )

        await db[ASSIGNMENTS_COLLECTION].update_one(
            {"assignment_id": assignment_id},
            {"$set": update_fields},
        )

        return await InterviewService.get_student_assignment_detail(db, assignment_id, clean_reg)
