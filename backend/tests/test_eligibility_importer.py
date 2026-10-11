import pytest
from unittest.mock import MagicMock

from app.models.eligibility import ApprovalDecision, ReviewGroup
from app.services.admin_review_manager import AdminReviewManager
from app.services.eligibility_importer import (
    EligibilityImporter,
    EligibilityPreflightFailedError,
)


class InMemoryMockCollection:
    """In-memory mock for Motor/MongoDB collection to test without touching Atlas."""

    def __init__(self):
        self.documents = {}  # keyed by (institution_id, registration_number)
        self.indexes = []

    async def create_index(self, keys, **options):
        self.indexes.append({"keys": keys, "options": options})
        return options.get("name", "index")

    async def bulk_write(self, operations, ordered=False):
        upserted_count = 0
        matched_count = 0
        modified_count = 0

        for op in operations:
            filter_dict = op._filter
            update_dict = op._doc
            upsert = op._upsert

            key = (filter_dict.get("institution_id"), filter_dict.get("registration_number"))

            if key in self.documents:
                matched_count += 1
                # $setOnInsert does not modify existing documents
            else:
                if upsert and "$setOnInsert" in update_dict:
                    self.documents[key] = dict(update_dict["$setOnInsert"])
                    upserted_count += 1

        mock_result = MagicMock()
        mock_result.upserted_count = upserted_count
        mock_result.matched_count = matched_count
        mock_result.modified_count = modified_count
        return mock_result

    async def find_one(self, query):
        for doc in self.documents.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    async def count_documents(self, query):
        count = 0
        for doc in self.documents.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count

    async def delete_many(self, query):
        to_delete = []
        for key, doc in list(self.documents.items()):
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                to_delete.append(key)

        for key in to_delete:
            del self.documents[key]

        mock_result = MagicMock()
        mock_result.deleted_count = len(to_delete)
        return mock_result


class InMemoryMockDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = InMemoryMockCollection()
        return self.collections[name]


@pytest.fixture
def mock_db():
    return InMemoryMockDatabase()


@pytest.fixture
def clean_sample_records():
    return [
        {
            "s_no": 1,
            "page": 1,
            "registration_number_raw": "241FA04001",
            "registration_number_normalized": "241FA04001",
            "student_name_raw": "ALICE SHARMA",
            "email_raw": "vu.241fa04001@gmail.com",
            "processed_email": "vu.241fa04001@gmail.com",
            "email_source": "provided",
            "section": "1",
            "validation_status": "VALID",
            "issues": [],
        },
        {
            "s_no": 2,
            "page": 1,
            "registration_number_raw": "241FA04002",
            "registration_number_normalized": "241FA04002",
            "student_name_raw": "BOB VARMA",
            "email_raw": "NA",
            "processed_email": "vu.241fa04002@gmail.com",
            "email_source": "generated_pending_verification",
            "section": "1",
            "validation_status": "GENERATED",
            "issues": [],
        },
    ]


@pytest.mark.anyio
async def test_preflight_aborts_on_duplicate_email(mock_db):
    """Refuse import when duplicate email addresses exist within the batch."""
    records = [
        {
            "s_no": 111,
            "registration_number_raw": "241FA04886",
            "registration_number_normalized": "241FA04886",
            "student_name_raw": "STUDENT A",
            "email_raw": "vu.241fa04d35@gmail.com",
            "processed_email": "vu.241fa04d35@gmail.com",
            "section": "2",
            "validation_status": "VALID",
            "issues": [],
        },
        {
            "s_no": 956,
            "registration_number_raw": "241FA04D35",
            "registration_number_normalized": "241FA04D35",
            "student_name_raw": "STUDENT B",
            "email_raw": "vu.241fa04d35@gmail.com",
            "processed_email": "vu.241fa04d35@gmail.com",
            "section": "14",
            "validation_status": "VALID",
            "issues": [],
        },
    ]

    is_valid, errors = await EligibilityImporter.run_preflight_checks(records, mock_db)
    assert is_valid is False
    assert any("email address 'vu.241fa04d35@gmail.com' occurs 2 times" in err for err in errors)


