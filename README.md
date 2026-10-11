# Adaptive Interview Intelligence for Vignan University (VFSTR)

> **Phase 2: Secure Authentication and Role-Based Access Control (RBAC)**  
> AI-driven adaptive mock interviews, dynamic behavioral analysis, and technical evaluation platform for Vignan's Foundation for Science, Technology & Research (VFSTR).

---

## 🏛️ Project Overview

**Adaptive Interview Intelligence** is an enterprise-grade technical assessment platform designed specifically for students and placement faculty at Vignan University (VFSTR, Vadlamudi, Guntur, AP).

This release completes **Phase 2**, delivering:
- MongoDB User model supporting normalized emails, bcrypt password hashing, account status, email verification, and institutional multi-tenancy.
- Strict 5-tier role hierarchy: `platform_admin`, `university_admin`, `department_admin`, `faculty`, and `student`.
- Backend endpoints: `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, and protected test probes.
- Reusable FastAPI authentication (`get_current_user`, `get_current_active_user`) and role authorization (`require_roles`) dependencies.
- Login abuse protection via client IP/email rate limiting.
- Secure CLI administrator bootstrap procedure (`app.cli.bootstrap_admin`) preventing duplicate privilege escalation.
- Polished React 19 + Tailwind CSS v4 login page with form validation, session restoration, and role-guarded routing (`/login`, `/dashboard`, `/admin`, `/unauthorized`).
- 12 automated unit & integration tests passing with 100% success rate.

---

## 📂 Project Structure

```
C:\VfstrInterview/
├── .env.example                  # Root environment template with JWT & rate-limit settings
├── .gitignore                    # Protects .env, venv/, node_modules/, dist/, and caches
├── README.md                     # Comprehensive project documentation & runbook
├── backend/                      # Backend Service (Python 3.13 + FastAPI)
│   ├── .env                      # Local development environment configuration
│   ├── .env.example              # Backend environment template
│   ├── requirements.txt          # Python dependencies (fastapi, bcrypt, pyjwt, motor, pydantic, etc.)
│   ├── venv/                     # Python virtual environment
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI entrypoint, CORS, lifespan, and route mounting
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py           # get_current_user and require_roles authorization guards
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       ├── health.py     # GET /api/health diagnostic endpoint
│   │   │       └── auth.py       # POST /login, POST /logout, GET /me, and protected probes
│   │   ├── cli/
│   │   │   ├── __init__.py
│   │   │   ├── bootstrap_admin.py # Secure CLI platform administrator bootstrap tool
│   │   │   └── seed_demo_users.py # Development seed utility for student/faculty accounts
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py         # Pydantic Settings (JWT, Mongo, CORS, Rate Limit)
│   │   │   ├── database.py       # Motor async MongoDB client, pooling & indexes
│   │   │   └── security.py       # bcrypt hashing, JWT create/decode, LoginRateLimiter
│   │   └── models/
│   │       ├── __init__.py
│   │       └── user.py           # UserRole, AccountStatus, UserInDB, TokenResponse models
│   └── tests/
│       ├── __init__.py
│       ├── test_health.py        # Pytest health and root endpoint test suite
│       └── test_auth.py          # Pytest suite covering all 10 Phase 2 auth/RBAC scenarios
└── frontend/                     # Frontend Application (React 19 + Vite 8 + Tailwind CSS v4)
    ├── .env                      # Local frontend environment configuration
    ├── .env.example              # Frontend environment template
    ├── index.html                # HTML5 entrypoint with VFSTR typography & SEO meta tags
    ├── package.json              # NPM dependencies & scripts
    ├── vite.config.js            # Vite config with Tailwind v4 & reverse proxy to port 8000
    └── src/
        ├── main.jsx              # React DOM entrypoint with BrowserRouter & AuthProvider
        ├── App.jsx               # Main router (/ , /login, /dashboard, /admin, /unauthorized)
        ├── index.css             # Tailwind CSS v4 tokens and glassmorphism utilities
        ├── api/
            └── client.js         # Axios client with bearer token interceptors & auth methods
        ├── context/
            └── AuthContext.jsx   # React AuthContext managing session, user state, and RBAC
        ├── components/
            └── ProtectedRoute.jsx # Route guard component checking authentication & allowed roles
        └── pages/
            ├── Login.jsx         # Polished login page with form validation & demo helpers
            ├── Dashboard.jsx     # Student/user dashboard with live server RBAC probes
            ├── AdminConsole.jsx  # Admin-only console protected by require_roles dependency
            └── Unauthorized.jsx  # HTTP 403 Forbidden Access Denied page
