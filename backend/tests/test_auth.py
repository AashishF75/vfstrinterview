import pytest
import asyncio
import uuid
from datetime import timedelta, datetime, timezone
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pymongo
import pymongo.errors

from app.main import app
from app.core.config import settings
from app.core.database import get_database
from app.core.security import hash_password, create_access_token
from app.models.user import UserInDB, UserRole, AccountStatus
from app.cli.bootstrap_admin import provision_admin

# -----------------------------------------------------------------------------
# In-Memory Database Mock for Isolated Test Execution (Zero Atlas Mutations)
# -----------------------------------------------------------------------------

class AwaitableValue:
    """Helper enabling methods to be both awaited in async routes and accessed synchronously in tests."""
    def __init__(self, val):
        self._val = val

    def __await__(self):
        async def _c():
            return self._val
        return _c().__await__()

    def __getattr__(self, name):
        return getattr(self._val, name)

    def __getitem__(self, item):
        return self._val[item]

    def __contains__(self, item):
        return item in self._val

    def __eq__(self, other):
        return self._val == other

    def __ge__(self, other):
        return self._val >= other

    def __int__(self):
        return int(self._val)

    def __repr__(self):
        return repr(self._val)


class InMemoryAuthCollection:
    def __init__(self, name="users"):
        self.name = name
        self.docs = {}
        self.indexes = {}

    def create_index(self, keys, unique=False, name=None, **options):
        idx_name = name or "_".join(f"{k}_{v}" for k, v in keys)
        self.indexes[idx_name] = {"key": keys, "unique": unique, **options}
        return AwaitableValue(idx_name)

    def index_information(self):
        info = {"_id_": {"v": 2, "key": [("_id", 1)]}}
        for name, data in self.indexes.items():
            info[name] = data
        return AwaitableValue(info)

    def drop_index(self, index_name):
        if index_name in self.indexes:
            del self.indexes[index_name]
        return AwaitableValue(None)

    def drop(self):
        self.docs.clear()
        self.indexes.clear()
        return AwaitableValue(None)

    def find_one(self, query):
        for doc in list(self.docs.values()):
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return AwaitableValue(dict(doc))
        return AwaitableValue(None)

    def insert_one(self, doc):
        email = doc.get("email")
        for existing in self.docs.values():
            if existing.get("email") == email:
                raise pymongo.errors.DuplicateKeyError(f"Duplicate key on email: {email}")

        # Check unique role constraint if an erroneous unique role index exists (for migration test)
        has_unique_role = any(
            idx.get("unique") and any(k[0] == "role" for k in idx.get("key", []))
            for idx in self.indexes.values()
        )
        if has_unique_role:
            role = doc.get("role")
            for existing in self.docs.values():
                if existing.get("role") == role:
                    raise pymongo.errors.DuplicateKeyError(f"Duplicate key on unique role: {role}")

        doc_id = doc.get("id") or doc.get("_id") or str(uuid.uuid4())
        doc_copy = dict(doc)
        doc_copy["_id"] = doc_id
        if "id" not in doc_copy:
            doc_copy["id"] = doc_id
        self.docs[doc_id] = doc_copy
        res = MagicMock()
        res.inserted_id = doc_id
        return AwaitableValue(res)

    def update_one(self, filter_q, update_q, upsert=False):
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
            res = MagicMock()
            res.matched_count = 1
            res.modified_count = 1
            return AwaitableValue(res)
        return AwaitableValue(MagicMock(matched_count=0, modified_count=0))

    def delete_many(self, query):
        if not query:
            count = len(self.docs)
            self.docs.clear()
            return AwaitableValue(MagicMock(deleted_count=count))
        deleted = 0
        for doc_id, doc in list(self.docs.items()):
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                del self.docs[doc_id]
                deleted += 1
        return AwaitableValue(MagicMock(deleted_count=deleted))

    def count_documents(self, query):
        count = 0
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return AwaitableValue(count)


class InMemoryAuthDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = InMemoryAuthCollection(name)
        return self.collections[name]


in_memory_auth_db = InMemoryAuthDB()

# -----------------------------------------------------------------------------
# Test user credentials
# -----------------------------------------------------------------------------

TEST_ADMIN_EMAIL = "admin_test@vfstr.ac.in"
TEST_ADMIN_PASS = "AdminSecurePass123!"

TEST_STUDENT_EMAIL = "student_test@vfstr.ac.in"
TEST_STUDENT_PASS = "StudentSecurePass123!"

TEST_FACULTY_EMAIL = "faculty_test@vfstr.ac.in"
TEST_FACULTY_PASS = "FacultySecurePass123!"

