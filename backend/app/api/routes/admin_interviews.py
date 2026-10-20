from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
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
from app.models.performance_tracking import (
    StudentPerformanceSummaryResponse,
    PaginatedStudentTrackingResponse,
)
from app.models.question_bank import (
    QuestionExtractionPreviewResponse,
    QuestionBatchSaveRequest,
    QuestionBatchSaveResponse,
    QuestionBankListResponse,
    QuestionSetListResponse,
    QuestionSetPreviewResponse,
)
from app.services.interview_service import InterviewService
from app.services.proctoring_service import ProctoringService
from app.services.interview_recommendation_service import InterviewRecommendationService
from app.services.question_bank_service import QuestionBankService

router = APIRouter()

# Strict RBAC guard: platform_admin, university_admin, and department_admin can manage interviews
admin_required = require_roles([UserRole.PLATFORM_ADMIN, UserRole.UNIVERSITY_ADMIN, UserRole.DEPARTMENT_ADMIN])

# Extended RBAC guard: administrators and placement faculty can review proctoring timelines and integrity decisions
proctoring_reviewer_required = require_roles([
    UserRole.PLATFORM_ADMIN,
    UserRole.UNIVERSITY_ADMIN,
    UserRole.DEPARTMENT_ADMIN,
    UserRole.FACULTY,
])


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
    department: Optional[str] = Query(None, description="Filter by department (e.g. 'CSE')"),
    batch_cohort: Optional[str] = Query(None, description="Filter by batch cohort (e.g. '2024-2028')"),
    eligibility: Optional[str] = Query(None, description="Filter by eligibility ('all', 'eligible', 'ineligible')"),
    search: Optional[str] = Query(None, description="Filter by roll number, student name, or email"),
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
        department=department,
        batch_cohort=batch_cohort,
        eligibility=eligibility,
        search=search,
        limit=limit,
        current_admin=current_admin,
    )

# ==============================================================================
# Institution Question Bank Management APIs (Faculty & Administration)
# ==============================================================================

@router.post("/questions/preview", response_model=QuestionExtractionPreviewResponse)
async def preview_question_file(
    file: UploadFile = File(...),
    default_topic: str = Form("Technical Assessment"),
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
):
    """
    Parses an uploaded question file (PDF, CSV, JSON, TXT, MD, ZIP) and generates
    an extraction preview for faculty review, inline editing, and validation.
    Does NOT save to database and does NOT schedule interviews.
    """
    MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Question file exceeds maximum permitted size of 15 MB (received {len(content) / (1024*1024):.1f} MB)",
        )

    return QuestionBankService.preview_uploaded_file(
        file_bytes=content,
        filename=file.filename or "uploaded_questions.pdf",
        default_topic=default_topic,
    )


@router.post("/questions/save", response_model=QuestionBatchSaveResponse)
async def save_confirmed_questions(
    data: QuestionBatchSaveRequest,
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Commits confirmed questions into the institution-scoped question bank.
    Enforces multi-tenant institutional isolation boundaries.
    Does NOT auto-assign candidates or schedule interviews.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await QuestionBankService.save_confirmed_questions(
        db=db,
        data=data,
        current_user=current_reviewer,
    )


@router.get("/questions", response_model=QuestionBankListResponse)
async def list_institution_questions(
    role: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    interview_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Lists stored questions accessible within the authenticated reviewer's institutional scope.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await QuestionBankService.list_questions(
        db=db,
        current_user=current_reviewer,
        role=role,
        topic=topic,
        difficulty=difficulty,
        interview_id=interview_id,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/question-sets", response_model=QuestionSetListResponse)
async def list_question_sets(
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Lists platform and institution question sets accessible to the reviewer.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await QuestionBankService.list_question_sets(
        db=db,
        current_user=current_reviewer,
    )


@router.get("/question-sets/{set_id}/preview", response_model=QuestionSetPreviewResponse)
async def preview_question_set(
    set_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves preview metadata and sample questions for a selected question set.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await QuestionBankService.preview_question_set(
        db=db,
        set_id=set_id,
        current_user=current_reviewer,
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
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """Retrieves proctoring event timeline and integrity metrics for admin and faculty review."""
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await ProctoringService.get_session_timeline(
        db=db,
        session_id=session_id,
        current_user=current_reviewer,
    )


@router.patch("/sessions/{session_id}/proctoring-review")
async def update_session_proctoring_review(
    session_id: str,
    data: UpdateProctoringReviewRequest,
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
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
        admin_user=current_reviewer,
    )


# ==============================================================================
# Student Performance Tracking & Level Recommendation APIs (Faculty & Admin)
# ==============================================================================

@router.get("/students/tracking", response_model=PaginatedStudentTrackingResponse)
async def list_students_performance_tracking(
    department: Optional[str] = Query(None),
    batch_cohort: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    recommended_level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves paginated student performance tracking and personalized level recommendations
    within the authenticated administrator's or faculty member's institutional scope.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewRecommendationService.get_faculty_student_tracking(
        db=db,
        current_reviewer=current_reviewer,
        department=department,
        batch_cohort=batch_cohort,
        role=role,
        recommended_level=recommended_level,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/students/{registration_number}/progress", response_model=StudentPerformanceSummaryResponse)
async def get_student_performance_progress(
    registration_number: str,
    current_reviewer: UserInDB = Depends(proctoring_reviewer_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves an authorized student's detailed progress summary, topic mastery,
    and level recommendation within institutional multi-tenant bounds.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewRecommendationService.get_student_performance_summary(
        db=db,
        current_user=current_reviewer,
        target_registration_number=registration_number,
    )
