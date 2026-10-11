import asyncio
import argparse
import getpass
import sys
import logging
from typing import Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import pymongo.errors

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import UserInDB, UserRole, AccountStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("bootstrap_admin")

async def provision_admin(
    email: str,
    password: str,
    full_name: str = "VFSTR Platform Admin",
    force: bool = False,
    db: Optional[AsyncIOMotorDatabase] = None,
) -> bool:
    """Provisions the initial platform administrator securely into MongoDB."""
    email = email.strip().lower()
    if len(password) < 8:
        logger.error("Password must be at least 8 characters long.")
        return False

    client = None
    if db is None:
        client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        target_db = client[settings.MONGODB_DB_NAME]
    else:
        target_db = db

    users_col = target_db["users"]

    # Audit existing indexes to ensure role is never unique
    existing_indexes = await users_col.index_information()
    for idx_name, idx_info in list(existing_indexes.items()):
        if idx_name != "_id_" and idx_info.get("key") in ([("role", 1)], [("role", pymongo.ASCENDING)]):
            if idx_info.get("unique", False):
                logger.warning(f"Dropping erroneous unique index '{idx_name}' on role field.")
                await users_col.drop_index(idx_name)

    # Ensure unique index on email and non-unique index on role
    await users_col.create_index([("email", 1)], unique=True, name="email_1")
    await users_col.create_index([("role", 1)], unique=False, name="role_1")

    # Check if a platform admin already exists
    existing_admin = await users_col.find_one({"role": UserRole.PLATFORM_ADMIN.value})
    if existing_admin and not force:
        logger.warning(
            f"A platform administrator already exists ({existing_admin.get('email')}). "
            "Bootstrap aborted to prevent duplicate privilege escalation. Use --force to override."
        )
        if client:
            client.close()
        return False

    # Check if this email is already registered
    existing_email = await users_col.find_one({"email": email})
    if existing_email:
        if force:
            logger.info(f"Updating existing user '{email}' to platform_admin role.")
            await users_col.update_one(
                {"email": email},
                {
                    "$set": {
                        "role": UserRole.PLATFORM_ADMIN.value,
                        "hashed_password": hash_password(password),
                        "account_status": AccountStatus.ACTIVE.value,
                        "is_verified": True,
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            logger.info("Admin updated successfully.")
            if client:
                client.close()
            return True
        else:
            logger.error(f"User with email '{email}' already exists.")
            if client:
                client.close()
            return False

    now = datetime.now(timezone.utc)
    new_admin = UserInDB(
        email=email,
        full_name=full_name,
        role=UserRole.PLATFORM_ADMIN,
        institution_id="VFSTR",
        account_status=AccountStatus.ACTIVE,
        is_verified=True,
        hashed_password=hash_password(password),
        created_at=now,
        updated_at=now
    )

    try:
        await users_col.insert_one(new_admin.model_dump())
        logger.info(f"Platform administrator '{email}' successfully provisioned for VFSTR.")
        if client:
            client.close()
        return True
    except pymongo.errors.DuplicateKeyError:
        logger.error(f"Account with email '{email}' already exists.")
        if client:
            client.close()
        return False
    except Exception as e:
        logger.error(f"Failed to provision administrator: {e}")
        if client:
            client.close()
        return False

def main():
    parser = argparse.ArgumentParser(description="Bootstrap initial VFSTR Platform Administrator")
    parser.add_argument("--email", help="Admin email address", default=settings.BOOTSTRAP_ADMIN_EMAIL)
    parser.add_argument("--password", help="Admin password (will prompt securely if not passed)")
    parser.add_argument("--name", help="Full name", default="VFSTR Platform Administrator")
    parser.add_argument("--force", action="store_true", help="Force provision even if an admin exists")

    args = parser.parse_args()

    email = args.email or settings.BOOTSTRAP_ADMIN_EMAIL
    if not email:
        email = input("Enter admin email: ").strip()

    password = args.password or settings.BOOTSTRAP_ADMIN_PASSWORD
    if args.password:
        logger.warning(
            "Supplying password via command line argument may expose it in system process listings. "
            "Using interactive prompt (getpass) or secure environment variable is strongly recommended."
        )
    if not password:
        password = getpass.getpass("Enter secure admin password (min 8 characters): ")

    success = asyncio.run(provision_admin(email=email, password=password, full_name=args.name, force=args.force))
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
