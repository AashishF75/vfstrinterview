import uuid
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
from datetime import datetime, timezone

from app.models.eligibility import (
    ApprovalDecision,
    ApprovalMetadata,
    EligibilityRecordInDB,
    EligibilityStatus,
    EmailSource,
    RawAuditSource,
    ReviewGroup,
    utc_now,
)
from app.services.admin_review_manager import AdminReviewManager


class EligibilityImportError(Exception):
    """Base exception for eligibility import operations."""
    pass


class EligibilityPreflightFailedError(EligibilityImportError):
    """Raised when preflight checks fail, aborting the import before any database write."""
    def __init__(self, errors: List[str]):
        super().__init__(f"Import aborted: preflight validation failed with {len(errors)} error(s).")
        self.errors = errors


class EligibilityIndexCreationError(EligibilityImportError):
    """Raised when unique or lookup index creation fails, halting before roster record writes."""
    pass


class EligibilityBulkWriteFailedError(EligibilityImportError):
    """Raised when bulk_write encounters write errors, reporting partial progress accurately."""
    def __init__(
        self,
        batch_id: str,
        inserted_count: int,
        matched_count: int,
        failed_count: int,
        write_errors: List[Dict[str, Any]],
    ):
        super().__init__(
            f"Bulk write failed for batch '{batch_id}'. Inserted: {inserted_count}, "
            f"Matched: {matched_count}, Failed: {failed_count}."
        )
        self.batch_id = batch_id
        self.inserted_count = inserted_count
        self.matched_count = matched_count
        self.failed_count = failed_count
        self.write_errors = write_errors


