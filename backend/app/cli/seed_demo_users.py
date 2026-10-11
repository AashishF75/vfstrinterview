import os
import sys
import argparse
import asyncio
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import UserInDB, UserRole, AccountStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_demo_users")

async def seed_demo():
    # 1. Strict guard: Prevent running in production environments
    if settings.ENVIRONMENT.lower() in ("production", "prod"):
        logger.error(
            "Demo account seeding is strictly disabled in production environments. "
            f"Current ENVIRONMENT='{settings.ENVIRONMENT}'."
        )
        sys.exit(1)

    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    db = client[settings.MONGODB_DB_NAME]
    users_col = db["users"]

    # Allow custom passwords via environment variables for credential rotation
    student_pass = os.getenv("DEMO_STUDENT_PASSWORD", "StudentPass2026!")
    faculty_pass = os.getenv("DEMO_FACULTY_PASSWORD", "FacultyPass2026!")

    demo_users = [
        {
            "email": "student@vfstr.ac.in",
            "full_name": "Sita Raman (Student)",
            "role": UserRole.STUDENT,
            "password": student_pass,
            "institution_id": "VFSTR",
        },
        {
            "email": "faculty@vfstr.ac.in",
            "full_name": "Dr. Ramesh Sharma (Faculty)",
            "role": UserRole.FACULTY,
            "password": faculty_pass,
            "institution_id": "VFSTR",
        },
    ]

    for u in demo_users:
        existing = await users_col.find_one({"email": u["email"]})
        if not existing:
            now = datetime.now(timezone.utc)
            user_doc = UserInDB(
                email=u["email"],
                full_name=u["full_name"],
                role=u["role"],
                institution_id=u["institution_id"],
                account_status=AccountStatus.ACTIVE,
                is_verified=True,
                hashed_password=hash_password(u["password"]),
                created_at=now,
                updated_at=now
            )
            await users_col.insert_one(user_doc.model_dump())
            logger.info(f"Created demo account: {u['email']} (role: {u['role'].value})")
        else:
            logger.info(f"Demo account already exists: {u['email']}")

    client.close()

def main():
    parser = argparse.ArgumentParser(
        description="Development-only seed utility for mock user accounts (VFSTR)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation to seed development demo accounts"
    )
    args = parser.parse_args()

    if not args.confirm:
        logger.error(
            "Explicit confirmation required to seed demo accounts. "
            "Run with '--confirm' flag in a development environment."
        )
        sys.exit(1)

    asyncio.run(seed_demo())

if __name__ == "__main__":
    main()
