import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserInDB, UserRole, AccountStatus
from app.core.database import get_interview_database
from app.api.deps import get_current_active_user
from app.services.interview_recommendation_service import InterviewRecommendationService
from app.models.performance_tracking import (
    RecommendationLevel,
    RecommendationStatus,
    EvidenceSufficiency,
    PerformanceTrend,
    StudentProfileInfo,
    LevelRecommendation,
    StudentPerformanceSummaryResponse,
    PaginatedInterviewHistoryResponse,
    StudentTrackingAdminItem,
    PaginatedStudentTrackingResponse,
)


@pytest.fixture
def mock_student():
    return UserInDB(
        id="usr-stud-101",
        email="rajesh.211fa@vignan.ac.in",
        full_name="Rajesh Kumar",
        role=UserRole.STUDENT,
        institution_id="VFSTR",
        registration_number="211FA04001",
        department="CSE",
        batch_cohort="2021-2025",
        section="A",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def mock_faculty():
    return UserInDB(
        id="usr-fac-201",
        email="faculty.cse@vignan.ac.in",
        full_name="Dr. Srinivas Rao",
        role=UserRole.FACULTY,
        institution_id="VFSTR",
        department="CSE",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def sample_summary_response():
    profile = StudentProfileInfo(
        registration_number="211FA04001",
        full_name="Rajesh Kumar",
        email="rajesh.211fa@vignan.ac.in",
        institution_id="VFSTR",
        department="CSE",
        batch_cohort="2021-2025",
        section="A",
        target_role="Software Development Engineer",
        technical_skills=["Python", "DSA"],
        preferred_languages=["Python"],
        experience_level="Entry Level",
        areas_of_interest=["Algorithms"],
    )
    rec = LevelRecommendation(
        recommended_level=RecommendationLevel.INTERMEDIATE,
        underlying_difficulty="medium",
        status=RecommendationStatus.PROVISIONAL,
        evidence_sufficiency=EvidenceSufficiency.LIMITED,
        completed_interviews_count=1,
        average_score=7.0,
        latest_score=7.0,
        score_trend=PerformanceTrend.INSUFFICIENT_DATA,
        consistency_score=None,
        explanation="Solid initial performance demonstrates foundational strength.",
        progression_requirements="Complete a second interview with >= 7.5 to unlock Advanced.",
        suggested_focus="Application of concepts and algorithms.",
        strongest_topics=["Data Structures"],
        weakest_topics=["Operating Systems"],
        practice_priorities=[],
    )
    return StudentPerformanceSummaryResponse(
        profile=profile,
        recommendation=rec,
        total_completed_interviews=1,
        latest_score=7.0,
        historical_average_score=7.0,
        highest_score=7.0,
        lowest_score=7.0,
        trend=PerformanceTrend.INSUFFICIENT_DATA,
        topic_mastery=[],
        recent_history=[],
    )


def test_student_progress_summary_route(mock_student, sample_summary_response):
    """Verifies that GET /api/student/interviews/progress/summary returns student performance summary."""
    mock_db = MagicMock()

    app.dependency_overrides[get_current_active_user] = lambda: mock_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    with patch.object(
        InterviewRecommendationService,
        "get_student_performance_summary",
        new=AsyncMock(return_value=sample_summary_response),
    ):
        client = TestClient(app)
        response = client.get("/api/student/interviews/progress/summary")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["registration_number"] == "211FA04001"
    assert data["recommendation"]["recommended_level"] == "Intermediate"
    assert data["recommendation"]["status"] == "provisional"
    assert data["total_completed_interviews"] == 1


def test_student_progress_history_route(mock_student):
    """Verifies that GET /api/student/interviews/progress/history returns paginated history."""
    mock_db = MagicMock()

    mock_history = PaginatedInterviewHistoryResponse(
        items=[],
        total=0,
        skip=0,
        limit=10,
    )

    app.dependency_overrides[get_current_active_user] = lambda: mock_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    with patch.object(
        InterviewRecommendationService,
        "get_student_interview_history",
        new=AsyncMock(return_value=mock_history),
    ):
        client = TestClient(app)
        response = client.get("/api/student/interviews/progress/history?skip=0&limit=10")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] == 0
    assert data["limit"] == 10


def test_student_profile_update_route(mock_student):
    """Verifies that PATCH /api/student/interviews/profile updates optional profile fields."""
    mock_db = MagicMock()
    updated_profile = StudentProfileInfo(
        registration_number="211FA04001",
        full_name="Rajesh Kumar",
        email="rajesh.211fa@vignan.ac.in",
        institution_id="VFSTR",
        department="CSE",
        target_role="Product Engineer",
        technical_skills=["React", "FastAPI"],
    )

    app.dependency_overrides[get_current_active_user] = lambda: mock_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    with patch.object(
        InterviewRecommendationService,
        "update_student_profile",
        new=AsyncMock(return_value=updated_profile),
    ):
        client = TestClient(app)
        response = client.patch(
            "/api/student/interviews/profile",
            json={
                "target_role": "Product Engineer",
                "technical_skills": ["React", "FastAPI"],
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["target_role"] == "Product Engineer"
    assert "React" in data["technical_skills"]


def test_student_cannot_access_faculty_tracking(mock_student):
    """Students cannot access /api/admin/interviews/students/tracking (403 Forbidden)."""
    mock_db = MagicMock()

    app.dependency_overrides[get_current_active_user] = lambda: mock_student
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    client = TestClient(app)
    response = client.get("/api/admin/interviews/students/tracking")

    app.dependency_overrides.clear()
    assert response.status_code == 403


def test_faculty_can_access_student_tracking(mock_faculty):
    """Faculty members can access /api/admin/interviews/students/tracking."""
    mock_db = MagicMock()
    mock_result = PaginatedStudentTrackingResponse(
        items=[
            StudentTrackingAdminItem(
                registration_number="211FA04001",
                full_name="Rajesh Kumar",
                email="rajesh@vignan.ac.in",
                institution_id="VFSTR",
                department="CSE",
                target_role="Software Development Engineer",
                completed_interviews_count=2,
                latest_score=8.0,
                average_score=7.8,
                trend=PerformanceTrend.IMPROVING,
                recommended_level=RecommendationLevel.ADVANCED,
                recommendation_status=RecommendationStatus.EVIDENCE_SUPPORTED,
                evidence_sufficiency=EvidenceSufficiency.MODERATE,
            )
        ],
        total=1,
        skip=0,
        limit=20,
        filters_applied={"department": "CSE"},
    )

    app.dependency_overrides[get_current_active_user] = lambda: mock_faculty
    app.dependency_overrides[get_interview_database] = lambda: mock_db

    with patch.object(
        InterviewRecommendationService,
        "get_faculty_student_tracking",
        new=AsyncMock(return_value=mock_result),
    ):
        client = TestClient(app)
        response = client.get("/api/admin/interviews/students/tracking?department=CSE")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["registration_number"] == "211FA04001"
    assert data["items"][0]["recommended_level"] == "Advanced"
