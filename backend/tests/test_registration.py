import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import ReturnDocument

from app.main import app
from app.core.database import get_database
from app.models.user import UserRole, AccountStatus
from app.models.eligibility import EmailSource, EligibilityStatus
from app.services.email_service import EmailService


class InMemoryCollection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query):
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    async def update_one(self, filter_q, update_q, upsert=False):
        matched_id = None
        for doc_id, doc in self.docs.items():
            match = True
            for k, v in filter_q.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
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
            doc_id = new_doc.get("_id", str(uuid.uuid4()))
            new_doc["_id"] = doc_id
            self.docs[doc_id] = new_doc

        res = MagicMock()
        res.matched_count = 1 if matched_id else 0
        return res

    async def find_one_and_update(self, filter_q, update_q, return_document=None):
        matched_id = None
        for doc_id, doc in self.docs.items():
            match = True
            for k, v in filter_q.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                matched_id = doc_id
                break

        if not matched_id:
            return None

        target = self.docs[matched_id]
        if "$set" in update_q:
            target.update(update_q["$set"])
        return dict(target)

    async def insert_one(self, doc):
        doc_id = doc.get("_id", doc.get("id", str(uuid.uuid4())))
        # Check unique constraint on email and registration_number
        for existing in self.docs.values():
            if existing.get("email") == doc.get("email"):
                import pymongo.errors
                raise pymongo.errors.DuplicateKeyError("Duplicate email")
            if doc.get("registration_number") and existing.get("registration_number") == doc.get("registration_number"):
                import pymongo.errors
                raise pymongo.errors.DuplicateKeyError("Duplicate registration_number")
        self.docs[doc_id] = dict(doc)
        res = MagicMock()
        res.inserted_id = doc_id
        return res

    async def count_documents(self, query):
        count = 0
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    async def delete_one(self, filter_q):
        matched_id = None
        for doc_id, doc in self.docs.items():
            match = True
            for k, v in filter_q.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                matched_id = doc_id
                break
        if matched_id:
            del self.docs[matched_id]
        res = MagicMock()
        res.deleted_count = 1 if matched_id else 0
        return res

    async def delete_many(self, filter_q):
        matched_ids = []
        for doc_id, doc in list(self.docs.items()):
            match = True
            for k, v in filter_q.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                matched_ids.append(doc_id)
        for d_id in matched_ids:
            del self.docs[d_id]
        res = MagicMock()
        res.deleted_count = len(matched_ids)
        return res


class InMemoryMockDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = InMemoryCollection()
        return self.collections[name]


@pytest.fixture
def mock_db():
    db = InMemoryMockDB()
    # Seed sample eligible student
    db["eligibility_registry"].docs["elig-1"] = {
        "_id": "elig-1",
        "institution_id": "VFSTR",
        "batch_cohort": "2024-2028",
        "department": "CSE",
        "registration_number": "241FA04001",
        "student_name": "TEST STUDENT ONE",
        "roster_email": "vu.241fa04001@gmail.com",
        "email_source": EmailSource.PROVIDED.value,
        "section": "1",
        "is_claimed": False,
        "claimed_user_id": None,
        "claimed_at": None,
        "validation_status": EligibilityStatus.ELIGIBLE.value,
        "is_eligible_for_registration": True,
    }
    # Seed generated pending verification record
    db["eligibility_registry"].docs["elig-gen"] = {
        "_id": "elig-gen",
        "institution_id": "VFSTR",
        "batch_cohort": "2024-2028",
        "department": "CSE",
        "registration_number": "241FA04037",
        "student_name": "TEST STUDENT GENERATED",
        "roster_email": "vu.241fa04037@gmail.com",
        "email_source": EmailSource.GENERATED_PENDING_VERIFICATION.value,
        "section": "1",
        "is_claimed": False,
        "claimed_user_id": None,
        "claimed_at": None,
        "validation_status": EligibilityStatus.ELIGIBLE.value,
        "is_eligible_for_registration": True,
    }
    return db


