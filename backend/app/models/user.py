from enum import Enum
from typing import Optional
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

class UserRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    UNIVERSITY_ADMIN = "university_admin"
    DEPARTMENT_ADMIN = "department_admin"
    FACULTY = "faculty"
    STUDENT = "student"

class AccountStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.STUDENT
    institution_id: str = "VFSTR"
    registration_number: Optional[str] = None
    department: Optional[str] = None
    batch_cohort: Optional[str] = None
    section: Optional[str] = None
    contact_number: Optional[str] = None
    college_name: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("registration_number", mode="before")
    @classmethod
    def normalize_reg_num(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
        return None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

class UserInDB(UserBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hashed_password: str
    account_status: AccountStatus = AccountStatus.ACTIVE
    is_verified: bool = False
    eligibility_registry_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    institution_id: str
    registration_number: Optional[str] = None
    department: Optional[str] = None
    batch_cohort: Optional[str] = None
    section: Optional[str] = None
    contact_number: Optional[str] = None
    college_name: Optional[str] = None
    account_status: AccountStatus
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class TokenData(BaseModel):
    sub: str  # user id
    email: str
    role: UserRole
    institution_id: str
