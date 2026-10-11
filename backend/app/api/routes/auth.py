import secrets
import uuid
import logging
import re
import time
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import pymongo.errors
from pymongo import ReturnDocument
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import get_database
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    login_limiter
)
from app.models.user import (
    LoginRequest,
    TokenResponse,
    UserResponse,
    UserInDB,
    UserRole,
    AccountStatus
)
from app.models.verification import (
    InitiateRegistrationRequest,
    VfstrDirectRegisterRequest,
    ResendVerificationRequest,
    CompleteRegistrationRequest,
    GeneralStudentRegisterRequest,
    GeneralStudentInitiateRequest,
    GeneralStudentResendRequest,
    GeneralStudentCompleteRequest
)
from app.models.eligibility import EmailSource, EligibilityStatus
from app.services.email_service import EmailService, mask_email
from app.services.verification_service import (
    generate_secure_otp,
    generate_salt,
    hash_otp,
    verify_otp_hash,
    hash_client_ip,
    mask_registration_number,
    utc_now
)
from app.api.deps import get_current_active_user, require_roles

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Authenticates a user using email and password.
    Includes rate-limiting for login abuse protection, generic error messages,
    and returns a signed JWT token with user details.
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{login_data.email}"

    if login_limiter.is_rate_limited(rate_limit_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again after 5 minutes."
        )

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    users_col = db["users"]
    clean_identifier = login_data.email.strip().lower()
    user_doc = await users_col.find_one({"email": clean_identifier})
    if not user_doc:
        roll_candidate = clean_identifier
        if roll_candidate.endswith("@vfstr.ac.in"):
            roll_candidate = roll_candidate.split("@")[0]
        user_doc = await users_col.find_one({"registration_number": roll_candidate.upper()})

    # Generic error message to prevent user enumeration
    if not user_doc or not verify_password(login_data.password, user_doc["hashed_password"]):
        login_limiter.record_failure(rate_limit_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check account status
    if user_doc.get("account_status") == AccountStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended. Please contact VFSTR administration."
        )

    # Reset failure counter on successful login
    login_limiter.reset(rate_limit_key)

    user = UserInDB(**user_doc)
    access_token = create_access_token(
        subject=user.id,
        email=user.email,
        role=user.role.value,
        institution_id=user.institution_id
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            institution_id=user.institution_id,
            registration_number=user.registration_number,
            department=user.department,
            batch_cohort=user.batch_cohort,
            section=user.section,
            contact_number=user.contact_number,
            college_name=user.college_name,
            account_status=user.account_status,
            is_verified=user.is_verified,
            created_at=user.created_at
        )
    )