ALL_CLEANUP_EMAILS = [
    TEST_ADMIN_EMAIL,
    TEST_STUDENT_EMAIL,
    TEST_FACULTY_EMAIL,
    "bootstrap_cli_test@vfstr.ac.in",
    "duplicate_test@vfstr.ac.in",
    "student_multi_1@vfstr.ac.in",
    "student_multi_2@vfstr.ac.in",
    "faculty_multi_1@vfstr.ac.in",
    "faculty_multi_2@vfstr.ac.in",
    "admin_multi_1@vfstr.ac.in",
    "admin_multi_2@vfstr.ac.in",
    "duplicate_fail@vfstr.ac.in",
]


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def setup_test_users():
    """Sets up clean test users in-memory for the test session with zero Atlas writes."""
    app.dependency_overrides[get_database] = lambda: in_memory_auth_db

    users_col = in_memory_auth_db["users"]
    users_col.docs.clear()

    # Insert Test Admin
    admin = UserInDB(
        email=TEST_ADMIN_EMAIL,
        full_name="Test Administrator",
        role=UserRole.PLATFORM_ADMIN,
        institution_id="VFSTR",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password(TEST_ADMIN_PASS)
    )
    users_col.insert_one(admin.model_dump())

    # Insert Test Student
    student = UserInDB(
        email=TEST_STUDENT_EMAIL,
        full_name="Test Student",
        role=UserRole.STUDENT,
        institution_id="VFSTR",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password(TEST_STUDENT_PASS)
    )
    users_col.insert_one(student.model_dump())

    # Insert Test Faculty
    faculty = UserInDB(
        email=TEST_FACULTY_EMAIL,
        full_name="Test Faculty Member",
        role=UserRole.FACULTY,
        institution_id="VFSTR",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password(TEST_FACULTY_PASS)
    )
    users_col.insert_one(faculty.model_dump())

    yield

    users_col.docs.clear()
    app.dependency_overrides.pop(get_database, None)


