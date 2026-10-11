import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import settings
from app.core.database import get_database
from app.models.user import UserRole, AccountStatus
from app.services.email_service import EmailService


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
        import pymongo.errors
        doc_id = doc.get("_id", doc.get("id", str(uuid.uuid4())))
        for existing in self.docs.values():
            if existing.get("email") == doc.get("email"):
                raise pymongo.errors.DuplicateKeyError("Duplicate email")
            if (
                doc.get("registration_number")
                and existing.get("registration_number") == doc.get("registration_number")
                and existing.get("institution_id") == doc.get("institution_id")
            ):
                raise pymongo.errors.DuplicateKeyError("Duplicate institution + registration_number")
        self.docs[doc_id] = dict(doc)
        res = MagicMock()
        res.inserted_id = doc_id
        return res


class InMemoryMockDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = InMemoryCollection()
        return self.collections[name]


@pytest.fixture
def mock_db():
    db = InMemoryMockDatabase()
    app.dependency_overrides[get_database] = lambda: db
    yield db
    app.dependency_overrides.pop(get_database, None)


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


@pytest.mark.anyio
async def test_allowed_institutions_endpoint():
    """Verify GET /api/auth/institutions/allowed exposes configured partner institutions policy."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/institutions/allowed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["policy"] == "partner_institutions_only"
        assert len(data["institutions"]) > 0
        assert any("VIIT" in inst for inst in data["institutions"])


@pytest.mark.anyio
async def test_general_registration_unauthorized_institution_rejected(mock_db):
    """Students from arbitrary unapproved universities are rejected with 403 Forbidden."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Test Candidate",
            "college_name": "Unauthorized Unknown Institute of Tech",
            "college_reg_no": "2024TEST001",
            "email": "candidate@unknown.edu",
            "contact_number": "9876543210",
            "password": "SecurePassword123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 403
        assert "not authorized under the platform's partner access policy" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_vfstr_rejected(mock_db):
    """VFSTR students attempting external registration are redirected with HTTP 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "VFSTR Student",
            "college_name": "VFSTR Deemed to be University",
            "college_reg_no": "211FA04001",
            "email": "student@vfstr.ac.in",
            "contact_number": "9876543210",
            "password": "SecurePassword123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 400
        assert "VFSTR students must use the dedicated VFSTR Student Verification Portal" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_password_complexity_rejected(mock_db):
    """Weak passwords (missing letters or digits or < 8 chars) are rejected with 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
        payload = {
            "full_name": "Test Student",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT001",
            "email": "student@viit.ac.in",
            "contact_number": "9876543210",
            "password": "onlyletters"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 400
        assert "Password must be at least 8 characters" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_invalid_contact_rejected(mock_db):
    """Invalid contact number format (non-digits) is rejected with 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
        payload = {
            "full_name": "Test Student",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT001",
            "email": "student@viit.ac.in",
            "contact_number": "12345abcdef",  # Invalid characters
            "password": "ValidPassword123"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 400
        assert "valid personal contact number" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_duplicate_email_conflict(mock_db):
    """Attempting to register with an email already in users collection returns 409 Conflict."""
    users_col = mock_db["users"]
    await users_col.insert_one({
        "id": "existing-user-1",
        "email": "existing@viit.ac.in",
        "role": UserRole.STUDENT.value,
        "institution_id": settings.ALLOWED_EXTERNAL_INSTITUTIONS[0],
        "registration_number": "211VIIT001",
        "account_status": AccountStatus.ACTIVE.value,
        "is_verified": True
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Duplicate Student",
            "college_name": settings.ALLOWED_EXTERNAL_INSTITUTIONS[0],
            "college_reg_no": "211VIIT999",
            "email": "existing@viit.ac.in",
            "contact_number": "9876543210",
            "password": "ValidPassword123"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_duplicate_student_id_conflict(mock_db):
    """Attempting to register with a student ID already registered for the same college returns 409."""
    users_col = mock_db["users"]
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    await users_col.insert_one({
        "id": "existing-user-2",
        "email": "other@viit.ac.in",
        "role": UserRole.STUDENT.value,
        "institution_id": allowed_college,
        "registration_number": "211VIIT002",
        "account_status": AccountStatus.ACTIVE.value,
        "is_verified": True
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "New Student Same Roll",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT002",
            "email": "newstudent@viit.ac.in",
            "contact_number": "9876543210",
            "password": "ValidPassword123"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 409
        assert "registration ID is already registered" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_complete_lifecycle(mock_db, capture_emails):
    """Full lifecycle: initiate -> email dispatch -> wrong OTP rejection -> right OTP complete -> JWT -> login."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initiate
        init_payload = {
            "full_name": "Aashish Sharma",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT099",
            "email": "aashish@viit.ac.in",
            "contact_number": "9876543210",
            "password": "StrongSecretPass123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=init_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        # Check that OTP email was dispatched
        assert len(capture_emails) == 1
        otp_dispatched = capture_emails[0]["code"]
        assert len(otp_dispatched) == 6

        # 2. Resend Cooldown
        resend_resp = await client.post(
            "/api/auth/general/register/resend",
            json={"email": "aashish@viit.ac.in"}
        )
        assert resend_resp.status_code == 429
        assert "Please wait" in resend_resp.json()["detail"]

        # 3. Wrong OTP rejected
        wrong_resp = await client.post(
            "/api/auth/general/register/complete",
            json={"email": "aashish@viit.ac.in", "verification_code": "000000"}
        )
        assert wrong_resp.status_code == 400
        assert "Invalid or expired verification code" in wrong_resp.json()["detail"]

        # 4. Correct OTP completes registration
        complete_resp = await client.post(
            "/api/auth/general/register/complete",
            json={"email": "aashish@viit.ac.in", "verification_code": otp_dispatched}
        )
        assert complete_resp.status_code == 201
        data = complete_resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == "aashish@viit.ac.in"
        assert data["user"]["full_name"] == "Aashish Sharma"
        # Verify role is strictly STUDENT
        assert data["user"]["role"] == "student"
        assert data["user"]["institution_id"] == allowed_college
        assert data["user"]["registration_number"] == "211VIIT099"
        assert data["user"]["contact_number"] == "9876543210"

        # 5. Verify user can now log in using standard credentials
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "aashish@viit.ac.in", "password": "StrongSecretPass123!"}
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert "access_token" in login_data
        assert login_data["user"]["role"] == "student"
        assert login_data["user"]["institution_id"] == allowed_college


@pytest.mark.anyio
async def test_general_registration_max_attempts_exceeded(mock_db, capture_emails):
    """Submitting 3 incorrect OTPs invalidates the verification session."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initiate
        init_payload = {
            "full_name": "Attempt Limit Test",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT888",
            "email": "attempts@viit.ac.in",
            "contact_number": "9876543210",
            "password": "Password123!"
        }
        await client.post("/api/auth/general/register/initiate", json=init_payload)
        real_otp = capture_emails[0]["code"]

        # Attempt 1 failed
        r1 = await client.post("/api/auth/general/register/complete", json={"email": "attempts@viit.ac.in", "verification_code": "111111"})
        assert r1.status_code == 400

        # Attempt 2 failed
        r2 = await client.post("/api/auth/general/register/complete", json={"email": "attempts@viit.ac.in", "verification_code": "222222"})
        assert r2.status_code == 400

        # Attempt 3 failed
        r3 = await client.post("/api/auth/general/register/complete", json={"email": "attempts@viit.ac.in", "verification_code": "333333"})
        assert r3.status_code == 400

        # Attempt 4 should inform that attempts are exceeded even with real code
        r4 = await client.post("/api/auth/general/register/complete", json={"email": "attempts@viit.ac.in", "verification_code": real_otp})
        assert r4.status_code == 400
        assert "invalidated due to too many failed attempts" in r4.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_role_escalation_impossible(mock_db, capture_emails):
    """Privileged roles like 'platform_admin' cannot be supplied; role is always 'student'."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Hacker Candidate",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT777",
            "email": "hacker@viit.ac.in",
            "contact_number": "9876543210",
            "password": "Password123!",
            "role": "platform_admin"  # Malicious extra field
        }
        await client.post("/api/auth/general/register/initiate", json=payload)
        otp = capture_emails[0]["code"]

        comp_resp = await client.post(
            "/api/auth/general/register/complete",
            json={"email": "hacker@viit.ac.in", "verification_code": otp, "role": "platform_admin"}
        )
        assert comp_resp.status_code == 201
        assert comp_resp.json()["user"]["role"] == "student"


