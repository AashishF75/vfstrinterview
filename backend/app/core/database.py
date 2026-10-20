import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None

db_manager = DatabaseManager()

def _mask_mongo_uri(uri: str) -> str:
    """Masks password credentials in MongoDB connection URI for safe logging."""
    import re
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", uri)

async def connect_to_mongo():
    """Initializes MongoDB connection pool and verifies target connectivity."""
    try:
        logger.info(
            f"Connecting to database '{settings.MONGODB_DB_NAME}' "
            f"[{settings.target_database_type}] (Config: {settings.CONFIG_FILE_PATH})"
        )
        db_manager.client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=3000
        )
        db_manager.db = db_manager.client[settings.MONGODB_DB_NAME]
        
        # Verify connectivity and resolve actual cluster target safely
        hello_info = await db_manager.client.admin.command('hello')
        hosts = hello_info.get("hosts", [])
        me = hello_info.get("me", "")
        set_name = hello_info.get("setName", "")
        is_atlas = any(".mongodb.net" in h for h in hosts) or ".mongodb.net" in me or "atlas" in set_name.lower()
        target_name = "MongoDB Atlas (Remote Cluster)" if is_atlas else "Non-Atlas MongoDB"
        logger.info(f"MongoDB connection established: target is {target_name}, database '{settings.MONGODB_DB_NAME}' ({len(hosts)} cluster nodes).")
    except Exception as e:
        logger.warning(f"Could not initialize MongoDB client: {type(e).__name__} - {e}")

async def close_mongo_connection():
    """Closes MongoDB connection pool."""
    if db_manager.client:
        logger.info("Closing MongoDB connection pool.")
        db_manager.client.close()
        db_manager.client = None
        db_manager.db = None

import pymongo

