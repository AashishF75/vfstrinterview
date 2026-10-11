from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_interview_database
from app.api.deps import require_roles
from app.models.user import UserInDB, UserRole
from app.models.interview import (
    UniversityInterviewCreate,
    UniversityInterviewUpdate,
    UniversityInterviewResponse,
    CandidateSummaryResponse,
    BulkAssignmentRequest,
    BulkAssignmentResponse,
)
from app.models.proctoring import (
    ProctoringTimelineResponse,
    UpdateProctoringReviewRequest,
)
from app.services.interview_service import InterviewService
from app.services.proctoring_service import ProctoringService

router = APIRouter()

# Strict RBAC guard: only university_admin and platform_admin can access these administration routes
admin_required = require_roles([UserRole.UNIVERSITY_ADMIN, UserRole.PLATFORM_ADMIN])


@router.post("", response_model=UniversityInterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    data: UniversityInterviewCreate,
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Creates a new university-wide scheduled interview definition."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.create_interview(db=db, data=data, creator=current_admin)


@router.get("", response_model=List[UniversityInterviewResponse])
async def list_interviews(
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Lists all scheduled university interviews with aggregated assignment metrics."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.list_interviews(db=db)


@router.get("/candidates/search", response_model=List[CandidateSummaryResponse])
async def search_candidates(
    interview_id: Optional[str] = Query(None, description="Optional interview ID to check assignment status"),
    section: Optional[str] = Query(None, description="Filter by section (e.g. '1', '2')"),
    search: Optional[str] = Query(None, description="Filter by roll number or email"),
    limit: int = Query(300, ge=1, le=1000),
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Searches approved, interview-eligible candidates from the official eligibility registry."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.search_eligible_candidates(
        db=db,
        interview_id=interview_id,
        section=section,
        search=search,
        limit=limit,
    )


@router.get("/{interview_id}")
async def get_interview_detail(
    interview_id: str,
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Retrieves detailed information and assigned student roster for a specific interview."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    detail = await InterviewService.get_interview_detail(db=db, interview_id=interview_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview '{interview_id}' not found",
        )
    return detail


@router.patch("/{interview_id}", response_model=UniversityInterviewResponse)
async def update_interview(
    interview_id: str,
    data: UniversityInterviewUpdate,
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Updates interview details or cancels an interview (cascading cancellation to active assignments)."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    updated = await InterviewService.update_interview(db=db, interview_id=interview_id, update_data=data)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview '{interview_id}' not found",
        )
    return updated


@router.post("/{interview_id}/assign", response_model=BulkAssignmentResponse)
async def assign_candidates(
    interview_id: str,
    data: BulkAssignmentRequest,
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Assigns approved, eligible student candidates to a university interview.
    Validates candidates against interview_eligibility_registry, rejects quarantined candidates,
    and prevents duplicate assignments.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewService.assign_candidates(
        db=db,
        interview_id=interview_id,
        reg_numbers=data.registration_numbers,
        assigner=current_admin,
    )


@router.get("/sessions/{session_id}/proctoring-events", response_model=ProctoringTimelineResponse)
async def get_admin_session_proctoring_timeline(
    session_id: str,
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Retrieves proctoring event timeline and integrity metrics for admin review."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await ProctoringService.get_session_timeline(
        db=db,
        session_id=session_id,
        current_user=current_admin,
    )


@router.patch("/sessions/{session_id}/proctoring-review")
async def update_session_proctoring_review(
    session_id: str,
    data: UpdateProctoringReviewRequest,
    current_admin: UserInDB = Depends(admin_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Updates the administrative integrity review decision and rationale notes."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await ProctoringService.update_review_status(
        db=db,
        session_id=session_id,
        review_status=data.review_status,
        review_notes=data.review_notes,
        admin_user=current_admin,
    )