@pytest.fixture
def async_client(mock_db):
    app.dependency_overrides[get_database] = lambda: mock_db
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    yield client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_initiate_registration_eligible_student(async_client):
    EmailService.clear_test_inbox()
    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241fa04001"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "verification code has been dispatched" in data["message"]

    inbox = EmailService.get_test_inbox()
    assert len(inbox) == 1
    assert inbox[0]["registration_number"] == "241FA04001"
    assert inbox[0]["to_email"] == "vu.241fa04001@gmail.com"
    assert len(inbox[0]["otp_code"]) == 6


@pytest.mark.anyio
async def test_initiate_registration_anti_enumeration(async_client):
    EmailService.clear_test_inbox()
    # Non-existent roll number
    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA99999"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    # Zero emails sent for unknown roll
    assert len(EmailService.get_test_inbox()) == 0


@pytest.mark.anyio
async def test_initiate_blocked_for_generated_pending_verification(async_client):
    EmailService.clear_test_inbox()
    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04037"}
    )
    assert resp.status_code == 403
    data = resp.json()
    assert "CSE Department Administration" in data["detail"]
    assert len(EmailService.get_test_inbox()) == 0


@pytest.mark.anyio
async def test_resend_cooldown_throttling(async_client):
    EmailService.clear_test_inbox()
    # First request
    r1 = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    assert r1.status_code == 200

    # Immediate resend should trigger 429 cooldown
    r2 = await async_client.post(
        "/api/auth/register/resend",
        json={"registration_number": "241FA04001"}
    )
    assert r2.status_code == 429
    assert "Please wait" in r2.json()["detail"]


@pytest.mark.anyio
async def test_complete_registration_success(async_client, mock_db):
    EmailService.clear_test_inbox()
    # 1. Initiate
    await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    otp = EmailService.get_test_inbox()[0]["otp_code"]

    # 2. Complete
    resp = await async_client.post(
        "/api/auth/register/complete",
        json={
            "registration_number": "241FA04001",
            "verification_code": otp,
            "password": "StrongPassword123!"
        }
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    user = data["user"]
    assert user["role"] == "student"
    assert user["registration_number"] == "241FA04001"
    assert user["email"] == "vu.241fa04001@gmail.com"
    assert user["department"] == "CSE"
    assert user["section"] == "1"

    # Verify registry is marked claimed
    elig = await mock_db["eligibility_registry"].find_one({"registration_number": "241FA04001"})
    assert elig["is_claimed"] is True
    assert elig["claimed_user_id"] == user["id"]


@pytest.mark.anyio
async def test_complete_registration_invalid_otp_and_lockout(async_client):
    EmailService.clear_test_inbox()
    await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )

    # 3 failed attempts
    for _ in range(3):
        r = await async_client.post(
            "/api/auth/register/complete",
            json={
                "registration_number": "241FA04001",
                "verification_code": "000000",
                "password": "StrongPassword123!"
            }
        )
        assert r.status_code == 400

    # 4th attempt should state locked out due to attempts
    r4 = await async_client.post(
        "/api/auth/register/complete",
        json={
            "registration_number": "241FA04001",
            "verification_code": "000000",
            "password": "StrongPassword123!"
        }
    )
    assert r4.status_code == 400
    assert "too many failed attempts" in r4.json()["detail"]


@pytest.mark.anyio
async def test_double_claim_prevention(async_client, mock_db):
    EmailService.clear_test_inbox()
    await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    otp = EmailService.get_test_inbox()[0]["otp_code"]

    # First claim succeeds
    r1 = await async_client.post(
        "/api/auth/register/complete",
        json={
            "registration_number": "241FA04001",
            "verification_code": otp,
            "password": "StrongPassword123!"
        }
    )
    assert r1.status_code == 201

    # Second claim attempt with same credentials fails
    r2 = await async_client.post(
        "/api/auth/register/complete",
        json={
            "registration_number": "241FA04001",
            "verification_code": otp,
            "password": "AnotherPassword123!"
        }
    )
    assert r2.status_code in (400, 409)


