from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InterviewStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class UniversityInterviewBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    instructions: str = Field(..., min_length=10, max_length=5000)
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    duration_minutes: int = Field(..., gt=0, le=360)
    target_cohort: Optional[str] = "2024-2028"
    target_department: Optional[str] = "CSE"


class UniversityInterviewCreate(UniversityInterviewBase):
    @model_validator(mode="after")
    def validate_schedule(self) -> "UniversityInterviewCreate":
        # 1. Enforce start time in UTC
        start = self.scheduled_start_time
        end = self.scheduled_end_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # 2. Reject past start times (allow 5 min grace for clock skew)
        now = utc_now()
        if start < now - timedelta(minutes=5):
            raise ValueError("scheduled_start_time cannot be in the past")

        # 3. Ensure end time is strictly after start time
        if end <= start:
            raise ValueError("scheduled_end_time must be strictly after scheduled_start_time")

        # 4. Duration must fit within scheduled window
        window_minutes = (end - start).total_seconds() / 60
        if self.duration_minutes > window_minutes:
            raise ValueError(
                f"duration_minutes ({self.duration_minutes}m) cannot exceed scheduled time window ({int(window_minutes)}m)"
            )

        return self


class UniversityInterviewUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = Field(None, max_length=1000)
    instructions: Optional[str] = Field(None, min_length=10, max_length=5000)
    scheduled_start_time: Optional[datetime] = None
    scheduled_end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, gt=0, le=360)
    status: Optional[InterviewStatus] = None

    @model_validator(mode="after")
    def validate_update(self) -> "UniversityInterviewUpdate":
        if self.scheduled_start_time and self.scheduled_end_time:
            if self.scheduled_end_time <= self.scheduled_start_time:
                raise ValueError("scheduled_end_time must be strictly after scheduled_start_time")
        return self


class UniversityInterviewInDB(UniversityInterviewBase):
    interview_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: InterviewStatus = InterviewStatus.SCHEDULED
    created_by_user_id: str
    created_by_email: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class UniversityInterviewResponse(BaseModel):
    interview_id: str
    title: str
    description: Optional[str] = None
    instructions: str
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    duration_minutes: int
    status: InterviewStatus
    created_by_user_id: str
    created_by_email: str
    target_cohort: Optional[str] = None
    target_department: Optional[str] = None
    total_assignments_count: int = 0
    status_counts: Dict[str, int] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentInterviewAssignmentInDB(BaseModel):
    assignment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    interview_id: str
    student_registration_number: str
    student_email: str
    student_user_id: Optional[str] = None
    eligibility_registry_id: Optional[str] = None
    section: Optional[str] = None
    status: AssignmentStatus = AssignmentStatus.ASSIGNED
    assigned_by_user_id: str
    assigned_at: datetime = Field(default_factory=utc_now)
    accepted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class StudentAssignmentResponse(BaseModel):
    assignment_id: str
    interview_id: str
    interview_title: str
    interview_instructions: str
    scheduled_start_time: datetime
    scheduled_end_time: datetime
    duration_minutes: int
    student_registration_number: str
    student_email: str
    section: Optional[str] = None
    status: AssignmentStatus
    assigned_at: datetime
    accepted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CandidateSummaryResponse(BaseModel):
    s_no: int
    registration_number: str
    email: str
    section: str
    review_status: str
    interview_eligible: bool
    batch_cohort: Optional[str] = None
    already_assigned: bool = False

    model_config = ConfigDict(from_attributes=True)


class BulkAssignmentRequest(BaseModel):
    registration_numbers: List[str] = Field(..., min_length=1, max_length=500)

    @field_validator("registration_numbers")
    @classmethod
    def clean_regs(cls, v: List[str]) -> List[str]:
        cleaned = [r.strip().upper() for r in v if r and r.strip()]
        if not cleaned:
            raise ValueError("registration_numbers list cannot be empty")
        return cleaned


class CandidateAssignmentResult(BaseModel):
    registration_number: str
    success: bool
    status: Optional[str] = None
    reason: Optional[str] = None


class BulkAssignmentResponse(BaseModel):
    interview_id: str
    total_requested: int
    assigned_count: int
    failed_count: int
    results: List[CandidateAssignmentResult]
