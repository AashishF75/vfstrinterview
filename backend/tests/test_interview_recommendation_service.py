import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from app.models.user import UserInDB, UserRole, AccountStatus
from app.models.performance_tracking import (
    RecommendationLevel,
    RecommendationStatus,
    EvidenceSufficiency,
    PerformanceTrend,
    StudentProfileInfo,
    StudentProfileUpdate,
    LevelRecommendation,
)
from app.core.config import settings
from app.services.interview_recommendation_service import (
    InterviewRecommendationService,
    _format_topic_name,
    safe_parse_score,
)


@pytest.fixture
def sample_student_user():
    return UserInDB(
        id="usr-student-1",
        email="student1@vignan.ac.in",
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
def other_student_user():
    return UserInDB(
        id="usr-student-2",
        email="student2@vignan.ac.in",
        full_name="Priya Sharma",
        role=UserRole.STUDENT,
        institution_id="VFSTR",
        registration_number="211FA04002",
        department="CSE",
        batch_cohort="2021-2025",
        section="B",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def faculty_user():
    return UserInDB(
        id="usr-faculty-1",
        email="faculty.cse@vignan.ac.in",
        full_name="Dr. K. Srinivas",
        role=UserRole.FACULTY,
        institution_id="VFSTR",
        department="CSE",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def ece_faculty_user():
    return UserInDB(
        id="usr-faculty-ece",
        email="faculty.ece@vignan.ac.in",
        full_name="Dr. V. Prasad",
        role=UserRole.FACULTY,
        institution_id="VFSTR",
        department="ECE",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def university_admin_user():
    return UserInDB(
        id="usr-uadmin-1",
        email="dean@vignan.ac.in",
        full_name="Prof. Registrar",
        role=UserRole.UNIVERSITY_ADMIN,
        institution_id="VFSTR",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def dept_admin_user():
    return UserInDB(
        id="usr-dadmin-1",
        email="hod.cse@vignan.ac.in",
        full_name="Dr. HOD CSE",
        role=UserRole.DEPARTMENT_ADMIN,
        institution_id="VFSTR",
        department="CSE",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def platform_admin_user():
    return UserInDB(
        id="usr-padmin-1",
        email="platform@interviews.ai",
        full_name="Platform Admin",
        role=UserRole.PLATFORM_ADMIN,
        institution_id="SYSTEM",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def other_inst_student_user():
    return UserInDB(
        id="usr-stud-other-inst",
        email="student@otheruniv.ac.in",
        full_name="External Student",
        role=UserRole.STUDENT,
        institution_id="OTHER_UNIV",
        registration_number="OTHER21001",
        department="CSE",
        batch_cohort="2021-2025",
        section="A",
        hashed_password="fakehashpassword123",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
    )


@pytest.fixture
def sample_profile(sample_student_user):
    return StudentProfileInfo(
        registration_number=sample_student_user.registration_number,
        full_name=sample_student_user.full_name,
        email=sample_student_user.email,
        institution_id=sample_student_user.institution_id,
        department=sample_student_user.department,
        batch_cohort=sample_student_user.batch_cohort,
        section=sample_student_user.section,
        target_role="Software Development Engineer",
        technical_skills=["Python", "DSA", "SQL"],
        preferred_languages=["Python", "C++"],
        experience_level="Entry Level",
        areas_of_interest=["Backend Systems"],
    )


# ==============================================================================
# Recommendation Algorithm Unit Tests
# ==============================================================================

def test_zero_interviews_gives_provisional_beginner(sample_profile):
    """When a student has 0 completed interviews, recommendation must be provisional Beginner."""
    records = []
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert rec.recommended_level == RecommendationLevel.BEGINNER
    assert rec.status == RecommendationStatus.PROVISIONAL
    assert rec.evidence_sufficiency == EvidenceSufficiency.LIMITED
    assert rec.completed_interviews_count == 0
    assert rec.average_score is None
    assert rec.latest_score is None
    assert rec.score_trend == PerformanceTrend.INSUFFICIENT_DATA
    assert "baseline" in rec.explanation.lower() or "no completed" in rec.explanation.lower()


def test_single_low_score_gives_provisional_beginner(sample_profile):
    """A single interview with score < 5.0 yields provisional Beginner."""
    records = [{
        "scorecard": {"overall_score": 4.2, "percentage_score": 42.0},
        "session": {"session_id": "sess-1", "current_difficulty": "medium"},
        "selected_role": "Associate Software Engineer",
        "completed_at": datetime.now(timezone.utc),
        "responses": [
            {"topic": "Data Structures", "evaluation_score": 4.0, "is_skipped": False},
            {"topic": "Algorithms", "evaluation_score": 4.4, "is_skipped": False},
        ],
    }]
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert rec.recommended_level == RecommendationLevel.BEGINNER
    assert rec.status == RecommendationStatus.PROVISIONAL
    assert rec.evidence_sufficiency == EvidenceSufficiency.LIMITED
    assert rec.completed_interviews_count == 1
    assert rec.latest_score == 4.2
    assert "foundational gaps" in rec.explanation.lower()


def test_single_high_score_does_not_jump_to_advanced(sample_profile):
    """
    CRITICAL POLICY: A single high score (e.g. 9.2/10) must NOT jump directly to Advanced.
    Must recommend Intermediate with provisional status and request corroborating evidence.
    """
    records = [{
        "scorecard": {"overall_score": 9.2, "percentage_score": 92.0},
        "session": {"session_id": "sess-1", "current_difficulty": "medium"},
        "selected_role": "Software Development Engineer",
        "completed_at": datetime.now(timezone.utc),
        "responses": [
            {"topic": "Data Structures", "evaluation_score": 9.0, "is_skipped": False},
            {"topic": "Algorithms", "evaluation_score": 9.4, "is_skipped": False},
        ],
    }]
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert rec.recommended_level == RecommendationLevel.INTERMEDIATE
    assert rec.status == RecommendationStatus.PROVISIONAL
    assert rec.evidence_sufficiency == EvidenceSufficiency.LIMITED
    assert rec.completed_interviews_count == 1
    assert rec.latest_score == 9.2
    assert "corroborate" in rec.progression_requirements.lower() or "second" in rec.progression_requirements.lower()


def test_consistent_strong_performance_promotes_to_advanced(sample_profile):
    """
    Two or more completed interviews with strong scores (>= 7.5) and solid topic coverage
    promote the student to Advanced with evidence_supported status.
    """
    now = datetime.now(timezone.utc)
    records = [
        {
            "scorecard": {"overall_score": 8.0, "percentage_score": 80.0},
            "session": {"session_id": "sess-1"},
            "selected_role": "Software Development Engineer",
            "completed_at": now - timedelta(days=5),
            "responses": [
                {"topic": "Data Structures", "evaluation_score": 8.0, "is_skipped": False},
                {"topic": "DBMS", "evaluation_score": 8.0, "is_skipped": False},
            ],
        },
        {
            "scorecard": {"overall_score": 8.5, "percentage_score": 85.0},
            "session": {"session_id": "sess-2"},
            "selected_role": "Software Development Engineer",
            "completed_at": now - timedelta(days=1),
            "responses": [
                {"topic": "Data Structures", "evaluation_score": 8.5, "is_skipped": False},
                {"topic": "Operating Systems", "evaluation_score": 8.5, "is_skipped": False},
            ],
        },
    ]
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert rec.recommended_level == RecommendationLevel.ADVANCED
    assert rec.status == RecommendationStatus.EVIDENCE_SUPPORTED
    assert rec.evidence_sufficiency == EvidenceSufficiency.MODERATE
    assert rec.completed_interviews_count == 2
    assert rec.average_score == 8.2 or rec.average_score == 8.3
    assert rec.latest_score == 8.5
    assert rec.score_trend == PerformanceTrend.IMPROVING


def test_stability_outlier_does_not_jump_unpredictably(sample_profile):
    """
    A student with one low score (4.0) and one high score (8.5) does not jump to Advanced
    because historical average (6.25) and consistency warrant Intermediate development.
    """
    now = datetime.now(timezone.utc)
    records = [
        {
            "scorecard": {"overall_score": 4.0, "percentage_score": 40.0},
            "session": {"session_id": "sess-1"},
            "selected_role": "Associate Software Engineer",
            "completed_at": now - timedelta(days=7),
            "responses": [
                {"topic": "Data Structures", "evaluation_score": 4.0, "is_skipped": False},
            ],
        },
        {
            "scorecard": {"overall_score": 8.5, "percentage_score": 85.0},
            "session": {"session_id": "sess-2"},
            "selected_role": "Associate Software Engineer",
            "completed_at": now - timedelta(days=1),
            "responses": [
                {"topic": "Data Structures", "evaluation_score": 8.5, "is_skipped": False},
            ],
        },
    ]
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert rec.recommended_level == RecommendationLevel.INTERMEDIATE
    assert rec.status == RecommendationStatus.EVIDENCE_SUPPORTED


def test_critical_topic_gap_holds_back_from_advanced(sample_profile):
    """
    Even with high overall scores (e.g. 8.0, 8.2), if a core subject has a severe deficit (< 4.5),
    the recommendation stays at Intermediate with targeted practice priorities.
    """
    now = datetime.now(timezone.utc)
    records = [
        {
            "scorecard": {"overall_score": 8.0, "percentage_score": 80.0},
            "session": {"session_id": "sess-1"},
            "selected_role": "Product Engineer",
            "completed_at": now - timedelta(days=4),
            "responses": [
                {"topic": "System Design", "evaluation_score": 9.0, "is_skipped": False},
                {"topic": "Operating Systems", "evaluation_score": 3.5, "is_skipped": False},
            ],
        },
        {
            "scorecard": {"overall_score": 8.0, "percentage_score": 80.0},
            "session": {"session_id": "sess-2"},
            "selected_role": "Product Engineer",
            "completed_at": now - timedelta(days=1),
            "responses": [
                {"topic": "System Design", "evaluation_score": 9.5, "is_skipped": False},
                {"topic": "Operating Systems", "evaluation_score": 4.0, "is_skipped": False},
            ],
        },
    ]
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert rec.recommended_level == RecommendationLevel.INTERMEDIATE
    assert rec.status == RecommendationStatus.EVIDENCE_SUPPORTED
    assert any(p.topic == "Operating Systems" for p in rec.practice_priorities)


def test_practice_priorities_generated_for_weak_topics(sample_profile):
    """Topics tested with average score < 6.0 generate actionable practice items."""
    records = [{
        "scorecard": {"overall_score": 6.0, "percentage_score": 60.0},
        "session": {"session_id": "sess-1"},
        "selected_role": "System Engineer",
        "completed_at": datetime.now(timezone.utc),
        "responses": [
            {"topic": "Computer Networks", "evaluation_score": 4.5, "is_skipped": False},
            {"topic": "Operating Systems", "evaluation_score": 7.5, "is_skipped": False},
        ],
    }]
    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    assert len(rec.practice_priorities) >= 1
    cn_priority = next((p for p in rec.practice_priorities if p.topic == "Computer Networks"), None)
    assert cn_priority is not None
    assert cn_priority.priority == "high"
    assert cn_priority.average_score == 4.5


def test_trend_and_consistency_calculation():
    """Verify linear slope and variance calculation across multiple sessions."""
    # Improving trend
    trend, consistency = InterviewRecommendationService.calculate_trend_and_consistency([5.0, 6.5, 8.0])
    assert trend == PerformanceTrend.IMPROVING
    assert consistency is not None and consistency > 0.0

    # Declining trend
    trend_dec, _ = InterviewRecommendationService.calculate_trend_and_consistency([8.5, 7.0, 5.5])
    assert trend_dec == PerformanceTrend.DECLINING

    # Stable trend
    trend_stb, const_stb = InterviewRecommendationService.calculate_trend_and_consistency([7.0, 7.2, 7.1])
    assert trend_stb == PerformanceTrend.STABLE
    assert const_stb > 8.0  # highly consistent


# ==============================================================================
# Security & RBAC Isolation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_student_cannot_access_other_student_progress(sample_student_user, other_student_user):
    """Students attempting to access another student's progress summary receive 403 Forbidden."""
    db_mock = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=sample_student_user,
            target_registration_number=other_student_user.registration_number,
        )

    assert exc_info.value.status_code == 403
    assert "strictly restricted" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_faculty_cannot_access_other_department_student(ece_faculty_user, sample_student_user):
    """Faculty from ECE cannot access CSE student progress summary (403 Forbidden)."""
    db_mock = MagicMock()
    auth_db_mock = MagicMock()
    db_mock.client = {settings.MONGODB_DB_NAME: auth_db_mock}

    # Student document in auth db has department CSE
    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": sample_student_user.registration_number,
        "department": "CSE",
        "institution_id": "VFSTR",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=ece_faculty_user,  # ECE faculty
            target_registration_number=sample_student_user.registration_number,  # CSE student
        )

    assert exc_info.value.status_code == 403
    assert "department" in exc_info.value.detail.lower()


def _make_mock_db():
    db_mock = MagicMock()
    collections = {}

    def _create_col_mock():
        col = MagicMock()
        col.create_index = AsyncMock()
        col.drop_index = AsyncMock()
        col.index_information = AsyncMock(return_value={})
        return col

    db_mock.__getitem__.side_effect = lambda k: collections.setdefault(k, _create_col_mock())
    auth_db_mock = MagicMock()
    auth_collections = {}
    auth_db_mock.__getitem__.side_effect = lambda k: auth_collections.setdefault(k, _create_col_mock())
    db_mock.client = {settings.MONGODB_DB_NAME: auth_db_mock}
    return db_mock, auth_db_mock


# ==============================================================================
# Fix 2 — Strict Multi-Tenant Authorization Matrix Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_university_admin_cross_institution_access_denied(university_admin_user, other_inst_student_user):
    """Case 1: University admin accessing a student from another institution is denied (403)."""
    db_mock, auth_db_mock = _make_mock_db()

    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": other_inst_student_user.registration_number,
        "institution_id": "OTHER_UNIV",
        "department": "CSE",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=university_admin_user,  # VFSTR admin
            target_registration_number=other_inst_student_user.registration_number,  # OTHER_UNIV student
        )

    assert exc_info.value.status_code == 403
    assert "cross-institution" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_faculty_cross_institution_same_department_denied(faculty_user, other_inst_student_user):
    """Case 2: Faculty accessing student from another institution with same department is denied (403)."""
    db_mock, auth_db_mock = _make_mock_db()

    # Target student is CSE, but from OTHER_UNIV
    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": other_inst_student_user.registration_number,
        "institution_id": "OTHER_UNIV",
        "department": "CSE",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=faculty_user,  # VFSTR CSE faculty
            target_registration_number=other_inst_student_user.registration_number,
        )

    assert exc_info.value.status_code == 403
    assert "cross-institution" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_department_admin_cross_department_access_denied(dept_admin_user, sample_student_user):
    """Case 3: Department admin accessing another department in same institution is denied (403)."""
    db_mock, auth_db_mock = _make_mock_db()

    # Student belongs to ECE, admin belongs to CSE
    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": sample_student_user.registration_number,
        "institution_id": "VFSTR",
        "department": "ECE",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=dept_admin_user,  # CSE Dept Admin
            target_registration_number=sample_student_user.registration_number,
        )

    assert exc_info.value.status_code == 403
    assert "department" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_missing_student_auth_insufficient_tenant_evidence_denied(faculty_user):
    """Case 4: Missing student-auth record with insufficient tenant evidence is denied (403 fail closed)."""
    db_mock, auth_db_mock = _make_mock_db()

    # Student not in users
    auth_db_mock["users"].find_one = AsyncMock(return_value=None)
    # Profile exists but has NO institution_id or department
    db_mock["student_profiles"].find_one = AsyncMock(return_value={
        "registration_number": "ORPHAN001",
        "full_name": "Orphan Student",
    })
    db_mock["student_interview_assignments"].find_one = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=faculty_user,
            target_registration_number="ORPHAN001",
        )

    assert exc_info.value.status_code == 403
    assert "cannot be verified" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_authorized_same_institution_access_allowed(faculty_user, sample_student_user, sample_profile):
    """Case 5: Authorized same-institution, same-department access is allowed (200)."""
    db_mock, auth_db_mock = _make_mock_db()

    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": sample_student_user.registration_number,
        "institution_id": "VFSTR",
        "department": "CSE",
        "full_name": "Rajesh Kumar",
        "email": "student1@vignan.ac.in",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value={
        "registration_number": sample_student_user.registration_number,
        "institution_id": "VFSTR",
        "department": "CSE",
    })

    # Mock cursor for completed scorecards
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    db_mock["interview_scorecards"].find.return_value = mock_cursor

    result = await InterviewRecommendationService.get_student_performance_summary(
        db=db_mock,
        current_user=faculty_user,
        target_registration_number=sample_student_user.registration_number,
    )

    assert result.profile.registration_number == sample_student_user.registration_number
    assert result.profile.institution_id == "VFSTR"
    assert result.profile.department == "CSE"


