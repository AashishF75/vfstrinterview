import logging
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_interview_database
from app.api.deps import require_roles, get_current_active_user
from app.models.user import UserInDB, UserRole
from app.models.interview_session import (
    StartSessionRequest,
    SessionQuestionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    ScorecardResponse,
)
from app.models.proctoring import (
    RecordProctoringEventsRequest,
    RecordProctoringEventsResponse,
    ProctoringTimelineResponse,
)
from app.services.interview_session_service import InterviewSessionService
from app.services.proctoring_service import ProctoringService

logger = logging.getLogger(__name__)

router = APIRouter()

student_required = require_roles([UserRole.STUDENT])


@router.post("/sessions/start", response_model=SessionQuestionResponse, status_code=status.HTTP_201_CREATED)
async def start_interview_session(
    data: StartSessionRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Starts an adaptive interview session for an assigned interview.
    Enforces student ownership, verifies scheduled interview validity,
    prevents duplicate concurrent active attempts, and generates Question 1.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.start_session(
        db=db,
        assignment_id=data.assignment_id,
        student_user=current_student,
    )


@router.get("/assignments/{assignment_id}/session")
async def get_assignment_session(
    assignment_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves the latest session (active or completed) associated with an assignment.
    Allows seamless resumption and reload of interview rooms without duplicate creation errors.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.get_session_by_assignment(
        db=db,
        assignment_id=assignment_id,
        student_user=current_student,
    )



@router.get("/sessions/{session_id}/current-question", response_model=SessionQuestionResponse)
async def get_current_question(
    session_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves the active question for an in-progress interview session.
    Verifies student ownership and enforces time limits.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.get_current_question(
        db=db,
        session_id=session_id,
        student_user=current_student,
    )


from app.models.code_execution import (
    RunCodeRequest,
    RunCodeResponse,
    SubmitCodeRequest,
)


@router.post("/sessions/{session_id}/run-code", response_model=RunCodeResponse)
async def run_interview_code(
    session_id: str,
    data: RunCodeRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Executes candidate code in an isolated sandbox for the active coding question.
    Runs against custom input or visible sample test cases.
    Does not reveal hidden evaluation test cases or advance the session.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.run_code(
        db=db,
        session_id=session_id,
        student_user=current_student,
        language=data.language,
        source_code=data.source_code,
        custom_input=data.custom_input,
    )


@router.post("/sessions/{session_id}/submit-code", response_model=SubmitAnswerResponse)
async def submit_interview_code(
    session_id: str,
    data: SubmitCodeRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Submits a final coding solution for the active coding question.
    Executes the full test suite (sample + hidden) in the sandbox,
    evaluates correctness, records metrics, and advances session state.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.submit_answer(
        db=db,
        session_id=session_id,
        answer_text=data.source_code,
        student_user=current_student,
        language=data.language,
        source_code=data.source_code,
    )


@router.post("/sessions/{session_id}/submit-answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    session_id: str,
    data: SubmitAnswerRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Submits a candidate answer. Evaluates response via the provider interface,
    applies adaptive difficulty progression, and returns either the next question
    or the finalized session scorecard reference.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.submit_answer(
        db=db,
        session_id=session_id,
        answer_text=data.answer_text or data.source_code or "",
        student_user=current_student,
        language=data.language,
        source_code=data.source_code,
    )


@router.get("/sessions/{session_id}/scorecard", response_model=ScorecardResponse)
async def get_session_scorecard(
    session_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves the completed session scorecard.
    Students can access only their own scorecard.
    Administrators and faculty can access for review and monitoring.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.get_scorecard(
        db=db,
        session_id=session_id,
        user=current_user,
    )


@router.post(
    "/sessions/{session_id}/proctoring-events",
    response_model=RecordProctoringEventsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_proctoring_events(
    session_id: str,
    data: RecordProctoringEventsRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Records a batch of Level 1 proctoring events for an active interview session.
    Enforces student ownership, validates event schema, and records server timestamps.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await ProctoringService.record_events(
        db=db,
        session_id=session_id,
        events=data.events,
        student_user=current_student,
    )


@router.get(
    "/sessions/{session_id}/proctoring-events",
    response_model=ProctoringTimelineResponse,
)
async def get_session_proctoring_timeline(
    session_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves the proctoring event timeline and summary metrics for an interview session.
    Students can access only their own session.
    Faculty and administrators can inspect any session.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await ProctoringService.get_session_timeline(
        db=db,
        session_id=session_id,
        current_user=current_user,
    )