@pytest.mark.anyio
async def test_demo_otp_hint_fail_closed_flags(async_client, mock_db):
    from app.core.config import settings

    # 1. By default (DEMO_MODE=False), demo_otp_hint must NEVER be returned
    mock_db["registration_verifications"].docs.clear()
    settings.DEMO_MODE = False
    settings.ENVIRONMENT = "development"
    settings.EMAIL_DISPATCH_ENABLED = False
    assert not settings.is_demo_otp_allowed

    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    assert resp.status_code == 200
    assert "demo_otp_hint" not in resp.json()

    # 2. In production, even if DEMO_MODE=True, must fail closed
    mock_db["registration_verifications"].docs.clear()
    settings.DEMO_MODE = True
    settings.ENVIRONMENT = "production"
    settings.EMAIL_DISPATCH_ENABLED = False
    assert not settings.is_demo_otp_allowed

    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    assert resp.status_code == 200
    assert "demo_otp_hint" not in resp.json()

    # 3. If real emails enabled, even if DEMO_MODE=True, must fail closed
    mock_db["registration_verifications"].docs.clear()
    settings.DEMO_MODE = True
    settings.ENVIRONMENT = "development"
    settings.EMAIL_DISPATCH_ENABLED = True
    assert not settings.is_demo_otp_allowed

    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    assert resp.status_code == 200
    assert "demo_otp_hint" not in resp.json()

    # 4. Only when DEMO_MODE=True AND dev AND email dispatch disabled -> allowed
    mock_db["registration_verifications"].docs.clear()
    settings.DEMO_MODE = True
    settings.ENVIRONMENT = "development"
    settings.EMAIL_DISPATCH_ENABLED = False
    assert settings.is_demo_otp_allowed

    resp = await async_client.post(
        "/api/auth/register/initiate",
        json={"registration_number": "241FA04001"}
    )
    assert resp.status_code == 200
    assert "demo_otp_hint" in resp.json()
    assert len(resp.json()["demo_otp_hint"]) == 6

    # Restore default
    mock_db["registration_verifications"].docs.clear()
    settings.DEMO_MODE = False
    settings.EMAIL_DISPATCH_ENABLED = False


@pytest.mark.anyio
async def test_generated_record_cannot_be_claimed_directly(async_client, mock_db):
    # Direct complete call on a generated pending record (e.g. 241FA04020)
    # must fail with 400 (no valid OTP) or 409
    resp = await async_client.post(
        "/api/auth/register/complete",
        json={
            "registration_number": "241FA04020",
            "verification_code": "123456",
            "password": "Password123!"
        }
    )
    assert resp.status_code in (400, 409)


@pytest.mark.anyio
async def test_registration_initiate_email_failure_returns_503(async_client, mock_db):
    """
    Verifies that when email dispatch fails (e.g. SMTP connection timeout/error),
    the API returns HTTP 503 Service Unavailable instead of hanging or returning a misleading 200.
    Also ensures no dirty unconsumed verification record is committed.
    """
    with patch("app.services.email_service.EmailService.send_verification_otp", return_value=False):
        resp = await async_client.post(
            "/api/auth/register/initiate",
            json={"registration_number": "241FA04001"}
        )
        assert resp.status_code == 503
        data = resp.json()
        assert "Unable to deliver verification code" in data["detail"]

        # Ensure no active verification was saved so the student is not penalized with cooldown
        active_verif = await mock_db["registration_verifications"].find_one({
            "registration_number_normalized": "241FA04001",
            "is_consumed": False
        })
        assert active_verif is None