@router.post("/logout")
async def logout(
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Stateless logout endpoint. Invalidates client-side session.
    """
    return {
        "status": "success",
        "message": f"Session closed for {current_user.email}"
    }

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Returns the current authenticated user profile.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        institution_id=current_user.institution_id,
        registration_number=current_user.registration_number,
        department=current_user.department,
        batch_cohort=current_user.batch_cohort,
        section=current_user.section,
        contact_number=current_user.contact_number,
        college_name=current_user.college_name,
        account_status=current_user.account_status,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at
    )

@router.get("/protected-test")
async def protected_test_endpoint(
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Demonstration endpoint verifying valid authentication for any active role.
    """
    return {
        "status": "authenticated",
        "message": "Access granted to authenticated user",
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "institution": current_user.institution_id
    }

@router.get("/admin-only")
async def admin_only_endpoint(
    current_user: UserInDB = Depends(
        require_roles([UserRole.PLATFORM_ADMIN, UserRole.UNIVERSITY_ADMIN])
    )
):
    """
    Demonstration endpoint strictly reserved for platform and university administrators.
    Rejects faculty and students with 403 Forbidden.
    """
    return {
        "status": "authorized",
        "message": "Access granted to administrative portal",
        "administrator": current_user.email,
        "role": current_user.role
    }

@router.post("/bootstrap-admin", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_initial_admin(
    payload: LoginRequest,
    x_bootstrap_secret: Optional[str] = Header(None),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Protected one-time administrator bootstrap endpoint.
    Note: The host CLI tool (backend/app/cli/bootstrap_admin.py) is the preferred provisioning mechanism.
    This HTTP endpoint is strictly disabled in production unless explicitly permitted,
    requires timing-attack-safe validation of BOOTSTRAP_SECRET_KEY / JWT_SECRET_KEY,
    and aborts if a platform_admin already exists to prevent repeated privilege escalation.
    """
    # Check if bootstrap endpoint is enabled
    if not settings.ENABLE_BOOTSTRAP_ENDPOINT or (
        settings.ENVIRONMENT.lower() in ("production", "prod") and not settings.ALLOW_BOOTSTRAP_IN_PRODUCTION
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator HTTP bootstrap endpoint is disabled. Use the CLI tool for administrative provisioning."
        )

    expected_secret = settings.BOOTSTRAP_SECRET_KEY or settings.JWT_SECRET_KEY
    if not x_bootstrap_secret or not secrets.compare_digest(x_bootstrap_secret, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bootstrap authorization credentials"
        )

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    users_col = db["users"]

    # Check if a platform admin already exists
    existing_admin = await users_col.find_one({"role": UserRole.PLATFORM_ADMIN.value})
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial platform administrator has already been provisioned"
        )

    # Check if this email is already registered
    existing_user = await users_col.find_one({"email": payload.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists"
        )

    now = datetime.now(timezone.utc)
    new_admin = UserInDB(
        email=payload.email,
        full_name="VFSTR Platform Administrator",
        role=UserRole.PLATFORM_ADMIN,
        institution_id="VFSTR",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password(payload.password),
        created_at=now,
        updated_at=now
    )

    try:
        await users_col.insert_one(new_admin.model_dump())
    except pymongo.errors.DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists"
        )

    return UserResponse(
        id=new_admin.id,
        email=new_admin.email,
        full_name=new_admin.full_name,
        role=new_admin.role,
        institution_id=new_admin.institution_id,
        account_status=new_admin.account_status,
        is_verified=new_admin.is_verified,
        created_at=new_admin.created_at
    )


# ==============================================================================
# PHASE 4: VERIFIED STUDENT REGISTRATION & ELIGIBILITY REGISTRY CLAIM
# ==============================================================================

GENERIC_INITIATE_RESPONSE = {
    "status": "success",
    "message": (
        "If this registration number is approved and eligible for registration, "
        "a single-use verification code has been dispatched to your official university email."
    ),
    "resend_cooldown_seconds": settings.REGISTRATION_RESEND_COOLDOWN_SECONDS,
    "expires_in_minutes": settings.REGISTRATION_OTP_EXPIRE_MINUTES
}


@router.post("/vfstr/register", response_model=TokenResponse)
@router.post("/register/direct", response_model=TokenResponse)
async def register_vfstr_student_direct(
    payload: VfstrDirectRegisterRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Direct VFSTR Student Self-Registration & Session Entry (Priority 1):
    1. Student enters their university registration number and personal contact number.
    2. Validates registration number against authoritative official eligibility_registry.
    3. Strictly enforces eligibility, rejecting invalid, ineligible, or pending-review students.
    4. Creates or retrieves the student profile without duplicate accounts.
    5. Returns JWT TokenResponse to authenticate session immediately without SMTP/email OTP.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    t_start = time.perf_counter()
    roll_norm = payload.get_normalized_roll()
    clean_contact = payload.get_clean_contact()
    masked_roll = mask_registration_number(roll_norm)
    now = utc_now()

    # 1. Validate contact number format (at least 10 digits)
    if not re.match(r"^\+?[0-9]{10,15}$", clean_contact):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid personal contact number with at least 10 digits."
        )

    elig_col = db["eligibility_registry"]
    users_col = db["users"]

    # 2. Authoritative lookup in official eligibility_registry
    elig_doc = await elig_col.find_one({
        "institution_id": "VFSTR",
        "registration_number": roll_norm
    })

    if not elig_doc:
        logger.warning(f"Registration rejected for {masked_roll}: roll not found in official registry.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration number '{roll_norm}' was not found in the official VFSTR student eligibility registry. Please check your roll number or contact the placement cell."
        )

    # 3. Guard against placeholder address (NA email) requiring physical department verification
    if elig_doc.get("email_source") == EmailSource.GENERATED_PENDING_VERIFICATION.value:
        logger.warning(f"Registration blocked for {masked_roll}: department verification required.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your student eligibility record is recognized but requires official university email "
                "verification before online account setup. Please contact the CSE Department Administration / "
                "Placement Cell with your physical VFSTR Student ID card to verify your university email."
            )
        )

    # 4. Check eligibility status restrictions
    if (
        elig_doc.get("validation_status") != EligibilityStatus.ELIGIBLE.value
        or not elig_doc.get("is_eligible_for_registration", False)
    ):
        logger.warning(f"Registration blocked for {masked_roll}: ineligible or pending review status.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Registration number '{roll_norm}' is currently marked as ineligible or pending administrative review. Please contact VFSTR Placement Cell."
        )

    # 5. Check if user account already exists in users collection
    existing_user = await users_col.find_one({
        "institution_id": "VFSTR",
        "registration_number": roll_norm
    })

    if existing_user:
        # Check suspended status
        if existing_user.get("account_status") == AccountStatus.SUSPENDED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is suspended. Please contact VFSTR administration."
            )

        # Verify contact number identity match if previously recorded
        saved_contact = existing_user.get("contact_number")
        if saved_contact:
            saved_contact_clean = re.sub(r"[\s\-\(\)]", "", saved_contact)
            # Compare last 10 digits to handle country code prefix variations safely
            if saved_contact_clean[-10:] != clean_contact[-10:]:
                logger.warning(f"Contact number mismatch for existing user {masked_roll}.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="The entered contact number does not match the registered contact number for this student account. Please use your registered contact number or contact administration."
                )
        else:
            # Update contact number on existing profile
            await users_col.update_one(
                {"_id": existing_user["_id"]},
                {"$set": {"contact_number": clean_contact, "updated_at": now}}
            )
            existing_user["contact_number"] = clean_contact

        user = UserInDB(**existing_user)
        logger.info(f"Existing student session retrieved for {masked_roll}")
    else:
        # Create fresh student account
        user_id = str(uuid.uuid4())
        roster_email = elig_doc.get("roster_email", f"vu.{roll_norm.lower()}@gmail.com")

        new_user = UserInDB(
            id=user_id,
            email=roster_email,
            full_name=elig_doc.get("student_name", "VFSTR Student"),
            role=UserRole.STUDENT,  # Strictly STUDENT role enforced by backend
            institution_id="VFSTR",
            registration_number=roll_norm,
            department=elig_doc.get("department", "CSE"),
            batch_cohort=elig_doc.get("batch_cohort", "2024-2028"),
            section=elig_doc.get("section"),
            contact_number=clean_contact,
            college_name="VFSTR (Deemed to be University)",
            account_status=AccountStatus.ACTIVE,
            is_verified=True,
            hashed_password=hash_password(secrets.token_urlsafe(16)),
            eligibility_registry_id=str(elig_doc.get("_id", "")),
            created_at=now,
            updated_at=now,
        )

        try:
            await users_col.insert_one(new_user.model_dump())
        except pymongo.errors.DuplicateKeyError:
            # Race condition: re-fetch
            existing_user = await users_col.find_one({
                "institution_id": "VFSTR",
                "registration_number": roll_norm
            })
            if existing_user:
                new_user = UserInDB(**existing_user)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Account already exists for this student."
                )

        # Atomically mark record in eligibility registry as claimed
        await elig_col.update_one(
            {"_id": elig_doc["_id"]},
            {
                "$set": {
                    "is_claimed": True,
                    "claimed_user_id": new_user.id,
                    "claimed_at": now,
                    "updated_at": now,
                }
            }
        )
        user = new_user
        logger.info(f"New student account provisioned for {masked_roll}")

    # 6. Issue JWT session token
    access_token = create_access_token(
        subject=user.id,
        email=user.email,
        role=user.role.value,
        institution_id=user.institution_id
    )

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(f"[TIMING] VFSTR direct registration session issued for {masked_roll} in {total_ms:.1f}ms")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            institution_id=user.institution_id,
            registration_number=user.registration_number,
            department=user.department,
            batch_cohort=user.batch_cohort,
            section=user.section,
            contact_number=user.contact_number,
            college_name=user.college_name,
            account_status=user.account_status,
            is_verified=user.is_verified,
            created_at=user.created_at
        )
    )


@router.post("/register/initiate")
async def initiate_registration(
    payload: InitiateRegistrationRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Stage 1 of Student Registration:
    - Normalizes registration number.
    - Checks eligibility in eligibility_registry.
    - Prevents automated dispatch to generated_pending_verification records.
    - Dispatches secure single-use OTP to verified roster email.
    - Returns generic response to prevent student enumeration.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    t_start = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"
    client_ip_h = hash_client_ip(client_ip)
    roll_norm = payload.get_normalized_roll()
    masked_roll = mask_registration_number(roll_norm)

    logger.info(f"Registration initiation requested for roll {masked_roll} from IP hash {client_ip_h}")

    elig_col = db["eligibility_registry"]
    users_col = db["users"]
    verif_col = db["registration_verifications"]

    # Lookup student record in approved eligibility registry
    elig_doc = await elig_col.find_one({
        "institution_id": "VFSTR",
        "registration_number": roll_norm
    })

    # Guard: If student has a generated placeholder address (NA email),
    # block automated email dispatch and provide institutional guidance.
    if elig_doc and elig_doc.get("email_source") == EmailSource.GENERATED_PENDING_VERIFICATION.value:
        logger.warning(f"Registration blocked for {masked_roll}: generated placeholder address requires department verification.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your student eligibility record is recognized but requires official university email "
                "verification before online account setup. Please contact the CSE Department Administration / "
                "Placement Cell with your physical VFSTR Student ID card to verify your university email."
            )
        )

    # Check if student is already registered in users collection
    existing_user = await users_col.find_one({
        "institution_id": "VFSTR",
        "registration_number": roll_norm
    })

    t_db = time.perf_counter()
    db_ms = (t_db - t_start) * 1000

    # If student is not found, not eligible, or already claimed, return generic message (Anti-Enumeration)
    if (
        not elig_doc
        or existing_user
        or elig_doc.get("is_claimed", False)
        or not elig_doc.get("is_eligible_for_registration", False)
        or elig_doc.get("validation_status") != EligibilityStatus.ELIGIBLE.value
    ):
        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TIMING] Registration initiation completed (generic response) for {masked_roll} | DB: {db_ms:.1f}ms | Total: {total_ms:.1f}ms")
        return GENERIC_INITIATE_RESPONSE

    now = utc_now()

    # Check resend cooldown if an active verification exists
    active_verif = await verif_col.find_one({
        "registration_number_normalized": roll_norm,
        "is_consumed": False
    })
    if active_verif:
        last_resend = active_verif.get("last_resend_at")
        if last_resend and last_resend.tzinfo is None:
            last_resend = last_resend.replace(tzinfo=timezone.utc)
        if last_resend:
            elapsed = (now - last_resend).total_seconds()
            if elapsed < settings.REGISTRATION_RESEND_COOLDOWN_SECONDS:
                total_ms = (time.perf_counter() - t_start) * 1000
                logger.info(f"[TIMING] Resend throttled for {masked_roll}: {elapsed:.1f}s elapsed < {settings.REGISTRATION_RESEND_COOLDOWN_SECONDS}s (completed in {total_ms:.1f}ms)")
                return GENERIC_INITIATE_RESPONSE

    # Generate cryptographically secure OTP and salt
    otp_code = generate_secure_otp()
    salt = generate_salt()
    code_hash = hash_otp(otp_code, salt)
    expires_at = now + timedelta(minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES)

    # Dispatch email to approved roster email before committing verification record
    t_email_start = time.perf_counter()
    email_sent = await EmailService.send_verification_otp(
        to_email=elig_doc["roster_email"],
        registration_number=roll_norm,
        otp_code=otp_code,
        expires_minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES
    )
    email_ms = (time.perf_counter() - t_email_start) * 1000

    if not email_sent:
        logger.warning(
            f"[TIMING] Registration initiation email dispatch failed for {masked_roll} after {email_ms:.1f}ms. "
            f"Error: {EmailService.get_last_error()}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to deliver verification code to your official email at this time. Please try again shortly or contact university administration."
        )

    t_store_start = time.perf_counter()
    # Store verification record only upon confirmed email dispatch
    await verif_col.update_one(
        {"registration_number_normalized": roll_norm},
        {
            "$set": {
                "roster_email_normalized": elig_doc["roster_email"],
                "code_hash": code_hash,
                "salt": salt,
                "attempt_count": 0,
                "max_attempts": settings.REGISTRATION_OTP_MAX_ATTEMPTS,
                "is_consumed": False,
                "created_at": now,
                "expires_at": expires_at,
                "last_resend_at": now,
                "client_ip_hash": client_ip_h,
            }
        },
        upsert=True
    )
    store_ms = (time.perf_counter() - t_store_start) * 1000

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"[TIMING] Registration initiation completed for {masked_roll} | "
        f"DB: {db_ms:.1f}ms | Email: {email_ms:.1f}ms | Store: {store_ms:.1f}ms | Total: {total_ms:.1f}ms"
    )

    response_data = dict(GENERIC_INITIATE_RESPONSE)
    if settings.is_demo_otp_allowed:
        response_data["demo_otp_hint"] = otp_code
        response_data["demo_mode"] = True
    return response_data


@router.post("/register/resend")
async def resend_registration_code(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Resends a verification OTP code for a student with an active registration session,
    enforcing a 60-second cooldown.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    t_start = time.perf_counter()
    roll_norm = payload.get_normalized_roll()
    masked_roll = mask_registration_number(roll_norm)
    now = utc_now()

    verif_col = db["registration_verifications"]
    active_verif = await verif_col.find_one({
        "registration_number_normalized": roll_norm,
        "is_consumed": False
    })

    t_db = time.perf_counter()
    db_ms = (t_db - t_start) * 1000

    if not active_verif:
        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TIMING] Registration resend completed (no active session) for {masked_roll} in {total_ms:.1f}ms")
        return GENERIC_INITIATE_RESPONSE

    # Check expiration
    exp = active_verif.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and now > exp:
        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TIMING] Registration resend completed (expired session) for {masked_roll} in {total_ms:.1f}ms")
        return GENERIC_INITIATE_RESPONSE

    # Enforce 60-second cooldown
    last_resend = active_verif.get("last_resend_at")
    if last_resend and last_resend.tzinfo is None:
        last_resend = last_resend.replace(tzinfo=timezone.utc)
    if last_resend:
        elapsed = (now - last_resend).total_seconds()
        if elapsed < settings.REGISTRATION_RESEND_COOLDOWN_SECONDS:
            remaining = int(settings.REGISTRATION_RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting another code."
            )

    # Generate fresh OTP
    otp_code = generate_secure_otp()
    salt = generate_salt()
    code_hash = hash_otp(otp_code, salt)
    expires_at = now + timedelta(minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES)

    # Dispatch email before updating verification record
    t_email_start = time.perf_counter()
    email_sent = await EmailService.send_verification_otp(
        to_email=active_verif["roster_email_normalized"],
        registration_number=roll_norm,
        otp_code=otp_code,
        expires_minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES
    )
    email_ms = (time.perf_counter() - t_email_start) * 1000

    if not email_sent:
        logger.warning(
            f"[TIMING] Registration resend email dispatch failed for {masked_roll} after {email_ms:.1f}ms. "
            f"Error: {EmailService.get_last_error()}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to deliver verification code to your official email at this time. Please try again shortly or contact university administration."
        )

    t_store_start = time.perf_counter()
    await verif_col.update_one(
        {"_id": active_verif["_id"]},
        {
            "$set": {
                "code_hash": code_hash,
                "salt": salt,
                "attempt_count": 0,
                "expires_at": expires_at,
                "last_resend_at": now
            }
        }
    )
    store_ms = (time.perf_counter() - t_store_start) * 1000

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"[TIMING] Registration resend completed for {masked_roll} | "
        f"DB: {db_ms:.1f}ms | Email: {email_ms:.1f}ms | Store: {store_ms:.1f}ms | Total: {total_ms:.1f}ms"
    )

    response_data = dict(GENERIC_INITIATE_RESPONSE)
    if settings.is_demo_otp_allowed:
        response_data["demo_otp_hint"] = otp_code
        response_data["demo_mode"] = True
    return response_data


@router.post("/register/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def complete_registration(
    payload: CompleteRegistrationRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Stage 2 of Student Registration:
    - Verifies 6-digit OTP code against HMAC-SHA256 hash.
    - Limits failed attempts to 3 before code invalidation.
    - Atomically claims eligibility_registry record (is_claimed=False -> True).
    - Creates UserInDB record with role='student' and official cohort/section.
    - Returns signed JWT token and user profile.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    roll_norm = payload.get_normalized_roll()
    clean_code = payload.get_clean_code()
    masked_roll = mask_registration_number(roll_norm)
    now = utc_now()

    verif_col = db["registration_verifications"]
    elig_col = db["eligibility_registry"]
    users_col = db["users"]

    # 1. Fetch active verification record
    verif_doc = await verif_col.find_one({
        "registration_number_normalized": roll_norm,
        "is_consumed": False
    })

    if not verif_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 2. Check expiration
    expires_at = verif_doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 3. Check attempt limit
    attempts = verif_doc.get("attempt_count", 0)
    max_attempts = verif_doc.get("max_attempts", 3)
    if attempts >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has been invalidated due to too many failed attempts. Please request a new code."
        )

    # 4. Verify candidate OTP hash in constant time
    is_valid_otp = verify_otp_hash(clean_code, verif_doc["salt"], verif_doc["code_hash"])
    if not is_valid_otp:
        # Increment failed attempts
        await verif_col.update_one(
            {"_id": verif_doc["_id"]},
            {"$inc": {"attempt_count": 1}}
        )
        remaining = max(0, max_attempts - (attempts + 1))
        logger.warning(f"Failed verification attempt for {masked_roll}. Remaining attempts: {remaining}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 5. Atomic Claim on eligibility_registry
    # Atomic pre-condition guarantees that only ONE concurrent transaction can claim the record
    new_user_id = str(uuid.uuid4())
    claimed_record = await elig_col.find_one_and_update(
        {
            "institution_id": "VFSTR",
            "registration_number": roll_norm,
            "is_claimed": False,
            "validation_status": EligibilityStatus.ELIGIBLE.value,
            "is_eligible_for_registration": True,
        },
        {
            "$set": {
                "is_claimed": True,
                "claimed_user_id": new_user_id,
                "claimed_at": now,
                "validation_status": EligibilityStatus.CLAIMED.value,
                "updated_at": now
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if not claimed_record:
        logger.warning(f"Atomic claim collision: {masked_roll} is already claimed or no longer eligible.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This student eligibility record has already been claimed or is unavailable."
        )

    # Guard: Placeholder email records can never be claimed without administrative email resolution
    if claimed_record.get("email_source") == EmailSource.GENERATED_PENDING_VERIFICATION.value:
        await elig_col.update_one(
            {"_id": claimed_record["_id"]},
            {
                "$set": {
                    "is_claimed": False,
                    "claimed_user_id": None,
                    "claimed_at": None,
                    "validation_status": EligibilityStatus.ELIGIBLE.value
                }
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your student record requires official university email verification before registration."
        )

    # 6. Create Student User Record (Role is strictly STUDENT; placement immutable)
    new_user = UserInDB(
        id=new_user_id,
        email=claimed_record["roster_email"],
        full_name=claimed_record["student_name"],
        role=UserRole.STUDENT,
        institution_id="VFSTR",
        registration_number=roll_norm,
        department=claimed_record.get("department", "CSE"),
        batch_cohort=claimed_record.get("batch_cohort", "2024-2028"),
        section=str(claimed_record.get("section", "")),
        eligibility_registry_id=str(claimed_record.get("_id", claimed_record.get("id"))),
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password(payload.password),
        created_at=now,
        updated_at=now
    )

    try:
        await users_col.insert_one(new_user.model_dump())
    except Exception as exc:
        # Roll back atomic claim if users collection insert fails for any reason
        await elig_col.update_one(
            {"_id": claimed_record["_id"]},
            {
                "$set": {
                    "is_claimed": False,
                    "claimed_user_id": None,
                    "claimed_at": None,
                    "validation_status": EligibilityStatus.ELIGIBLE.value
                }
            }
        )
        if isinstance(exc, pymongo.errors.DuplicateKeyError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email or registration number already exists."
            )
        logger.error(f"User account creation error during claim: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation could not be completed. The eligibility claim has been rolled back safely."
        )

    # 7. Consume verification token
    await verif_col.update_one(
        {"_id": verif_doc["_id"]},
        {
            "$set": {
                "is_consumed": True,
                "expires_at": now
            }
        }
    )

    logger.info(f"Student account successfully created and claimed for {masked_roll}")

    # 8. Issue JWT access token for immediate session initiation
    access_token = create_access_token(
        subject=new_user.id,
        email=new_user.email,
        role=new_user.role.value,
        institution_id=new_user.institution_id
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            institution_id=new_user.institution_id,
            registration_number=new_user.registration_number,
            department=new_user.department,
            batch_cohort=new_user.batch_cohort,
            section=new_user.section,
            contact_number=new_user.contact_number,
            college_name=new_user.college_name,
            account_status=new_user.account_status,
            is_verified=new_user.is_verified,
            created_at=new_user.created_at
        )
    )


# ==============================================================================
# GENERAL STUDENT REGISTRATION (PARTNER COLLEGES & UNIVERSITIES)
# ==============================================================================

@router.get("/institutions/allowed")
async def get_allowed_institutions():
    """
    Returns the list of accredited partner institutions permitted under the
    platform's institution-access policy.
    """
    return {
        "status": "success",
        "policy": "partner_institutions_only",
        "institutions": settings.ALLOWED_EXTERNAL_INSTITUTIONS
    }


async def _execute_general_student_registration(
    payload: GeneralStudentRegisterRequest,
    request: Request,
    db: AsyncIOMotorDatabase
) -> Dict[str, Any]:
    """
    Direct registration execution for General Students (Partner Colleges & Universities):
    - Validates full name, college name, student ID, email, contact number, password.
    - Strictly enforces configured partner institution-access policy.
    - Prevents duplicate email or duplicate college+ID accounts.
    - Role is strictly determined by the backend as 'student' (role escalation prevented).
    - Directly creates active User record with bcrypt hashed password.
    - Does NOT call email service, does NOT send OTP, does NOT create pending verification state.
    - Does NOT falsely mark email as verified (is_verified=False).
    - Issues JWT access token for immediate login capability.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    t_start = time.perf_counter()
    now = utc_now()

    clean_name = payload.get_clean_name()
    clean_college = payload.get_clean_college()
    clean_reg_no = payload.get_clean_reg_no()
    clean_email = payload.get_clean_email()
    clean_contact = payload.get_clean_contact()

    # 1. Validate password complexity (at least 8 chars, letters and digits)
    if len(payload.password) < 8 or not (re.search(r"[A-Za-z]", payload.password) and re.search(r"[0-9]", payload.password)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long and contain both letters and numbers."
        )

    # 2. Validate contact number format
    if not re.match(r"^\+?[0-9\s\-()]{10,20}$", clean_contact):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid personal contact number with at least 10 digits."
        )

    # 3. Enforce institution-access policy & prevent VFSTR impersonation
    if clean_email.endswith("@vfstr.ac.in") or clean_email.endswith(".vfstr.ac.in") or clean_email.endswith("@vignan.ac.in"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VFSTR students must use the dedicated VFSTR Student Verification Portal with their official university registration number."
        )

    if "vfstr" in clean_college.lower() or "vignan's foundation" in clean_college.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="VFSTR students must use the dedicated VFSTR Student Verification Portal with their official university registration number."
        )

    if not settings.is_institution_access_permitted(clean_college):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Institution '{clean_college}' is not authorized under the platform's partner access policy. "
                "Registration is permitted only for accredited partner institutions."
            )
        )

    users_col = db["users"]
    elig_col = db["eligibility_registry"]

    # Block registration if this registration number belongs to VFSTR registry or existing VFSTR user
    vfstr_elig = await elig_col.find_one({
        "institution_id": "VFSTR",
        "registration_number": clean_reg_no
    })
    if vfstr_elig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This registration number belongs to VFSTR Deemed University. Please use the dedicated VFSTR Student Verification Portal."
        )

    existing_vfstr_user = await users_col.find_one({
        "institution_id": "VFSTR",
        "registration_number": clean_reg_no
    })
    if existing_vfstr_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This registration number belongs to VFSTR Deemed University. Please use the dedicated VFSTR Student Verification Portal."
        )

    # 4. Check duplicate email in users collection
    existing_user_email = await users_col.find_one({"email": clean_email})
    if existing_user_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists. Please sign in instead."
        )

    # 5. Check duplicate college registration ID for this institution
    existing_user_reg = await users_col.find_one({
        "institution_id": clean_college,
        "registration_number": clean_reg_no
    })
    if existing_user_reg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this student registration ID is already registered for this institution. Please sign in."
        )

    # 6. Securely hash password (never plaintext)
    hashed_pwd = hash_password(payload.password)

    # 7. Create Student User Record (Role strictly STUDENT; active status; is_verified=False)
    new_user = UserInDB(
        id=str(uuid.uuid4()),
        email=clean_email,
        full_name=clean_name,
        role=UserRole.STUDENT,
        institution_id=clean_college,
        registration_number=clean_reg_no,
        contact_number=clean_contact,
        college_name=clean_college,
        account_status=AccountStatus.ACTIVE,
        is_verified=False,
        hashed_password=hashed_pwd,
        created_at=now,
        updated_at=now
    )

    try:
        await users_col.insert_one(new_user.model_dump())
    except pymongo.errors.DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address or registration ID already exists."
        )

    # 8. Issue JWT access token for immediate session initiation
    access_token = create_access_token(
        subject=new_user.id,
        email=new_user.email,
        role=new_user.role.value,
        institution_id=new_user.institution_id
    )

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"General student account created for {mask_email(clean_email)} [{clean_college}] in {total_ms:.1f}ms without OTP"
    )

    return {
        "status": "success",
        "message": "General student account created successfully. You can now log in.",
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            institution_id=new_user.institution_id,
            registration_number=new_user.registration_number,
            department=new_user.department,
            batch_cohort=new_user.batch_cohort,
            section=new_user.section,
            contact_number=new_user.contact_number,
            college_name=new_user.college_name,
            account_status=new_user.account_status,
            is_verified=new_user.is_verified,
            created_at=new_user.created_at
        )
    }


