"""Tests for Phase 8: Selective Student Assignment and Institution Question-Set Integration.

Regression and feature coverage:
- Faculty selecting a question set from their own institution.
- Cross-institution question-set access being denied (403 Forbidden).
- Department admin / faculty question-set mismatch being denied (403 Forbidden).
- Default interview creation remaining backward-compatible (no question_set_id).
- Candidate search with multi-field search and department, cohort, and eligibility filtering.
- Selecting individual students and filtered subsets.
- Server-side rejection of unauthorized cross-institution students (CROSS_INSTITUTION_UNAUTHORIZED).
- Server-side rejection of department mismatch (DEPARTMENT_MISMATCH).
- Server-side rejection of ineligible/quarantined students.
- Duplicate assignment handling (skips already assigned students without failing the batch).
- Empty selections rejection (HTTP 422).
- Stale student records / registry lookups.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.models.user import UserInDB, UserRole
from app.models.interview import (
    UniversityInterviewCreate,
    utc_now,
    AssignmentStatus,
)
from app.models.interview_session import (
    SessionStatus,
    EvaluatorMode,
    SubmitAnswerResponse,
    QuestionDifficulty,
)
from app.services.interview_service import InterviewService
from app.services.question_bank_service import QuestionBankService
from app.services.interview_session_service import InterviewSessionService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def vfstr_faculty():
    return UserInDB(
        id="vfstr-fac-1",
        email="cse_faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )


@pytest.fixture
def vfstr_admin():
    return UserInDB(
        id="vfstr-admin-1",
        email="admin@vfstr.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
    )


@pytest.fixture
def other_inst_admin():
    return UserInDB(
        id="other-admin-1",
        email="admin@otheruniv.edu",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="OTHER_UNIV",
    )


@pytest.fixture
def vfstr_student():
    return UserInDB(
        id="vfstr-stu-1",
        email="241fa04001@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )


def make_mock_db():
    mock_db = MagicMock()
    collections = {
        "university_interviews": MagicMock(),
        "student_interview_assignments": MagicMock(),
        "interview_eligibility_registry": MagicMock(),
        "interview_questions": MagicMock(),
        "interview_sessions": MagicMock(),
        "interview_responses": MagicMock(),
        "interview_scorecards": MagicMock(),
    }
    mock_db.__getitem__.side_effect = lambda name: collections.get(name, MagicMock())
    return mock_db, collections


# ==============================================================================
# 1. Question Set Discovery & Multi-Tenant Authorization Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_question_sets_includes_platform_and_institution_batches(vfstr_faculty):
    """Verify list_question_sets discovers platform sets and user's institution batches only."""
    mock_db, colls = make_mock_db()

    mock_batch_doc = {
        "_id": "batch-upload-vfstr-cse",
        "question_count": 25,
        "role": "Computer Science Faculty",
        "topics": ["Algorithms", "Data Structures"],
        "difficulties": ["medium", "hard"],
        "source_filename": "algorithms.csv",
        "institution_id": "VFSTR",
        "department": "CSE",
        "created_at": datetime.now(timezone.utc),
        "created_by_email": "cse_faculty@vfstr.ac.in",
    }

    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=[mock_batch_doc])
    colls["interview_questions"].aggregate.return_value = mock_cursor

    result = await QuestionBankService.list_question_sets(mock_db, vfstr_faculty)

    # 5 platform canonical sets + 1 institution batch
    assert result.total >= 6
    platform_sets = [s for s in result.items if s.source_type == "platform"]
    inst_sets = [s for s in result.items if s.source_type == "institution"]

    assert len(platform_sets) == 5
    assert any(s.set_id == "platform-role-software-development-engineer" for s in platform_sets)
    assert len(inst_sets) == 1
    assert inst_sets[0].set_id == "batch-upload-vfstr-cse"
    assert inst_sets[0].question_count == 25
    assert inst_sets[0].institution_id == "VFSTR"


