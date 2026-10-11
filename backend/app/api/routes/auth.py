import secrets
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from typing import Optional
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
    ResendVerificationRequest,
    CompleteRegistrationRequest
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
    user_doc = await users_col.find_one({"email": login_data.email})

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

    # If student is not found, not eligible, or already claimed, return generic message (Anti-Enumeration)
    if (
        not elig_doc
        or existing_user
        or elig_doc.get("is_claimed", False)
        or not elig_doc.get("is_eligible_for_registration", False)
        or elig_doc.get("validation_status") != EligibilityStatus.ELIGIBLE.value
    ):
        logger.info(f"Registration initiation completed (generic response) for {masked_roll}")
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
                logger.info(f"Resend throttled for {masked_roll}: {elapsed:.1f}s elapsed < {settings.REGISTRATION_RESEND_COOLDOWN_SECONDS}s")
                return GENERIC_INITIATE_RESPONSE

    # Generate cryptographically secure OTP and salt
    otp_code = generate_secure_otp()
    salt = generate_salt()
    code_hash = hash_otp(otp_code, salt)
    expires_at = now + timedelta(minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES)

    # Store verification record
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

    # Dispatch email to approved roster email (captured in memory during tests)
    await EmailService.send_verification_otp(
        to_email=elig_doc["roster_email"],
        registration_number=roll_norm,
        otp_code=otp_code,
        expires_minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES
    )

    logger.info(f"Verification code successfully generated and dispatched for {masked_roll}")
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

    roll_norm = payload.get_normalized_roll()
    masked_roll = mask_registration_number(roll_norm)
    now = utc_now()

    verif_col = db["registration_verifications"]
    active_verif = await verif_col.find_one({
        "registration_number_normalized": roll_norm,
        "is_consumed": False
    })

    if not active_verif:
        return GENERIC_INITIATE_RESPONSE

    # Check expiration
    exp = active_verif.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and now > exp:
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

    await EmailService.send_verification_otp(
        to_email=active_verif["roster_email_normalized"],
        registration_number=roll_norm,
        otp_code=otp_code,
        expires_minutes=settings.REGISTRATION_OTP_EXPIRE_MINUTES
    )

    logger.info(f"Verification code resent for {masked_roll}")
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
            account_status=new_user.account_status,
            is_verified=new_user.is_verified,
            created_at=new_user.created_at
        )
    )