@router.post("/general/register", status_code=status.HTTP_201_CREATED)
async def register_general_student(
    payload: GeneralStudentRegisterRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Direct registration for General Students (Partner Colleges & Universities) without email OTP:
    - Validates inputs, partner college allowlist, password complexity, duplicate checks.
    - Hashes password securely.
    - Immediately creates active Student account.
    - Email verification is not required.
    """
    return await _execute_general_student_registration(payload, request, db)


@router.post("/general/register/initiate", status_code=status.HTTP_200_OK)
async def initiate_general_registration(
    payload: GeneralStudentRegisterRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Backward-compatible registration endpoint for General Students without email OTP.
    Directly creates the active Student account.
    """
    return await _execute_general_student_registration(payload, request, db)


@router.post("/general/register/resend")
async def resend_general_registration_code(
    payload: GeneralStudentResendRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Resends an OTP verification code for a pending general student registration,
    enforcing a 60-second cooldown timer.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    t_start = time.perf_counter()
    clean_email = payload.get_clean_email()
    now = utc_now()
    verif_col = db["registration_verifications"]

    active_verif = await verif_col.find_one({
        "email_normalized": clean_email,
        "registration_type": "external_student",
        "is_consumed": False
    })

    t_db = time.perf_counter()
    db_ms = (t_db - t_start) * 1000

    generic_resend_response = {
        "status": "success",
        "message": f"If an active registration exists for {clean_email}, a verification code has been dispatched.",
        "resend_cooldown_seconds": settings.REGISTRATION_RESEND_COOLDOWN_SECONDS,
        "expires_in_minutes": settings.REGISTRATION_OTP_EXPIRE_MINUTES
    }

    if not active_verif:
        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TIMING] General registration resend completed (no active session) for {mask_email(clean_email)} in {total_ms:.1f}ms")
        return generic_resend_response

    # Check expiration
    exp = active_verif.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and now > exp:
        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TIMING] General registration resend completed (session expired) for {mask_email(clean_email)} in {total_ms:.1f}ms")
        return generic_resend_response

    # Enforce 60-second cooldown
    last_resend = active_verif.get("last_resend_at")
    if last_resend and last_resend.tzinfo is None:
        last_resend = last_resend.replace(tzinfo=timezone.utc)
    if last_resend:
        elapsed = (now - last_resend).total_seconds()
        if elapsed < settings.REGISTRATION_RESEND_COOLDOWN_SECONDS:
            remaining = int(settings.REGISTRATION_RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting another code."
            )

    # Generate fresh OTP
    otp_code = generate_secure_otp()
    salt = generate_salt()
    code_hash = hash_otp(otp_code, salt)
    expires_at = now + timedelta(minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES)

    # Dispatch email before updating verification record
    t_email_start = time.perf_counter()
    email_sent = await EmailService.send_verification_otp(
        to_email=clean_email,
        registration_number=active_verif.get("college_reg_no", "STUDENT"),
        otp_code=otp_code,
        expires_minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES
    )
    email_ms = (time.perf_counter() - t_email_start) * 1000

    if not email_sent:
        logger.warning(
            f"[TIMING] General registration resend email dispatch failed for {mask_email(clean_email)} after {email_ms:.1f}ms. "
            f"Error: {EmailService.get_last_error()}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to deliver verification code to your email at this time. Please try again shortly."
        )

    t_store_start = time.perf_counter()
    await verif_col.update_one(
        {"_id": active_verif["_id"]},
        {
            "$set": {
                "code_hash": code_hash,
                "salt": salt,
                "attempt_count": 0,
                "expires_at": expires_at,
                "last_resend_at": now
            }
        }
    )
    store_ms = (time.perf_counter() - t_store_start) * 1000

    total_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        f"[TIMING] General registration resend completed for {mask_email(clean_email)} | "
        f"DB: {db_ms:.1f}ms | Email: {email_ms:.1f}ms | Store: {store_ms:.1f}ms | Total: {total_ms:.1f}ms"
    )

    response_data = dict(generic_resend_response)
    if settings.is_demo_otp_allowed:
        response_data["demo_otp_hint"] = otp_code
        response_data["demo_mode"] = True
    return response_data