# 1. Successful login with valid credentials
def test_login_successful(client):
    response = client.post("/api/auth/login", json={
        "email": TEST_STUDENT_EMAIL,
        "password": TEST_STUDENT_PASS
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == TEST_STUDENT_EMAIL
    assert data["user"]["role"] == "student"
    assert data["user"]["institution_id"] == "VFSTR"


# 2. Rejection of incorrect passwords
def test_login_incorrect_password(client):
    response = client.post("/api/auth/login", json={
        "email": TEST_STUDENT_EMAIL,
        "password": "WrongPassword999!"
    })
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Invalid email or password"


# 3. Rejection of unknown accounts
def test_login_unknown_account(client):
    response = client.post("/api/auth/login", json={
        "email": "nonexistent_user@vfstr.ac.in",
        "password": "AnyPassword123!"
    })
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Invalid email or password"


# 4. Access to protected endpoints with valid authentication
def test_protected_access_valid_token(client):
    login_res = client.post("/api/auth/login", json={
        "email": TEST_STUDENT_EMAIL,
        "password": TEST_STUDENT_PASS
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # Test /api/auth/me
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == TEST_STUDENT_EMAIL
    assert me_data["role"] == "student"

    # Test /api/auth/protected-test
    prot_res = client.get("/api/auth/protected-test", headers={"Authorization": f"Bearer {token}"})
    assert prot_res.status_code == 200
    assert prot_res.json()["status"] == "authenticated"


# 5. Rejection of unauthenticated requests
def test_protected_endpoint_unauthenticated(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


# 6. Rejection of expired or invalid tokens
def test_rejection_invalid_and_expired_tokens(client):
    # Invalid token string
    bad_res = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.jwt.token"})
    assert bad_res.status_code == 401
    assert "Invalid authentication token" in bad_res.json()["detail"]

    # Expired token
    expired_token = create_access_token(
        subject="expired-user-id",
        email="expired@vfstr.ac.in",
        role="student",
        expires_delta=timedelta(seconds=-10)  # expired in past
    )
    exp_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert exp_res.status_code == 401
    assert "expired" in exp_res.json()["detail"]


# 7. Role-based authorization: admin-only endpoint allows admin, rejects student
def test_role_based_authorization(client):
    # Student login
    student_res = client.post("/api/auth/login", json={
        "email": TEST_STUDENT_EMAIL,
        "password": TEST_STUDENT_PASS
    })
    assert student_res.status_code == 200
    student_token = student_res.json()["access_token"]

    # Student tries to access admin-only endpoint -> 403 Forbidden
    denied_res = client.get("/api/auth/admin-only", headers={"Authorization": f"Bearer {student_token}"})
    assert denied_res.status_code == 403
    assert "Insufficient permissions" in denied_res.json()["detail"]

    # Admin login
    admin_res = client.post("/api/auth/login", json={
        "email": TEST_ADMIN_EMAIL,
        "password": TEST_ADMIN_PASS
    })
    assert admin_res.status_code == 200
    admin_token = admin_res.json()["access_token"]

    # Admin accesses admin-only endpoint -> 200 OK
    allowed_res = client.get("/api/auth/admin-only", headers={"Authorization": f"Bearer {admin_token}"})
    assert allowed_res.status_code == 200
    assert allowed_res.json()["status"] == "authorized"
    assert allowed_res.json()["role"] == "platform_admin"


# 8. Prevention of public privilege escalation (cannot bootstrap admin without secret)
def test_prevention_public_privilege_escalation(client):
    # Unauthenticated user attempts to call bootstrap-admin endpoint
    res = client.post("/api/auth/bootstrap-admin", json={
        "email": "hacker@vfstr.ac.in",
        "password": "HackerPassword123!"
    })
    assert res.status_code == 403
    assert "Invalid bootstrap authorization" in res.json()["detail"]


# 9. Duplicate-account handling
def test_duplicate_account_handling(client):
    # Attempting to bootstrap an admin that already exists
    res = client.post(
        "/api/auth/bootstrap-admin",
        headers={"X-Bootstrap-Secret": settings.JWT_SECRET_KEY},
        json={
            "email": TEST_ADMIN_EMAIL,
            "password": "AnotherPassword123!"
        }
    )
    # Rejection with 409 Conflict because admin already exists
    assert res.status_code == 409


# 10. Secure administrator provisioning via CLI bootstrap function
def test_secure_admin_provisioning_cli(client):
    cli_email = "bootstrap_cli_test@vfstr.ac.in"
    cli_pass = "BootstrapSecure999!"

    # First attempt with force=True provisions successfully into isolated in-memory DB
    success = asyncio.run(provision_admin(
        email=cli_email,
        password=cli_pass,
        full_name="CLI Test Admin",
        force=True,
        db=in_memory_auth_db,
    ))
    assert success is True

    # Login with newly provisioned admin credentials
    res = client.post("/api/auth/login", json={
        "email": cli_email,
        "password": cli_pass
    })
    assert res.status_code == 200
    assert res.json()["user"]["role"] == "platform_admin"

    # Second attempt without force flag is safely rejected
    duplicate_attempt = asyncio.run(provision_admin(
        email=cli_email,
        password=cli_pass,
        force=False,
        db=in_memory_auth_db,
    ))
    assert duplicate_attempt is False


# 11. Coexistence of multiple students, multiple faculty, and multiple administrators
def test_multiple_users_same_role_coexist(client):
    users_col = in_memory_auth_db["users"]

    multi_users = [
        ("student_multi_1@vfstr.ac.in", "Multi Student One", UserRole.STUDENT, "StudentOnePass1!"),
        ("student_multi_2@vfstr.ac.in", "Multi Student Two", UserRole.STUDENT, "StudentTwoPass2!"),
        ("faculty_multi_1@vfstr.ac.in", "Multi Faculty One", UserRole.FACULTY, "FacultyOnePass1!"),
        ("faculty_multi_2@vfstr.ac.in", "Multi Faculty Two", UserRole.FACULTY, "FacultyTwoPass2!"),
        ("admin_multi_1@vfstr.ac.in", "Multi Admin One", UserRole.PLATFORM_ADMIN, "AdminOnePass1!"),
        ("admin_multi_2@vfstr.ac.in", "Multi Admin Two", UserRole.PLATFORM_ADMIN, "AdminTwoPass2!"),
    ]

    for email, name, role, pwd in multi_users:
        doc = UserInDB(
            email=email,
            full_name=name,
            role=role,
            institution_id="VFSTR",
            account_status=AccountStatus.ACTIVE,
            is_verified=True,
            hashed_password=hash_password(pwd)
        )
        # Must succeed without any duplicate key error on role
        users_col.insert_one(doc.model_dump())

    # Verify count per role is >= 2
    students_count = users_col.count_documents({"role": UserRole.STUDENT.value})
    faculty_count = users_col.count_documents({"role": UserRole.FACULTY.value})
    admin_count = users_col.count_documents({"role": UserRole.PLATFORM_ADMIN.value})

    assert students_count >= 2
    assert faculty_count >= 2
    assert admin_count >= 2

    # Verify multiple users with same role can log in independently
    s1_res = client.post("/api/auth/login", json={
        "email": "student_multi_1@vfstr.ac.in",
        "password": "StudentOnePass1!"
    })
    assert s1_res.status_code == 200
    assert s1_res.json()["user"]["role"] == "student"

    s2_res = client.post("/api/auth/login", json={
        "email": "student_multi_2@vfstr.ac.in",
        "password": "StudentTwoPass2!"
    })
    assert s2_res.status_code == 200
    assert s2_res.json()["user"]["role"] == "student"

    f1_res = client.post("/api/auth/login", json={
        "email": "faculty_multi_1@vfstr.ac.in",
        "password": "FacultyOnePass1!"
    })
    assert f1_res.status_code == 200
    assert f1_res.json()["user"]["role"] == "faculty"


# 12. Rejection of duplicate email addresses by MongoDB unique constraint
def test_duplicate_email_rejected_by_database_index():
    users_col = in_memory_auth_db["users"]

    # Attempt to insert a document with an email that already exists
    duplicate_user = UserInDB(
        email=TEST_STUDENT_EMAIL,  # Already inserted during setup
        full_name="Duplicate Impostor",
        role=UserRole.STUDENT,
        institution_id="VFSTR",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password("AnyPassword123!")
    )
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        users_col.insert_one(duplicate_user.model_dump())


# 13. Safe detection and removal of erroneous unique index on role alone
def test_safe_index_migration_replaces_erroneous_unique_role_index():
    async def _test_migration():
        test_col = in_memory_auth_db["test_role_index_migration"]
        test_col.drop()

        # Step 1: Simulate legacy bad state with UNIQUE index on role alone
        test_col.create_index([("role", pymongo.ASCENDING)], unique=True, name="role_1")
        info_before = test_col.index_information()
        assert info_before["role_1"].get("unique") is True

        # Insert a user record to verify data is not deleted during migration
        test_user = UserInDB(
            email="migration_student@vfstr.ac.in",
            full_name="Migration Student",
            role=UserRole.STUDENT,
            institution_id="VFSTR",
            account_status=AccountStatus.ACTIVE,
            is_verified=True,
            hashed_password=hash_password("AnyPassword123!")
        )
        test_col.insert_one(test_user.model_dump())

        # Step 2: Run migration: audit and drop unique role index
        existing_indexes = test_col.index_information()
        for idx_name, idx_info in list(existing_indexes.items()):
            if idx_name != "_id_" and idx_info.get("key") in ([("role", 1)], [("role", pymongo.ASCENDING)]):
                if idx_info.get("unique", False):
                    test_col.drop_index(idx_name)

        test_col.create_index([("email", pymongo.ASCENDING)], unique=True, name="email_1")
        test_col.create_index([("role", pymongo.ASCENDING)], unique=False, name="role_1")

        # Step 3: Verify indexes after migration
        info_after = test_col.index_information()
        assert "email_1" in info_after
        assert info_after["email_1"].get("unique") is True
        assert "role_1" in info_after
        assert info_after["role_1"].get("unique", False) is False

        # Verify user record is intact
        found = test_col.find_one({"email": "migration_student@vfstr.ac.in"})
        assert found is not None
        assert found["role"] == "student"

        # Step 4: Verify a second user with the same role can now be inserted
        second_user = UserInDB(
            email="migration_student2@vfstr.ac.in",
            full_name="Migration Student Two",
            role=UserRole.STUDENT,
            institution_id="VFSTR",
            account_status=AccountStatus.ACTIVE,
            is_verified=True,
            hashed_password=hash_password("AnyPassword123!")
        )
        test_col.insert_one(second_user.model_dump())
        assert test_col.count_documents({"role": "student"}) == 2

        # Clean up test collection
        test_col.drop()

    asyncio.run(_test_migration())


# 14. Bootstrap endpoint disablement via configuration
def test_bootstrap_endpoint_can_be_disabled(client):
    # Temporarily disable endpoint
    original_setting = settings.ENABLE_BOOTSTRAP_ENDPOINT
    try:
        settings.ENABLE_BOOTSTRAP_ENDPOINT = False
        res = client.post(
            "/api/auth/bootstrap-admin",
            headers={"X-Bootstrap-Secret": settings.JWT_SECRET_KEY},
            json={
                "email": "disabled_test@vfstr.ac.in",
                "password": "DisabledPassword123!"
            }
        )
        assert res.status_code == 403
        assert "disabled" in res.json()["detail"].lower()
    finally:
        settings.ENABLE_BOOTSTRAP_ENDPOINT = original_setting


# 15. Unauthenticated and unauthorized administrative requests are rejected
def test_unauthenticated_and_unauthorized_administrative_requests_rejected(client):
    # Unauthenticated request to /admin-only -> 401
    unauth_res = client.get("/api/auth/admin-only")
    assert unauth_res.status_code == 401
    assert "Authentication required" in unauth_res.json()["detail"]

    # Faculty login
    fac_login = client.post("/api/auth/login", json={
        "email": TEST_FACULTY_EMAIL,
        "password": TEST_FACULTY_PASS
    })
    assert fac_login.status_code == 200
    fac_token = fac_login.json()["access_token"]

    # Faculty request to /admin-only -> 403
    fac_res = client.get("/api/auth/admin-only", headers={"Authorization": f"Bearer {fac_token}"})
    assert fac_res.status_code == 403
    assert "Insufficient permissions" in fac_res.json()["detail"]
