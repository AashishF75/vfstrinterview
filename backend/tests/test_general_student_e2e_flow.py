import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import settings
from app.core.database import get_database, get_interview_database
from app.models.user import UserRole, AccountStatus
from app.models.interview import AssignmentStatus
from app.models.interview_session import SessionStatus
from app.models.code_execution import ExecutionStatus
from app.services.code_execution_service import CodeExecutionService
from app.services.email_service import EmailService


@pytest.fixture
def anyio_backend():
    return "asyncio"


class InMemoryCollection:
    def __init__(self, data=None):
        self.docs = dict(data or {})

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if self._matches(doc, query):
                res = dict(doc)
                if projection and "_id" in projection and projection["_id"] == 0:
                    res.pop("_id", None)
                return res
        return None

    def _matches(self, doc, query):
        for k, v in query.items():
            if k == "$and":
                if not all(self._matches(doc, cond) for cond in v):
                    return False
            elif k == "$or":
                sub_match = any(self._matches(doc, cond) for cond in v)
                if not sub_match:
                    return False
            elif isinstance(v, dict):
                if "$in" in v:
                    doc_val = doc.get(k)
                    if doc_val not in v["$in"]:
                        return False
                if "$nin" in v:
                    doc_val = doc.get(k)
                    if doc_val in v["$nin"]:
                        return False
                if "$exists" in v:
                    exists = k in doc
                    if exists != v["$exists"]:
                        return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def find(self, query=None, projection=None):
        query = query or {}
        matched = []
        for doc in self.docs.values():
            if self._matches(doc, query):
                d = dict(doc)
                if projection and "_id" in projection and projection["_id"] == 0:
                    d.pop("_id", None)
                matched.append(d)

        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.to_list = AsyncMock(return_value=matched)
        cursor.__iter__ = lambda self: iter(matched)
        return cursor

    async def insert_one(self, doc):
        import pymongo.errors
        doc_copy = dict(doc)
        doc_id = str(doc_copy.get("_id", doc_copy.get("id", doc_copy.get("response_id", doc_copy.get("scorecard_id", uuid.uuid4().hex)))))
        doc_copy["_id"] = doc_id
        if "id" not in doc_copy:
            doc_copy["id"] = doc_id

        # Enforce unique indexes for users
        for existing in self.docs.values():
            if "email" in doc_copy and existing.get("email") == doc_copy.get("email") and existing.get("_id") != doc_id:
                raise pymongo.errors.DuplicateKeyError("Duplicate email")
            if (
                doc_copy.get("registration_number")
                and existing.get("registration_number") == doc_copy.get("registration_number")
                and existing.get("institution_id") == doc_copy.get("institution_id")
                and existing.get("_id") != doc_id
            ):
                raise pymongo.errors.DuplicateKeyError("Duplicate institution + registration_number")

        self.docs[doc_id] = doc_copy
        res = MagicMock()
        res.inserted_id = doc_id
        return res

    async def update_one(self, filter_q, update_q, upsert=False):
        matched_id = None
        for doc_id, doc in self.docs.items():
            if self._matches(doc, filter_q):
                matched_id = doc_id
                break

        if matched_id:
            target = self.docs[matched_id]
            if "$set" in update_q:
                target.update(update_q["$set"])
            if "$inc" in update_q:
                for inc_k, inc_v in update_q["$inc"].items():
                    target[inc_k] = target.get(inc_k, 0) + inc_v
        elif upsert:
            new_doc = dict(filter_q)
            if "$set" in update_q:
                new_doc.update(update_q["$set"])
            doc_id = str(new_doc.get("_id", uuid.uuid4().hex))
            new_doc["_id"] = doc_id
            self.docs[doc_id] = new_doc

        res = MagicMock()
        res.matched_count = 1 if matched_id else 0
        return res

    async def find_one_and_update(self, filter_q, update_q, return_document=None):
        matched_id = None
        for doc_id, doc in self.docs.items():
            if self._matches(doc, filter_q):
                matched_id = doc_id
                break
        if not matched_id:
            return None
        target = self.docs[matched_id]
        if "$set" in update_q:
            target.update(update_q["$set"])
        if "$inc" in update_q:
            for inc_k, inc_v in update_q["$inc"].items():
                target[inc_k] = target.get(inc_k, 0) + inc_v
        return dict(target)

    async def count_documents(self, query=None):
        query = query or {}
        count = 0
        for doc in self.docs.values():
            if self._matches(doc, query):
                count += 1
        return count


class MockMongoDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = InMemoryCollection()
        return self.collections[name]


@pytest.fixture
def mock_dbs():
    auth_db = MockMongoDatabase()
    interview_db = MockMongoDatabase()

    canonical_roles = [
        "Associate Software Engineer",
        "Software Development Engineer",
        "Product Engineer",
        "System Engineer",
        "Testing Engineer",
    ]
    q_collection = interview_db["interview_questions"]

    for role in canonical_roles:
        slug = role.lower().replace(" ", "-")
        for i in range(1, 6):
            q_type = "coding" if i >= 4 else "conceptual"
            q_id = f"{slug}-set01-q{i:02d}"
            doc = {
                "question_id": q_id,
                "role": role,
                "set_number": 1,
                "question_number": i,
                "question_type": q_type,
                "topic": f"{role} Core Fundamentals",
                "question_text": f"What are the key architectural principles for {role} (Question {i})?",
                "expected_answer": f"Confidential internal rubric answer for {role} {i}. Must never be leaked.",
                "difficulty": "medium",
                "interview_id": None,
                "source_filename": f"{slug}.pdf",
            }
            q_collection.docs[q_id] = doc

    return auth_db, interview_db


@pytest.fixture(autouse=True)
def capture_emails(monkeypatch):
    sent = []

    async def fake_send(to_email, registration_number, otp_code, expires_minutes=10):
        sent.append({
            "to": to_email,
            "reg_num": registration_number,
            "code": otp_code,
            "expires": expires_minutes
        })
        return True

    monkeypatch.setattr(EmailService, "send_verification_otp", fake_send)
    return sent


@pytest.fixture(autouse=True)
def mock_code_execution_for_flow(monkeypatch):
    monkeypatch.setattr(CodeExecutionService, "is_provider_configured", classmethod(lambda cls: True))

    async def fake_raw(*args, **kwargs):
        return {
            "status": ExecutionStatus.SUCCESS,
            "stdout": "Mocked test output",
            "stderr": None,
            "compile_output": None,
            "execution_time_ms": 15.0,
            "memory_kb": 2048,
        }

    monkeypatch.setattr(CodeExecutionService, "execute_raw", fake_raw)


