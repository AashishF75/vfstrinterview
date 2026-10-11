import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
import threading
from fastapi import HTTPException, status
from app.core.config import settings

def hash_password(plain_password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(
    subject: str,
    email: str,
    role: str,
    institution_id: str = "VFSTR",
    expires_delta: Optional[timedelta] = None
) -> str:
    """Creates a signed JWT with strict issuer, audience, and expiry claims."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": subject,
        "email": email,
        "role": role,
        "institution_id": institution_id,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """
    Decodes and validates JWT token signature, expiry, algorithm, issuer and audience.
    Raises HTTPException(401) on invalid or expired token.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

class LoginRateLimiter:
    """
    In-memory thread-safe rate limiter tracking failed login attempts per client key (IP or email).
    Protects against credential stuffing and brute force attacks.
    """
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._failures: Dict[str, List[datetime]] = {}

    def _cleanup_old(self, key: str, now: datetime):
        cutoff = now - timedelta(seconds=self.window_seconds)
        if key in self._failures:
            self._failures[key] = [t for t in self._failures[key] if t > cutoff]
            if not self._failures[key]:
                del self._failures[key]

    def is_rate_limited(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._cleanup_old(key, now)
            attempts = len(self._failures.get(key, []))
            return attempts >= self.max_attempts

    def record_failure(self, key: str):
        now = datetime.now(timezone.utc)
        with self._lock:
            self._cleanup_old(key, now)
            if key not in self._failures:
                self._failures[key] = []
            self._failures[key].append(now)

    def reset(self, key: str):
        with self._lock:
            if key in self._failures:
                del self._failures[key]

login_limiter = LoginRateLimiter(
    max_attempts=settings.RATE_LIMIT_LOGIN_MAX_ATTEMPTS,
    window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS
)