@pytest.mark.asyncio
async def test_validate_question_set_access_cross_institution_rejected(vfstr_faculty):
    """Verify accessing another institution's question set raises 403 Forbidden."""
    mock_db, colls = make_mock_db()

    # Question belongs to OTHER_UNIV
    colls["interview_questions"].find_one = AsyncMock(return_value={
        "_id": "q-other-1",
        "import_batch_id": "batch-upload-other",
        "institution_id": "OTHER_UNIV",
        "department": "CSE",
    })

    with pytest.raises(HTTPException) as exc_info:
        await QuestionBankService.validate_question_set_access(
            mock_db, "batch-upload-other", vfstr_faculty
        )
    assert exc_info.value.status_code == 403
    assert "belongs to another institution" in exc_info.value.detail


@pytest.mark.asyncio
async def test_validate_question_set_access_department_mismatch_rejected(vfstr_faculty):
    """Verify faculty/department admin cannot use question batches from another department."""
    mock_db, colls = make_mock_db()

    # Question from VFSTR but department ECE
    colls["interview_questions"].find_one = AsyncMock(return_value={
        "_id": "q-ece-1",
        "import_batch_id": "batch-upload-ece",
        "institution_id": "VFSTR",
        "department": "ECE",
    })

    with pytest.raises(HTTPException) as exc_info:
        await QuestionBankService.validate_question_set_access(
            mock_db, "batch-upload-ece", vfstr_faculty
        )
    assert exc_info.value.status_code == 403
    assert "belongs to another department" in exc_info.value.detail


@pytest.mark.asyncio
async def test_preview_question_set_returns_metadata_and_items(vfstr_admin):
    """Verify previewing a question set returns metadata and sample question items."""
    mock_db, colls = make_mock_db()

    sample_questions = [
        {
            "question_id": "q-101",
            "question_text": "Explain the time complexity of Dijkstra's algorithm with a min-heap.",
            "topic": "Algorithms",
            "difficulty": "medium",
            "question_type": "conceptual",
            "expected_answer": "O((V + E) log V)",
            "institution_id": "VFSTR",
            "import_batch_id": "batch-vfstr-algo",
        }
    ]

    colls["interview_questions"].find_one = AsyncMock(return_value=sample_questions[0])
    colls["interview_questions"].count_documents = AsyncMock(return_value=1)

    mock_cursor = MagicMock()
    mock_cursor.limit.return_value.to_list = AsyncMock(return_value=sample_questions)
    colls["interview_questions"].find.return_value = mock_cursor

    preview = await QuestionBankService.preview_question_set(
        mock_db, "batch-vfstr-algo", vfstr_admin, limit=5
    )

    assert preview.set_id == "batch-vfstr-algo"
    assert preview.question_count == 1
    assert preview.source_type == "institution"
    assert len(preview.questions) == 1
    assert "Dijkstra" in preview.questions[0]["question_text"]


# ==============================================================================
# 2. Interview Creation with Question Set Integration
# ==============================================================================

@pytest.mark.asyncio
async def test_create_interview_with_valid_question_set(vfstr_admin):
    """Verify creating interview with an authorized question set persists question_set_id."""
    mock_db, colls = make_mock_db()
    colls["university_interviews"].insert_one = AsyncMock(return_value=MagicMock(acknowledged=True))

    now = utc_now()
    interview_data = UniversityInterviewCreate(
        title="Campus Technical Placement Round",
        instructions="Complete all questions within 45 minutes.",
        scheduled_start_time=now + timedelta(days=1),
        scheduled_end_time=now + timedelta(days=1, hours=2),
        duration_minutes=45,
        target_department="CSE",
        target_cohort="2024-2028",
        question_set_id="platform-role-software-development-engineer",
        question_set_name="Software Development Engineer (SDE)",
    )

    created = await InterviewService.create_interview(mock_db, interview_data, vfstr_admin)

    assert created.question_set_id == "platform-role-software-development-engineer"
    assert created.question_set_name == "Software Development Engineer (SDE)"
    assert created.created_by_user_id == vfstr_admin.id
    assert created.created_by_email == vfstr_admin.email