@pytest.mark.asyncio
async def test_platform_admin_access_allowed_across_tenants(platform_admin_user, other_inst_student_user):
    """Case 6: Platform administrator access follows existing policy across all institutions."""
    db_mock, auth_db_mock = _make_mock_db()

    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": other_inst_student_user.registration_number,
        "institution_id": "OTHER_UNIV",
        "department": "CSE",
        "full_name": "External Student",
        "email": "student@otheruniv.ac.in",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value=None)

    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    db_mock["interview_scorecards"].find.return_value = mock_cursor

    result = await InterviewRecommendationService.get_student_performance_summary(
        db=db_mock,
        current_user=platform_admin_user,
        target_registration_number=other_inst_student_user.registration_number,
    )

    assert result.profile.registration_number == other_inst_student_user.registration_number


@pytest.mark.asyncio
async def test_conflicting_tenant_records_denied(university_admin_user, sample_student_user):
    """Fail closed when authoritative data sources disagree on institution (403)."""
    db_mock, auth_db_mock = _make_mock_db()

    # Auth db says VFSTR, profile says OTHER_UNIV
    auth_db_mock["users"].find_one = AsyncMock(return_value={
        "registration_number": sample_student_user.registration_number,
        "institution_id": "VFSTR",
        "department": "CSE",
    })
    db_mock["student_profiles"].find_one = AsyncMock(return_value={
        "registration_number": sample_student_user.registration_number,
        "institution_id": "OTHER_UNIV",
        "department": "CSE",
    })

    with pytest.raises(HTTPException) as exc_info:
        await InterviewRecommendationService.get_student_performance_summary(
            db=db_mock,
            current_user=university_admin_user,
            target_registration_number=sample_student_user.registration_number,
        )

    assert exc_info.value.status_code == 403
    assert "conflicting" in exc_info.value.detail.lower()