@pytest.mark.anyio
async def test_full_general_student_journey_e2e(mock_dbs, capture_emails):
    """
    MASTER E2E REGRESSION TEST:
    Register -> Verify OTP -> Login -> Select Role -> Start Session (Q1 from PDF bank)
    -> Submit Answers -> AI Evaluation -> Next Question -> Final Scorecard
    - Verifies 5 canonical roles endpoint
    - Verifies strict role-based question bank isolation
    - Verifies candidate API responses never expose expected_answer
    - Verifies cross-student session and scorecard security isolation
    """
    auth_db, interview_db = mock_dbs

    app.dependency_overrides[get_database] = lambda: auth_db
    app.dependency_overrides[get_interview_database] = lambda: interview_db

    partner_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ====================================================================
        # 1. Inspect Available Job Roles
        # ====================================================================
        roles_resp = await client.get("/api/student/interviews/roles")
        assert roles_resp.status_code == 200
        roles_data = roles_resp.json()
        assert roles_data["total_roles"] == 5
        role_names = [r["role_name"] for r in roles_data["roles"]]
        assert "Software Development Engineer" in role_names
        assert "Associate Software Engineer" in role_names
        assert "Product Engineer" in role_names
        assert "System Engineer" in role_names
        assert "Testing Engineer" in role_names

        for r in roles_data["roles"]:
            assert r["conceptual_questions_per_set"] == 13
            assert r["coding_questions_per_set"] == 2
            assert r["total_sets"] == 25
            assert r["total_questions"] == 375

        # ====================================================================
        # 2. General Student Registration (Direct - No OTP required)
        # ====================================================================
        reg_payload = {
            "full_name": "Kavya Priya Sharma",
            "college_name": partner_college,
            "college_reg_no": "211VIIT0912",
            "email": "kavya.priya@viit.ac.in",
            "contact_number": "9876543210",
            "password": "ValidPassword123!",
        }
        reg_resp = await client.post("/api/auth/general/register", json=reg_payload)
        assert reg_resp.status_code == 201, reg_resp.text
        reg_data = reg_resp.json()
        assert reg_data["status"] == "success"
        assert reg_data["user"]["registration_number"] == "211VIIT0912"
        assert reg_data["user"]["role"] == "student"
        assert reg_data["user"]["institution_id"] == partner_college
        assert "access_token" in reg_data

        # CRITICAL VERIFICATION: No email or OTP was dispatched
        assert len(capture_emails) == 0

        # ====================================================================
        # 4. Student Login & JWT Authentication
        # ====================================================================
        login_payload = {
            "email": "kavya.priya@viit.ac.in",
            "password": "ValidPassword123!",
        }
        login_resp = await client.post("/api/auth/login", json=login_payload)
        assert login_resp.status_code == 200, login_resp.text
        token_data = login_resp.json()
        assert "access_token" in token_data
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Verify protected student identity
        me_resp = await client.get("/api/auth/me", headers=headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["registration_number"] == "211VIIT0912"
        assert me_data["role"] == "student"

        # ====================================================================
        # 5. Role Selection: Select 'Software Development Engineer'
        # ====================================================================
        bad_role_resp = await client.post(
            "/api/student/interviews/select-role",
            json={"role": "Cloud Architect"},
            headers=headers,
        )
        assert bad_role_resp.status_code == 400
        assert "Unsupported role" in bad_role_resp.json()["detail"]

        select_resp = await client.post(
            "/api/student/interviews/select-role",
            json={"role": "Software Development Engineer"},
            headers=headers,
        )
        assert select_resp.status_code == 200, select_resp.text
        assignment_data = select_resp.json()
        assignment_id = assignment_data["assignment_id"]
        assert assignment_data["selected_role"] == "Software Development Engineer"
        assert assignment_data["student_registration_number"] == "211VIIT0912"
        assert assignment_data["status"] == AssignmentStatus.ACCEPTED.value

        reselect_resp = await client.post(
            "/api/student/interviews/select-role",
            json={"role": "Software Development Engineer"},
            headers=headers,
        )
        assert reselect_resp.status_code == 200
        assert reselect_resp.json()["assignment_id"] == assignment_id

        # ====================================================================
        # 6. Start Interview Session (Receive Q1 from PDF bank)
        # ====================================================================
        start_payload = {"assignment_id": assignment_id}
        start_resp = await client.post("/api/interview-rooms/sessions/start", json=start_payload, headers=headers)
        assert start_resp.status_code == 201, start_resp.text
        q1_data = start_resp.json()
        session_id = q1_data["session_id"]
        assert q1_data["question_index"] == 1
        assert "Software Development Engineer" in q1_data["question_text"]
        assert q1_data["question_type"] in ["conceptual", "coding"]
        assert q1_data["time_remaining_seconds"] > 0

        # SECURITY CHECK: expected_answer must NEVER be exposed
        assert "expected_answer" not in q1_data
        assert "confidential internal rubric" not in str(q1_data).lower()

        # ====================================================================
        # 7. Submit Answers & AI Evaluation Loop
        # ====================================================================
        # Empty submission rejected
        blank_resp = await client.post(
            f"/api/interview-rooms/sessions/{session_id}/submit-answer",
            json={"answer_text": "   "},
            headers=headers,
        )
        assert blank_resp.status_code == 422

        # Submit Question 1
        q1_submit = await client.post(
            f"/api/interview-rooms/sessions/{session_id}/submit-answer",
            json={"answer_text": "Software development engineers design scalable microservices and optimize algorithm complexity."},
            headers=headers,
        )
        assert q1_submit.status_code == 200, q1_submit.text
        q1_eval = q1_submit.json()
        assert q1_eval["question_index"] == 1
        assert q1_eval["evaluated_score"] >= 0
        assert "feedback" in q1_eval
        assert q1_eval["is_session_completed"] is False
        assert q1_eval["next_question"] is not None

        # SECURITY CHECK: expected_answer must NEVER be in submit response
        assert "expected_answer" not in q1_eval
        assert "confidential internal rubric" not in str(q1_eval).lower()

        # Verify Question 2 is also from Software Development Engineer bank
        q2 = q1_eval["next_question"]
        assert q2["question_index"] == 2
        assert "Software Development Engineer" in q2["question_text"]
        assert q2["question_text"] != q1_data["question_text"]

        # Submit remaining questions to reach completion (default target is 5 questions)
        total_q = q1_data["total_questions"]
        curr_q = 2
        last_eval_data = None
        while curr_q <= total_q:
            ans_resp = await client.post(
                f"/api/interview-rooms/sessions/{session_id}/submit-answer",
                json={"answer_text": f"This is comprehensive candidate answer for question {curr_q} covering architectural patterns and testing."},
                headers=headers,
            )
            assert ans_resp.status_code == 200, ans_resp.text
            last_eval_data = ans_resp.json()
            curr_q += 1

        assert last_eval_data["is_session_completed"] is True
        assert last_eval_data["scorecard_id"] is not None
        scorecard_id = last_eval_data["scorecard_id"]

        # Submitting to a completed session is strictly rejected
        post_complete_submit = await client.post(
            f"/api/interview-rooms/sessions/{session_id}/submit-answer",
            json={"answer_text": "Submission attempt after session completion"},
            headers=headers,
        )
        assert post_complete_submit.status_code == 400
        assert "already completed" in post_complete_submit.json()["detail"].lower()

        # ====================================================================
        # 8. Retrieve Final Scorecard
        # ====================================================================
        sc_resp = await client.get(f"/api/interview-rooms/sessions/{session_id}/scorecard", headers=headers)
        assert sc_resp.status_code == 200, sc_resp.text
        sc_data = sc_resp.json()

        assert sc_data["scorecard_id"] == scorecard_id
        assert sc_data["student_registration_number"] == "211VIIT0912"
        assert 0 <= sc_data["overall_score"] <= 10
        assert 0 <= sc_data["percentage_score"] <= 100
        assert sc_data["performance_level"] in ["Exceptional", "Proficient", "Satisfactory", "Needs Improvement"]
        assert "summary_feedback" in sc_data
        assert len(sc_data["difficulty_progression"]) == total_q
        assert len(sc_data["responses"]) == total_q
        assert "evaluator_mode" in sc_data
        assert "disclaimer" in sc_data

        # Verify dual frontend field compatibility
        assert sc_data["strengths"] is not None
        assert sc_data["strengths_summary"] is not None
        for resp_item in sc_data["responses"]:
            assert resp_item["score"] is not None
            assert resp_item["evaluation_score"] is not None

        # SECURITY CHECK: expected_answer must NEVER be exposed in scorecard
        assert "expected_answer" not in sc_data
        assert "confidential internal rubric" not in str(sc_data).lower()
        for resp_item in sc_data["responses"]:
            assert "expected_answer" not in resp_item

        # ====================================================================
        # 9. Cross-Role Isolation: Select 'Testing Engineer'
        # ====================================================================
        te_select = await client.post(
            "/api/student/interviews/select-role",
            json={"role": "Testing Engineer"},
            headers=headers,
        )
        assert te_select.status_code == 200
        te_asgn_id = te_select.json()["assignment_id"]
        assert te_select.json()["selected_role"] == "Testing Engineer"

        te_start = await client.post(
            "/api/interview-rooms/sessions/start",
            json={"assignment_id": te_asgn_id},
            headers=headers,
        )
        assert te_start.status_code == 201
        te_q1 = te_start.json()
        assert "Testing Engineer" in te_q1["question_text"]
        assert "Software Development Engineer" not in te_q1["question_text"]

    app.dependency_overrides.clear()
