import sys
import argparse
import json
import logging
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add backend directory to path if run directly
backend_root = Path(__file__).resolve().parent.parent.parent
workspace_root = backend_root.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.core.config import settings
from app.services.networking_pdf_parser import NetworkingAssessmentParser
from app.services.interview_eligibility_importer import (
    InterviewEligibilityImporter,
    TargetDatabaseSafetyError,
    InterviewEligibilityImportError,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("import_networking_assessment_cli")


def main():
    parser = argparse.ArgumentParser(
        description="VFSTR - Networking Essentials Assessment PDF Importer for University Interview Assignment"
    )
    parser.add_argument(
        "--pdf-path",
        type=str,
        default=str(workspace_root / "Networking Essentials Assessment_20_09.pdf"),
        help="Path to the Networking Essentials Assessment PDF file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run parser and preflight validation without writing to MongoDB Atlas.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute production bulk import into MongoDB Atlas interview_db.interview_eligibility_registry.",
    )

    args = parser.parse_args()

    # Default to dry-run if --execute is not provided
    is_execute = args.execute
    is_dry_run = args.dry_run or not is_execute

    print("=" * 80)
    print(" ADAPTIVE INTERVIEW INTELLIGENCE – VFSTR")
    print(" NETWORKING ESSENTIALS ASSESSMENT PDF IMPORT PIPELINE")
    print("=" * 80)

    # 1. Inspect configuration & safety diagnostics
    diag = settings.get_sanitized_diagnostic()
    print(f"Configuration File:     {diag['config_file_path']}")
    print(f"Target Database Host:   {diag['target_database_type']}")
    print(f"Target Database Name:   {InterviewEligibilityImporter.TARGET_DB_NAME}")
    print(f"Target Collection Name: {InterviewEligibilityImporter.COLLECTION_NAME}")
    print(f"Execution Mode:         {'PRODUCTION WRITE (--execute)' if is_execute else 'DRY RUN AUDIT (--dry-run)'}")
    print("=" * 80)

    # 2. Locate and check the PDF file
    pdf_file = Path(args.pdf_path).resolve()
    print(f"\n[STEP 1] Locating PDF File: {pdf_file.name}")
    if not pdf_file.exists():
        print(f"\n[FATAL ERROR] PDF file was NOT found at expected location:")
        print(f"  --> {pdf_file}")
        print("\nPlease ensure the file is placed at the workspace root:")
        print(f"  {workspace_root / 'Networking Essentials Assessment_20_09.pdf'}")
        print("Import aborted. Zero database modifications performed.")
        sys.exit(1)

    print(f"  [OK] PDF located successfully ({pdf_file.stat().st_size:,} bytes).")

    # 3. Extract and parse table across all pages
    print("\n[STEP 2] Extracting Table Data from PDF...")
    pdf_parser = NetworkingAssessmentParser(str(pdf_file))
    try:
        records = pdf_parser.parse()
    except Exception as e:
        print(f"[FATAL ERROR] Failed to parse PDF: {e}")
        sys.exit(1)

    summary = pdf_parser.get_summary_metrics()
    print(f"  ✓ Processed {summary['total_pages']} pages.")
    print(f"  ✓ Total Extracted Student Rows: {summary['total_extracted_rows']}")
    print(f"  ✓ Standard CSE Batch (2024-2028 Approved): {summary['approved_records']}")
    print(f"  ✓ Flagged Records Needing Manual Review:   {summary['needs_review_records']}")
    print(f"  ✓ Interview Eligible (Auto-Approved):      {summary['interview_eligible_records']}")
    print(f"  ✓ Missing Registration Numbers (#N/A):     {summary['missing_registration_numbers']}")

    print("\n  Batch Cohort Breakdown:")
    for cohort, count in summary["batch_breakdown"].items():
        print(f"    - {cohort:<25}: {count} records")

    print("\n  Review Reasons Breakdown:")
    for reason, count in summary["review_reasons"].items():
        print(f"    - {reason:<30}: {count} records")

    # 4. Initialize importer & target safety check
    importer = InterviewEligibilityImporter()

    print("\n[STEP 3] Verifying Target Database Safety & Atlas Connectivity...")
    try:
        safety_diag = importer.verify_target_safety()
        print(f"  ✓ Target safety verified.")
        print(f"    - Remote Atlas Verified: {safety_diag['is_atlas']}")
        print(f"    - Cluster Nodes:         {safety_diag['cluster_nodes_count']}")
        print(f"    - Target Database:       {safety_diag['database_name']}")
    except TargetDatabaseSafetyError as se:
        print(f"[SAFETY ABORT] {se}")
        sys.exit(1)

    # 5. Preflight check
    print("\n[STEP 4] Running Preflight Validation & Conflict Detection...")
    preflight = importer.preflight_check(records)
    print(f"  - Unique Registration Numbers:    {preflight['unique_valid_registration_numbers']}")
    print(f"  - Duplicate Registration Numbers: {preflight['duplicate_registration_numbers_count']}")
    print(f"  - Duplicate Emails:               {preflight['duplicate_emails_count']}")
    print(f"  - Existing Target Collection Rows:{preflight['existing_collection_count']}")
    print(f"  - Existing Database Conflicts:    {preflight['conflicting_records_count']}")

    if not preflight["is_preflight_valid"]:
        print("\n[PREFLIGHT FAILED] Validation issues found:")
        if preflight["duplicate_registration_numbers_count"] > 0:
            print(f"  Duplicates: {preflight['duplicate_registration_numbers']}")
        if preflight["duplicate_emails_count"] > 0:
            print(f"  Duplicate emails: {preflight['duplicate_emails']}")
        if preflight["conflicting_records_count"] > 0:
            print(f"  Conflicts: {preflight['conflicting_records']}")
        sys.exit(1)

    print("  ✓ Preflight validation passed successfully. Clean dataset ready for import.")

    # 6. Execute Import or Report Dry Run
    if not is_execute:
        print("\n" + "=" * 80)
        print(" [DRY RUN COMPLETE] Zero database writes performed.")
        print(" To execute production import into MongoDB Atlas, run with --execute.")
        print("=" * 80)
        return

    print("\n[STEP 5] Executing Production Bulk Import into MongoDB Atlas...")
    try:
        result = importer.execute_import(records)
        print("  ✓ Import successfully completed!")
        print(f"    - Import Batch ID:       {result['import_batch_id']}")
        print(f"    - Target Database:       {result['target_database']}")
        print(f"    - Target Collection:     {result['target_collection']}")
        print(f"    - Collection Count Before: {result['count_before']}")
        print(f"    - Upserted (New Inserts): {result['upserted_count']}")
        print(f"    - Matched Existing:       {result['matched_existing_count']}")
        print(f"    - Collection Count After: {result['count_after']}")
        print(f"    - Approved In DB:         {result['approved_in_db']}")
        print(f"    - Needs Review In DB:     {result['needs_review_in_db']}")
        print(f"    - Interview Eligible:     {result['interview_eligible_in_db']}")
        print(f"    - Assignment Status Unassigned: {result['interview_assignment_status_unassigned_in_db']}")
        print("\n  Created/Verified Indexes:")
        for idx in result["created_indexes"]:
            print(f"    - {idx}")

        print("\n[STEP 6] Reading Back Sanitized Sample Records from Atlas:")
        samples = importer.sample_records_sanitized(limit=3)
        for s in samples:
            print(f"    Sample Row {s['s_no']}: Reg={s['registration_number_masked']}, Email={s['email_masked']}, "
                  f"Sec={s['section']}, Status={s['review_status']}, Eligible={s['interview_eligible']}, "
                  f"Scores/Grades Excluded={not s['has_score_or_grade_fields']}")

        print("\n" + "=" * 80)
        print(" [SUCCESS] Networking Assessment dataset safely imported into MongoDB Atlas.")
        print("=" * 80)

    except Exception as e:
        print(f"\n[FATAL ERROR] Import execution failed: {type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        importer.close()


if __name__ == "__main__":
    main()