@pytest.mark.asyncio
async def test_create_interview_default_backward_compatible(vfstr_admin):
    """Verify default interview creation without custom question set remains fully functional."""
    mock_db, colls = make_mock_db()
    colls["university_interviews"].insert_one = AsyncMock(return_value=MagicMock(acknowledged=True))

    now = utc_now()
    interview_data = UniversityInterviewCreate(
        title="General Assessment",
        instructions="Standard instructions.",
        scheduled_start_time=now + timedelta(days=2),
        scheduled_end_time=now + timedelta(days=2, hours=3),
        duration_minutes=60,
    )

    created = await InterviewService.create_interview(mock_db, interview_data, vfstr_admin)
    assert created.question_set_id is None
    assert created.question_set_name is None
    assert created.status.value == "scheduled"


# ==============================================================================
# 3. Candidate Search & Multi-Field Filtering
# ==============================================================================

@pytest.mark.asyncio
async def test_candidate_search_multi_filter(vfstr_admin):
    """Verify candidate search applies department, cohort, eligibility, and keyword search."""
    mock_db, colls = make_mock_db()

    mock_students = [
        {
            "s_no": 1,
            "registration_number": "241FA04001",
            "student_name": "Aarav Sharma",
            "student_name_raw": "Aarav Sharma",
            "email": "aarav.241fa04001@vfstr.ac.in",
            "section": "1",
            "department": "CSE",
            "batch_cohort": "2024-2028",
            "interview_eligible": True,
            "review_status": "approved",
            "institution_id": "VFSTR",
        },
        {
            "s_no": 2,
            "registration_number": "241FA04002",
            "student_name": "Bhavna Patel",
            "student_name_raw": "Bhavna Patel",
            "email": "bhavna.241fa04002@vfstr.ac.in",
            "section": "1",
            "department": "CSE",
            "batch_cohort": "2024-2028",
            "interview_eligible": False,
            "review_status": "quarantined",
            "institution_id": "VFSTR",
        },
    ]

    mock_find_cursor = MagicMock()
    mock_sort_cursor = MagicMock()
    mock_limit_cursor = MagicMock()
    mock_limit_cursor.to_list = AsyncMock(return_value=mock_students)
    mock_sort_cursor.limit.return_value = mock_limit_cursor
    mock_find_cursor.sort.return_value = mock_sort_cursor
    colls["interview_eligibility_registry"].find.return_value = mock_find_cursor

    mock_assign_cursor = MagicMock()
    mock_assign_cursor.to_list = AsyncMock(return_value=[])
    colls["student_interview_assignments"].find.return_value = mock_assign_cursor

    results = await InterviewService.search_eligible_candidates(
        db=mock_db,
        interview_id="int-123",
        section="1",
        department="CSE",
        batch_cohort="2024-2028",
        eligibility="all",
        search="Aarav",
        limit=10,
        current_admin=vfstr_admin,
    )

    assert len(results) == 2
    assert results[0].registration_number == "241FA04001"
    assert results[0].student_name == "Aarav Sharma"
    assert results[0].interview_eligible is True
    assert results[1].interview_eligible is False


# ==============================================================================
# 4. Selective Student Assignment & Server-Side Atomic Revalidation
# ==============================================================================

