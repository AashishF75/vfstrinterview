from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import get_interview_database
from app.api.deps import require_roles
from app.models.user import UserInDB, UserRole
from app.models.interview import (
    StudentAssignmentResponse,
    AssignmentStatus,
)
from app.services.interview_service import InterviewService

router = APIRouter()

student_required = require_roles([UserRole.STUDENT])


def _resolve_student_registration_number(student: UserInDB) -> str:
    """
    Safely resolves the student's verified registration number from their authenticated identity.
    Fails closed if the student account does not have a verified registration number.
    Never trusts client-supplied query parameters or headers for authorization.
    """
    reg = student.registration_number
    if not reg or not reg.strip() or reg.strip().upper() in ["#N/A", "NA", "N/A"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student account is not linked to a verified university registration number",
        )
    return reg.strip().upper()


@router.get("/my-assignments", response_model=List[StudentAssignmentResponse])
async def list_my_assignments(
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves all university interview assignments strictly belonging to the authenticated student.
    Guarantees cross-student isolation.
    """
    student_reg = _resolve_student_registration_number(current_student)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.list_student_assignments(db=db, student_reg_no=student_reg)


@router.get("/my-assignments/{assignment_id}", response_model=StudentAssignmentResponse)
async def get_my_assignment_detail(
    assignment_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves a single interview assignment.
    Enforces that the assignment belongs strictly to the authenticated student.
    """
    student_reg = _resolve_student_registration_number(current_student)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.get_student_assignment_detail(
        db=db,
        assignment_id=assignment_id,
        student_reg_no=student_reg,
    )


@router.patch("/my-assignments/{assignment_id}/accept", response_model=StudentAssignmentResponse)
async def accept_assignment(
    assignment_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Student accepts an assigned interview."""
    student_reg = _resolve_student_registration_number(current_student)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.transition_assignment_status(
        db=db,
        assignment_id=assignment_id,
        target_status=AssignmentStatus.ACCEPTED,
        student_reg_no=student_reg,
    )


@router.patch("/my-assignments/{assignment_id}/start", response_model=StudentAssignmentResponse)
async def start_interview(
    assignment_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Student starts an interview (transitions assignment to in_progress)."""
    student_reg = _resolve_student_registration_number(current_student)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.transition_assignment_status(
        db=db,
        assignment_id=assignment_id,
        target_status=AssignmentStatus.IN_PROGRESS,
        student_reg_no=student_reg,
    )


@router.patch("/my-assignments/{assignment_id}/complete", response_model=StudentAssignmentResponse)
async def complete_interview(
    assignment_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Student completes an interview (transitions assignment from in_progress to completed)."""
    student_reg = _resolve_student_registration_number(current_student)
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.transition_assignment_status(
        db=db,
        assignment_id=assignment_id,
        target_status=AssignmentStatus.COMPLETED,
        student_reg_no=student_reg,
    )


CANONICAL_ROLES = [
    {
        "role_id": "associate-software-engineer",
        "role_name": "Associate Software Engineer",
        "description": "Foundational programming, software development fundamentals, OOP concepts, and entry-level engineering.",
        "conceptual_questions_per_set": 13,
        "coding_questions_per_set": 2,
        "total_sets": 25,
        "total_questions": 375,
    },
    {
        "role_id": "product-engineer",
        "role_name": "Product Engineer",
        "description": "End-to-end product architecture, system integration, API development, scalability, and user-centric problem solving.",
        "conceptual_questions_per_set": 13,
        "coding_questions_per_set": 2,
        "total_sets": 25,
        "total_questions": 375,
    },
    {
        "role_id": "software-development-engineer",
        "role_name": "Software Development Engineer",
        "description": "Core software engineering, algorithms, data structures, backend systems, and operational coding.",
        "conceptual_questions_per_set": 13,
        "coding_questions_per_set": 2,
        "total_sets": 25,
        "total_questions": 375,
    },
    {
        "role_id": "system-engineer",
        "role_name": "System Engineer",
        "description": "Operating systems, computer networks, system design, infrastructure engineering, and cloud deployment.",
        "conceptual_questions_per_set": 13,
        "coding_questions_per_set": 2,
        "total_sets": 25,
        "total_questions": 375,
    },
    {
        "role_id": "testing-engineer",
        "role_name": "Testing Engineer",
        "description": "Quality assurance, test automation, unit/integration/regression testing, validation methodologies, and debugging.",
        "conceptual_questions_per_set": 13,
        "coding_questions_per_set": 2,
        "total_sets": 25,
        "total_questions": 375,
    },
]

CANONICAL_ROLE_NAMES = [r["role_name"] for r in CANONICAL_ROLES]


class SelectRoleRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=100)


@router.get("/roles")
async def list_available_job_roles():
    """
    Returns the supported job roles derived from the official role question bank.
    Includes conceptual and coding question breakdowns per set.
    """
    return {
        "roles": CANONICAL_ROLES,
        "total_roles": len(CANONICAL_ROLES),
        "total_questions_in_bank": 1875,
    }


@router.post("/select-role", response_model=StudentAssignmentResponse)
async def select_job_role_and_create_assignment(
    payload: SelectRoleRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Allows a student (general or institutional) to select one of the five canonical job roles,
    binding or retrieving an interview assignment for that role.
    Prevents duplicate active assignments and strictly enforces cross-student isolation.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )

    student_reg = _resolve_student_registration_number(current_student)

    # Match role case-insensitively against canonical list
    target_role = payload.role.strip()
    matched_role = None
    for r in CANONICAL_ROLE_NAMES:
        if r.lower() == target_role.lower():
            matched_role = r
            break

    if not matched_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported role '{payload.role}'. Supported roles: {', '.join(CANONICAL_ROLE_NAMES)}",
        )

    now = datetime.now(timezone.utc)

    # 1. Check if the student already has an active assignment for this specific role
    existing_assignment = await db["student_interview_assignments"].find_one({
        "student_registration_number": student_reg,
        "selected_role": matched_role,
        "status": {"$in": [
            AssignmentStatus.ASSIGNED.value,
            AssignmentStatus.ACCEPTED.value,
            AssignmentStatus.IN_PROGRESS.value,
        ]}
    })

    if existing_assignment:
        parent_int = await db["university_interviews"].find_one(
            {"interview_id": existing_assignment["interview_id"]},
            {"_id": 0}
        )
        parent_int = parent_int or {}
        return StudentAssignmentResponse(
            assignment_id=existing_assignment["assignment_id"],
            interview_id=existing_assignment["interview_id"],
            interview_title=parent_int.get("title", f"Adaptive Technical Interview — {matched_role}"),
            interview_instructions=parent_int.get("instructions", f"Technical mock interview for {matched_role}."),
            scheduled_start_time=parent_int.get("scheduled_start_time", now),
            scheduled_end_time=parent_int.get("scheduled_end_time", now + timedelta(days=90)),
            duration_minutes=parent_int.get("duration_minutes", 45),
            student_registration_number=existing_assignment["student_registration_number"],
            student_email=existing_assignment.get("student_email", current_student.email),
            selected_role=matched_role,
            section=existing_assignment.get("section", "General"),
            status=AssignmentStatus(existing_assignment["status"]),
            assigned_at=existing_assignment["assigned_at"],
            accepted_at=existing_assignment.get("accepted_at"),
            started_at=existing_assignment.get("started_at"),
            completed_at=existing_assignment.get("completed_at"),
            cancelled_at=existing_assignment.get("cancelled_at"),
            cancellation_reason=existing_assignment.get("cancellation_reason"),
        )

    # 2. Ensure parent interview definition exists in university_interviews
    interview_doc = await db["university_interviews"].find_one({
        "role": matched_role
    })

    if not interview_doc:
        int_id = f"interview-{uuid.uuid4().hex[:12]}"
        interview_doc = {
            "interview_id": int_id,
            "title": f"Adaptive Technical Interview — {matched_role}",
            "description": f"Adaptive technical interview for {matched_role} based on official question bank.",
            "instructions": (
                f"Comprehensive 5-question adaptive technical interview for {matched_role}. "
                "Covers conceptual principles, architecture, and coding questions from the university question bank."
            ),
            "role": matched_role,
            "scheduled_start_time": now - timedelta(minutes=5),
            "scheduled_end_time": now + timedelta(days=90),
            "duration_minutes": 45,
            "status": "scheduled",
            "created_by_user_id": str(current_student.id),
            "created_by_email": current_student.email,
            "created_at": now,
            "updated_at": now,
        }
        await db["university_interviews"].insert_one(interview_doc)

    interview_id = interview_doc["interview_id"]

    # 3. Create fresh assignment in student_interview_assignments
    asgn_id = f"asgn-{uuid.uuid4().hex[:12]}"
    new_asgn = {
        "assignment_id": asgn_id,
        "interview_id": interview_id,
        "student_registration_number": student_reg,
        "student_email": current_student.email,
        "student_user_id": str(current_student.id),
        "selected_role": matched_role,
        "section": getattr(current_student, "section", None) or "General",
        "status": AssignmentStatus.ACCEPTED.value,  # Set to ACCEPTED so student can enter immediately
        "assigned_by_user_id": str(current_student.id),
        "assigned_at": now,
        "accepted_at": now,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "cancellation_reason": None,
        "created_at": now,
        "updated_at": now,
    }

    await db["student_interview_assignments"].insert_one(new_asgn)

    return StudentAssignmentResponse(
        assignment_id=asgn_id,
        interview_id=interview_id,
        interview_title=interview_doc.get("title", f"Adaptive Technical Interview — {matched_role}"),
        interview_instructions=interview_doc.get("instructions", ""),
        scheduled_start_time=interview_doc.get("scheduled_start_time", now),
        scheduled_end_time=interview_doc.get("scheduled_end_time", now + timedelta(days=90)),
        duration_minutes=interview_doc.get("duration_minutes", 45),
        student_registration_number=student_reg,
        student_email=current_student.email,
        selected_role=matched_role,
        section=new_asgn.get("section"),
        status=AssignmentStatus.ACCEPTED,
        assigned_at=now,
        accepted_at=now,
    )
