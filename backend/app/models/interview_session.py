from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, field_validator, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    TIMED_OUT = "timed_out"


class QuestionDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class EvaluatorMode(str, Enum):
    AI_PROVIDER = "ai_provider"
    MOCK_RULE_ENGINE = "mock_rule_engine"
    GEMINI = "gemini"
    OPENAI = "openai"
    UNAVAILABLE = "unavailable"


class InterviewSessionInDB(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    interview_id: str
    assignment_id: str
    student_registration_number: str
    student_user_id: str
    session_status: SessionStatus = SessionStatus.IN_PROGRESS
    current_question_index: int = 1
    total_questions_target: int = 5
    current_difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    expires_at: datetime
    final_scorecard_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class InterviewResponseInDB(BaseModel):
    response_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    question_index: int
    question_text: str
    difficulty: QuestionDifficulty
    topic: str
    answer_text: str
    evaluation_score: float = Field(..., ge=0.0, le=10.0)
    evaluation_feedback: str
    strengths: List[str] = Field(default_factory=list)
    improvements: List[str] = Field(default_factory=list)
    difficulty_adjustment_rationale: str
    evaluator_mode: EvaluatorMode = EvaluatorMode.MOCK_RULE_ENGINE
    evaluated_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class InterviewScorecardInDB(BaseModel):
    scorecard_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    interview_id: str
    student_registration_number: str
    overall_score: float = Field(..., ge=0.0, le=10.0)
    percentage_score: float = Field(..., ge=0.0, le=100.0)
    performance_level: str
    summary_feedback: str
    difficulty_progression: List[str] = Field(default_factory=list)
    strengths_summary: List[str] = Field(default_factory=list)
    areas_for_growth: List[str] = Field(default_factory=list)
    evaluator_mode: EvaluatorMode = EvaluatorMode.MOCK_RULE_ENGINE
    disclaimer: str = (
        "Evaluations reflect algorithmic rubrics based on user responses "
        "and do not claim objective or bias-free scoring."
    )
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# API Request / Response Models
# ==============================================================================

class StartSessionRequest(BaseModel):
    assignment_id: str


class SessionQuestionResponse(BaseModel):
    session_id: str
    assignment_id: str
    interview_title: str
    question_index: int
    total_questions: int
    difficulty: QuestionDifficulty
    question_text: str
    topic: str
    time_remaining_seconds: int
    evaluator_mode: str

    model_config = ConfigDict(from_attributes=True)


class SubmitAnswerRequest(BaseModel):
    answer_text: str = Field(..., min_length=1, max_length=5000)

    @field_validator("answer_text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Answer text cannot be blank or whitespace only")
        return cleaned


class SubmitAnswerResponse(BaseModel):
    session_id: str
    question_index: int
    evaluated_score: float
    feedback: str
    strengths: List[str]
    improvements: List[str]
    next_difficulty: QuestionDifficulty
    difficulty_rationale: str
    is_session_completed: bool
    next_question: Optional[SessionQuestionResponse] = None
    scorecard_id: Optional[str] = None
    evaluator_mode: Optional[str] = None


class ResponseSummary(BaseModel):
    question_index: int
    question_text: str
    difficulty: QuestionDifficulty
    answer_text: str
    evaluation_score: float
    feedback: str
    strengths: List[str]
    improvements: List[str]
    difficulty_adjustment_rationale: str


class ScorecardResponse(BaseModel):
    scorecard_id: str
    session_id: str
    interview_id: str
    interview_title: Optional[str] = None
    student_registration_number: str
    overall_score: float
    percentage_score: float
    performance_level: str
    summary_feedback: str
    difficulty_progression: List[str]
    strengths_summary: List[str]
    areas_for_growth: List[str]
    evaluator_mode: str
    disclaimer: str
    completed_at: datetime
    responses: List[ResponseSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