@pytest.mark.asyncio
async def test_selective_assignment_revalidates_and_rejects_cross_institution(vfstr_admin):
    """Verify server rejects cross-institution students during selective assignment."""
    mock_db, colls = make_mock_db()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-vfstr-1",
        "institution_id": "VFSTR",
        "target_department": "CSE",
        "target_cohort": "2024-2028",
        "status": "scheduled",
    })

    # Registry records: 1 valid VFSTR student, 1 student from OTHER_UNIV
    async def mock_registry_lookup(query):
        reg = query.get("registration_number")
        if reg == "241FA04001":
            return {
                "registration_number": "241FA04001",
                "institution_id": "VFSTR",
                "department": "CSE",
                "review_status": "approved",
                "interview_eligible": True,
            }
        elif reg == "999OTHER001":
            return {
                "registration_number": "999OTHER001",
                "institution_id": "OTHER_UNIV",
                "department": "CSE",
                "review_status": "approved",
                "interview_eligible": True,
            }
        return None

    colls["interview_eligibility_registry"].find_one = AsyncMock(side_effect=mock_registry_lookup)
    colls["student_interview_assignments"].find_one = AsyncMock(return_value=None)
    colls["student_interview_assignments"].insert_one = AsyncMock(return_value=MagicMock(acknowledged=True))
    colls["university_interviews"].update_one = AsyncMock()

    result = await InterviewService.assign_candidates(
        db=mock_db,
        interview_id="int-vfstr-1",
        reg_numbers=["241FA04001", "999OTHER001"],
        assigner=vfstr_admin,
    )

    assert result.assigned_count == 1
    assert result.failed_count == 1
    results_map = {r.registration_number: r for r in result.results}
    assert results_map["241FA04001"].success is True
    assert results_map["999OTHER001"].success is False
    assert "CROSS_INSTITUTION_UNAUTHORIZED" in results_map["999OTHER001"].reason


@pytest.mark.asyncio
async def test_selective_assignment_rejects_department_mismatch(vfstr_faculty):
    """Verify department reviewer cannot assign students outside their department."""
    mock_db, colls = make_mock_db()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-vfstr-1",
        "institution_id": "VFSTR",
        "target_department": "CSE",
        "status": "scheduled",
    })

    # Student belongs to ECE, while faculty is CSE
    colls["interview_eligibility_registry"].find_one = AsyncMock(return_value={
        "registration_number": "241FA05001",
        "institution_id": "VFSTR",
        "department": "ECE",
        "review_status": "approved",
        "interview_eligible": True,
    })

    # Convert faculty role temporarily to DEPARTMENT_ADMIN
    dept_admin = UserInDB(
        id="dept-admin-cse",
        email="cse_hod@vfstr.ac.in",
        role=UserRole.DEPARTMENT_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )

    result = await InterviewService.assign_candidates(
        db=mock_db,
        interview_id="int-vfstr-1",
        reg_numbers=["241FA05001"],
        assigner=dept_admin,
    )

    assert result.assigned_count == 0
    assert result.failed_count == 1
    assert "DEPARTMENT_MISMATCH" in result.results[0].reason


@pytest.mark.asyncio
async def test_selective_assignment_rejects_ineligible_student(vfstr_admin):
    """Verify server rejects ineligible student from the authoritative registry."""
    mock_db, colls = make_mock_db()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-vfstr-1",
        "institution_id": "VFSTR",
        "target_department": "CSE",
        "status": "scheduled",
    })

    colls["interview_eligibility_registry"].find_one = AsyncMock(return_value={
        "registration_number": "241FA04099",
        "institution_id": "VFSTR",
        "department": "CSE",
        "review_status": "quarantined",
        "interview_eligible": False,
        "review_reasons": ["Backlogs > 0", "CGPA < 7.0"],
    })

    result = await InterviewService.assign_candidates(
        db=mock_db,
        interview_id="int-vfstr-1",
        reg_numbers=["241FA04099"],
        assigner=vfstr_admin,
    )

    assert result.assigned_count == 0
    assert result.failed_count == 1
    assert "INELIGIBLE_CANDIDATE" in result.results[0].reason


