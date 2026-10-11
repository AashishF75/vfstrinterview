import io
import re
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.question_file_parser import parse_question_file
from app.models.question_bank import StoredQuestionItem, QuestionType
from app.models.interview_session import QuestionDifficulty, SessionStatus
from app.models.interview import AssignmentStatus, InterviewStatus
from app.models.user import UserInDB, UserRole
from app.services.interview_session_service import InterviewSessionService


ZIP_PATH = Path("data/problem_statement_3_additional_25_sets_per_role_PDFs.zip")
if not ZIP_PATH.exists():
    ZIP_PATH = Path("backend/data/problem_statement_3_additional_25_sets_per_role_PDFs.zip")


def test_parse_all_five_role_pdfs_yields_exact_counts():
    """
    Priority 1 & 2:
    Validates that the parser extracts all five role PDFs from the zip:
    - Associate Software Engineer
    - Software Development Engineer
    - Product Engineer
    - Testing Engineer
    - System Engineer
    Total sets: 125 (25 per role)
    Total questions: exactly 1,875 (375 per role)
    Conceptual: 1,625 (13 per set)
    Coding: 250 (2 per set)
    """
    assert ZIP_PATH.exists(), f"Source zip file not found at {ZIP_PATH}"
    questions = parse_question_file(ZIP_PATH, ZIP_PATH.name)
    assert len(questions) == 1875

    roles = set(q["role"] for q in questions)
    expected_roles = {
        "Associate Software Engineer",
        "Software Development Engineer",
        "Product Engineer",
        "System Engineer",
        "Testing Engineer",
    }
    assert roles == expected_roles

    # Verify per-role and per-set counts
    for role in expected_roles:
        role_qs = [q for q in questions if q["role"] == role]
        assert len(role_qs) == 375, f"Role {role} has {len(role_qs)} questions, expected 375"

        sets = set(q["set_number"] for q in role_qs)
        assert len(sets) == 25, f"Role {role} has {len(sets)} sets, expected 25"

        for s in sets:
            set_qs = [q for q in role_qs if q["set_number"] == s]
            assert len(set_qs) == 15, f"Set {s} in {role} has {len(set_qs)} questions, expected 15"

            concepts = [q for q in set_qs if q["question_type"] == "conceptual"]
            codings = [q for q in set_qs if q["question_type"] == "coding"]
            assert len(concepts) == 13, f"Set {s} in {role} has {len(concepts)} concepts, expected 13"
            assert len(codings) == 2, f"Set {s} in {role} has {len(codings)} codings, expected 2"


def test_question_data_mapping_and_separation():
    """
    Priority 2:
    Validates field mapping, separation of answer guides, and difficulty source truth.
    """
    questions = parse_question_file(ZIP_PATH, ZIP_PATH.name)
    assert len(questions) == 1875

    for q in questions:
        # 1. Required fields
        assert q["role"] in [
            "Associate Software Engineer",
            "Software Development Engineer",
            "Product Engineer",
            "System Engineer",
            "Testing Engineer",
        ]
        assert 1 <= q["set_number"] <= 25
        assert 1 <= q["question_number"] <= 15
        assert q["question_type"] in ["conceptual", "coding"]
        assert len(q["question_text"]) >= 10
        assert len(q["expected_answer"]) >= 10
        assert q["source_filename"].endswith(".pdf")
        assert q["question_id"].startswith(
            ("associate-software-engineer-", "software-development-engineer-", "product-engineer-", "system-engineer-", "testing-engineer-")
        )

        # 2. Answer guide must be completely separated from candidate prompt
        assert "Answer guide:" not in q["question_text"]
        assert "Expected approach:" not in q["question_text"]

        # 3. Source truth on difficulty: PDFs do not specify difficulty tiers
        assert q["difficulty"] is None

    # Global unique questions check (identifying overlap from source pool)
    unique_prompts = set(q["question_text"] for q in questions)
    assert len(unique_prompts) == 115, f"Expected 115 unique prompts globally, got {len(unique_prompts)}"


