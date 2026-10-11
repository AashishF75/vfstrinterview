import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.networking_pdf_parser import (
    NetworkingAssessmentParser,
    NetworkingAssessmentRecord,
)
from app.services.interview_eligibility_importer import (
    InterviewEligibilityImporter,
    TargetDatabaseSafetyError,
)

PDF_PATH = Path(__file__).resolve().parent.parent.parent / "Networking Essentials Assessment_20_09.pdf"


def test_pdf_extraction_and_counts():
    """Verify that the parser extracts exactly 1,507 rows from all 28 pages of the PDF."""
    if not PDF_PATH.exists():
        pytest.skip(f"PDF file not found at {PDF_PATH}")

    parser = NetworkingAssessmentParser(str(PDF_PATH))
    records = parser.parse()
    summary = parser.get_summary_metrics()

    assert len(records) == 1507
    assert summary["total_pages"] == 28
    assert summary["total_extracted_rows"] == 1507
    assert summary["approved_records"] == 1484
    assert summary["needs_review_records"] == 23
    assert summary["missing_registration_numbers"] == 9

    # Cohort breakdown
    assert summary["batch_breakdown"].get("2024-2028") == 1484
    assert summary["batch_breakdown"].get("2023-2027") == 3
    assert summary["batch_breakdown"].get("2024-2028_LATERAL") == 11


def test_missing_registration_numbers_flagged_correctly():
    """Verify that rows with #N/A registration numbers are flagged for review and marked ineligible."""
    rec = NetworkingAssessmentRecord(
        s_no=1500,
        source_page=28,
        source_row=42,
        source_file="test.pdf",
        raw_reg_no="#N/A",
        raw_email="test.student@example.com",
        raw_section="#N/A",
    )
    assert rec.registration_number == "#N/A"
    assert rec.section == "#N/A"
    assert rec.review_status == "needs_review"
    assert rec.interview_eligible is False
    assert "MISSING_REGISTRATION_NUMBER" in rec.review_reasons
    assert "MISSING_SECTION" in rec.review_reasons


def test_unexpected_batch_flagged_for_review():
    """Verify that 2023-batch students are flagged as needs_review and ineligible."""
    rec = NetworkingAssessmentRecord(
        s_no=113,
        source_page=3,
        source_row=5,
        source_file="test.pdf",
        raw_reg_no="231FA04941",
        raw_email="alokamneeraj01@gmail.com",
        raw_section="2",
    )
    assert rec.batch_cohort == "2023-2027"
    assert rec.review_status == "needs_review"
    assert rec.interview_eligible is False
    assert "UNEXPECTED_BATCH_2023" in rec.review_reasons


def test_lateral_entry_flagged_for_review():
    """Verify that 2025 lateral-entry students are flagged as needs_review and ineligible."""
    rec = NetworkingAssessmentRecord(
        s_no=267,
        source_page=5,
        source_row=51,
        source_file="test.pdf",
        raw_reg_no="251LA04001",
        raw_email="251la04001@gmail.com",
        raw_section="4",
    )
    assert rec.batch_cohort == "2024-2028_LATERAL"
    assert rec.review_status == "needs_review"
    assert rec.interview_eligible is False
    assert "LATERAL_ENTRY_BATCH_2025" in rec.review_reasons


def test_score_and_grade_exclusion_in_mongo_doc():
    """Verify that no exam scores or grades are stored in the MongoDB document."""
    rec = NetworkingAssessmentRecord(
        s_no=1,
        source_page=1,
        source_row=1,
        source_file="test.pdf",
        raw_reg_no="241FA04E71",
        raw_email="vu.241fa04e71@gmail.com",
        raw_section="1",
    )
    doc = rec.to_mongo_doc(import_batch_id="test-batch-uuid")

    forbidden_keys = [
        "score",
        "final_exam_score",
        "grade",
        "class_grade",
        "final_exam_submitted",
        "survey_submitted",
    ]
    for key in forbidden_keys:
        assert key not in doc, f"Forbidden key '{key}' found in MongoDB document"

    # Verify required fields
    assert doc["registration_number"] == "241FA04E71"
    assert doc["email"] == "vu.241fa04e71@gmail.com"
    assert doc["section"] == "1"
    assert doc["source_file"] == "test.pdf"
    assert doc["source_page"] == 1
    assert doc["source_row"] == 1
    assert doc["email_status"] == "provided_unverified"
    assert doc["review_status"] == "approved"
    assert doc["interview_eligible"] is True
    assert doc["interview_assignment_status"] == "unassigned"
    assert doc["import_batch_id"] == "test-batch-uuid"
    assert "created_at" in doc
    assert "updated_at" in doc


def test_target_safety_check_aborts_on_wrong_database():
    """Verify that importer aborts if target database name is not 'interview_db'."""
    importer = InterviewEligibilityImporter(target_db_name="wrong_db")
    with pytest.raises(TargetDatabaseSafetyError, match="Target database must strictly be 'interview_db'"):
        importer.verify_target_safety()


def test_target_safety_check_aborts_on_localhost():
    """Verify that importer aborts if URI targets localhost or 127.0.0.1."""
    importer = InterviewEligibilityImporter(
        mongo_uri="mongodb://localhost:27017",
        target_db_name="interview_db"
    )
    with pytest.raises(TargetDatabaseSafetyError, match="SAFETY ABORT: MONGODB_URI is unconfigured or defaulting to localhost"):
        importer.verify_target_safety()

    importer_127 = InterviewEligibilityImporter(
        mongo_uri="mongodb://127.0.0.1:27017/interview_db",
        target_db_name="interview_db"
    )
    with pytest.raises(TargetDatabaseSafetyError, match="SAFETY ABORT: Connection targets local MongoDB"):
        importer_127.verify_target_safety()


def test_target_safety_check_aborts_on_empty_uri():
    """Verify that importer aborts if URI is empty."""
    importer = InterviewEligibilityImporter(
        mongo_uri="",
        target_db_name="interview_db"
    )
    with pytest.raises(TargetDatabaseSafetyError, match="SAFETY ABORT: MONGODB_URI is unconfigured"):
        importer.verify_target_safety()
