import pytest
import io
import json
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserInDB, UserRole
from app.core.database import get_interview_database
from app.api.deps import get_current_active_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def faculty_user():
    return UserInDB(
        id="fac-inst-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
        department="CSE",
    )


@pytest.fixture
def student_user():
    return UserInDB(
        id="stu-inst-1",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )


@pytest.fixture
def university_admin_user():
    return UserInDB(
        id="admin-inst-1",
        email="admin@vfstr.ac.in",
        role=UserRole.UNIVERSITY_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
    )


def test_preview_questions_rejects_unauthenticated(client):
    """Verify unauthenticated requests to question preview are rejected with 401."""
    files = {"file": ("sample.csv", io.BytesIO(b"Topic,Question\nAI,Explain backprop"), "text/csv")}
    response = client.post("/api/admin/interviews/questions/preview", files=files)
    assert response.status_code == 401


def test_preview_questions_rejects_student(client, student_user):
    """Verify students cannot preview or upload question banks (403)."""
    app.dependency_overrides[get_current_active_user] = lambda: student_user
    try:
        files = {"file": ("sample.csv", io.BytesIO(b"Topic,Question\nAI,Explain backprop"), "text/csv")}
        response = client.post("/api/admin/interviews/questions/preview", files=files)
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_preview_questions_csv_success(client, faculty_user):
    """Verify faculty can upload a CSV and receive a structured extraction preview."""
    csv_content = (
        "Topic,Question,QuestionType,Difficulty,ExpectedAnswer\n"
        "Operating Systems,Explain virtual memory and page fault handling in Linux.,conceptual,medium,Virtual memory uses paging to map virtual addresses to physical RAM.\n"
        "Data Structures,Write an algorithm to reverse a singly linked list in O(n) time.,coding,easy,Use three pointers prev current next to invert link directions.\n"
    ).encode("utf-8")

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        files = {"file": ("sample_questions.csv", io.BytesIO(csv_content), "text/csv")}
        data = {"default_topic": "Computer Science"}
        response = client.post("/api/admin/interviews/questions/preview", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert result["filename"] == "sample_questions.csv"
        assert result["total_extracted"] == 2
        assert result["valid_count"] == 2
        assert result["invalid_count"] == 0
        assert len(result["questions"]) == 2

        q0 = result["questions"][0]
        assert "virtual memory" in q0["question_text"]
        assert q0["topic"] == "Operating Systems"
        assert q0["difficulty"] == "medium"
        assert q0["question_type"] == "conceptual"
        assert q0["is_valid"] is True
        assert len(q0["validation_errors"]) == 0

        q1 = result["questions"][1]
        assert "singly linked list" in q1["question_text"]
        assert q1["question_type"] == "coding"
        assert q1["difficulty"] == "easy"
    finally:
        app.dependency_overrides.clear()


def test_preview_questions_json_success(client, faculty_user):
    """Verify faculty can upload a JSON array of questions for preview."""
    json_data = [
        {
            "question_text": "What is the difference between TCP and UDP protocols?",
            "topic": "Networking",
            "difficulty": "medium",
            "question_type": "conceptual",
            "expected_answer": "TCP is connection-oriented with guaranteed delivery, UDP is connectionless.",
        }
    ]
    raw_json = json.dumps(json_data).encode("utf-8")

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        files = {"file": ("networking.json", io.BytesIO(raw_json), "application/json")}
        response = client.post("/api/admin/interviews/questions/preview", files=files)

        assert response.status_code == 200
        result = response.json()
        assert result["total_extracted"] == 1
        assert result["valid_count"] == 1
        assert "TCP and UDP" in result["questions"][0]["question_text"]
    finally:
        app.dependency_overrides.clear()


def test_preview_questions_flags_invalid_questions_without_crashing(client, faculty_user):
    """Verify short or malformed questions are flagged with is_valid=False and validation_errors."""
    csv_content = (
        "Topic,Question\n"
        "Math,Short\n"
        "Algorithms,Explain merge sort time complexity and recursion tree.\n"
    ).encode("utf-8")

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        files = {"file": ("test_invalid.csv", io.BytesIO(csv_content), "text/csv")}
        response = client.post("/api/admin/interviews/questions/preview", files=files)

        assert response.status_code == 200
        result = response.json()
        assert result["total_extracted"] == 2
        assert result["valid_count"] == 1
        assert result["invalid_count"] == 1

        short_q = result["questions"][0]
        assert short_q["is_valid"] is False
        assert any("minimum 10 characters" in err for err in short_q["validation_errors"])
    finally:
        app.dependency_overrides.clear()


def test_preview_questions_rejects_unsupported_format(client, faculty_user):
    """Verify unsupported file extensions produce 400 Bad Request."""
    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        files = {"file": ("malicious.exe", io.BytesIO(b"binary data"), "application/octet-stream")}
        response = client.post("/api/admin/interviews/questions/preview", files=files)
        assert response.status_code == 400
        assert "Unsupported file format" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_preview_questions_rejects_empty_file(client, faculty_user):
    """Verify empty file upload produces 400 Bad Request."""
    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
        response = client.post("/api/admin/interviews/questions/preview", files=files)
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_save_confirmed_questions_success(client, faculty_user):
    """Verify faculty can confirm and save verified questions tagged with institution_id."""
    mock_db = AsyncMock()
    mock_db["interview_questions"].insert_many = AsyncMock(return_value=AsyncMock(inserted_ids=["1", "2"]))

    save_payload = {
        "role": "Software Development Engineer",
        "questions": [
            {
                "question_text": "Describe the lifecycle of a thread in Java and state transitions.",
                "topic": "Java Concurrency",
                "difficulty": "medium",
                "question_type": "conceptual",
                "expected_answer": "New, Runnable, Blocked, Waiting, Timed Waiting, Terminated.",
            },
            {
                "question_text": "How does HashMap handle collisions in Java 8?",
                "topic": "Data Structures",
                "difficulty": "easy",
                "question_type": "conceptual",
                "expected_answer": "LinkedList transitions to Red-Black tree after TREEIFY_THRESHOLD (8).",
            },
        ],
    }

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        response = client.post("/api/admin/interviews/questions/save", json=save_payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["saved_count"] == 2
        assert data["institution_id"] == "VFSTR"
        assert "batch_id" in data

        # Verify insert_many was called with documents containing institution_id & department
        inserted_call = mock_db["interview_questions"].insert_many.call_args[0][0]
        assert len(inserted_call) == 2
        assert inserted_call[0]["institution_id"] == "VFSTR"
        assert inserted_call[0]["department"] == "CSE"
        assert inserted_call[0]["created_by_email"] == "faculty@vfstr.ac.in"
        assert inserted_call[0]["topic"] == "Java Concurrency"
    finally:
        app.dependency_overrides.clear()


def test_save_confirmed_questions_rejects_student(client, student_user):
    """Verify students cannot save questions to the institution question bank."""
    mock_db = AsyncMock()
    app.dependency_overrides[get_current_active_user] = lambda: student_user
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        response = client.post(
            "/api/admin/interviews/questions/save",
            json={
                "questions": [
                    {
                        "question_text": "What is polymorphism in object oriented programming?",
                        "topic": "OOP",
                    }
                ]
            },
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_list_institution_questions(client, faculty_user):
    """Verify faculty can query questions within their institution scope."""
    mock_db = AsyncMock()
    mock_db["interview_questions"].count_documents = AsyncMock(return_value=1)
    mock_cursor = AsyncMock()
    mock_cursor.sort = lambda *args, **kwargs: mock_cursor
    mock_cursor.skip = lambda *args, **kwargs: mock_cursor
    mock_cursor.limit = lambda *args, **kwargs: mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "question_id": "q-101",
            "institution_id": "VFSTR",
            "department": "CSE",
            "role": "SDE",
            "topic": "Algorithms",
            "difficulty": "medium",
            "question_type": "conceptual",
            "question_text": "Explain Dijkstra shortest path algorithm.",
            "created_by_email": "faculty@vfstr.ac.in",
        }
    ])
    mock_db["interview_questions"].find = lambda *args, **kwargs: mock_cursor

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        response = client.get("/api/admin/interviews/questions?topic=Algorithms")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["question_id"] == "q-101"
        assert data["items"][0]["institution_id"] == "VFSTR"
    finally:
        app.dependency_overrides.clear()
