from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, ConfigDict

from app.models.interview_session import QuestionDifficulty


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class QuestionType(str, Enum):
    CONCEPTUAL = "conceptual"
    CODING = "coding"


class StoredQuestionItem(BaseModel):
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    interview_id: Optional[str] = None  # None indicates platform/role shared question pool
    institution_id: Optional[str] = "VFSTR"  # Multi-tenant isolation boundary
    department: Optional[str] = None  # Optional department-level scoping
    role: Optional[str] = None  # e.g. "Associate Software Engineer", "Product Engineer", etc.
    set_number: Optional[int] = None
    question_number: Optional[int] = None
    question_type: QuestionType = QuestionType.CONCEPTUAL
    topic: str = "Technical Assessment"
    difficulty: Optional[QuestionDifficulty] = None  # Explicitly None when unstated in source
    question_text: str
    expected_answer: Optional[str] = None  # Internal answer guide, never exposed as candidate prompt
    keywords: List[str] = Field(default_factory=list)
    source_filename: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_by_email: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class QuestionBankImportResult(BaseModel):
    source_file: str
    total_parsed: int
    imported_count: int
    duplicates_skipped: int
    by_role: Dict[str, int] = Field(default_factory=dict)
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_topic: Dict[str, int] = Field(default_factory=dict)
    by_difficulty: Dict[str, int] = Field(default_factory=dict)
    questions_preview: List[Dict[str, Any]] = Field(default_factory=list)


class QuestionPreviewItem(BaseModel):
    temp_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_text: str
    question_type: QuestionType = QuestionType.CONCEPTUAL
    topic: str = "Technical Assessment"
    difficulty: Optional[QuestionDifficulty] = None
    expected_answer: Optional[str] = None
    role: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    is_valid: bool = True
    validation_errors: List[str] = Field(default_factory=list)


class QuestionExtractionPreviewResponse(BaseModel):
    filename: str
    total_extracted: int
    valid_count: int
    invalid_count: int
    detected_role: Optional[str] = None
    questions: List[QuestionPreviewItem]


class QuestionBatchSaveRequest(BaseModel):
    interview_id: Optional[str] = None
    role: Optional[str] = None
    target_department: Optional[str] = None
    questions: List[QuestionPreviewItem] = Field(..., min_length=1)


class QuestionBatchSaveResponse(BaseModel):
    success: bool
    saved_count: int
    batch_id: str
    institution_id: str
    interview_id: Optional[str] = None


class QuestionBankListResponse(BaseModel):
    total: int
    items: List[StoredQuestionItem]


class QuestionSetSummary(BaseModel):
    set_id: str
    title: str
    source_type: str  # "institution" or "platform"
    institution_id: Optional[str] = "VFSTR"
    department: Optional[str] = None
    role: Optional[str] = None
    question_count: int
    topics: List[str] = Field(default_factory=list)
    difficulties: List[str] = Field(default_factory=list)
    source_filename: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by_email: Optional[str] = None


class QuestionSetListResponse(BaseModel):
    total: int
    items: List[QuestionSetSummary]


class QuestionSetPreviewResponse(BaseModel):
    set_id: str
    title: str
    source_type: str
    question_count: int
    questions: List[Dict[str, Any]]
