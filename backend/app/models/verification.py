from datetime import datetime, timezone
import uuid
from typing import Optional
from pydantic import BaseModel, Field, EmailStr

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RegistrationVerificationInDB(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    registration_number_normalized: str
    roster_email_normalized: EmailStr
    code_hash: str
    salt: str
    attempt_count: int = 0
    max_attempts: int = 3
    is_consumed: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    last_resend_at: datetime = Field(default_factory=utc_now)
    client_ip_hash: str

class InitiateRegistrationRequest(BaseModel):
    registration_number: str

    def get_normalized_roll(self) -> str:
        return self.registration_number.strip().upper()

class ResendVerificationRequest(BaseModel):
    registration_number: str

    def get_normalized_roll(self) -> str:
        return self.registration_number.strip().upper()

class CompleteRegistrationRequest(BaseModel):
    registration_number: str
    verification_code: str
    password: str = Field(..., min_length=8, max_length=128)

    def get_normalized_roll(self) -> str:
        return self.registration_number.strip().upper()

    def get_clean_code(self) -> str:
        return self.verification_code.strip()