@pytest.mark.anyio
async def test_registration_resend_email_failure_returns_503(async_client, mock_db):
    """
    Verifies that when resend email dispatch fails, the API returns HTTP 503
    and preserves the previous verification state without resetting cooldown.
    """
    # Seed an active verification
    initial_resend_at = datetime.now(timezone.utc) - timedelta(seconds=70)
    mock_db["registration_verifications"].docs["verif-resend"] = {
        "_id": "verif-resend",
        "registration_number_normalized": "241FA04001",
        "roster_email_normalized": "vu.241fa04001@gmail.com",
        "code_hash": "original_hash",
        "salt": "original_salt",
        "attempt_count": 0,
        "is_consumed": False,
        "created_at": initial_resend_at,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "last_resend_at": initial_resend_at,
    }

    with patch("app.services.email_service.EmailService.send_verification_otp", return_value=False):
        resp = await async_client.post(
            "/api/auth/register/resend",
            json={"registration_number": "241FA04001"}
        )
        assert resp.status_code == 503
        data = resp.json()
        assert "Unable to deliver verification code" in data["detail"]

        # Ensure original code_hash was not overwritten on failure
        saved = mock_db["registration_verifications"].docs["verif-resend"]
        assert saved["code_hash"] == "original_hash"


def test_smtp_alias_resolution_and_password_sanitization():
    """
    Verifies that the config model validator resolves SMTP aliases, strips whitespace
    from Gmail app passwords, and auto-enables SSL for port 465.
    """
    from app.core.config import Settings

    raw_env = {
        "SMTP_SERVER": "smtp.gmail.com",
        "SMTP_PORT": "465",
        "SMTP_USER": "testuser@gmail.com",
        "GMAIL_APP_PASSWORD": " abcd efgh ijkl mnop ",
        "JWT_SECRET_KEY": "test-secret-at-least-32-characters-long-12345"
    }
    s = Settings(**raw_env)
    assert s.SMTP_HOST == "smtp.gmail.com"
    assert s.SMTP_PORT == 465
    assert s.SMTP_USERNAME == "testuser@gmail.com"
    assert s.SMTP_PASSWORD == "abcdefghijklmnop"
    assert s.SMTP_USE_SSL is True
    assert s.SMTP_TIMEOUT_SECONDS <= 5.0