# ==============================================================================
# Fix 4 — Safe Score Parsing Tests
# ==============================================================================

def test_safe_parse_score_inputs():
    """Verify safe parsing helper handles valid, boundary, null, malformed, and non-finite values."""
    # Valid numeric values
    assert safe_parse_score(7.5) == 7.5
    assert safe_parse_score(0.0) == 0.0
    assert safe_parse_score(0) == 0.0
    assert safe_parse_score("8.2") == 8.2
    assert safe_parse_score(10.0) == 10.0
    assert safe_parse_score("10.0") == 10.0

    # Percentage range (0.0 to 100.0)
    assert safe_parse_score(85.5, 0.0, 100.0) == 85.5
    assert safe_parse_score(0.0, 0.0, 100.0) == 0.0
    assert safe_parse_score(100.0, 0.0, 100.0) == 100.0

    # Missing and Null
    assert safe_parse_score(None) is None

    # Malformed strings
    assert safe_parse_score("") is None
    assert safe_parse_score("   ") is None
    assert safe_parse_score("invalid") is None
    assert safe_parse_score("N/A") is None

    # Non-finite values
    assert safe_parse_score(float("nan")) is None
    assert safe_parse_score(float("inf")) is None
    assert safe_parse_score(float("-inf")) is None

    # Out of range
    assert safe_parse_score(-1.0, 0.0, 10.0) is None
    assert safe_parse_score(11.0, 0.0, 10.0) is None
    assert safe_parse_score(105.0, 0.0, 100.0) is None


