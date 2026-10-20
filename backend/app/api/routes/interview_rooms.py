import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_interview_database
from app.api.deps import require_roles, get_current_active_user
from app.models.user import UserInDB, UserRole
from app.models.interview_session import (
    StartSessionRequest,
    SessionQuestionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    ScorecardResponse,
    StudentPerformanceReportResponse,
    UpdateVideoWatchStatusRequest,
    UpdateVideoWatchStatusResponse,
)
from app.models.voice import (
    VoiceSpeakRequest,
    VoiceTranscribeResponse,
    VoiceStatusResponse,
)
from app.models.proctoring import (
    RecordProctoringEventsRequest,
    RecordProctoringEventsResponse,
    ProctoringTimelineResponse,
)
from app.services.interview_session_service import InterviewSessionService
from app.services.proctoring_service import ProctoringService
from app.services.deepgram_service import DeepgramService

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


@router.post("/sessions/{session_id}/skip-question", response_model=SubmitAnswerResponse)
async def skip_question(
    session_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Skips the active question without assigning an answer score.
    Records the question as skipped and immediately advances to the next question,
    or finalizes the interview session if on the final question.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.skip_question(
        db=db,
        session_id=session_id,
        student_user=current_student,
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


@router.get("/sessions/{session_id}/report", response_model=StudentPerformanceReportResponse)
async def get_session_performance_report(
    session_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Retrieves the comprehensive student performance report for a session.
    Students access only their own report.
    Administrators and faculty can access for academic review.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    return await InterviewSessionService.get_performance_report_by_session(
        db=db,
        session_id=session_id,
        user=current_user,
    )


@router.patch(
    "/sessions/{session_id}/videos/{resource_id}/watch",
    response_model=UpdateVideoWatchStatusResponse,
)
async def update_session_video_watch_status(
    session_id: str,
    resource_id: str,
    payload: Optional[UpdateVideoWatchStatusRequest] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Student-authorized action to mark or unmark a recommended video as watched using session_id:
    - Resolves the parent assignment and delegates to InterviewSessionService.update_video_watch_status_by_session.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    watched = payload.watched if payload is not None else True
    return await InterviewSessionService.update_video_watch_status_by_session(
        db=db,
        session_id=session_id,
        resource_id=resource_id,
        watched=watched,
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


async def _verify_active_student_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
    student_user: UserInDB,
) -> dict:
    """Verifies that the session exists, belongs to the calling student, and is in progress."""
    clean_reg = (student_user.registration_number or "").strip().upper()
    if not clean_reg:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student account is not linked to a verified university registration number",
        )
    col = db["interview_sessions"]
    res = col.find_one({"session_id": session_id})
    session = await res if hasattr(res, "__await__") else res
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
    if session.get("session_status") != "in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is already {session.get('session_status')}. Voice actions are only permitted for active interview sessions.",
        )
    return session


@router.get("/sessions/{session_id}/voice/status", response_model=VoiceStatusResponse)
async def get_voice_status(
    session_id: str,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Checks if Deepgram voice capabilities (STT & TTS) are configured and available.
    Verifies session ownership before returning provider configuration state.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    await _verify_active_student_session(db, session_id, current_student)
    return VoiceStatusResponse(
        configured=DeepgramService.is_configured(),
        stt_model=settings.DEEPGRAM_STT_MODEL,
        tts_model=settings.DEEPGRAM_TTS_MODEL,
    )


@router.post("/sessions/{session_id}/voice/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_interview_audio(
    session_id: str,
    file: UploadFile = File(...),
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Transcribes candidate spoken answer using backend Deepgram STT service.
    Validates student ownership, file size limits (10 MB), and audio format.
    Never stores recordings persistently and never logs audio bytes or transcripts.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    await _verify_active_student_session(db, session_id, current_student)

    # Read uploaded audio into memory with size validation
    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio recording payload is empty.",
        )
    if len(audio_bytes) > settings.DEEPGRAM_MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio payload exceeds maximum permitted size of {settings.DEEPGRAM_MAX_AUDIO_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    content_type = file.content_type or "audio/webm"
    transcript, confidence, duration = await DeepgramService.transcribe_audio(
        audio_bytes=audio_bytes,
        content_type=content_type,
    )

    return VoiceTranscribeResponse(
        success=True,
        transcript=transcript,
        confidence=confidence,
        duration_seconds=duration,
    )


@router.post("/sessions/{session_id}/voice/speak")
async def synthesize_interview_speech(
    session_id: str,
    data: VoiceSpeakRequest,
    current_student: UserInDB = Depends(student_required),
    db: AsyncIOMotorDatabase = Depends(get_interview_database),
):
    """
    Synthesizes interview question text into spoken audio using Deepgram TTS service.
    Returns binary audio/mpeg stream directly without disk persistence.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interview database connection is unavailable",
        )
    await _verify_active_student_session(db, session_id, current_student)

    audio_bytes = await DeepgramService.synthesize_speech(data.text)

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Disposition": "inline; filename=speech.mp3",
        },
    )
