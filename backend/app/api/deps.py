from typing import List, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_access_token
from app.core.database import get_database
from app.models.user import UserRole, AccountStatus, UserInDB
from motor.motor_asyncio import AsyncIOMotorDatabase

security_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> UserInDB:
    """
    Extracts Bearer token from Authorization header and verifies the user.
    Returns 401 Unauthorized for missing or invalid tokens.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not available"
        )

    user_doc = await db["users"].find_one({"id": user_id})
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account does not exist or has been removed",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert to UserInDB model
    user = UserInDB(**user_doc)
    return user

async def get_current_active_user(
    current_user: UserInDB = Depends(get_current_user)
) -> UserInDB:
    """Verifies that the authenticated user account is active."""
    if current_user.account_status == AccountStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended"
        )
    return current_user

def require_roles(allowed_roles: List[UserRole]) -> Callable:
    """
    Authorization dependency factory checking that the authenticated user
    possesses at least one of the specified roles.
    Returns 403 Forbidden if user lacks sufficient privileges.
    """
    async def role_checker(
        current_user: UserInDB = Depends(get_current_active_user)
    ) -> UserInDB:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource"
            )
        return current_user
    return role_checker