@pytest.mark.asyncio
async def test_selective_assignment_handles_duplicates(vfstr_admin):
    """Verify server detects and skips already assigned candidates without failing the batch."""
    mock_db, colls = make_mock_db()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-vfstr-1",
        "institution_id": "VFSTR",
        "target_department": "CSE",
        "status": "scheduled",
    })

    colls["interview_eligibility_registry"].find_one = AsyncMock(return_value={
        "registration_number": "241FA04001",
        "institution_id": "VFSTR",
        "department": "CSE",
        "review_status": "approved",
        "interview_eligible": True,
    })

    colls["student_interview_assignments"].find_one = AsyncMock(return_value={
        "assignment_id": "assign-existing",
        "status": AssignmentStatus.ASSIGNED.value,
    })

    result = await InterviewService.assign_candidates(
        db=mock_db,
        interview_id="int-vfstr-1",
        reg_numbers=["241FA04001"],
        assigner=vfstr_admin,
    )

    assert result.assigned_count == 0
    assert result.failed_count == 1
    assert "DUPLICATE_ASSIGNMENT" in result.results[0].reason or "already assigned" in result.results[0].reason.lower()


@pytest.mark.asyncio
async def test_selective_assignment_rejects_empty_selection(vfstr_admin):
    """Verify assigning an empty list of registration numbers raises 422."""
    mock_db, colls = make_mock_db()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-vfstr-1",
        "status": "scheduled",
    })

    with pytest.raises(HTTPException) as exc_info:
        await InterviewService.assign_candidates(
            db=mock_db,
            interview_id="int-vfstr-1",
            reg_numbers=[],
            assigner=vfstr_admin,
        )
    assert exc_info.value.status_code == 422
    assert "No candidate registration numbers provided" in exc_info.value.detail


# ==============================================================================
# 5. Student Interview Progression with Question Sets & Multi-Tenant Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_student_starts_interview_receives_first_question_from_custom_set(vfstr_student):
    """Verify student starts assigned interview and receives the first question in sequence from custom set."""
    mock_db, colls = make_mock_db()
    now = utc_now()

    colls["student_interview_assignments"].find_one = AsyncMock(return_value={
        "assignment_id": "asgn-qset-1",
        "interview_id": "int-qset-1",
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.ASSIGNED.value,
    })
    colls["student_interview_assignments"].update_one = AsyncMock()

    colls["interview_sessions"].find_one = AsyncMock(return_value=None)
    colls["interview_sessions"].insert_one = AsyncMock()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-qset-1",
        "title": "Algorithms Placement Round",
        "duration_minutes": 45,
        "question_set_id": "batch-vfstr-algo",
        "role": "Software Development Engineer",
    })

    q1_doc = {
        "question_id": "q-algo-1",
        "question_text": "Explain QuickSort algorithm and its average time complexity.",
        "topic": "Algorithms",
        "question_type": "conceptual",
        "difficulty": "medium",
        "import_batch_id": "batch-vfstr-algo",
        "institution_id": "VFSTR",
        "question_number": 1,
    }

    # inst_check and stored_q queries
    colls["interview_questions"].find_one = AsyncMock(return_value=q1_doc)

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response = await InterviewSessionService.start_session(
            db=mock_db,
            assignment_id="asgn-qset-1",
            student_user=vfstr_student,
        )

    assert response.current_question_index == 1
    assert response.question_text == "Explain QuickSort algorithm and its average time complexity."
    assert response.topic == "Algorithms"


