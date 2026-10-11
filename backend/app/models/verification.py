from datetime import datetime, timezone
import uuid
from typing import Optional
from pydantic import BaseModel, Field, EmailStr

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RegistrationVerificationInDB(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    registration_type: str = "vfstr"  # "vfstr" or "external_student"
    registration_number_normalized: Optional[str] = None
    roster_email_normalized: Optional[EmailStr] = None
    email_normalized: Optional[EmailStr] = None
    full_name: Optional[str] = None
    college_name: Optional[str] = None
    college_reg_no: Optional[str] = None
    contact_number: Optional[str] = None
    hashed_password: Optional[str] = None
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

class VfstrDirectRegisterRequest(BaseModel):
    registration_number: str = Field(..., min_length=3, max_length=50)
    contact_number: str = Field(..., min_length=10, max_length=20)

    def get_normalized_roll(self) -> str:
        return self.registration_number.strip().upper()

    def get_clean_contact(self) -> str:
        import re
        return re.sub(r"[\s\-\(\)]", "", self.contact_number.strip())

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


class GeneralStudentInitiateRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    college_name: str = Field(..., min_length=2, max_length=150)
    college_reg_no: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    contact_number: str = Field(..., min_length=10, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)

    def get_clean_name(self) -> str:
        return self.full_name.strip()

    def get_clean_college(self) -> str:
        return self.college_name.strip()

    def get_clean_reg_no(self) -> str:
        return self.college_reg_no.strip().upper()

    def get_clean_contact(self) -> str:
        return self.contact_number.strip()

    def get_clean_email(self) -> str:
        return str(self.email).strip().lower()


class GeneralStudentResendRequest(BaseModel):
    email: EmailStr

    def get_clean_email(self) -> str:
        return str(self.email).strip().lower()


class GeneralStudentCompleteRequest(BaseModel):
    email: EmailStr
    verification_code: str = Field(..., min_length=6, max_length=10)

    def get_clean_email(self) -> str:
        return str(self.email).strip().lower()

    def get_clean_code(self) -> str:
        return self.verification_code.strip()