@pytest.mark.anyio
async def test_general_registration_otp_expiration(mock_db, capture_emails):
    """Expired OTP codes cannot be redeemed and return 400 Bad Request."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Expired Test Student",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT555",
            "email": "expired@viit.ac.in",
            "contact_number": "9876543210",
            "password": "Password123!"
        }
        await client.post("/api/auth/general/register/initiate", json=payload)
        otp = capture_emails[0]["code"]

        # Manually expire the record in the mock database
        verif_col = mock_db["registration_verifications"]
        for doc in verif_col.docs.values():
            if doc.get("email_normalized") == "expired@viit.ac.in":
                doc["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=5)

        comp_resp = await client.post(
            "/api/auth/general/register/complete",
            json={"email": "expired@viit.ac.in", "verification_code": otp}
        )
        assert comp_resp.status_code == 400
        assert "Invalid or expired verification code" in comp_resp.json()["detail"]


@pytest.mark.anyio
async def test_demo_otp_safeguards_in_production(mock_db, monkeypatch, capture_emails):
    """In production mode or when DEMO_MODE=False, demo_otp_hint must never be exposed."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    # Force production settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert not settings.is_demo_otp_allowed

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Prod Candidate",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT444",
            "email": "prod@viit.ac.in",
            "contact_number": "9876543210",
            "password": "Password123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "demo_otp_hint" not in data
        assert "demo_mode" not in data


