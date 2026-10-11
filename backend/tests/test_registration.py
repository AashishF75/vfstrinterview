import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
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