```

---

## 🔐 Authentication & Security Architecture

### 1. User Roles
The platform defines 5 explicit, validated roles:
1. `platform_admin` — Full platform authority, tenant control, system bootstrap.
2. `university_admin` — Central Vignan University placement authority.
3. `department_admin` — Departmental placement coordinators (CSE, IT, ECE, etc.).
4. `faculty` — Mock interviewers, rubrics evaluators, and assessment reviews.
5. `student` — Interview candidates, profile owners, practice participants.

### 2. Password Security & Hashing
- Utilizes `bcrypt` with salt work factor 12. Plaintext passwords are never stored.
- Generic error messages (`401 Unauthorized: Invalid email or password`) prevent user enumeration attacks.

### 3. JWT Token Specification
- Algorithm: `HS256`.
- Claims: Subject (`sub`: user id), `email`, `role`, `institution_id`, Issuer (`iss`: `vfstr-interview`), Audience (`aud`: `vfstr-interview-client`), `iat`, and Expiration (`exp`).
- Expiration: Configurable via `ACCESS_TOKEN_EXPIRE_MINUTES` (defaults to 60 minutes).
- Frontend Token Storage: Stored in `sessionStorage` (automatically destroyed when browser tab/window is closed), avoiding long-term persistent token vulnerability in `localStorage`.

### 4. Abuse Protection & Rate Limiting
- `LoginRateLimiter` enforces a sliding window (maximum 5 failed attempts per 5-minute window per client IP/email).
- Returns `HTTP 429 Too Many Requests` when limits are exceeded.

### 5. Server-Enforced RBAC
Every protected endpoint independently inspects the JWT payload and verifies account status against MongoDB:
- Missing / Expired / Altered token $\rightarrow$ `HTTP 401 Unauthorized`
- Authenticated with insufficient role $\rightarrow$ `HTTP 403 Forbidden`

---

## 🛠️ Initial Administrator Provisioning

Administrator accounts are never provisioned through public registration. Use the secure CLI tool:

```powershell
# Navigate to the backend directory
cd C:\VfstrInterview\backend

# Run the bootstrap utility with secure interactive password prompt:
.\venv\Scripts\python -m app.cli.bootstrap_admin --email admin@vfstr.ac.in --name "VFSTR System Administrator"

# Or provide via command-line arguments:
.\venv\Scripts\python -m app.cli.bootstrap_admin --email admin@vfstr.ac.in --password "YourStrongPassword123!" --force
```

**Security Safeguards:**
- Refuses to run if a `platform_admin` already exists in MongoDB (unless `--force` is explicitly provided).
- Enforces minimum 8-character password complexity.
- Creates unique database indexes before insertion to guarantee integrity.

---

## 🚀 Running the Application

### 1. Run the Backend

```powershell
cd C:\VfstrInterview\backend
.\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- API Base: `http://127.0.0.1:8000/`
- Health Endpoint: `http://127.0.0.1:8000/api/health`
- Swagger Documentation: `http://127.0.0.1:8000/docs`

### 2. Run the Frontend

```powershell
cd C:\VfstrInterview\frontend
npm run dev
```
- Web Application: `http://localhost:5173/`
- Direct Login Page: `http://localhost:5173/login`

---

