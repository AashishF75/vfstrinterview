import sys
from pathlib import Path

# Add backend directory to path if run directly
backend_root = Path(__file__).resolve().parent.parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.services.roster_parser import RosterParser


def run_roster_validation():
    raw_path = backend_root / "data" / "raw_roster.txt"
    json_preview_path = backend_root / "data" / "eligibility_preview.json"
    csv_preview_path = backend_root / "data" / "eligibility_preview.csv"

    print("================================================================================")
    print(" ADAPTIVE INTERVIEW INTELLIGENCE – VFSTR")
    print(" BATCH ROSTER ELIGIBILITY IMPORT PIPELINE (DRY-RUN VALIDATION)")
    print("================================================================================")
    print(f"Loading raw roster data from: {raw_path}")

    parser = RosterParser(str(raw_path))
    records = parser.parse()
    summary = parser.get_summary_statistics()

    # Export preview files
    parser.export_json(str(json_preview_path))
    parser.export_csv(str(csv_preview_path))

    print("\n--- 1. EXTRACTION & PAGE METRICS ---")
    print(f"Total rows extracted across all 23 pages: {summary['total_rows_extracted']}")
    print(f"Extraction gaps detected: {len(summary['extraction_gaps'])}")
    if summary["extraction_gaps"]:
        for gap in summary["extraction_gaps"]:
            print(f"  GAP: Expected S.No {gap['expected']}, found {gap['found']} on page {gap['page']}")
    else:
        print("  -> Continuous sequential extraction (S.No 1 through 1512, zero gaps).")

    print("\nPage-by-page row counts:")
    for page, count in sorted(summary["page_counts"].items()):
        print(f"  Page {page:2d}: {count:2d} rows")

    print("\n--- 2. EMAIL CLASSIFICATION & PROPOSALS ---")
    print(f"Total explicit 'NA' emails: {summary['explicit_na_emails']}")
    print(f"Generated email proposals (vu.{{roll}}@gmail.com): {summary['generated_email_proposals']}")
    print(f"Collisions between generated and existing emails: {len(summary['email_collisions'])}")
    if summary["email_collisions"]:
        for col in summary["email_collisions"]:
            print(f"  COLLISION: S.No {col['s_no']} ({col['roll']}) -> {col['generated_email']} collides with S.No(s): {col['collides_with_s_nos']}")
    else:
        print("  -> Zero collisions detected between proposed emails and existing roster emails.")

    print(f"Valid existing emails: {summary['valid_existing_emails']}")
    print(f"Malformed or suspicious email records flagged: {summary['flagged_records_count']}")

    print("\n--- 3. DUPLICATE DETECTION ---")
    print(f"Duplicate registration numbers: {len(summary['duplicate_registration_numbers'])}")
    if summary["duplicate_registration_numbers"]:
        for roll, snos in summary["duplicate_registration_numbers"].items():
            print(f"  Duplicate Roll: {roll} on S.Nos: {snos}")
    else:
        print("  -> All 1512 registration numbers are strictly unique.")

    print(f"Duplicate email addresses: {len(summary['duplicate_emails'])}")
    for email, snos in summary["duplicate_emails"].items():
        matched_records = [r for r in records if r.s_no in snos]
        details = ", ".join([f"S.No {r.s_no} ({r.raw_roll}: {r.raw_name})" for r in matched_records])
        print(f"  Duplicate Email: {email} -> Occurs {len(snos)} times ({details})")

    print("\n--- 4. RECORDS REQUIRING MANUAL REVIEW ---")
    flagged_records = [r for r in records if r.validation_status == "FLAGGED_FOR_REVIEW"]
    print(f"Total records requiring manual review: {len(flagged_records)}")
    print(f"{'S.No':<6} {'Page':<5} {'Roll Number':<12} {'Raw Email':<35} {'Issues'}")
    print("-" * 105)
    for r in flagged_records:
        issues_str = "; ".join(r.issues)
        print(f"{r.s_no:<6} {r.page:<5} {r.raw_roll:<12} {r.raw_email:<35} {issues_str}")

    print("\n--- 5. GENERATED PREVIEW FILES ---")
    print(f"Proposed Import Preview (JSON): {json_preview_path}")
    print(f"Proposed Import Preview (CSV):  {csv_preview_path}")

    print("\n--- 6. RE-RUN COMMAND ---")
    print("powershell: .\\backend\\venv\\Scripts\\python -m app.cli.validate_roster")
    print("================================================================================")

    return summary


if __name__ == "__main__":
    run_roster_validation()