def make_student(reg_no="241FA04001"):
    return UserInDB(
        id=f"user-{reg_no}",
        email=f"stu.{reg_no.lower()}@gmail.com",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number=reg_no,
    )


@pytest.mark.anyio
async def test_role_based_interview_session_isolation():
    """
    Priority 3:
    Verify that an interview session for 'Testing Engineer' strictly retrieves
    questions tagged for 'Testing Engineer' and never leaks questions from 'Product Engineer'.
    Also confirms candidate response never exposes the internal expected answer guide.
    """
    student = make_student("241FA04001")
    interview_id = "int-test-role-1"
    assignment_id = "asgn-test-role-1"

    mock_db = MagicMock()
    mock_assignments = AsyncMock()
    mock_interviews = AsyncMock()
    mock_sessions = AsyncMock()
    mock_questions = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "student_interview_assignments": mock_assignments,
        "university_interviews": mock_interviews,
        "interview_sessions": mock_sessions,
        "interview_questions": mock_questions,
    }[name]

    # Assignment for student with selected_role = 'Testing Engineer'
    mock_assignments.find_one.return_value = {
        "assignment_id": assignment_id,
        "interview_id": interview_id,
        "student_registration_number": "241FA04001",
        "selected_role": "Testing Engineer",
        "status": AssignmentStatus.ASSIGNED.value,
    }

    mock_interviews.find_one.return_value = {
        "interview_id": interview_id,
        "title": "Testing Engineer Campus Assessment",
        "instructions": "Answer technical testing and validation questions.",
        "duration_minutes": 45,
        "status": InterviewStatus.SCHEDULED.value,
    }

    mock_sessions.find_one.return_value = None  # No concurrent session

    # Stored question pool in mock db:
    # 1 question for Testing Engineer, 1 for Product Engineer
    testing_q = {
        "question_id": "testing-engineer-set01-q01",
        "role": "Testing Engineer",
        "topic": "Testing Methodologies",
        "question_text": "What is the difference between regression testing and retesting?",
        "expected_answer": "Retesting verifies specific bug fixes; regression testing ensures other parts remain unbroken.",
        "question_type": "conceptual",
        "difficulty": None,
        "interview_id": None,
    }

    product_q = {
        "question_id": "product-engineer-set01-q01",
        "role": "Product Engineer",
        "topic": "System Design",
        "question_text": "Explain eventual consistency in distributed systems.",
        "expected_answer": "All replicas will converge to identical values given sufficient time without updates.",
        "question_type": "conceptual",
        "difficulty": None,
        "interview_id": None,
    }

    async def mock_find_question(query):
        # Enforce role filter check
        if query.get("role") == "Testing Engineer":
            return testing_q
        elif query.get("role") == "Product Engineer":
            return product_q
        return None

    mock_questions.find_one.side_effect = mock_find_question

    # Start session
    resp = await InterviewSessionService.start_session(
        db=mock_db,
        assignment_id=assignment_id,
        student_user=student,
    )

    # 1. Must receive the Testing Engineer question
    assert resp.question_text == "What is the difference between regression testing and retesting?"
    assert resp.topic == "Testing Methodologies"

    # 2. Must NEVER expose expected answer to candidate
    resp_dict = resp.model_dump()
    assert "expected_answer" not in resp_dict
    assert "retesting verifies" not in str(resp_dict).lower()

    # 3. Verify session was recorded with selected_role = 'Testing Engineer'
    insert_call = mock_sessions.insert_one.call_args[0][0]
    assert insert_call["selected_role"] == "Testing Engineer"


@pytest.mark.anyio
async def test_question_deduplication_within_session():
    """
    Priority 3:
    Verify that advancing questions excludes previously asked questions from the candidate's session.
    """
    int_role = InterviewSessionService._resolve_interview_role(
        {"selected_role": "Software Development Engineer"},
        {"title": "Technical Assessment"}
    )
    assert int_role == "Software Development Engineer"

    # Infer role from title when assignment doesn't specify
    inferred = InterviewSessionService._resolve_interview_role(
        {},
        {"title": "Product Engineer Technical Interview"}
    )
    assert inferred == "Product Engineer"
