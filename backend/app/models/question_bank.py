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