@router.post("/general/register/complete", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def complete_general_registration(
    payload: GeneralStudentCompleteRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Stage 2 of General Student Registration:
    - Verifies single-use OTP code in constant time (max 3 attempts).
    - Ensures email ownership verification before enabling the account.
    - Role is strictly determined as 'student' by the backend (never user-supplied).
    - Creates active User record and issues JWT session token.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable"
        )

    clean_email = payload.get_clean_email()
    clean_code = payload.get_clean_code()
    now = utc_now()

    verif_col = db["registration_verifications"]
    users_col = db["users"]

    # Check if user was already registered via direct no-OTP flow
    existing_user_doc = await users_col.find_one({"email": clean_email})
    if existing_user_doc:
        user = UserInDB(**existing_user_doc)
        access_token = create_access_token(
            subject=user.id,
            email=user.email,
            role=user.role.value,
            institution_id=user.institution_id
        )
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=user.role,
                institution_id=user.institution_id,
                registration_number=user.registration_number,
                department=user.department,
                batch_cohort=user.batch_cohort,
                section=user.section,
                contact_number=user.contact_number,
                college_name=user.college_name,
                account_status=user.account_status,
                is_verified=user.is_verified,
                created_at=user.created_at
            )
        )

    # 1. Fetch active verification session
    verif_doc = await verif_col.find_one({
        "email_normalized": clean_email,
        "registration_type": "external_student",
        "is_consumed": False
    })

    if not verif_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 2. Check expiration
    expires_at = verif_doc.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 3. Check attempt limit
    attempts = verif_doc.get("attempt_count", 0)
    max_attempts = verif_doc.get("max_attempts", 3)
    if attempts >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has been invalidated due to too many failed attempts. Please request a new code."
        )

    # 4. Verify candidate OTP hash in constant time
    is_valid_otp = verify_otp_hash(clean_code, verif_doc["salt"], verif_doc["code_hash"])
    if not is_valid_otp:
        await verif_col.update_one(
            {"_id": verif_doc["_id"]},
            {"$inc": {"attempt_count": 1}}
        )
        remaining = max(0, max_attempts - (attempts + 1))
        logger.warning(f"Failed external student OTP attempt for {mask_email(clean_email)}. Remaining: {remaining}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 5. Atomically mark verification as consumed (concurrency-safe)
    consumed_verif = await verif_col.find_one_and_update(
        {
            "_id": verif_doc["_id"],
            "is_consumed": False
        },
        {
            "$set": {
                "is_consumed": True,
                "expires_at": now
            }
        },
        return_document=ReturnDocument.AFTER
    )
    if not consumed_verif:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # 6. Create Student User Record (Role is strictly STUDENT; backend controlled)
    new_user = UserInDB(
        id=str(uuid.uuid4()),
        email=verif_doc["email_normalized"],
        full_name=verif_doc["full_name"],
        role=UserRole.STUDENT,  # Backend enforces student role; privilege escalation blocked
        institution_id=verif_doc["college_name"],
        registration_number=verif_doc["college_reg_no"],
        contact_number=verif_doc.get("contact_number"),
        college_name=verif_doc["college_name"],
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=verif_doc["hashed_password"],
        created_at=now,
        updated_at=now
    )

    try:
        await users_col.insert_one(new_user.model_dump())
    except pymongo.errors.DuplicateKeyError:
        await verif_col.update_one(
            {"_id": verif_doc["_id"]},
            {"$set": {"is_consumed": False}}
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address or registration number already exists."
        )
    except Exception as exc:
        await verif_col.update_one(
            {"_id": verif_doc["_id"]},
            {"$set": {"is_consumed": False}}
        )
        logger.error(f"Failed to create external student account: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation could not be completed."
        )

    logger.info(f"External student account created for {mask_email(clean_email)} from {new_user.institution_id}")

    # 7. Issue JWT token
    access_token = create_access_token(
        subject=new_user.id,
        email=new_user.email,
        role=new_user.role.value,
        institution_id=new_user.institution_id
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=new_user.id,
            email=new_user.email,
            full_name=new_user.full_name,
            role=new_user.role,
            institution_id=new_user.institution_id,
            registration_number=new_user.registration_number,
            department=new_user.department,
            batch_cohort=new_user.batch_cohort,
            section=new_user.section,
            contact_number=new_user.contact_number,
            college_name=new_user.college_name,
            account_status=new_user.account_status,
            is_verified=new_user.is_verified,
            created_at=new_user.created_at
        )
    )