async def ensure_indexes(db: Optional[AsyncIOMotorDatabase] = None):
    """
    Safely verifies and ensures MongoDB indexes for the 'users' collection:
    - 'email' must have a unique index (primary account identity constraint).
    - 'role' must NOT be unique (multiple users share student, faculty, admin roles).
    - If a unique index exists on 'role' alone, drops it safely without touching unrelated
      indexes or deleting any user records, and replaces it with a non-unique index.
    """
    target_db = db if db is not None else db_manager.db
    if target_db is None:
        return

    try:
        users_col = target_db["users"]
        existing_indexes = await users_col.index_information()

        # Audit existing indexes on 'role'
        for index_name, index_info in list(existing_indexes.items()):
            if index_name == "_id_":
                continue
            key = index_info.get("key")
            # Check if this index is on the role field alone
            if key in ([("role", 1)], [("role", pymongo.ASCENDING)]):
                if index_info.get("unique", False):
                    logger.warning(
                        f"Erroneous unique index detected on role field: '{index_name}'. "
                        "Safely dropping index to allow multiple users per role."
                    )
                    await users_col.drop_index(index_name)
                    logger.info(f"Successfully dropped erroneous unique index '{index_name}'.")

        # Ensure unique index on email
        await users_col.create_index([("email", pymongo.ASCENDING)], unique=True, name="email_1")

        # Ensure non-unique index on role for efficient querying
        await users_col.create_index([("role", pymongo.ASCENDING)], unique=False, name="role_1")

        # Ensure unique index on institution_id and registration_number only for records with a string roll
        await users_col.create_index(
            [("institution_id", pymongo.ASCENDING), ("registration_number", pymongo.ASCENDING)],
            unique=True,
            partialFilterExpression={"registration_number": {"$type": "string"}},
            name="unique_institution_registration_number"
        )

        # Ensure TTL index and lookup index on registration_verifications
        verifications_col = target_db["registration_verifications"]
        await verifications_col.create_index(
            [("expires_at", pymongo.ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_expires_at"
        )
        await verifications_col.create_index(
            [("registration_number_normalized", pymongo.ASCENDING)],
            unique=False,
            name="idx_reg_num"
        )

        logger.info("Database indexes successfully verified and ensured for users and verification collections.")
    except Exception as e:
        logger.warning(f"Could not ensure database indexes: {e}")

async def check_db_health() -> dict:
    """Checks MongoDB connectivity status and safely verifies targets without exposing secrets."""
    if not db_manager.client:
        return {"status": "not_configured", "details": "MongoDB client is not initialized"}
    try:
        hello_info = await db_manager.client.admin.command('hello')
        hosts = hello_info.get("hosts", [])
        me = hello_info.get("me", "")
        set_name = hello_info.get("setName", "")
        is_atlas = any(".mongodb.net" in h for h in hosts) or ".mongodb.net" in me or "atlas" in set_name.lower()
        target_name = "MongoDB Atlas" if is_atlas else ("Local MongoDB" if ("localhost" in me or "127.0.0.1" in me) else "Remote MongoDB")
        return {
            "status": "connected",
            "database": settings.MONGODB_DB_NAME,
            "interview_database": settings.INTERVIEW_DB_NAME,
            "target": target_name,
            "is_atlas": is_atlas,
            "cluster_nodes": len(hosts) if hosts else 1
        }
    except Exception as e:
        return {"status": "disconnected", "error": type(e).__name__}

def get_auth_database() -> Optional[AsyncIOMotorDatabase]:
    """Dependency injection helper returning the auth & accounts database (configured via settings.MONGODB_DB_NAME)."""
    if db_manager.client is None:
        return None
    return db_manager.client[settings.MONGODB_DB_NAME]

def get_interview_database() -> Optional[AsyncIOMotorDatabase]:
    """Dependency injection helper returning the configured interview & assignment database (configured via settings.INTERVIEW_DB_NAME)."""
    if db_manager.client is None:
        return None
    return db_manager.client[settings.INTERVIEW_DB_NAME]

def get_database() -> Optional[AsyncIOMotorDatabase]:
    """Backward-compatible default dependency helper pointing to the auth database."""
    return get_auth_database()

async def ensure_interview_indexes(db: Optional[AsyncIOMotorDatabase] = None):
    """
    Ensures required indexes on interview_db collections:
    - university_interviews:
        - unique index on interview_id
        - composite index on status + scheduled_start_time
    - student_interview_assignments:
        - unique compound index on (interview_id, student_registration_number)
        - unique index on assignment_id
        - index on student_registration_number
        - index on status
    """
    target_db = db if db is not None else get_interview_database()
    if target_db is None:
        return

    try:
        # university_interviews indexes
        interviews_col = target_db["university_interviews"]
        await interviews_col.create_index(
            [("interview_id", pymongo.ASCENDING)],
            unique=True,
            name="unique_interview_id"
        )
        await interviews_col.create_index(
            [("status", pymongo.ASCENDING), ("scheduled_start_time", pymongo.ASCENDING)],
            name="idx_status_scheduled_start"
        )

        # student_interview_assignments indexes
        assignments_col = target_db["student_interview_assignments"]
        await assignments_col.create_index(
            [("interview_id", pymongo.ASCENDING), ("student_registration_number", pymongo.ASCENDING)],
            unique=True,
            name="unique_interview_student_assignment"
        )
        await assignments_col.create_index(
            [("assignment_id", pymongo.ASCENDING)],
            unique=True,
            name="unique_assignment_id"
        )
        await assignments_col.create_index(
            [("student_registration_number", pymongo.ASCENDING)],
            name="idx_student_reg_no"
        )
        # interview_sessions indexes
        sessions_col = target_db["interview_sessions"]
        await sessions_col.create_index(
            [("session_id", pymongo.ASCENDING)],
            unique=True,
            name="unique_session_id"
        )
        await sessions_col.create_index(
            [("assignment_id", pymongo.ASCENDING)],
            unique=True,
            partialFilterExpression={"session_status": "in_progress"},
            name="unique_active_assignment_session"
        )
        await sessions_col.create_index(
            [("student_registration_number", pymongo.ASCENDING)],
            name="idx_session_student_reg"
        )

        # interview_responses indexes
        responses_col = target_db["interview_responses"]
        await responses_col.create_index(
            [("response_id", pymongo.ASCENDING)],
            unique=True,
            name="unique_response_id"
        )
        await responses_col.create_index(
            [("session_id", pymongo.ASCENDING), ("question_index", pymongo.ASCENDING)],
            unique=True,
            name="unique_session_question_index"
        )

        # interview_scorecards indexes
        scorecards_col = target_db["interview_scorecards"]
        await scorecards_col.create_index(
            [("scorecard_id", pymongo.ASCENDING)],
            unique=True,
            name="unique_scorecard_id"
        )
        await scorecards_col.create_index(
            [("session_id", pymongo.ASCENDING)],
            unique=True,
            name="unique_session_scorecard"
        )
        await scorecards_col.create_index(
            [("student_registration_number", pymongo.ASCENDING)],
            name="idx_scorecard_student_reg"
        )
        await scorecards_col.create_index(
            [("student_registration_number", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
            name="idx_scorecard_student_created"
        )

        # student_profiles indexes
        profiles_col = target_db["student_profiles"]
        try:
            profile_indexes = await profiles_col.index_information()
        except Exception:
            profile_indexes = {}

        existing_reg_idx = profile_indexes.get("unique_student_profile_reg")
        if existing_reg_idx:
            partial_expr = existing_reg_idx.get("partialFilterExpression")
            if partial_expr != {"registration_number": {"$type": "string"}}:
                logger.warning(
                    "Index 'unique_student_profile_reg' already exists with differing options (%s). "
                    "Skipping automatic index update to avoid index conflict or downtime. "
                    "Manual migration required in production if non-partial index is present.",
                    partial_expr,
                )
            else:
                logger.info("Index 'unique_student_profile_reg' verified with partialFilterExpression.")
        else:
            await profiles_col.create_index(
                [("registration_number", pymongo.ASCENDING)],
                unique=True,
                partialFilterExpression={"registration_number": {"$type": "string"}},
                name="unique_student_profile_reg",
            )
        # proctoring_events indexes
        proctoring_col = target_db["proctoring_events"]
        await proctoring_col.create_index(
            [("session_id", pymongo.ASCENDING), ("server_timestamp", pymongo.ASCENDING)],
            name="idx_session_timestamp",
        )
        await proctoring_col.create_index(
            [("assignment_id", pymongo.ASCENDING)],
            name="idx_assignment_proctoring",
        )
        await proctoring_col.create_index(
            [("student_registration_number", pymongo.ASCENDING)],
            name="idx_student_reg_proctoring",
        )
        await proctoring_col.create_index(
            [("server_timestamp", pymongo.ASCENDING)],
            expireAfterSeconds=7776000,  # 90-day privacy retention policy
            name="ttl_proctoring_retention",
        )

        logger.info("Successfully ensured indexes for interview_db collections.")
    except Exception as e:
        logger.warning(f"Could not ensure interview_db indexes: {e}")


