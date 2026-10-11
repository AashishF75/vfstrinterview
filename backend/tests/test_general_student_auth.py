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
async def test_general_registration_direct_success_without_otp(mock_db, capture_emails):
    """
    1. General-student registration succeeds without OTP.
    2. General-student registration does not call the email-sending service.
    7. Password is hashed rather than stored in plaintext.
    8. Newly registered general student can log in immediately.
    10. General-student registration does not create an OTP/pending-verification requirement.
    """
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Aashish Sharma",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT099",
            "email": "aashish@viit.ac.in",
            "contact_number": "9876543210",
            "password": "StrongSecretPass123!"
        }
        # 1. Register directly without OTP
        resp = await client.post("/api/auth/general/register", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "success"
        assert "access_token" in data
        assert data["user"]["email"] == "aashish@viit.ac.in"
        assert data["user"]["role"] == "student"
        assert data["user"]["institution_id"] == allowed_college
        assert data["user"]["registration_number"] == "211VIIT099"
        # Truthfully unverified via OTP, yet active
        assert data["user"]["is_verified"] is False

        # 2. Confirm email-sending service was NOT called
        assert len(capture_emails) == 0

        # 3. Confirm no OTP verification record or pending requirement was created
        verif_col = mock_db["registration_verifications"]
        verif_doc = await verif_col.find_one({"email_normalized": "aashish@viit.ac.in"})
        assert verif_doc is None

        # 4. Confirm password is encrypted with bcrypt hash and not stored in plaintext
        users_col = mock_db["users"]
        user_record = await users_col.find_one({"email": "aashish@viit.ac.in"})
        assert user_record is not None
        assert "hashed_password" in user_record
        assert user_record["hashed_password"] != "StrongSecretPass123!"
        assert user_record["hashed_password"].startswith("$2b$") or user_record["hashed_password"].startswith("$2a$")

        # 5. Newly registered general student can log in immediately
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
async def test_general_registration_succeeds_when_smtp_unavailable(mock_db, monkeypatch):
    """
    3. Registration succeeds when SMTP is unavailable.
    Even if the email service raises a fatal connection failure, registration succeeds
    because email verification is completely bypassed for general students.
    """
    async def broken_smtp(*args, **kwargs):
        raise RuntimeError("SMTP connection failed: Host unreachable")

    monkeypatch.setattr(EmailService, "send_verification_otp", broken_smtp)

    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Resilient Candidate",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT321",
            "email": "resilient@viit.ac.in",
            "contact_number": "9876543210",
            "password": "StrongPass123!"
        }
        resp = await client.post("/api/auth/general/register", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["user"]["email"] == "resilient@viit.ac.in"


@pytest.mark.anyio
async def test_general_student_jwt_can_access_dashboard_and_enforces_rbac(mock_db):
    """
    9. A valid JWT can access the general-student dashboard / protected routes.
    11. General student cannot access admin routes (RBAC preserved).
    """
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register and log in
        reg_payload = {
            "full_name": "Dashboard Tester",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT654",
            "email": "dashboard@viit.ac.in",
            "contact_number": "9876543210",
            "password": "ValidPassword123!"
        }
        reg_resp = await client.post("/api/auth/general/register", json=reg_payload)
        assert reg_resp.status_code == 201

        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "dashboard@viit.ac.in", "password": "ValidPassword123!"}
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Student can access protected endpoint
        prot_resp = await client.get("/api/auth/protected-test", headers=headers)
        assert prot_resp.status_code == 200
        assert prot_resp.json()["email"] == "dashboard@viit.ac.in"
        assert prot_resp.json()["role"] == "student"

        # Also verify /api/auth/me
        me_resp = await client.get("/api/auth/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "dashboard@viit.ac.in"
        assert me_resp.json()["role"] == "student"

        # General student is strictly denied from admin routes
        admin_resp = await client.get("/api/auth/admin-only", headers=headers)
        assert admin_resp.status_code == 403


@pytest.mark.anyio
async def test_general_registration_role_escalation_impossible(mock_db):
    """Privileged roles like 'platform_admin' cannot be supplied; role is always strictly 'student'."""
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
        comp_resp = await client.post("/api/auth/general/register", json=payload)
        assert comp_resp.status_code == 201
        assert comp_resp.json()["user"]["role"] == "student"


@pytest.mark.anyio
async def test_general_registration_backward_compatible_endpoint(mock_db, capture_emails):
    """Verify backward-compatible POST /api/auth/general/register/initiate also registers without OTP."""
    allowed_college = settings.ALLOWED_EXTERNAL_INSTITUTIONS[0]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "full_name": "Compat Candidate",
            "college_name": allowed_college,
            "college_reg_no": "211VIIT111",
            "email": "compat@viit.ac.in",
            "contact_number": "9876543210",
            "password": "Password123!"
        }
        resp = await client.post("/api/auth/general/register/initiate", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert len(capture_emails) == 0


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