@pytest.mark.asyncio
async def test_student_submits_answer_advances_to_subsequent_question_in_custom_set(vfstr_student):
    """Verify student answer submission advances to subsequent question in custom batch without UnboundLocalError."""
    mock_db, colls = make_mock_db()
    now = utc_now()
    session_id = "sess-qset-1"

    colls["interview_sessions"].find_one = AsyncMock(return_value={
        "session_id": session_id,
        "interview_id": "int-qset-1",
        "assignment_id": "asgn-qset-1",
        "student_registration_number": "241FA04001",
        "student_institution_id": "VFSTR",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 1,
        "total_questions_target": 3,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=45),
        "selected_role": "Software Development Engineer",
        "active_question": {
            "question_text": "Explain QuickSort algorithm and its average time complexity.",
            "topic": "Algorithms",
            "difficulty": "medium",
            "question_type": "conceptual",
        },
    })
    colls["interview_sessions"].update_one = AsyncMock()
    colls["interview_responses"].insert_one = AsyncMock()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-qset-1",
        "question_set_id": "batch-vfstr-algo",
        "role": "Software Development Engineer",
    })

    q2_doc = {
        "question_id": "q-algo-2",
        "question_text": "Describe Binary Search Tree operations and balancing.",
        "topic": "Algorithms",
        "question_type": "conceptual",
        "difficulty": "medium",
        "import_batch_id": "batch-vfstr-algo",
        "institution_id": "VFSTR",
        "question_number": 2,
    }

    # inst_check returns verification doc, then next question returns q2
    colls["interview_questions"].find_one = AsyncMock(side_effect=[
        {"institution_id": "VFSTR"},  # inst_check
        q2_doc,  # stored_next_q
    ])

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    mock_provider.evaluate_answer = AsyncMock(return_value={
        "score": 8.0,
        "feedback": "Solid understanding of divide and conquer.",
        "strengths": ["Clear recurrence", "Average O(n log n) explained"],
        "improvements": [],
    })

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.submit_answer(
            db=mock_db,
            session_id=session_id,
            answer_text="QuickSort partitions the array around a pivot in O(n log n) average time.",
            student_user=vfstr_student,
        )

    assert response.is_session_completed is False
    assert response.next_question is not None
    assert response.next_question.question_index == 2
    assert response.next_question.question_text == "Describe Binary Search Tree operations and balancing."


@pytest.mark.asyncio
async def test_student_skips_question_advances_to_subsequent_question_in_custom_set(vfstr_student):
    """Verify skipping question advances to next question from custom batch."""
    mock_db, colls = make_mock_db()
    now = utc_now()
    session_id = "sess-qset-skip"

    colls["interview_sessions"].find_one = AsyncMock(return_value={
        "session_id": session_id,
        "interview_id": "int-qset-1",
        "assignment_id": "asgn-qset-1",
        "student_registration_number": "241FA04001",
        "student_institution_id": "VFSTR",
        "session_status": SessionStatus.IN_PROGRESS.value,
        "current_question_index": 2,
        "total_questions_target": 3,
        "current_difficulty": "medium",
        "expires_at": now + timedelta(minutes=45),
        "selected_role": "Software Development Engineer",
        "active_question": {
            "question_text": "Describe Binary Search Tree operations and balancing.",
            "topic": "Algorithms",
            "difficulty": "medium",
            "question_type": "conceptual",
        },
    })
    colls["interview_sessions"].update_one = AsyncMock()
    colls["interview_responses"].insert_one = AsyncMock()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-qset-1",
        "question_set_id": "batch-vfstr-algo",
        "role": "Software Development Engineer",
    })

    q3_doc = {
        "question_id": "q-algo-3",
        "question_text": "Explain Dynamic Programming memoization vs tabulation.",
        "topic": "Algorithms",
        "question_type": "conceptual",
        "difficulty": "medium",
        "import_batch_id": "batch-vfstr-algo",
        "institution_id": "VFSTR",
        "question_number": 3,
    }

    colls["interview_questions"].find_one = AsyncMock(side_effect=[
        {"institution_id": "VFSTR"},  # inst_check
        q3_doc,  # stored_next_q
    ])

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)

    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response: SubmitAnswerResponse = await InterviewSessionService.skip_question(
            db=mock_db,
            session_id=session_id,
            student_user=vfstr_student,
        )

    assert response.is_skipped is True
    assert response.next_question is not None
    assert response.next_question.question_index == 3
    assert response.next_question.question_text == "Explain Dynamic Programming memoization vs tabulation."