@pytest.mark.anyio
async def test_execute_import_raises_and_aborts_on_duplicate_email(mock_db):
    records = [
        {
            "s_no": 1,
            "registration_number_raw": "241FA04001",
            "student_name_raw": "A",
            "processed_email": "shared@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        },
        {
            "s_no": 2,
            "registration_number_raw": "241FA04002",
            "student_name_raw": "B",
            "processed_email": "shared@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        },
    ]

    with pytest.raises(EligibilityPreflightFailedError) as exc_info:
        await EligibilityImporter.execute_import(records, mock_db)

    assert "shared@gmail.com" in str(exc_info.value.errors)
    assert len(mock_db["eligibility_registry"].documents) == 0


@pytest.mark.anyio
async def test_preflight_aborts_on_duplicate_registration_number(mock_db):
    records = [
        {
            "s_no": 1,
            "registration_number_raw": "241FA04001",
            "registration_number_normalized": "241FA04001",
            "student_name_raw": "STUDENT ONE",
            "processed_email": "email1@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        },
        {
            "s_no": 2,
            "registration_number_raw": "241FA04001",
            "registration_number_normalized": "241FA04001",
            "student_name_raw": "STUDENT TWO",
            "processed_email": "email2@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        },
    ]

    is_valid, errors = await EligibilityImporter.run_preflight_checks(records, mock_db)
    assert is_valid is False
    assert any("registration number '241FA04001' occurs 2 times" in err for err in errors)


@pytest.mark.anyio
async def test_preflight_aborts_on_unapproved_flagged_records(mock_db):
    """Refuse import if unapproved flagged records are included in candidate set."""
    records = [
        {
            "s_no": 606,
            "registration_number_raw": "241FA04749",
            "registration_number_normalized": "241FA04749",
            "student_name_raw": "TEST STUDENT",
            "email_raw": "vu.241fao4749@gmail.com",
            "processed_email": "vu.241fao4749@gmail.com",
            "section": "9",
            "validation_status": "FLAGGED_FOR_REVIEW",
            "issues": ["OCR/Typo anomaly: letter 'o' substituted for digit '0'"],
        }
    ]

    is_valid, errors = await EligibilityImporter.run_preflight_checks(records, mock_db)
    assert is_valid is False
    assert any("attempted to import 1 unapproved flagged record" in err for err in errors)


@pytest.mark.anyio
async def test_dry_run_produces_report_without_database_write(clean_sample_records, mock_db):
    dry_run_res = await EligibilityImporter.dry_run(clean_sample_records, mock_db)
    assert dry_run_res["dry_run_success"] is True
    assert dry_run_res["records_evaluated"] == 2
    assert dry_run_res["projected_new_inserts"] == 2
    assert "unique_institution_registration_number" in dry_run_res["indexes_required"]
    assert "unique_institution_roster_email" in dry_run_res["indexes_required"]
    assert len(mock_db["eligibility_registry"].documents) == 0


@pytest.mark.anyio
async def test_cross_database_duplicate_and_conflict_rejection(mock_db):
    """Ensure incoming record cannot reassign an existing email or conflict on registration number."""
    # Pre-populate DB with existing record
    existing_key = ("VFSTR", "241FA04001")
    mock_db["eligibility_registry"].documents[existing_key] = {
        "institution_id": "VFSTR",
        "registration_number": "241FA04001",
        "student_name": "EXISTING STUDENT",
        "roster_email": "vu.241fa04001@gmail.com",
        "is_claimed": False,
        "import_batch_id": "batch-initial",
    }

    # Case 1: Same roll number, conflicting email
    conflict_roll = [
        {
            "s_no": 1,
            "registration_number_raw": "241FA04001",
            "student_name_raw": "EXISTING STUDENT",
            "processed_email": "conflicting.email@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        }
    ]
    is_valid, errors = await EligibilityImporter.run_preflight_checks(conflict_roll, mock_db)
    assert is_valid is False
    assert any("already exists with email 'vu.241fa04001@gmail.com'" in err for err in errors)

    # Case 2: Different roll number trying to steal existing student's email
    conflict_email = [
        {
            "s_no": 2,
            "registration_number_raw": "241FA04002",
            "student_name_raw": "NEW STUDENT",
            "processed_email": "vu.241fa04001@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        }
    ]
    is_valid, errors = await EligibilityImporter.run_preflight_checks(conflict_email, mock_db)
    assert is_valid is False
    assert any("already registered to student '241FA04001'" in err for err in errors)


@pytest.mark.anyio
async def test_idempotent_import_and_safe_deduplication(clean_sample_records, mock_db):
    """Verify first run inserts N records and second run modifies 0 records."""
    res1 = await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id="batch-001")
    assert res1["success"] is True
    assert res1["inserted_count"] == 2
    assert res1["matched_existing_count"] == 0
    assert len(mock_db["eligibility_registry"].documents) == 2

    res2 = await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id="batch-002")
    assert res2["success"] is True
    assert res2["inserted_count"] == 0
    assert res2["matched_existing_count"] == 2
    assert res2["modified_count"] == 0
    assert len(mock_db["eligibility_registry"].documents) == 2


@pytest.mark.anyio
async def test_resumable_partial_import(clean_sample_records, mock_db):
    """Verify that an interrupted import resumes without duplicating existing records."""
    # Insert first record
    rec1 = [clean_sample_records[0]]
    res1 = await EligibilityImporter.execute_import(rec1, mock_db, batch_id="batch-part1")
    assert res1["inserted_count"] == 1
    assert len(mock_db["eligibility_registry"].documents) == 1

    # Resume with both records
    res2 = await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id="batch-part2")
    assert res2["matched_existing_count"] == 1
    assert res2["inserted_count"] == 1
    assert len(mock_db["eligibility_registry"].documents) == 2


@pytest.mark.anyio
async def test_rollback_batch_preserves_other_batches_and_claimed_records(mock_db):
    """Rollback on batch-B removes only batch-B unclaimed records and preserves batch-A and claimed records."""
    # Batch A
    rec_a = [
        {
            "s_no": 1,
            "registration_number_raw": "241FA04001",
            "student_name_raw": "STUDENT A",
            "processed_email": "a@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        }
    ]
    await EligibilityImporter.execute_import(rec_a, mock_db, batch_id="batch-A")

    # Batch B
    rec_b = [
        {
            "s_no": 2,
            "registration_number_raw": "241FA04002",
            "student_name_raw": "STUDENT B",
            "processed_email": "b@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        },
        {
            "s_no": 3,
            "registration_number_raw": "241FA04003",
            "student_name_raw": "STUDENT C",
            "processed_email": "c@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        },
    ]
    await EligibilityImporter.execute_import(rec_b, mock_db, batch_id="batch-B")

    # Student B claims account
    mock_db["eligibility_registry"].documents[("VFSTR", "241FA04002")]["is_claimed"] = True

    assert len(mock_db["eligibility_registry"].documents) == 3

    # Execute rollback on batch-B
    rollback_res = await EligibilityImporter.rollback_import_batch("batch-B", mock_db)
    assert rollback_res["unclaimed_deleted_count"] == 1  # Only student C deleted
    assert rollback_res["claimed_preserved_count"] == 1   # Student B claimed, preserved

    # Verify Batch A student (A) and claimed Batch B student (B) remain
    assert ("VFSTR", "241FA04001") in mock_db["eligibility_registry"].documents
    assert ("VFSTR", "241FA04002") in mock_db["eligibility_registry"].documents
    assert ("VFSTR", "241FA04003") not in mock_db["eligibility_registry"].documents


@pytest.mark.anyio
async def test_stage_unresolved_records_ineligible_for_registration(mock_db):
    """Ensure staged records have is_eligible_for_registration=False and validation_status='pending_review'."""
    unresolved = [
        {
            "s_no": 111,
            "registration_number_raw": "241FA04886",
            "student_name_raw": "JADDA MAHESH",
            "email_raw": "vu.241fa04d35@gmail.com",
            "section": "2",
        }
    ]

    res = await EligibilityImporter.stage_unresolved_records(unresolved, mock_db, batch_id="stage-batch-1")
    assert res["staged_count"] == 1

    doc = mock_db["eligibility_registry"].documents[("VFSTR", "241FA04886")]
    assert doc["is_eligible_for_registration"] is False
    assert doc["validation_status"] == "pending_review"
    assert "quarantine" in doc["roster_email"]


def test_partition_by_review_status_and_approved_transitions():
    """Verify 3-way partition and promotion only upon administrative approval."""
    preview = [
        {"s_no": 1, "validation_status": "VALID"},
        {"s_no": 2, "validation_status": "FLAGGED_FOR_REVIEW"},
        {"s_no": 3, "validation_status": "FLAGGED_FOR_REVIEW"},
    ]
    flagged = [
        {"s_no": 2, "resolution_status": "PROPOSED_UNAMBIGUOUS"},
        {"s_no": 3, "resolution_status": "MANUAL_REVIEW"},
    ]

    # Without approval
    parts = EligibilityImporter.partition_records_by_review_status(preview, flagged)
    assert len(parts[ReviewGroup.READY_FOR_IMPORT.value]) == 1
    assert len(parts[ReviewGroup.PROPOSED_UNAMBIGUOUS.value]) == 1
    assert len(parts[ReviewGroup.MANUAL_REVIEW.value]) == 1
    assert len(parts["APPROVED_ADDITIONS"]) == 0

    # With admin approval on S.No 2
    mgr = AdminReviewManager()
    mgr.entries = {
        2: {
            "s_no": 2,
            "administrator_decision": ApprovalDecision.APPROVED.value,
            "reviewed_by_admin_id": "admin@vignan.ac.in",
            "reason": "Verified typo correction",
            "timestamp": "2026-10-10T19:30:00Z",
            "source_roster_value": "vu241fao4002@gmail.com",
            "proposed_value": "vu.241fa04002@gmail.com",
            "effective_value": "vu.241fa04002@gmail.com",
        }
    }

    parts_approved = EligibilityImporter.partition_records_by_review_status(preview, flagged, review_manager=mgr)
    assert len(parts_approved[ReviewGroup.READY_FOR_IMPORT.value]) == 1
    assert len(parts_approved[ReviewGroup.PROPOSED_UNAMBIGUOUS.value]) == 0
    assert len(parts_approved[ReviewGroup.MANUAL_REVIEW.value]) == 1
    assert len(parts_approved["APPROVED_ADDITIONS"]) == 1
    assert parts_approved["APPROVED_ADDITIONS"][0]["processed_email"] == "vu.241fa04002@gmail.com"


@pytest.mark.anyio
async def test_batch_identity_isolation_and_stability(clean_sample_records, mock_db):
    """Verify one stable batch_id is generated and pre-existing records are NOT reassigned."""
    batch_1 = "batch-stable-1"
    res1 = await EligibilityImporter.execute_import([clean_sample_records[0]], mock_db, batch_id=batch_1)
    assert res1["inserted_count"] == 1
    doc_1 = mock_db["eligibility_registry"].documents[("VFSTR", "241FA04001")]
    assert doc_1["import_batch_id"] == batch_1

    # Second batch run with second student AND first student
    batch_2 = "batch-stable-2"
    res2 = await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id=batch_2)
    assert res2["inserted_count"] == 1  # only second student
    assert res2["matched_existing_count"] == 1  # first student matched

    # Verify first student STILL has batch_1 (NEVER reassigned!)
    doc_1_after = mock_db["eligibility_registry"].documents[("VFSTR", "241FA04001")]
    assert doc_1_after["import_batch_id"] == batch_1

    # Verify second student has batch_2
    doc_2 = mock_db["eligibility_registry"].documents[("VFSTR", "241FA04002")]
    assert doc_2["import_batch_id"] == batch_2


@pytest.mark.anyio
async def test_index_creation_failure_stops_import_before_writes(clean_sample_records, mock_db):
    """Verify index creation failure stops import with EligibilityIndexCreationError and zero writes."""
    from app.services.eligibility_importer import EligibilityIndexCreationError

    # Simulate index creation failure
    async def failing_create_index(keys, **options):
        raise RuntimeError("Simulated Atlas Index Limit Exceeded")

    mock_db["eligibility_registry"].create_index = failing_create_index

    with pytest.raises(EligibilityIndexCreationError) as exc_info:
        await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id="batch-fail")

    assert "Index creation failed" in str(exc_info.value)
    # Ensure zero documents were written
    assert len(mock_db["eligibility_registry"].documents) == 0


@pytest.mark.anyio
async def test_bulk_write_error_reports_accurate_counts(clean_sample_records, mock_db):
    """Verify bulk write failure reports accurate partial counts rather than claiming complete success."""
    from pymongo.errors import BulkWriteError
    from app.services.eligibility_importer import EligibilityBulkWriteFailedError

    # Simulate partial bulk write error
    async def failing_bulk_write(operations, ordered=False):
        raise BulkWriteError({
            "nUpserted": 1,
            "nMatched": 0,
            "nModified": 0,
            "writeErrors": [{"index": 1, "code": 11000, "errmsg": "Duplicate key error"}],
        })

    mock_db["eligibility_registry"].bulk_write = failing_bulk_write

    with pytest.raises(EligibilityBulkWriteFailedError) as exc_info:
        await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id="batch-partial")

    err = exc_info.value
    assert err.batch_id == "batch-partial"
    assert err.inserted_count == 1
    assert err.failed_count == 1
    assert len(err.write_errors) == 1


@pytest.mark.anyio
async def test_cross_database_conflicting_identity_name_and_section_rejection(mock_db):
    """Verify conflict rejection if incoming record has same roll but different name or section."""
    existing_key = ("VFSTR", "241FA04001")
    mock_db["eligibility_registry"].documents[existing_key] = {
        "institution_id": "VFSTR",
        "registration_number": "241FA04001",
        "student_name": "ALICE SHARMA",
        "roster_email": "vu.241fa04001@gmail.com",
        "section": "1",
        "is_claimed": False,
        "import_batch_id": "batch-init",
    }

    # Case 1: Conflicting student name
    conflict_name = [
        {
            "s_no": 1,
            "registration_number_raw": "241FA04001",
            "student_name_raw": "DIFFERENT PERSON",
            "processed_email": "vu.241fa04001@gmail.com",
            "section": "1",
            "validation_status": "VALID",
        }
    ]
    is_valid_1, errors_1 = await EligibilityImporter.run_preflight_checks(conflict_name, mock_db)
    assert is_valid_1 is False
    assert any("already exists for student 'ALICE SHARMA'" in e for e in errors_1)

    # Case 2: Conflicting section
    conflict_sec = [
        {
            "s_no": 1,
            "registration_number_raw": "241FA04001",
            "student_name_raw": "ALICE SHARMA",
            "processed_email": "vu.241fa04001@gmail.com",
            "section": "9",
            "validation_status": "VALID",
        }
    ]
    is_valid_2, errors_2 = await EligibilityImporter.run_preflight_checks(conflict_sec, mock_db)
    assert is_valid_2 is False
    assert any("already exists in section '1'" in e for e in errors_2)


@pytest.mark.anyio
async def test_dry_run_creates_no_indexes_and_performs_no_writes(clean_sample_records, mock_db):
    """Verify that dry_run performs 0 database writes and 0 index creations."""
    res = await EligibilityImporter.dry_run(clean_sample_records, mock_db)
    assert res["dry_run_success"] is True
    assert len(mock_db["eligibility_registry"].documents) == 0
    assert len(mock_db["eligibility_registry"].indexes) == 0


@pytest.mark.anyio
async def test_account_isolation_never_modifies_users_collection(clean_sample_records, mock_db):
    """Verify that EligibilityImporter operates strictly on eligibility_registry and leaves users untouched."""
    # Pre-populate users collection
    mock_db["users"].documents[("system", "admin")] = {
        "email": "admin@vfstr.ac.in",
        "role": "platform_admin",
    }

    await EligibilityImporter.execute_import(clean_sample_records, mock_db, batch_id="batch-isolate")

    # Verify eligibility_registry got 2 docs
    assert len(mock_db["eligibility_registry"].documents) == 2
    # Verify users collection remains exactly 1 doc, untouched
    assert len(mock_db["users"].documents) == 1
    assert ("system", "admin") in mock_db["users"].documents

