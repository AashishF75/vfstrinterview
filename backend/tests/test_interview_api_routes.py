import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserInDB, UserRole
from app.core.security import create_access_token
from app.core.database import get_interview_database
from app.api.deps import get_current_user, get_current_active_user


@pytest.fixture
def client():
    return TestClient(app)


def test_admin_routes_reject_unauthenticated(client):
    """Verify that unauthenticated requests to admin interview endpoints are rejected with 401."""
    response = client.get("/api/admin/interviews")
    assert response.status_code == 401


def test_admin_routes_reject_faculty(client):
    """Verify that faculty users cannot access university admin interview management."""
    faculty_user = UserInDB(
        id="fac-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
    )

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    try:
        response = client.get("/api/admin/interviews")
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_admin_routes_reject_student(client):
    """Verify that student users cannot access university admin interview management."""
    student_user = UserInDB(
        id="stu-1",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )

    app.dependency_overrides[get_current_active_user] = lambda: student_user
    try:
        response = client.get("/api/admin/interviews")
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_student_routes_reject_unverified_registration_number(client):
    """Verify that students without a valid registration number are denied access."""
    unverified_student = UserInDB(
        id="stu-unverified",
        email="unverified@gmail.com",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number=None,  # Not verified!
    )

    app.dependency_overrides[get_current_active_user] = lambda: unverified_student
    try:
        response = client.get("/api/student/interviews/my-assignments")
        assert response.status_code == 403
        assert "not linked to a verified university registration number" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_admin_routes_permit_department_admin(client):
    """Verify that department_admin users can access interview administration."""
    dept_admin = UserInDB(
        id="dept-1",
        email="dept_admin@vfstr.ac.in",
        role=UserRole.DEPARTMENT_ADMIN,
        hashed_password="pw",
        institution_id="VFSTR",
    )

    mock_db = AsyncMock()
    mock_db["university_interviews"].find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

    app.dependency_overrides[get_current_active_user] = lambda: dept_admin
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        response = client.get("/api/admin/interviews")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_proctoring_review_routes_permit_faculty(client):
    """Verify that faculty users can inspect proctoring event timelines."""
    faculty_user = UserInDB(
        id="fac-1",
        email="faculty@vfstr.ac.in",
        role=UserRole.FACULTY,
        hashed_password="pw",
        institution_id="VFSTR",
    )

    mock_db = AsyncMock()
    mock_db["interview_sessions"].find_one = AsyncMock(return_value={
        "session_id": "sess-test-1",
        "assignment_id": "asgn-1",
        "student_registration_number": "241FA04001",
        "session_status": "completed",
        "proctoring_review_status": "unreviewed",
        "proctoring_review_notes": None,
    })
    mock_db["proctoring_events"].find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

    app.dependency_overrides[get_current_active_user] = lambda: faculty_user
    app.dependency_overrides[get_interview_database] = lambda: mock_db
    try:
        response = client.get("/api/admin/interviews/sessions/sess-test-1/proctoring-events")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-test-1"
        assert data["review_status"] == "unreviewed"
    finally:
        app.dependency_overrides.clear()


def test_proctoring_review_routes_reject_student(client):
    """Verify that students cannot access administrative proctoring review routes."""
    student_user = UserInDB(
        id="stu-1",
        email="student@vfstr.ac.in",
        role=UserRole.STUDENT,
        hashed_password="pw",
        institution_id="VFSTR",
        registration_number="241FA04001",
    )

    app.dependency_overrides[get_current_active_user] = lambda: student_user
    try:
        response = client.get("/api/admin/interviews/sessions/sess-test-1/proctoring-events")
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
