import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple

from app.core.config import settings

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def generate_secure_otp() -> str:
    """Generates a cryptographically secure 6-digit numeric verification code."""
    return f"{secrets.randbelow(900000) + 100000}"

def generate_salt() -> str:
    """Generates a cryptographic 32-character hex salt."""
    return secrets.token_hex(16)

def hash_otp(code: str, salt: str) -> str:
    """
    Computes HMAC-SHA256 digest of salt and OTP using server-side JWT_SECRET_KEY as secret key.
    Prevents rainbow table and offline dictionary attacks on low-entropy 6-digit codes.
    """
    key = settings.JWT_SECRET_KEY.encode("utf-8")
    message = f"{salt}:{code.strip()}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()

def verify_otp_hash(candidate_code: str, salt: str, expected_hash: str) -> bool:
    """Constant-time verification of candidate OTP code."""
    candidate_hash = hash_otp(candidate_code, salt)
    return secrets.compare_digest(candidate_hash, expected_hash)

def hash_client_ip(client_ip: str) -> str:
    """Produces a privacy-preserving 16-character hash of requester IP for abuse tracking."""
    if not client_ip:
        return "unknown"
    return hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]

def mask_registration_number(roll: str) -> str:
    """Masks middle characters of roll number for audit logs (e.g. 241FA***01)."""
    if not roll or len(roll) < 6:
        return "***"
    return f"{roll[:5]}***{roll[-2:]}"