@pytest.mark.anyio
async def test_vfstr_direct_register_eligible_new_student(async_client, mock_db):
    """
    Priority 1 & 2: Direct VFSTR registration without OTP.
    Validates against official eligibility_registry, registers student, returns JWT token,
    and flags eligibility registry record as claimed.
    """
    payload = {
        "registration_number": "241fa04001",
        "contact_number": "9876543210"
    }
    resp = await async_client.post("/api/auth/vfstr/register", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "student"
    assert data["user"]["registration_number"] == "241FA04001"
    assert data["user"]["contact_number"] == "9876543210"
    assert data["user"]["institution_id"] == "VFSTR"

    # Verify eligibility record was updated to claimed
    elig_rec = await mock_db["eligibility_registry"].find_one({"registration_number": "241FA04001"})
    assert elig_rec["is_claimed"] is True


@pytest.mark.anyio
async def test_vfstr_direct_register_duplicate_reentry_prevents_duplicate_account(async_client, mock_db):
    """
    Priority 1 & 2: Student re-enters their registration number and matching contact number.
    Returns existing session without creating a duplicate user account.
    """
    payload = {
        "registration_number": "241FA04001",
        "contact_number": "9876543210"
    }
    # First entry
    resp1 = await async_client.post("/api/auth/vfstr/register", json=payload)
    assert resp1.status_code == 200
    user_count_before = await mock_db["users"].count_documents({})

    # Second entry (re-entry)
    resp2 = await async_client.post("/api/auth/vfstr/register", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert "access_token" in data2
    assert data2["user"]["registration_number"] == "241FA04001"

    # Ensure no duplicate user was created
    user_count_after = await mock_db["users"].count_documents({})
    assert user_count_after == user_count_before


@pytest.mark.anyio
async def test_vfstr_direct_register_contact_number_mismatch_rejected(async_client):
    """
    Priority 2: Re-entry with mismatched contact number must be rejected to prevent unauthorized takeover.
    """
    # First entry with 9876543210
    await async_client.post("/api/auth/vfstr/register", json={
        "registration_number": "241FA04001",
        "contact_number": "9876543210"
    })

    # Second attempt with conflicting contact number
    resp_conflict = await async_client.post("/api/auth/vfstr/register", json={
        "registration_number": "241FA04001",
        "contact_number": "9123456789"
    })
    assert resp_conflict.status_code == 403
    assert "does not match the registered contact number" in resp_conflict.json()["detail"]


@pytest.mark.anyio
async def test_vfstr_direct_register_invalid_registration_number(async_client):
    """
    Priority 1: Invalid registration number returns 404 with clear message.
    """
    resp = await async_client.post("/api/auth/vfstr/register", json={
        "registration_number": "999XX00000",
        "contact_number": "9876543210"
    })
    assert resp.status_code == 404
    assert "not found in the official VFSTR student eligibility registry" in resp.json()["detail"]


@pytest.mark.anyio
async def test_vfstr_direct_register_pending_verification_blocked(async_client):
    """
    Priority 1 & 2: Students with unverified email source remain restricted.
    """
    resp = await async_client.post("/api/auth/vfstr/register", json={
        "registration_number": "241FA04037",
        "contact_number": "9876543210"
    })
    assert resp.status_code == 403
    assert "requires official university email verification" in resp.json()["detail"]


@pytest.mark.anyio
async def test_vfstr_direct_register_invalid_contact_format(async_client):
    """
    Priority 1: Contact numbers with fewer than 10 digits are rejected with 422 Unprocessable Entity.
    """
    resp = await async_client.post("/api/auth/vfstr/register", json={
        "registration_number": "241FA04001",
        "contact_number": "12345"
    })
    assert resp.status_code == 422



def test_question_parser_pdf_text_extraction():
    """
    Priority 3: Test parsing of question text into structured questions with difficulty and topic.
    """
    from app.services.question_file_parser import parse_pdf_text_to_questions

    sample_text = """
    Q1. Explain the three-way handshake in TCP/IP protocol. [Medium]
    Topic: Networking

    Q2. What is the fundamental difference between a Hub, Switch, and Router? [Easy]
    Topic: Network Devices

    3. Describe the mechanism of BGP path vector routing and loop prevention. [Hard]
    Topic: Routing Protocols
    """

    questions = parse_pdf_text_to_questions(sample_text)
    assert len(questions) == 3
    assert questions[0]["difficulty"] == "medium"
    assert questions[0]["topic"] == "Networking"
    assert "handshake" in questions[0]["question_text"].lower()

    assert questions[1]["difficulty"] == "easy"
    assert questions[1]["topic"] == "Network Devices"

    assert questions[2]["difficulty"] == "hard"
    assert questions[2]["topic"] == "Routing Protocols"


def test_question_parser_zip_archive():
    """
    Priority 3: Test parsing questions from a ZIP archive containing JSON and TXT.
    """
    import io
    import zipfile
    import json
    from app.services.question_file_parser import extract_questions_from_zip

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        json_content = json.dumps([
            {"question": "How does DNS resolution work across recursive and authoritative servers?", "difficulty": "medium", "topic": "DNS"},
            {"question": "Explain subnet masking and calculate the usable IPs for /26 CIDR block.", "difficulty": "easy", "topic": "IP Addressing"}
        ])
        zf.writestr("questions.json", json_content)

        txt_content = "Q1. What is ARP poisoning and how can it be mitigated using Dynamic ARP Inspection? [Hard]\nTopic: Security"
        zf.writestr("more_questions.txt", txt_content)

    zip_bytes = zip_buffer.getvalue()
    parsed = extract_questions_from_zip(zip_bytes)
    assert len(parsed) == 3
    topics = [q["topic"] for q in parsed]
    assert "DNS" in topics
    assert "IP Addressing" in topics
    assert "Security" in topics