def test_recommendation_handles_malformed_and_null_scores(sample_profile):
    """Records with null or malformed scores are excluded; evidence sufficiency reflects incomplete data."""
    now = datetime.now(timezone.utc)
    records = [
        {
            "scorecard": {"overall_score": 8.0, "percentage_score": 80.0},
            "session": {"session_id": "sess-valid-1"},
            "selected_role": "Software Engineer",
            "completed_at": now - timedelta(days=2),
            "responses": [],
        },
        {
            # Malformed scorecard (None score)
            "scorecard": {"overall_score": None, "percentage_score": None},
            "session": {"session_id": "sess-invalid-1"},
            "selected_role": "Software Engineer",
            "completed_at": now - timedelta(days=1),
            "responses": [],
        },
        {
            # Malformed scorecard (string garbage)
            "scorecard": {"overall_score": "NaN_SCORE"},
            "session": {"session_id": "sess-invalid-2"},
            "selected_role": "Software Engineer",
            "completed_at": now,
            "responses": [],
        },
    ]

    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)

    # Only 1 valid score (8.0), so it should behave as 1 completed interview (Provisional)
    assert rec.completed_interviews_count == 1
    assert rec.latest_score == 8.0
    assert rec.average_score == 8.0
    assert rec.status == RecommendationStatus.PROVISIONAL


