import sys
import argparse
import asyncio
import json
from pathlib import Path

# Add backend directory to path if run directly
backend_root = Path(__file__).resolve().parent.parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.services.roster_parser import RosterParser
from app.services.roster_resolver import generate_flagged_records_resolution
from app.services.admin_review_manager import AdminReviewManager
from app.services.eligibility_importer import (
    EligibilityImporter,
    EligibilityPreflightFailedError,
    EligibilityIndexCreationError,
    EligibilityBulkWriteFailedError,
)
from app.core.config import settings


async def main():
    parser = argparse.ArgumentParser(
        description="Adaptive Interview Intelligence – VFSTR Eligibility Roster Importer"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run preflight validation without writing to MongoDB (default: True)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute actual import into MongoDB eligibility_registry collection (requires confirmation)",
    )
    parser.add_argument(
        "--review-manifest",
        type=str,
        default="backend/data/admin_review_manifest.json",
        help="Path to signed administrative review manifest JSON file",
    )
    parser.add_argument(
        "--stage-unresolved",
        action="store_true",
        help="Additionally stage unapproved records as ineligible for registration (is_eligible_for_registration=False)",
    )
    parser.add_argument(
        "--rollback-batch",
        type=str,
        help="Rollback unclaimed eligibility records for a specific import batch ID",
    )

    args = parser.parse_args()

    print("================================================================================")
    print(" ADAPTIVE INTERVIEW INTELLIGENCE – VFSTR")
    print(" ELIGIBILITY ROSTER SAFE IMPORT PIPELINE")
    print("================================================================================")
    diag = settings.get_sanitized_diagnostic()
    print(f"Configuration Source:  {diag['config_file_path']}")
    print(f"Resolved Target Type:  {diag['target_database_type']}")
    print(f"Target Database Name:  {diag['database_name']}")
    print("================================================================================")

    # 1. Load preview records
    preview_path = backend_root / "data" / "eligibility_preview.json"
    if not preview_path.exists():
        print(f"Error: Eligibility preview not found at {preview_path}. Run parser first.")
        sys.exit(1)

    with open(preview_path, "r", encoding="utf-8") as f:
        preview_records = json.load(f)

    # 2. Load flagged resolution metadata
    flagged_res_path = backend_root / "data" / "flagged_records_resolution.json"
    flagged_records = []
    if flagged_res_path.exists():
        with open(flagged_res_path, "r", encoding="utf-8") as f:
            flagged_records = json.load(f).get("records", [])

    # 3. Load admin review manifest if present
    manifest_path = backend_root / "data" / "admin_review_manifest.json"
    review_mgr = None
    if manifest_path.exists():
        review_mgr = AdminReviewManager(str(manifest_path))
        review_mgr.load()

    # 4. Partition into review groups
    partitions = EligibilityImporter.partition_records_by_review_status(
        preview_records=preview_records,
        flagged_resolution_records=flagged_records,
        review_manager=review_mgr,
    )

    ready = partitions["READY_FOR_IMPORT"]
    proposed = partitions["PROPOSED_UNAMBIGUOUS"]
    manual = partitions["MANUAL_REVIEW"]
    approved = partitions["APPROVED_ADDITIONS"]

    print("\n--- 1. ROSTER PARTITION BY REVIEW STATUS ---")
    print(f"Total Student Records:        {len(preview_records)}")
    print(f"  [READY_FOR_IMPORT]:         {len(ready)} (Clean validated records, 0 issues)")
    print(f"  [PROPOSED_UNAMBIGUOUS]:     {len(proposed)} (Awaiting admin approval)")
    print(f"  [MANUAL_REVIEW]:            {len(manual)} (Awaiting admin decision)")
    print(f"  [APPROVED_ADDITIONS]:       {len(approved)} (Flagged records approved by admin)")

    # Records eligible for active import
    candidate_import_records = list(ready) + list(approved)
    print(f"\nCandidate Approved Import Total: {len(candidate_import_records)} records")

    # 5. Handle rollback action
    if args.rollback_batch:
        if not settings.CONFIG_FILE_LOADED or not settings.is_remote_or_atlas:
            print("\n[BLOCKED BY FAIL-SAFE] Batch rollback refused:")
            print(f"  Reason: Database target is not configured for remote MongoDB Atlas ({settings.target_database_type}).")
            sys.exit(1)
        print(f"\n[ACTION] Rolling back batch ID: {args.rollback_batch}")
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DB_NAME]
        res = await EligibilityImporter.rollback_import_batch(args.rollback_batch, db)
        print(f"Rollback complete: {res['message']}")
        return

    # 6. Dry-run mode
    if not args.execute:
        print("\n--- 2. PREFLIGHT DRY-RUN EVALUATION ---")
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DB_NAME]

        dry_run_report = await EligibilityImporter.dry_run(
            candidate_import_records, db=db, allow_unapproved=False
        )

        print(f"Preflight Validation Status:    {'PASSED' if dry_run_report['dry_run_success'] else 'FAILED'}")
        print(f"Records Evaluated:              {dry_run_report['records_evaluated']}")
        print(f"Projected New Inserts:          {dry_run_report['projected_new_inserts']}")
        print(f"Projected Matched/Resumes:      {dry_run_report['projected_matched_resumes']}")
        print(f"Preflight Error Count:          {dry_run_report['preflight_errors_count']}")

        if dry_run_report["preflight_errors"]:
            print("\nPreflight Issues Detected:")
            for err in dry_run_report["preflight_errors"][:10]:
                print(f"  - {err}")

        print(f"\nUnique Indexes Required:")
        for idx in dry_run_report["indexes_required"]:
            print(f"  - {idx}")

        print(f"\nIdempotency Strategy: {dry_run_report['idempotency_strategy']}")
        print(f"Rollback Strategy:    {dry_run_report['rollback_strategy']}")
        print("\n[NOTE] Dry-run executed successfully. Zero records were written to MongoDB.")
        print("To execute import once authorized: rerun with --execute")
        print("================================================================================")
        return

    # 7. Execution mode (guarded)
    print("\n--- 3. EXECUTING LIVE DATABASE IMPORT ---")
    if not settings.CONFIG_FILE_LOADED or not settings.is_remote_or_atlas:
        print("\n[BLOCKED BY FAIL-SAFE] Production execution refused:")
        if not settings.CONFIG_FILE_LOADED:
            print(f"  Reason: Configuration file not loaded or not found at '{settings.CONFIG_FILE_PATH}'.")
        if not settings.is_remote_or_atlas:
            print(f"  Reason: Database target resolved to localhost ({settings.target_database_type}).")
        print("  Production import requires an active remote MongoDB Atlas configuration.")
        print("  Check that 'backend/.env' contains the valid Atlas connection URI before running --execute.")
        print("  Live database write aborted. Zero records written.")
        sys.exit(1)

    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]

    try:
        import_res = await EligibilityImporter.execute_import(
            records_to_import=candidate_import_records,
            db=db,
            allow_unapproved=False,
        )
        print("Import completed successfully!")
        print(f"  Batch ID:          {import_res['import_batch_id']}")
        print(f"  Records Processed: {import_res['records_processed']}")
        print(f"  Inserted (New):    {import_res['inserted_count']}")
        print(f"  Matched (Resumed): {import_res['matched_existing_count']}")

        if args.stage_unresolved:
            unresolved = list(proposed) + list(manual)
            stage_res = await EligibilityImporter.stage_unresolved_records(
                unresolved, db=db, batch_id=import_res["import_batch_id"]
            )
            print(f"  Staged Unresolved (Ineligible for registration): {stage_res['staged_count']}")

    except EligibilityPreflightFailedError as e:
        print(f"\n[ABORTED] Import halted prior to database write due to preflight errors:")
        for err in e.errors:
            print(f"  - {err}")
        sys.exit(1)
    except EligibilityIndexCreationError as e:
        print(f"\n[ABORTED] Import halted due to index creation failure prior to roster record writes:")
        print(f"  - {str(e)}")
        sys.exit(1)
    except EligibilityBulkWriteFailedError as e:
        print(f"\n[PARTIAL FAILURE] Bulk write failed during import for batch '{e.batch_id}':")
        print(f"  - Inserted so far: {e.inserted_count}")
        print(f"  - Matched so far:  {e.matched_count}")
        print(f"  - Failed items:    {e.failed_count}")
        print(f"To safely undo partial writes from this batch without touching pre-existing records:")
        print(f"  python backend/app/cli/import_roster_cli.py --rollback-batch {e.batch_id}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
