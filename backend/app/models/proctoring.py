from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
import uuid
from pydantic import BaseModel, Field, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProctoringEventType(str, Enum):
    # Camera / Video stream lifecycle
    CAMERA_PERMISSION_GRANTED = "camera_permission_granted"
    CAMERA_PERMISSION_DENIED = "camera_permission_denied"
    CAMERA_STREAM_CONNECTED = "camera_stream_connected"
    CAMERA_STREAM_DISCONNECTED = "camera_stream_disconnected"
    CAMERA_TRACK_ENDED = "camera_track_ended"

    # Face presence monitoring (debounced)
    FACE_NORMAL = "face_normal"
    FACE_ABSENT = "face_absent"
    MULTIPLE_FACES = "multiple_faces_detected"
    FACE_RESTORED = "face_restored"

    # Tab / Page visibility tracking
    TAB_HIDDEN = "tab_hidden"
    TAB_VISIBLE = "tab_visible"

    # Window focus tracking
    WINDOW_BLUR = "window_blur"
    WINDOW_FOCUS = "window_focus"


class ProctoringReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    FLAGGED = "flagged"
    CLEARED = "cleared"


class ProctoringEventInDB(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    assignment_id: str
    interview_id: str
    student_registration_number: str
    event_type: ProctoringEventType
    client_timestamp: datetime
    server_timestamp: datetime = Field(default_factory=utc_now)
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Ingestion API Models (Student Client -> Backend)
# ==============================================================================

class SingleProctoringEventInput(BaseModel):
    event_type: ProctoringEventType
    client_timestamp: datetime
    duration_seconds: Optional[float] = Field(None, ge=0.0, le=86400.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RecordProctoringEventsRequest(BaseModel):
    events: List[SingleProctoringEventInput] = Field(..., min_length=1, max_length=50)


class RecordProctoringEventsResponse(BaseModel):
    success: bool = True
    session_id: str
    persisted_count: int
    server_received_at: datetime


# ==============================================================================
# Reviewer API Models (Admin / Faculty Inspection)
# ==============================================================================

class ProctoringEventSummary(BaseModel):
    total_tab_hidden_count: int = 0
    total_tab_hidden_duration_seconds: float = 0.0
    total_face_absent_count: int = 0
    total_face_absent_duration_seconds: float = 0.0
    total_multiple_faces_count: int = 0
    stream_disruptions_count: int = 0
    camera_active_percentage: Optional[float] = None
    integrity_status: str = "normal"  # "normal" | "notice" | "review_suggested"
    disclaimer: str = (
        "Integrity indicators represent browser-side client telemetry events and do not "
        "constitute automated evidence of misconduct or grounds for automatic disqualification."
    )


class ProctoringTimelineItem(BaseModel):
    event_id: str
    event_type: ProctoringEventType
    client_timestamp: datetime
    server_timestamp: datetime
    duration_seconds: Optional[float] = None
    description: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProctoringTimelineResponse(BaseModel):
    session_id: str
    assignment_id: str
    student_registration_number: str
    summary: ProctoringEventSummary
    timeline: List[ProctoringTimelineItem]
    review_status: ProctoringReviewStatus = ProctoringReviewStatus.UNREVIEWED
    review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_email: Optional[str] = None


class UpdateProctoringReviewRequest(BaseModel):
    review_status: ProctoringReviewStatus
    review_notes: Optional[str] = Field(None, max_length=2000)