def test_recommendation_preserves_valid_zero_score(sample_profile):
    """Legitimate score of 0.0 is preserved and not silently treated as missing."""
    now = datetime.now(timezone.utc)
    records = [
        {
            "scorecard": {"overall_score": 0.0, "percentage_score": 0.0},
            "session": {"session_id": "sess-zero-1"},
            "selected_role": "Software Engineer",
            "completed_at": now,
            "responses": [],
        }
    ]

    rec = InterviewRecommendationService.calculate_level_recommendation(records, sample_profile)
    assert rec.completed_interviews_count == 1
    assert rec.latest_score == 0.0
    assert rec.average_score == 0.0
    assert rec.recommended_level == RecommendationLevel.BEGINNER


def test_topic_mastery_safe_parsing_excludes_invalid():
    """Questions with malformed scores do not crash or corrupt topic mastery averages."""
    records = [{
        "scorecard": {"overall_score": 7.0},
        "session": {"session_id": "sess-1"},
        "selected_role": "Engineer",
        "completed_at": datetime.now(timezone.utc),
        "responses": [
            {"topic": "Algorithms", "evaluation_score": 8.0, "is_skipped": False},
            {"topic": "Algorithms", "evaluation_score": None, "is_skipped": False},
            {"topic": "Algorithms", "evaluation_score": "corrupt", "is_skipped": False},
            {"topic": "Algorithms", "evaluation_score": 6.0, "is_skipped": False},
        ],
    }]

    mastery = InterviewRecommendationService.aggregate_topic_mastery(records)
    algo_item = next((m for m in mastery if m.topic == "Algorithms"), None)
    assert algo_item is not None
    # Valid scores are [8.0, 6.0] -> avg = 7.0
    assert algo_item.average_score == 7.0
    assert algo_item.questions_tested == 4


