from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

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
