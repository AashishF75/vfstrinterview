from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    CLAIMED = "claimed"
    FLAGGED = "flagged"
    PENDING_REVIEW = "pending_review"


class EmailSource(str, Enum):
    PROVIDED = "provided"
    GENERATED_PENDING_VERIFICATION = "generated_pending_verification"
    ADMIN_RESOLVED = "admin_resolved"


class ReviewGroup(str, Enum):
    READY_FOR_IMPORT = "READY_FOR_IMPORT"
    PROPOSED_UNAMBIGUOUS = "PROPOSED_UNAMBIGUOUS"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ApprovalDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class ApprovalMetadata(BaseModel):
    reviewed_by_admin_id: Optional[str] = None
    decision: ApprovalDecision = ApprovalDecision.PENDING
    reason: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_roster_value: str
    proposed_value: str
    effective_value: Optional[str] = None


class RawAuditSource(BaseModel):
    s_no: int
    page: int
    raw_roll: str
    raw_name: str
    raw_email: str
    raw_section: str


class EligibilityRecordBase(BaseModel):
    institution_id: str = "VFSTR"
    batch_cohort: str = "2024-2028"
    department: str = "CSE"
    registration_number: str
    student_name: str
    roster_email: EmailStr
    email_source: EmailSource
    section: str
    is_claimed: bool = False
    claimed_user_id: Optional[str] = None
    claimed_at: Optional[datetime] = None
    validation_status: EligibilityStatus = EligibilityStatus.ELIGIBLE
    is_eligible_for_registration: bool = True
    review_group: ReviewGroup = ReviewGroup.READY_FOR_IMPORT
    approval_metadata: Optional[ApprovalMetadata] = None
    resolution_notes: Optional[str] = None
    raw_source: RawAuditSource

    @field_validator("registration_number", mode="before")
    @classmethod
    def normalize_registration_number(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("roster_email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class EligibilityRecordCreate(EligibilityRecordBase):
    pass


class EligibilityRecordInDB(EligibilityRecordBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    import_batch_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)