# ==============================================================================
# Fix 5 — Session Deduplication Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_get_student_completed_evaluations_deduplicates_by_session_id():
    """Duplicate scorecards for the same session_id contribute exactly once."""
    db_mock, _ = _make_mock_db()
    now = datetime.now(timezone.utc)

    # Two scorecards with the exact same session_id
    duplicate_scorecards = [
        {
            "scorecard_id": "sc-dup-1",
            "session_id": "sess-100",
            "student_registration_number": "211FA04001",
            "overall_score": 7.5,
            "percentage_score": 75.0,
            "created_at": now - timedelta(minutes=10),
        },
        {
            "scorecard_id": "sc-dup-2",
            "session_id": "sess-100",
            "student_registration_number": "211FA04001",
            "overall_score": 7.5,
            "percentage_score": 75.0,
            "created_at": now,
        },
    ]

    mock_sc_cursor = MagicMock()
    mock_sc_cursor.sort.return_value = mock_sc_cursor
    mock_sc_cursor.to_list = AsyncMock(return_value=duplicate_scorecards)
    db_mock["interview_scorecards"].find.return_value = mock_sc_cursor

    # Session is completed
    db_mock["interview_sessions"].find_one = AsyncMock(return_value={
        "session_id": "sess-100",
        "session_status": "completed",
        "final_scorecard_id": "sc-dup-2",
        "assignment_id": "asgn-100",
    })
    db_mock["student_interview_assignments"].find_one = AsyncMock(return_value={"selected_role": "Engineer"})
    db_mock["university_interviews"].find_one = AsyncMock(return_value={"role": "Engineer"})

    mock_resp_cursor = MagicMock()
    mock_resp_cursor.sort.return_value = mock_resp_cursor
    mock_resp_cursor.to_list = AsyncMock(return_value=[])
    db_mock["interview_responses"].find.return_value = mock_resp_cursor

    records = await InterviewRecommendationService.get_student_completed_evaluations(
        db=db_mock,
        student_reg_no="211FA04001",
    )

    # Exactly 1 record returned despite 2 scorecards
    assert len(records) == 1
    assert records[0]["scorecard"]["scorecard_id"] == "sc-dup-2"


