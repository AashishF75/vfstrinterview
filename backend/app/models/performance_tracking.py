from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationLevel(str, Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class RecommendationStatus(str, Enum):
    PROVISIONAL = "provisional"
    EVIDENCE_SUPPORTED = "evidence_supported"


class EvidenceSufficiency(str, Enum):
    LIMITED = "limited"
    MODERATE = "moderate"
    STRONG = "strong"


class PerformanceTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    INSUFFICIENT_DATA = "insufficient_data"


class StudentProfileUpdate(BaseModel):
    target_role: Optional[str] = Field(None, max_length=100)
    technical_skills: Optional[List[str]] = Field(None, max_length=30)
    preferred_languages: Optional[List[str]] = Field(None, max_length=10)
    experience_level: Optional[str] = Field(None, max_length=50)
    areas_of_interest: Optional[List[str]] = Field(None, max_length=20)


class StudentProfileInfo(BaseModel):
    registration_number: str
    full_name: Optional[str] = None
    email: str
    institution_id: str
    department: Optional[str] = None
    batch_cohort: Optional[str] = None
    section: Optional[str] = None
    target_role: Optional[str] = None
    technical_skills: List[str] = Field(default_factory=list)
    preferred_languages: List[str] = Field(default_factory=list)
    experience_level: Optional[str] = "Entry Level"
    areas_of_interest: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InterviewHistorySummaryItem(BaseModel):
    assignment_id: str
    session_id: str
    interview_id: str
    interview_title: str
    selected_role: Optional[str] = None
    completed_at: datetime
    overall_score: float
    percentage_score: float
    performance_level: str
    difficulty_level: str  # Beginner / Intermediate / Advanced
    difficulty_progression: List[str] = Field(default_factory=list)
    total_questions: int = 5
    answered_questions: int = 5
    skipped_questions: int = 0
    report_url: str

    model_config = ConfigDict(from_attributes=True)


class TopicMasterySummaryItem(BaseModel):
    topic: str
    questions_tested: int
    average_score: float
    min_score: float
    max_score: float
    category: str  # "strength" | "moderate" | "weakness"
    mastery_level: str  # "Proficient" | "Developing" | "Foundational Gap"
    evidence_level: str  # "limited" | "moderate" | "sufficient"

    model_config = ConfigDict(from_attributes=True)


class PracticePriorityItem(BaseModel):
    topic: str
    priority: str  # "high" | "medium" | "low"
    average_score: float
    reason: str
    recommended_focus: str

    model_config = ConfigDict(from_attributes=True)


class LevelRecommendation(BaseModel):
    recommended_level: RecommendationLevel
    underlying_difficulty: str  # "easy" | "medium" | "hard"
    status: RecommendationStatus
    evidence_sufficiency: EvidenceSufficiency
    completed_interviews_count: int
    average_score: Optional[float] = None
    latest_score: Optional[float] = None
    score_trend: PerformanceTrend
    consistency_score: Optional[float] = None
    explanation: str
    progression_requirements: str
    suggested_focus: str
    strongest_topics: List[str] = Field(default_factory=list)
    weakest_topics: List[str] = Field(default_factory=list)
    practice_priorities: List[PracticePriorityItem] = Field(default_factory=list)
    calculated_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(from_attributes=True)


class StudentPerformanceSummaryResponse(BaseModel):
    profile: StudentProfileInfo
    recommendation: LevelRecommendation
    total_completed_interviews: int
    latest_score: Optional[float] = None
    historical_average_score: Optional[float] = None
    highest_score: Optional[float] = None
    lowest_score: Optional[float] = None
    trend: PerformanceTrend
    topic_mastery: List[TopicMasterySummaryItem] = Field(default_factory=list)
    recent_history: List[InterviewHistorySummaryItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PaginatedInterviewHistoryResponse(BaseModel):
    items: List[InterviewHistorySummaryItem]
    total: int
    skip: int
    limit: int


class StudentTrackingAdminItem(BaseModel):
    registration_number: str
    full_name: Optional[str] = None
    email: str
    institution_id: str
    department: Optional[str] = None
    batch_cohort: Optional[str] = None
    section: Optional[str] = None
    target_role: Optional[str] = None
    completed_interviews_count: int
    latest_score: Optional[float] = None
    average_score: Optional[float] = None
    trend: PerformanceTrend
    recommended_level: RecommendationLevel
    recommendation_status: RecommendationStatus
    evidence_sufficiency: EvidenceSufficiency
    last_interview_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedStudentTrackingResponse(BaseModel):
    items: List[StudentTrackingAdminItem]
    total: int
    skip: int
    limit: int
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