## 🧪 Automated Testing & Results

Run the full pytest suite from the project root:

```powershell
cd C:\VfstrInterview\backend
.\venv\Scripts\python -m pytest tests
```

**Results:** `17 passed` (100% passing)

| # | Test Name | Target Behavior | Result |
| :---: | :--- | :--- | :--- |
| 1 | `test_login_successful` | Returns 200 OK + JWT bearer token + student profile | **PASSED** |
| 2 | `test_login_incorrect_password` | Returns 401 Unauthorized with generic message | **PASSED** |
| 3 | `test_login_unknown_account` | Returns 401 Unauthorized with generic message | **PASSED** |
| 4 | `test_protected_access_valid_token` | Authenticated user accesses `/api/auth/me` and `/protected-test` | **PASSED** |
| 5 | `test_protected_endpoint_unauthenticated` | Unauthenticated request rejected with 401 | **PASSED** |
| 6 | `test_rejection_invalid_and_expired_tokens` | Expired signature or invalid token string rejected with 401 | **PASSED** |
| 7 | `test_role_based_authorization` | Admin accesses `/admin-only` (200), Student rejected (403) | **PASSED** |
| 8 | `test_prevention_public_privilege_escalation` | Unauthenticated call to bootstrap endpoint rejected with 403 | **PASSED** |
| 9 | `test_duplicate_account_handling` | Duplicate email insertion safely rejected with 409 Conflict | **PASSED** |
| 10 | `test_secure_admin_provisioning_cli` | CLI provisions platform admin & prevents duplicate escalation | **PASSED** |
| 11 | `test_multiple_users_same_role_coexist` | Multiple students, faculty, and admins cleanly coexist in DB | **PASSED** |
| 12 | `test_duplicate_email_rejected_by_database_index` | Duplicate email insertion triggers DuplicateKeyError | **PASSED** |
| 13 | `test_safe_index_migration_replaces_erroneous_unique_role_index` | Erroneous unique role index detected & dropped without data loss | **PASSED** |
| 14 | `test_bootstrap_endpoint_can_be_disabled` | Disabling bootstrap endpoint in config rejects with 403 | **PASSED** |
| 15 | `test_unauthenticated_and_unauthorized_administrative_requests_rejected` | Probes reject unauthorized callers with 401/403 | **PASSED** |
| 16 | `test_root_endpoint` | Root greeting and health URL response | **PASSED** |
| 17 | `test_health_endpoint` | `/api/health` diagnostic payload and database status | **PASSED** |

### Frontend Production Build & Lint:
```powershell
cd C:\VfstrInterview\frontend
npm run lint
npm run build
```
**Results:** Production assets generated in `<1s` with `0` errors. Demo autofill buttons are strictly excluded from production bundles.

---

## 🗺️ Multi-Phase Roadmap & Current Limitations

| Phase | Title | Status | Scope |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Safe Foundation** | **Completed** | Scaffolding, FastAPI health service, React 19 + Tailwind v4, MongoDB driver, tests. |
| **Phase 2** | **Secure Auth & RBAC** | **Completed** | User models, bcrypt, JWT tokens, role dependencies, rate limiting, login UI, admin CLI bootstrap. |
| **Phase 3** | **Adaptive AI Interviews** | *Next Phase* | LLM question engine, branching difficulty, voice/text answers, scoring rubrics. |
| **Phase 4** | **Monitoring & Drive Sync** | *Planned* | Webcam anti-cheat proctoring, live code compilation sandbox, Google Drive report export. |

> [!NOTE]  
> **Current Limitations (Phase 2 Boundaries)**:  
> Open student self-registration, student registry verification, email OTP verification, complete university administration management portals, AI interview generation, proctoring, and code execution are intentionally scheduled for upcoming phases.

---

## 🏫 Vignan University (VFSTR)
*Vadlamudi, Guntur, Andhra Pradesh, India - 522213*  
*Adaptive Interview Intelligence Initiative*