@pytest.mark.asyncio
async def test_duplicate_scorecards_conflicting_scores_indeterminate_excluded():
    """Conflicting duplicate scorecards with indeterminate timestamps are excluded with diagnostic log."""
    db_mock, _ = _make_mock_db()
    same_time = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Two scorecards with conflicting scores and identical timestamps
    conflicting_scorecards = [
        {
            "scorecard_id": "sc-conflict-1",
            "session_id": "sess-ambiguous",
            "student_registration_number": "211FA04001",
            "overall_score": 4.0,
            "created_at": same_time,
        },
        {
            "scorecard_id": "sc-conflict-2",
            "session_id": "sess-ambiguous",
            "student_registration_number": "211FA04001",
            "overall_score": 8.5,
            "created_at": same_time,
        },
    ]

    mock_sc_cursor = MagicMock()
    mock_sc_cursor.sort.return_value = mock_sc_cursor
    mock_sc_cursor.to_list = AsyncMock(return_value=conflicting_scorecards)
    db_mock["interview_scorecards"].find.return_value = mock_sc_cursor

    db_mock["interview_sessions"].find_one = AsyncMock(return_value={
        "session_id": "sess-ambiguous",
        "session_status": "completed",
        "final_scorecard_id": None,  # No authoritative final pointer
    })

    records = await InterviewRecommendationService.get_student_completed_evaluations(
        db=db_mock,
        student_reg_no="211FA04001",
    )

    # Excluded from calculations because ambiguous conflict could not be determined
    assert len(records) == 0


# ==============================================================================
# Fix 3 — Administrative Tracking Bounded Pagination & Batching Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_faculty_student_tracking_bounded_pagination(faculty_user):
    """Tracking applies safe skip/limit bounds and queries total count efficiently."""
    db_mock, auth_db_mock = _make_mock_db()

    auth_db_mock["users"].count_documents = AsyncMock(return_value=120)

    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    auth_db_mock["users"].find.return_value = mock_cursor

    result = await InterviewRecommendationService.get_faculty_student_tracking(
        db=db_mock,
        current_reviewer=faculty_user,
        skip=-10,  # Negative skip should be clamped to 0
        limit=200,  # Excessive limit should be clamped to 50
    )

    assert result.total == 120
    assert result.skip == 0
    assert result.limit == 50
    mock_cursor.skip.assert_called_with(0)
    mock_cursor.limit.assert_called_with(50)


@pytest.mark.asyncio
async def test_faculty_student_tracking_batched_queries(faculty_user):
    """Tracking batch-queries profiles, scorecards, sessions using $in instead of per-student loops."""
    db_mock, auth_db_mock = _make_mock_db()

    students_page = [
        {"registration_number": "211FA04001", "full_name": "Student One", "role": "student", "department": "CSE", "institution_id": "VFSTR", "email": "s1@vignan.ac.in"},
        {"registration_number": "211FA04002", "full_name": "Student Two", "role": "student", "department": "CSE", "institution_id": "VFSTR", "email": "s2@vignan.ac.in"},
    ]

    auth_db_mock["users"].count_documents = AsyncMock(return_value=2)
    mock_user_cursor = MagicMock()
    mock_user_cursor.sort.return_value = mock_user_cursor
    mock_user_cursor.skip.return_value = mock_user_cursor
    mock_user_cursor.limit.return_value = mock_user_cursor
    mock_user_cursor.to_list = AsyncMock(return_value=students_page)
    auth_db_mock["users"].find.return_value = mock_user_cursor

    # Profiles batched cursor
    mock_p_cursor = MagicMock()
    mock_p_cursor.to_list = AsyncMock(return_value=[
        {"registration_number": "211FA04001", "target_role": "Backend Engineer"},
        {"registration_number": "211FA04002", "target_role": "Data Engineer"},
    ])
    db_mock["student_profiles"].find.return_value = mock_p_cursor

    # Scorecards batched cursor
    mock_sc_cursor = MagicMock()
    mock_sc_cursor.sort.return_value = mock_sc_cursor
    mock_sc_cursor.to_list = AsyncMock(return_value=[])
    db_mock["interview_scorecards"].find.return_value = mock_sc_cursor

    result = await InterviewRecommendationService.get_faculty_student_tracking(
        db=db_mock,
        current_reviewer=faculty_user,
        skip=0,
        limit=20,
    )

    assert result.total == 2
    assert len(result.items) == 2
    # Verify profiles were fetched with $in for the page registration numbers
    db_mock["student_profiles"].find.assert_called_once_with({
        "registration_number": {"$in": ["211FA04001", "211FA04002"]}
    })
    # Verify scorecards were fetched with $in for the page registration numbers
    db_mock["interview_scorecards"].find.assert_called_once_with({
        "student_registration_number": {"$in": ["211FA04001", "211FA04002"]}
    })