class EligibilityImporter:
    """Safe, idempotent, resumable eligibility roster importer with preflight validation and rollback."""

    COLLECTION_NAME = "eligibility_registry"

    INDEX_DEFINITIONS = [
        {
            "keys": [("institution_id", 1), ("registration_number", 1)],
            "options": {"unique": True, "name": "unique_institution_registration_number"},
        },
        {
            "keys": [("institution_id", 1), ("roster_email", 1)],
            "options": {"unique": True, "name": "unique_institution_roster_email"},
        },
        {
            "keys": [("institution_id", 1), ("batch_cohort", 1), ("department", 1), ("section", 1)],
            "options": {"unique": False, "name": "lookup_institution_cohort_dept_sec"},
        },
        {
            "keys": [("is_claimed", 1)],
            "options": {"unique": False, "name": "lookup_is_claimed"},
        },
        {
            "keys": [("is_eligible_for_registration", 1)],
            "options": {"unique": False, "name": "lookup_is_eligible_for_registration"},
        },
    ]

    @classmethod
    def partition_records_by_review_status(
        cls,
        preview_records: List[Dict[str, Any]],
        flagged_resolution_records: Optional[List[Dict[str, Any]]] = None,
        review_manager: Optional[AdminReviewManager] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Partitions records into:
        - READY_FOR_IMPORT: passes all validations cleanly.
        - PROPOSED_UNAMBIGUOUS: records with unambiguous proposed corrections awaiting decision.
        - MANUAL_REVIEW: records requiring administrator decision.
        - APPROVED_ADDITIONS: records from flagged categories that received valid admin approval.
        """
        flagged_map = {}
        if flagged_resolution_records:
            flagged_map = {r["s_no"]: r for r in flagged_resolution_records}

        approved_map = {}
        if review_manager:
            for item in review_manager.get_approved_records():
                approved_map[item["s_no"]] = item

        ready_for_import = []
        proposed_unambiguous = []
        manual_review = []
        approved_additions = []

        for r in preview_records:
            sno = r["s_no"]

            # If this row was approved by administrator
            if sno in approved_map:
                approved_item = approved_map[sno]
                rec_copy = dict(r)
                rec_copy["processed_email"] = approved_item["effective_value"]
                rec_copy["email_source"] = EmailSource.ADMIN_RESOLVED.value
                rec_copy["approval_metadata"] = {
                    "reviewed_by_admin_id": approved_item["reviewed_by_admin_id"],
                    "decision": ApprovalDecision.APPROVED.value,
                    "reason": approved_item["reason"],
                    "timestamp": approved_item["timestamp"],
                    "source_roster_value": approved_item["source_roster_value"],
                    "proposed_value": approved_item["proposed_value"],
                    "effective_value": approved_item["effective_value"],
                }
                approved_additions.append(rec_copy)
            elif sno in flagged_map:
                rev = flagged_map[sno]
                if rev.get("resolution_status") == "PROPOSED_UNAMBIGUOUS":
                    proposed_unambiguous.append(r)
                else:
                    manual_review.append(r)
            elif r.get("validation_status") == "FLAGGED_FOR_REVIEW":
                manual_review.append(r)
            else:
                ready_for_import.append(r)

        return {
            ReviewGroup.READY_FOR_IMPORT.value: ready_for_import,
            ReviewGroup.PROPOSED_UNAMBIGUOUS.value: proposed_unambiguous,
            ReviewGroup.MANUAL_REVIEW.value: manual_review,
            "APPROVED_ADDITIONS": approved_additions,
        }

    @classmethod
    async def run_preflight_checks(
        cls,
        records_to_import: List[Dict[str, Any]],
        db: Any,
        allow_unapproved: bool = False,
    ) -> Tuple[bool, List[str]]:
        """
        Comprehensive preflight checks:
        1. Intra-batch duplicate registration numbers.
        2. Intra-batch duplicate emails.
        3. Mandatory field presence and format.
        4. Rejection of unapproved records (unless allow_unapproved is explicitly true).
        5. Cross-database checks against existing records in eligibility_registry:
           - Same roll number with conflicting email, name, or section -> Error.
           - Existing email assigned to different student roll -> Error.
        """
        errors: List[str] = []

        if not records_to_import:
            errors.append("Empty dataset: cannot import 0 records.")
            return False, errors

        # 1. Intra-batch duplicate registration numbers
        roll_counts = Counter()
        for r in records_to_import:
            roll = (r.get("registration_number_normalized") or r.get("registration_number_raw", "")).upper()
            roll_counts[roll] += 1
        for roll, count in roll_counts.items():
            if count > 1:
                errors.append(f"Intra-batch error: duplicate registration number '{roll}' occurs {count} times.")

        # 2. Intra-batch duplicate emails
        email_counts = Counter()
        for r in records_to_import:
            email = r.get("processed_email", "").lower()
            if email:
                email_counts[email] += 1
        for email, count in email_counts.items():
            if count > 1:
                errors.append(f"Intra-batch error: duplicate email address '{email}' occurs {count} times across batch.")

        # 3. Check for unapproved flagged records in the import set
        if not allow_unapproved:
            unapproved = [
                r.get("s_no") for r in records_to_import
                if r.get("validation_status") == "FLAGGED_FOR_REVIEW" and not r.get("approval_metadata")
            ]
            if unapproved:
                errors.append(
                    f"Security policy error: attempted to import {len(unapproved)} unapproved flagged record(s) "
                    f"(S.Nos: {unapproved[:10]}{'...' if len(unapproved) > 10 else ''})."
                )

        # 4. Mandatory fields
        for r in records_to_import:
            sno = r.get("s_no", 0)
            roll = r.get("registration_number_raw", "").strip()
            name = r.get("student_name_raw", "").strip()
            sec = str(r.get("section", "")).strip()
            email = r.get("processed_email", "").strip()

            if not roll:
                errors.append(f"Row {sno}: missing required registration number.")
            if not name:
                errors.append(f"Row {sno}: missing required student name.")
            if not sec:
                errors.append(f"Row {sno}: missing required section.")
            if not email:
                errors.append(f"Row {sno}: missing required email address.")

        # 5. Cross-database checks against existing eligibility_registry records
        if db is not None:
            collection = db[cls.COLLECTION_NAME]
            existing_count = await collection.count_documents({})
            if existing_count > 0:
                # Fast single batch query if collection supports find().to_list() (Motor)
                existing_by_roll_map = None
                existing_by_email_map = None
                if hasattr(collection, "find"):
                    try:
                        cursor = collection.find(
                            {},
                            {"registration_number": 1, "roster_email": 1, "student_name": 1, "section": 1}
                        )
                        if hasattr(cursor, "to_list"):
                            existing_docs = await cursor.to_list(length=None)
                            existing_by_roll_map = {doc["registration_number"]: doc for doc in existing_docs if "registration_number" in doc}
                            existing_by_email_map = {doc["roster_email"]: doc for doc in existing_docs if "roster_email" in doc}
                    except Exception:
                        existing_by_roll_map = None
                        existing_by_email_map = None

                for r in records_to_import:
                    roll_norm = (r.get("registration_number_normalized") or r.get("registration_number_raw", "")).upper()
                    eff_email = r.get("processed_email", "").lower()
                    incoming_name = r.get("student_name_raw", "").strip().upper()
                    incoming_sec = str(r.get("section", "")).strip()

                    # Check existing registration number
                    if existing_by_roll_map is not None:
                        existing_by_roll = existing_by_roll_map.get(roll_norm)
                    else:
                        existing_by_roll = await collection.find_one({"registration_number": roll_norm})

                    if existing_by_roll:
                        # If existing record has different email, conflict!
                        if existing_by_roll.get("roster_email") != eff_email:
                            errors.append(
                                f"Database conflict: registration number '{roll_norm}' already exists with email "
                                f"'{existing_by_roll.get('roster_email')}', but incoming record specifies '{eff_email}'."
                            )

                        # If existing record has conflicting student identity name
                        existing_name = existing_by_roll.get("student_name", "").strip().upper()
                        if incoming_name and existing_name and incoming_name != existing_name:
                            errors.append(
                                f"Database conflict: registration number '{roll_norm}' already exists for student "
                                f"'{existing_name}', but incoming record specifies '{incoming_name}'."
                            )

                        # If existing record has conflicting section
                        existing_sec = str(existing_by_roll.get("section", "")).strip()
                        if incoming_sec and existing_sec and incoming_sec != existing_sec:
                            errors.append(
                                f"Database conflict: registration number '{roll_norm}' already exists in section "
                                f"'{existing_sec}', but incoming record specifies section '{incoming_sec}'."
                            )

                    # Check existing email
                    if existing_by_email_map is not None:
                        existing_by_email = existing_by_email_map.get(eff_email)
                    else:
                        existing_by_email = await collection.find_one({"roster_email": eff_email})

                    if existing_by_email:
                        # If existing email is owned by a different student, collision!
                        if existing_by_email.get("registration_number") != roll_norm:
                            errors.append(
                                f"Database conflict: email '{eff_email}' is already registered to "
                                f"student '{existing_by_email.get('registration_number')}', cannot reassign to '{roll_norm}'."
                            )

        return len(errors) == 0, errors

    @classmethod
    async def dry_run(
        cls,
        records_to_import: List[Dict[str, Any]],
        db: Any,
        allow_unapproved: bool = False,
    ) -> Dict[str, Any]:
        """
        Dry-run validation mode. Evaluates batch without performing any database write or creating any index.
        """
        is_valid, errors = await cls.run_preflight_checks(
            records_to_import, db, allow_unapproved=allow_unapproved
        )

        projected_new_inserts = 0
        projected_matched_resumes = 0

        if is_valid and db is not None:
            collection = db[cls.COLLECTION_NAME]
            existing_count = await collection.count_documents({})
            if existing_count == 0:
                projected_new_inserts = len(records_to_import)
                projected_matched_resumes = 0
            else:
                existing_rolls_set = None
                if hasattr(collection, "find"):
                    try:
                        cursor = collection.find({}, {"registration_number": 1})
                        if hasattr(cursor, "to_list"):
                            docs = await cursor.to_list(length=None)
                            existing_rolls_set = {d["registration_number"] for d in docs if "registration_number" in d}
                    except Exception:
                        existing_rolls_set = None

                for r in records_to_import:
                    roll_norm = (r.get("registration_number_normalized") or r.get("registration_number_raw", "")).upper()
                    if existing_rolls_set is not None:
                        existing = roll_norm in existing_rolls_set
                    else:
                        existing = bool(await collection.find_one({"registration_number": roll_norm}))
                    if existing:
                        projected_matched_resumes += 1
                    else:
                        projected_new_inserts += 1
        elif is_valid:
            projected_new_inserts = len(records_to_import)

        return {
            "dry_run_success": is_valid,
            "records_evaluated": len(records_to_import),
            "projected_new_inserts": projected_new_inserts,
            "projected_matched_resumes": projected_matched_resumes,
            "preflight_errors_count": len(errors),
            "preflight_errors": errors,
            "indexes_required": [idx["options"]["name"] for idx in cls.INDEX_DEFINITIONS],
            "idempotency_strategy": "bulk_write UpdateOne($setOnInsert, upsert=True)",
            "rollback_strategy": "Delete only records matching {import_batch_id: batch_id, is_claimed: False}",
        }

    @classmethod
    async def execute_import(
        cls,
        records_to_import: List[Dict[str, Any]],
        db: Any,
        batch_id: Optional[str] = None,
        allow_unapproved: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes safe, idempotent import into eligibility_registry.
        Aborts with EligibilityPreflightFailedError if any error is detected.
        Guarantees that index creation failure halts prior to bulk_write.
        Accurately reports partial failures if BulkWriteError is encountered.
        """
        is_valid, errors = await cls.run_preflight_checks(
            records_to_import, db, allow_unapproved=allow_unapproved
        )
        if not is_valid:
            raise EligibilityPreflightFailedError(errors)

        batch_id = batch_id or str(uuid.uuid4())
        collection = db[cls.COLLECTION_NAME]

        # 1. Ensure indexes (if index creation fails, halt before any record write)
        for idx in cls.INDEX_DEFINITIONS:
            try:
                await collection.create_index(idx["keys"], **idx["options"])
            except Exception as e:
                raise EligibilityIndexCreationError(
                    f"Index creation failed for '{idx['options'].get('name')}': {str(e)}. "
                    "Halted prior to any roster record writes."
                ) from e

        # 2. Build bulk write operations
        from pymongo import UpdateOne
        from pymongo.errors import BulkWriteError
        now = utc_now()
        operations = []

        for r in records_to_import:
            sno = r.get("s_no")
            roll_norm = (r.get("registration_number_normalized") or r.get("registration_number_raw", "")).upper()
            eff_email = r.get("processed_email", "").lower()
            source = r.get("email_source", EmailSource.PROVIDED.value)

            doc = {
                "id": str(uuid.uuid4()),
                "institution_id": "VFSTR",
                "batch_cohort": "2024-2028",
                "department": "CSE",
                "registration_number": roll_norm,
                "student_name": r.get("student_name_raw", "").strip(),
                "roster_email": eff_email,
                "email_source": source,
                "section": str(r.get("section", "")).strip(),
                "is_claimed": False,
                "claimed_user_id": None,
                "claimed_at": None,
                "validation_status": EligibilityStatus.ELIGIBLE.value,
                "is_eligible_for_registration": True,
                "review_group": ReviewGroup.READY_FOR_IMPORT.value if not r.get("approval_metadata") else ReviewGroup.PROPOSED_UNAMBIGUOUS.value,
                "approval_metadata": r.get("approval_metadata"),
                "resolution_notes": f"Imported via batch {batch_id}",
                "raw_source": {
                    "s_no": sno,
                    "page": r.get("page", 0),
                    "raw_roll": r.get("registration_number_raw", ""),
                    "raw_name": r.get("student_name_raw", ""),
                    "raw_email": r.get("email_raw", ""),
                    "raw_section": str(r.get("section", "")),
                },
                "import_batch_id": batch_id,
                "created_at": now,
                "updated_at": now,
            }

            operations.append(
                UpdateOne(
                    {
                        "institution_id": "VFSTR",
                        "registration_number": roll_norm,
                    },
                    {"$setOnInsert": doc},
                    upsert=True,
                )
            )

        try:
            result = await collection.bulk_write(operations, ordered=False)
        except BulkWriteError as bwe:
            details = bwe.details or {}
            upserted = details.get("nUpserted", 0)
            matched = details.get("nMatched", 0)
            write_errors = details.get("writeErrors", [])
            raise EligibilityBulkWriteFailedError(
                batch_id=batch_id,
                inserted_count=upserted,
                matched_count=matched,
                failed_count=len(write_errors),
                write_errors=write_errors,
            ) from bwe

        return {
            "success": True,
            "import_batch_id": batch_id,
            "records_processed": len(records_to_import),
            "inserted_count": result.upserted_count,
            "matched_existing_count": result.matched_count,
            "modified_count": result.modified_count,
        }

    @classmethod
    async def stage_unresolved_records(
        cls,
        unresolved_records: List[Dict[str, Any]],
        db: Any,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Stores unresolved / pending-decision records in eligibility_registry
        with is_eligible_for_registration=False and validation_status='pending_review'
        so they are preserved for future audit and review without allowing student registration.
        """
        batch_id = batch_id or str(uuid.uuid4())
        collection = db[cls.COLLECTION_NAME]

        from pymongo import UpdateOne
        now = utc_now()
        operations = []

        for r in unresolved_records:
            sno = r.get("s_no")
            roll_norm = (r.get("registration_number_normalized") or r.get("registration_number_raw", "")).upper()
            raw_email = r.get("email_raw", "")

            doc = {
                "id": str(uuid.uuid4()),
                "institution_id": "VFSTR",
                "batch_cohort": "2024-2028",
                "department": "CSE",
                "registration_number": roll_norm,
                "student_name": r.get("student_name_raw", "").strip(),
                "roster_email": f"staged_pending_review.{roll_norm.lower()}@quarantine.vfstr",
                "email_source": EmailSource.PROVIDED.value,
                "section": str(r.get("section", "")).strip(),
                "is_claimed": False,
                "claimed_user_id": None,
                "claimed_at": None,
                "validation_status": EligibilityStatus.PENDING_REVIEW.value,
                "is_eligible_for_registration": False,  # STRICT: Ineligible for registration
                "review_group": ReviewGroup.MANUAL_REVIEW.value,
                "approval_metadata": None,
                "resolution_notes": f"Staged for administrative review via batch {batch_id}",
                "raw_source": {
                    "s_no": sno,
                    "page": r.get("page", 0),
                    "raw_roll": r.get("registration_number_raw", ""),
                    "raw_name": r.get("student_name_raw", ""),
                    "raw_email": raw_email,
                    "raw_section": str(r.get("section", "")),
                },
                "import_batch_id": batch_id,
                "created_at": now,
                "updated_at": now,
            }

            operations.append(
                UpdateOne(
                    {
                        "institution_id": "VFSTR",
                        "registration_number": roll_norm,
                    },
                    {"$setOnInsert": doc},
                    upsert=True,
                )
            )

        if operations:
            result = await collection.bulk_write(operations, ordered=False)
            upserted = result.upserted_count
            matched = result.matched_count
        else:
            upserted = 0
            matched = 0

        return {
            "success": True,
            "staged_batch_id": batch_id,
            "staged_count": upserted,
            "matched_count": matched,
        }

    @classmethod
    async def rollback_import_batch(
        cls,
        batch_id: str,
        db: Any,
    ) -> Dict[str, Any]:
        """
        Safely deletes ONLY unclaimed records belonging to the specific batch ID.
        Never drops collections and never deletes claimed records or records from other batches.
        """
        collection = db[cls.COLLECTION_NAME]
        query = {
            "import_batch_id": batch_id,
            "is_claimed": False,
        }

        claimed_count = await collection.count_documents(
            {"import_batch_id": batch_id, "is_claimed": True}
        )

        del_result = await collection.delete_many(query)

        return {
            "rollback_batch_id": batch_id,
            "unclaimed_deleted_count": del_result.deleted_count,
            "claimed_preserved_count": claimed_count,
            "message": f"Successfully rolled back {del_result.deleted_count} unclaimed eligibility record(s).",
        }