@pytest.mark.asyncio
async def test_cross_institution_question_set_isolated_from_student_session(vfstr_student):
    """Verify question set belonging to OTHER_UNIV is blocked and falls back to safe platform pool."""
    mock_db, colls = make_mock_db()
    now = utc_now()

    colls["student_interview_assignments"].find_one = AsyncMock(return_value={
        "assignment_id": "asgn-cross-1",
        "interview_id": "int-cross-1",
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.ASSIGNED.value,
    })
    colls["student_interview_assignments"].update_one = AsyncMock()
    colls["interview_sessions"].find_one = AsyncMock(return_value=None)
    colls["interview_sessions"].insert_one = AsyncMock()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-cross-1",
        "title": "Cross Institution Attempt",
        "duration_minutes": 45,
        "question_set_id": "batch-other-private",
        "role": "Software Development Engineer",
    })

    platform_fallback_doc = {
        "question_id": "q-plat-1",
        "question_text": "Explain SOLID principles in software engineering.",
        "topic": "Software Engineering",
        "question_type": "conceptual",
        "difficulty": "medium",
        "role": "Software Development Engineer",
    }

    # inst_check returns an OTHER_UNIV batch doc!
    # Fallback platform query returns platform question
    colls["interview_questions"].find_one = AsyncMock(side_effect=[
        {"institution_id": "OTHER_UNIV", "import_batch_id": "batch-other-private"},  # inst_check mismatch!
        platform_fallback_doc,  # fallback platform question
    ])

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response = await InterviewSessionService.start_session(
            db=mock_db,
            assignment_id="asgn-cross-1",
            student_user=vfstr_student,
        )

    assert response.question_text == "Explain SOLID principles in software engineering."
    assert response.question_text != "Private question from other institution"


@pytest.mark.asyncio
async def test_missing_or_stale_question_set_falls_back_safely(vfstr_student):
    """Verify non-existent/stale question_set_id does not crash the session and falls back gracefully."""
    mock_db, colls = make_mock_db()
    now = utc_now()

    colls["student_interview_assignments"].find_one = AsyncMock(return_value={
        "assignment_id": "asgn-stale-1",
        "interview_id": "int-stale-1",
        "student_registration_number": "241FA04001",
        "status": AssignmentStatus.ASSIGNED.value,
    })
    colls["student_interview_assignments"].update_one = AsyncMock()
    colls["interview_sessions"].find_one = AsyncMock(return_value=None)
    colls["interview_sessions"].insert_one = AsyncMock()

    colls["university_interviews"].find_one = AsyncMock(return_value={
        "interview_id": "int-stale-1",
        "title": "Stale Question Set Test",
        "duration_minutes": 45,
        "question_set_id": "batch-deleted-nonexistent",
        "role": "Software Development Engineer",
    })

    platform_doc = {
        "question_id": "q-plat-fallback",
        "question_text": "What is the difference between synchronous and asynchronous I/O?",
        "topic": "Operating Systems",
        "question_type": "conceptual",
        "difficulty": "medium",
        "role": "Software Development Engineer",
    }

    # inst_check returns None (batch not found in questions collection)
    # Then query 1 returns platform_doc
    colls["interview_questions"].find_one = AsyncMock(side_effect=[
        None,  # inst_check
        platform_doc,  # platform query tier 1
    ])

    mock_provider = AsyncMock()
    mock_provider.get_mode = MagicMock(return_value=EvaluatorMode.MOCK_RULE_ENGINE)
    with patch("app.services.interview_session_service.get_ai_provider", return_value=mock_provider):
        response = await InterviewSessionService.start_session(
            db=mock_db,
            assignment_id="asgn-stale-1",
            student_user=vfstr_student,
        )

    assert response.current_question_index == 1
    assert response.question_text == "What is the difference between synchronous and asynchronous I/O?"
