import os
import re
import sys
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pymongo
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

from app.core.config import settings
from app.services.networking_pdf_parser import (
    NetworkingAssessmentParser,
    NetworkingAssessmentRecord,
    utc_now,
)

logger = logging.getLogger(__name__)


class TargetDatabaseSafetyError(Exception):
    """Raised when safety checks fail for MongoDB Atlas target or database name."""
    pass


class InterviewEligibilityImportError(Exception):
    """Base exception for interview eligibility import operations."""
    pass


class InterviewEligibilityImporter:
    """
    Service to import student records from Networking Essentials Assessment PDF
    into MongoDB Atlas under database 'interview_db' and collection 'interview_eligibility_registry'.
    Guarantees isolation, preflight validation, idempotency, and score/grade exclusion.
    """

    TARGET_DB_NAME = "interview_db"
    COLLECTION_NAME = "interview_eligibility_registry"

    INDEX_DEFINITIONS = [
        {
            "keys": [("s_no", pymongo.ASCENDING), ("source_file", pymongo.ASCENDING)],
            "options": {"unique": True, "name": "unique_s_no_source_file"},
        },
        {
            "keys": [("registration_number", pymongo.ASCENDING)],
            "options": {
                "unique": True,
                "name": "unique_valid_registration_number",
                "partialFilterExpression": {
                    "registration_number": {"$gt": "0"}
                },
            },
        },
        {
            "keys": [("email", pymongo.ASCENDING)],
            "options": {"unique": True, "name": "unique_email"},
        },
        {
            "keys": [("section", pymongo.ASCENDING)],
            "options": {"unique": False, "name": "idx_section"},
        },
        {
            "keys": [("review_status", pymongo.ASCENDING)],
            "options": {"unique": False, "name": "idx_review_status"},
        },
        {
            "keys": [("interview_eligible", pymongo.ASCENDING)],
            "options": {"unique": False, "name": "idx_interview_eligible"},
        },
        {
            "keys": [("interview_assignment_status", pymongo.ASCENDING)],
            "options": {"unique": False, "name": "idx_interview_assignment_status"},
        },
        {
            "keys": [("import_batch_id", pymongo.ASCENDING)],
            "options": {"unique": False, "name": "idx_import_batch_id"},
        },
    ]

    def __init__(self, mongo_uri: Optional[str] = None, target_db_name: Optional[str] = None):
        self.mongo_uri = mongo_uri if mongo_uri is not None else settings.MONGODB_URI
        self.target_db_name = target_db_name or self.TARGET_DB_NAME
        self._client: Optional[MongoClient] = None

    def _mask_uri_for_diagnostics(self) -> str:
        """Returns masked URI showing only scheme and target host without credentials."""
        if not self.mongo_uri:
            return "[EMPTY URI]"
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", self.mongo_uri)

    def verify_target_safety(self) -> Dict[str, Any]:
        """
        Validates target connection before ANY operation:
        1. Target database MUST be 'interview_db'.
        2. URI must be configured and not localhost/127.0.0.1.
        3. Connection must be confirmed against remote MongoDB Atlas cluster.
        """
        # Rule 1: Database name validation
        if self.target_db_name != self.TARGET_DB_NAME:
            raise TargetDatabaseSafetyError(
                f"SAFETY ABORT: Target database must strictly be '{self.TARGET_DB_NAME}', "
                f"received '{self.target_db_name}'. Prevents accidental collision."
            )

        # Rule 2: URI configuration validation
        if not self.mongo_uri or self.mongo_uri == "mongodb://localhost:27017":
            raise TargetDatabaseSafetyError(
                "SAFETY ABORT: MONGODB_URI is unconfigured or defaulting to localhost:27017. "
                "Must be configured to point to MongoDB Atlas in backend/.env."
            )

        uri_lower = self.mongo_uri.lower().strip()
        if "localhost" in uri_lower or "127.0.0.1" in uri_lower or uri_lower.startswith("mongodb://127."):
            raise TargetDatabaseSafetyError(
                "SAFETY ABORT: Connection targets local MongoDB (localhost). "
                "The requested target is remote MongoDB Atlas. Aborting immediately."
            )

        # Rule 3: Remote connectivity probe
        try:
            client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            hello_info = client.admin.command("hello")
            hosts = hello_info.get("hosts", [])
            me = hello_info.get("me", "")
            set_name = hello_info.get("setName", "")
            is_atlas = (
                any(".mongodb.net" in h for h in hosts)
                or ".mongodb.net" in me
                or "atlas" in set_name.lower()
                or uri_lower.startswith("mongodb+srv://")
            )

            if not is_atlas and ("localhost" in me or "127.0.0.1" in me):
                client.close()
                raise TargetDatabaseSafetyError(
                    "SAFETY ABORT: Cluster hello probe resolved to local instance. "
                    "Must be remote MongoDB Atlas."
                )

            diagnostics = {
                "database_name": self.target_db_name,
                "is_atlas": is_atlas,
                "cluster_set_name": set_name or "standalone/direct",
                "cluster_nodes_count": len(hosts),
                "is_safe_to_proceed": True,
            }
            client.close()
            return diagnostics
        except Exception as e:
            if isinstance(e, TargetDatabaseSafetyError):
                raise
            raise TargetDatabaseSafetyError(
                f"SAFETY ABORT: Failed to probe remote database connectivity: {type(e).__name__}: {str(e)}"
            )

    def get_client(self) -> MongoClient:
        if self._client is None:
            self._client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def ensure_indexes(self) -> List[str]:
        """
        Creates all required unique and lookup indexes on interview_eligibility_registry.
        Returns list of created index names.
        """
        client = self.get_client()
        db = client[self.target_db_name]
        col = db[self.COLLECTION_NAME]

        created_indexes = []
        for index_def in self.INDEX_DEFINITIONS:
            idx_name = col.create_index(index_def["keys"], **index_def["options"])
            created_indexes.append(idx_name)

        return created_indexes

    def preflight_check(
        self, records: List[NetworkingAssessmentRecord]
    ) -> Dict[str, Any]:
        """
        Performs in-depth preflight analysis on extracted records:
        - Checks for internal duplicate registration numbers.
        - Checks for internal duplicate emails.
        - Audits email validity.
        - Checks conflicts against any existing records in interview_db.interview_eligibility_registry.
        """
        total_rows = len(records)
        reg_counter: Dict[str, List[int]] = {}
        email_counter: Dict[str, List[int]] = {}

        for r in records:
            if r.registration_number != "#N/A":
                reg_counter.setdefault(r.registration_number, []).append(r.s_no)
            email_counter.setdefault(r.email, []).append(r.s_no)

        dup_regs = {k: v for k, v in reg_counter.items() if len(v) > 1}
        dup_emails = {k: v for k, v in email_counter.items() if len(v) > 1}

        # Check existing records in target collection
        client = self.get_client()
        db = client[self.target_db_name]
        col = db[self.COLLECTION_NAME]

        existing_count = col.count_documents({})
        conflicting_records: List[Dict[str, Any]] = []

        if existing_count > 0:
            # Check if any incoming registration number exists with a different email
            valid_regs = [r.registration_number for r in records if r.registration_number != "#N/A"]
            cursor = col.find({"registration_number": {"$in": valid_regs}}, {"registration_number": 1, "email": 1, "s_no": 1})
            existing_map = {doc["registration_number"]: doc for doc in cursor}

            for r in records:
                if r.registration_number in existing_map:
                    ex = existing_map[r.registration_number]
                    if ex.get("email") != r.email:
                        conflicting_records.append({
                            "s_no": r.s_no,
                            "registration_number": r.registration_number,
                            "incoming_email": r.email,
                            "existing_email": ex.get("email"),
                        })

        approved_count = sum(1 for r in records if r.review_status == "approved")
        needs_review_count = sum(1 for r in records if r.review_status == "needs_review")
        interview_eligible_count = sum(1 for r in records if r.interview_eligible)

        return {
            "total_extracted": total_rows,
            "unique_valid_registration_numbers": len(reg_counter),
            "duplicate_registration_numbers_count": len(dup_regs),
            "duplicate_registration_numbers": dup_regs,
            "duplicate_emails_count": len(dup_emails),
            "duplicate_emails": dup_emails,
            "approved_count": approved_count,
            "needs_review_count": needs_review_count,
            "interview_eligible_count": interview_eligible_count,
            "existing_collection_count": existing_count,
            "conflicting_records_count": len(conflicting_records),
            "conflicting_records": conflicting_records,
            "is_preflight_valid": len(dup_regs) == 0 and len(dup_emails) == 0 and len(conflicting_records) == 0,
        }

    def execute_import(
        self,
        records: List[NetworkingAssessmentRecord],
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes idempotent bulk import into interview_db.interview_eligibility_registry.
        Preconditions:
        - Safety verification passed.
        - Preflight check passed.
        - Indexes ensured.
        """
        # 1. Safety check
        self.verify_target_safety()

        # 2. Preflight validation
        preflight = self.preflight_check(records)
        if not preflight["is_preflight_valid"]:
            errors = []
            if preflight["duplicate_registration_numbers_count"] > 0:
                errors.append(f"Found {preflight['duplicate_registration_numbers_count']} duplicate registration numbers.")
            if preflight["duplicate_emails_count"] > 0:
                errors.append(f"Found {preflight['duplicate_emails_count']} duplicate emails.")
            if preflight["conflicting_records_count"] > 0:
                errors.append(f"Found {preflight['conflicting_records_count']} conflicting existing records.")
            raise InterviewEligibilityImportError("; ".join(errors))

        # 3. Ensure indexes
        created_indexes = self.ensure_indexes()

        # 4. Prepare batch ID
        import_batch_id = batch_id or str(uuid.uuid4())

        client = self.get_client()
        db = client[self.target_db_name]
        col = db[self.COLLECTION_NAME]

        count_before = col.count_documents({})

        # 5. Build bulk operations (Idempotent update with $setOnInsert)
        # Using compound identity: (s_no, source_file)
        operations = []
        for r in records:
            doc = r.to_mongo_doc(import_batch_id=import_batch_id)
            # Ensure NO scores or grades exist in the document
            assert "final_exam_score" not in doc
            assert "class_grade" not in doc
            assert "score" not in doc

            filter_query = {"s_no": r.s_no, "source_file": r.source_file}
            operations.append(
                UpdateOne(
                    filter=filter_query,
                    update={"$setOnInsert": doc},
                    upsert=True,
                )
            )

        # 6. Execute bulk write
        try:
            result = col.bulk_write(operations, ordered=False)
            inserted_count = result.upserted_count
            matched_count = result.matched_count
        except BulkWriteError as bwe:
            raise InterviewEligibilityImportError(
                f"Bulk write error during import batch {import_batch_id}: {bwe.details}"
            )

        count_after = col.count_documents({})

        # 7. Verification read-back
        batch_docs_count = col.count_documents({"import_batch_id": import_batch_id})
        approved_in_db = col.count_documents({"review_status": "approved"})
        needs_review_in_db = col.count_documents({"review_status": "needs_review"})
        eligible_in_db = col.count_documents({"interview_eligible": True})
        unassigned_in_db = col.count_documents({"interview_assignment_status": "unassigned"})

        return {
            "import_batch_id": import_batch_id,
            "target_database": self.target_db_name,
            "target_collection": self.COLLECTION_NAME,
            "count_before": count_before,
            "count_after": count_after,
            "upserted_count": inserted_count,
            "matched_existing_count": matched_count,
            "batch_documents_count": batch_docs_count,
            "approved_in_db": approved_in_db,
            "needs_review_in_db": needs_review_in_db,
            "interview_eligible_in_db": eligible_in_db,
            "interview_assignment_status_unassigned_in_db": unassigned_in_db,
            "created_indexes": created_indexes,
        }

    def sample_records_sanitized(self, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Reads back sample records from interview_eligibility_registry with PII masked,
        safe for reporting and auditing.
        """
        client = self.get_client()
        db = client[self.target_db_name]
        col = db[self.COLLECTION_NAME]

        samples = []
        for doc in col.find({}, {"_id": 0}).limit(limit):
            # Mask PII
            email = doc.get("email", "")
            reg_no = doc.get("registration_number", "")
            masked_email = email[:3] + "***@" + email.split("@")[-1] if "@" in email else "***"
            masked_reg = reg_no[:5] + "***" if len(reg_no) > 5 else reg_no

            sanitized = {
                "s_no": doc.get("s_no"),
                "registration_number_masked": masked_reg,
                "email_masked": masked_email,
                "section": doc.get("section"),
                "source_file": doc.get("source_file"),
                "source_page": doc.get("source_page"),
                "source_row": doc.get("source_row"),
                "email_status": doc.get("email_status"),
                "review_status": doc.get("review_status"),
                "interview_eligible": doc.get("interview_eligible"),
                "interview_assignment_status": doc.get("interview_assignment_status"),
                "import_batch_id": doc.get("import_batch_id"),
                "batch_cohort": doc.get("batch_cohort"),
                "review_reasons": doc.get("review_reasons"),
                "has_score_or_grade_fields": any(k in doc for k in ["score", "grade", "final_exam_score", "class_grade"]),
            }
            samples.append(sanitized)
        return samples
