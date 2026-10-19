from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


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
    NEMOTRON = "nemotron"
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
    question_type: Optional[str] = "conceptual"
    time_remaining_seconds: int
    evaluator_mode: str
    coding_spec: Optional[Dict[str, Any]] = None
    # Dual compatibility fields for both flat and nested frontend consumption
    active_question: Optional[Dict[str, Any]] = None
    question: Optional[str] = None
    current_question_index: Optional[int] = None
    total_questions_target: Optional[int] = None
    current_difficulty: Optional[str] = None
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def populate_dual_compatibility_fields(self) -> "SessionQuestionResponse":
        if self.question is None:
            self.question = self.question_text
        if self.current_question_index is None:
            self.current_question_index = self.question_index
        if self.total_questions_target is None:
            self.total_questions_target = self.total_questions
        diff_str = self.difficulty.value if hasattr(self.difficulty, "value") else str(self.difficulty)
        if self.current_difficulty is None:
            self.current_difficulty = diff_str
        if self.active_question is None:
            self.active_question = {
                "question_text": self.question_text,
                "question": self.question_text,
                "topic": self.topic,
                "difficulty": diff_str,
                "question_type": self.question_type or "conceptual",
                "question_index": self.question_index,
                "total_questions": self.total_questions,
                "coding_spec": self.coding_spec,
            }
        elif "coding_spec" not in self.active_question:
            self.active_question["coding_spec"] = self.coding_spec
        return self


class SubmitAnswerRequest(BaseModel):
    answer_text: Optional[str] = Field(default=None, max_length=65536)
    language: Optional[str] = Field(default=None, max_length=50)
    source_code: Optional[str] = Field(default=None, max_length=65536)

    @model_validator(mode="after")
    def validate_content_present(self) -> "SubmitAnswerRequest":
        has_answer = bool(self.answer_text and self.answer_text.strip())
        has_code = bool(self.source_code and self.source_code.strip())
        if not has_answer and not has_code:
            raise ValueError("Either answer_text or source_code must be provided.")
        if not has_answer and has_code:
            self.answer_text = self.source_code
        return self


class SubmitAnswerResponse(BaseModel):
    session_id: str
    question_index: int
    evaluated_score: Optional[float] = None
    feedback: str
    strengths: List[str]
    improvements: List[str]
    next_difficulty: QuestionDifficulty
    difficulty_rationale: str
    is_session_completed: bool
    is_skipped: Optional[bool] = False
    next_question: Optional[SessionQuestionResponse] = None
    scorecard_id: Optional[str] = None
    evaluator_mode: Optional[str] = None
    code_execution_summary: Optional[Dict[str, Any]] = None


class ResponseSummary(BaseModel):
    question_index: int
    question_text: str
    difficulty: QuestionDifficulty
    topic: Optional[str] = "Technical Assessment"
    answer_text: str
    evaluation_score: Optional[float] = None
    score: Optional[float] = None
    feedback: str
    strengths: List[str]
    improvements: List[str]
    difficulty_adjustment_rationale: str
    question_type: Optional[str] = "conceptual"
    language: Optional[str] = None
    code_execution_summary: Optional[Dict[str, Any]] = None
    status: Optional[str] = "answered"
    is_skipped: Optional[bool] = False


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
    strengths: Optional[List[str]] = None
    areas_for_growth: List[str]
    evaluator_mode: str
    disclaimer: str
    completed_at: datetime
    responses: List[ResponseSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TopicPerformanceItem(BaseModel):
    topic: str
    questions_tested: int
    average_score: float
    min_score: float
    max_score: float
    category: str  # "strength" | "moderate" | "weakness"
    is_limited_evidence: bool = False
    evidence_level: str = "sufficient"  # "limited" | "moderate" | "sufficient"
    evidence_note: str

    model_config = ConfigDict(from_attributes=True)


class ActionablePriorityItem(BaseModel):
    topic: str
    priority: str  # "high" | "medium" | "low"
    average_score: float
    reason: str
    actionable_steps: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class VideoRecommendationItem(BaseModel):
    resource_id: str
    title: str
    provider: str
    topic: str
    video_url: str
    embed_url: Optional[str] = None
    video_id: Optional[str] = None
    can_embed: bool = True
    difficulty_level: str
    reason: str
    watched: bool = False
    is_verified: bool = True

    model_config = ConfigDict(from_attributes=True)


class StudentPerformanceReportResponse(BaseModel):
    report_id: str
    assignment_id: str
    session_id: str
    interview_id: str
    interview_title: str
    selected_role: Optional[str] = None
    student_registration_number: str
    student_email: Optional[str] = None
    overall_score: float
    percentage_score: float
    performance_level: str
    summary_feedback: str
    evaluator_mode: str
    difficulty_progression: List[str] = Field(default_factory=list)
    completed_at: datetime
    total_questions_assigned: int = 5
    questions_answered: int = 0
    questions_skipped: int = 0
    questions_evaluated: int = 0
    topic_breakdown: List[TopicPerformanceItem] = Field(default_factory=list)
    actionable_priorities: List[ActionablePriorityItem] = Field(default_factory=list)
    video_recommendations: List[VideoRecommendationItem] = Field(default_factory=list)
    responses: List[ResponseSummary] = Field(default_factory=list)
    disclaimer: str

    model_config = ConfigDict(from_attributes=True)