@pytest.mark.anyio
async def test_faculty_and_admin_login_flows(mock_db):
    """Verify existing faculty and admin accounts log in via /api/auth/login and enforce RBAC."""
    users_col = mock_db["users"]
    now = datetime.now(timezone.utc)
    from app.core.security import hash_password

    # Seed faculty account
    await users_col.insert_one({
        "id": "faculty-user-1",
        "email": "faculty@vfstr.ac.in",
        "full_name": "VFSTR Faculty Member",
        "role": UserRole.FACULTY.value,
        "institution_id": "VFSTR",
        "hashed_password": hash_password("FacultyPass2026!"),
        "account_status": AccountStatus.ACTIVE.value,
        "is_verified": True,
        "created_at": now,
        "updated_at": now
    })

    # Seed university admin account
    await users_col.insert_one({
        "id": "admin-user-1",
        "email": "admin@vfstr.ac.in",
        "full_name": "VFSTR University Admin",
        "role": UserRole.UNIVERSITY_ADMIN.value,
        "institution_id": "VFSTR",
        "hashed_password": hash_password("AdminPass2026!"),
        "account_status": AccountStatus.ACTIVE.value,
        "is_verified": True,
        "created_at": now,
        "updated_at": now
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Faculty Login
        fac_resp = await client.post(
            "/api/auth/login",
            json={"email": "faculty@vfstr.ac.in", "password": "FacultyPass2026!"}
        )
        assert fac_resp.status_code == 200
        fac_token = fac_resp.json()["access_token"]
        assert fac_resp.json()["user"]["role"] == "faculty"

        # Faculty can access protected-test
        fac_me = await client.get("/api/auth/protected-test", headers={"Authorization": f"Bearer {fac_token}"})
        assert fac_me.status_code == 200

        # Faculty is rejected from admin-only
        fac_admin = await client.get("/api/auth/admin-only", headers={"Authorization": f"Bearer {fac_token}"})
        assert fac_admin.status_code == 403

        # 2. University Admin Login
        adm_resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@vfstr.ac.in", "password": "AdminPass2026!"}
        )
        assert adm_resp.status_code == 200
        adm_token = adm_resp.json()["access_token"]
        assert adm_resp.json()["user"]["role"] == "university_admin"

        # Admin can access admin-only
        adm_check = await client.get("/api/auth/admin-only", headers={"Authorization": f"Bearer {adm_token}"})
        assert adm_check.status_code == 200
        assert adm_check.json()["status"] == "authorized"


@pytest.mark.anyio
async def test_general_registration_blocks_vfstr_impersonation_email(mock_db):
    """An applicant using an approved partner college name but a VFSTR email is rejected with 400."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Impersonator",
            "college_name": allowed_college,
            "college_reg_no": "211FA04001",
            "email": "student@vfstr.ac.in",
            "contact_number": "9876543210",
            "password": "SecurePassword123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 400
        assert "VFSTR students must use the dedicated VFSTR Student Verification Portal" in resp.json()["detail"]


@pytest.mark.anyio
async def test_general_registration_blocks_vfstr_impersonation_reg_no(mock_db):
    """An applicant using an approved partner college name with a VFSTR registry roll number is rejected with 400."""
    elig_col = mock_db["eligibility_registry"]
    await elig_col.insert_one({
        "institution_id": "VFSTR",
        "registration_number": "211FA04999",
        "roster_email": "candidate@vfstr.ac.in",
        "student_name": "Official VFSTR Student",
        "is_claimed": False,
        "is_eligible_for_registration": True,
        "validation_status": "eligible"
    })

    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Impersonator Two",
            "college_name": allowed_college,
            "college_reg_no": "211FA04999",
            "email": "external.student@gmail.com",
            "contact_number": "9876543210",
            "password": "SecurePassword123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 400
        assert "belongs to VFSTR Deemed University" in resp.json()["detail"]


@pytest.mark.anyio
async def test_student_login_with_registration_number_and_profile_fields(mock_db):
    """Verifies that students can log in using either email or registration number, and profile attributes are returned."""
    from app.core.security import hash_password
    users_col = mock_db["users"]
    now = datetime.now(timezone.utc)
    await users_col.insert_one({
        "id": "student-user-profile-test",
        "email": "roster.student@gmail.com",
        "full_name": "Roster Student",
        "role": UserRole.STUDENT.value,
        "institution_id": "VFSTR",
        "registration_number": "211FA04555",
        "department": "CSE",
        "batch_cohort": "2024-2028",
        "section": "A",
        "contact_number": "9876543210",
        "college_name": "VFSTR",
        "hashed_password": hash_password("StudentPassword123!"),
        "account_status": AccountStatus.ACTIVE.value,
        "is_verified": True,
        "created_at": now,
        "updated_at": now
    })

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login with roll number directly
        roll_resp = await client.post(
            "/api/auth/login",
            json={"email": "211FA04555", "password": "StudentPassword123!"}
        )
        assert roll_resp.status_code == 200
        data = roll_resp.json()
        assert data["user"]["registration_number"] == "211FA04555"
        assert data["user"]["department"] == "CSE"
        assert data["user"]["contact_number"] == "9876543210"

        token = data["access_token"]
        # 2. Verify /me endpoint returns complete profile
        me_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["registration_number"] == "211FA04555"
        assert me_data["department"] == "CSE"
        assert me_data["section"] == "A"
        assert me_data["contact_number"] == "9876543210"