# ==============================================================================
# Fix 1 — Unique Index Safety & Conflict Detection Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_student_profile_index_creation_spec():
    """ensure_interview_indexes applies unique=True and partialFilterExpression for string registration numbers."""
    from app.core.database import ensure_interview_indexes

    db_mock, _ = _make_mock_db()
    for name in ["interview_sessions", "interview_responses", "interview_scorecards", "student_profiles", "proctoring_events"]:
        db_mock[name].create_index = AsyncMock()
        db_mock[name].index_information = AsyncMock(return_value={})

    await ensure_interview_indexes(db=db_mock)

    profiles_col = db_mock["student_profiles"]
    called_with_partial = False
    for call in profiles_col.create_index.call_args_list:
        kwargs = call.kwargs
        if (
            kwargs.get("name") == "unique_student_profile_reg"
            and kwargs.get("unique") is True
            and kwargs.get("partialFilterExpression") == {"registration_number": {"$type": "string"}}
        ):
            called_with_partial = True
            break

    assert called_with_partial, "student_profiles.registration_number must have partial unique index with $type: string"


@pytest.mark.asyncio
async def test_student_profile_index_conflict_detection():
    """When unique_student_profile_reg already exists with conflicting options, skips without dropping or crashing."""
    from app.core.database import ensure_interview_indexes

    db_mock, _ = _make_mock_db()
    for name in ["interview_sessions", "interview_responses", "interview_scorecards", "student_profiles", "proctoring_events"]:
        db_mock[name].create_index = AsyncMock()
        db_mock[name].drop_index = AsyncMock()
        db_mock[name].index_information = AsyncMock(return_value={})

    profiles_col = db_mock["student_profiles"]
    profiles_col.index_information = AsyncMock(return_value={
        "unique_student_profile_reg": {
            "key": [("registration_number", 1)],
            "unique": True,
            # Missing partialFilterExpression
        }
    })

    # Should not raise any error and must not drop the index
    await ensure_interview_indexes(db=db_mock)

    profiles_col.drop_index.assert_not_called()
    for call in profiles_col.create_index.call_args_list:
        assert call.kwargs.get("name") != "unique_student_profile_reg"


def test_student_profile_partial_filter_expression_rules():
    """Validates partial unique index semantics for missing, null, and string registration numbers."""
    partial_filter = {"registration_number": {"$type": "string"}}

    # Documents evaluated against {"registration_number": {"$type": "string"}}
    doc_valid_string = {"registration_number": "211FA04001", "target_role": "Engineer"}
    doc_null_reg = {"registration_number": None, "target_role": "Engineer"}
    doc_missing_reg = {"target_role": "Engineer"}

    # String type check simulates MongoDB BSON type checking:
    def matches_partial_filter(doc):
        val = doc.get("registration_number")
        return isinstance(val, str)

    # Only documents with string registration numbers are indexed uniquely
    assert matches_partial_filter(doc_valid_string) is True
    # Missing or null documents do NOT match the index filter, allowing multiple instances
    assert matches_partial_filter(doc_null_reg) is False
    assert matches_partial_filter(doc_missing_reg) is False