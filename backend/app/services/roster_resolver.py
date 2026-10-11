import json
from pathlib import Path
from typing import Dict, List, Any


def generate_flagged_records_resolution(preview_json_path: str) -> Dict[str, Any]:
    preview_path = Path(preview_json_path)
    if not preview_path.exists():
        raise FileNotFoundError(f"Preview JSON not found at: {preview_path}")

    with open(preview_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    flagged_records = [r for r in records if r["validation_status"] == "FLAGGED_FOR_REVIEW"]

    reviewed_records = []
    category_counts = {}

    for r in flagged_records:
        sno = r["s_no"]
        page = r["page"]
        sec = r["section"]
        roll = r["registration_number_raw"]
        norm_roll = r["registration_number_normalized"]
        name = r["student_name_raw"]
        email = r["email_raw"]
        issues = r["issues"]

        cat = ""
        proposed_resolution = ""
        resolution_status = "PROPOSED_UNAMBIGUOUS"  # "PROPOSED_UNAMBIGUOUS" or "MANUAL_REVIEW"
        rationale = ""

        # 1. OCR Typo Substitution ('o' for '0')
        if any("letter 'o' substituted for digit '0'" in iss for iss in issues):
            cat = "OCR Typo Substitution ('o' for '0')"
            proposed_resolution = f"vu.{roll.lower()}@gmail.com"
            resolution_status = "PROPOSED_UNAMBIGUOUS"
            rationale = (
                f"OCR letter 'o' in '{email}' replaces digit '0'. "
                f"Can be unambiguously derived from registration number {roll}."
            )

        # 2. OCR Typo Substitution ('l' or 'i' for '1')
        elif any("letter 'l' or 'i' substituted for digit '1'" in iss for iss in issues):
            cat = "OCR Typo Substitution ('l'/'i' for '1')"
            proposed_resolution = f"vu.{roll.lower()}@gmail.com"
            resolution_status = "PROPOSED_UNAMBIGUOUS"
            rationale = (
                f"OCR letter 'l'/'i' in '{email}' replaces digit '1'. "
                f"Unambiguously derived from registration number {roll}."
            )

        # 3. Leading stray digits
        elif any("Suspicious leading digit" in iss for iss in issues):
            if email.lower().startswith("1vu.") or email.lower().startswith("1vu"):
                cat = "OCR Prefix Artifact (Leading '1')"
                proposed_resolution = f"vu.{roll.lower()}@gmail.com"
                resolution_status = "PROPOSED_UNAMBIGUOUS"
                rationale = f"OCR scanner prepended stray '1' to 'vu.'. Derived from registration number {roll}."
            else:
                cat = "Suspicious Leading Digit in Personal Email"
                proposed_resolution = "MANUAL_REVIEW"
                resolution_status = "MANUAL_REVIEW"
                rationale = (
                    f"Email '{email}' starts with digit '3'. Cannot determine if student intended "
                    "this personal address or if '3' is an artifact. Requires manual student verification."
                )

        # 4. OCR Column Concatenation
        elif any("PDF OCR extraction anomaly" in iss for iss in issues):
            cat = "OCR Column Concatenation"
            if sno == 1098:
                proposed_resolution = "MANUAL_REVIEW"
                resolution_status = "MANUAL_REVIEW"
                rationale = (
                    "Student name token 'BABU' merged into raw email column. "
                    "Extracted email is 'pusuluridhanush@gmail.com'. Requires administrator confirmation whether "
                    f"to accept this personal email or assign default vu.{roll.lower()}@gmail.com."
                )
            elif sno == 1462:
                proposed_resolution = f"vu.{roll.lower()}@gmail.com"
                resolution_status = "PROPOSED_UNAMBIGUOUS"
                rationale = (
                    "Student name token 'JAYANTH' merged into raw email column. "
                    f"Remaining email 'vu241fa04658@gmail.com' matches registration number {roll}."
                )

        # 5. Duplicate Email Conflict
        elif any("Duplicate email address" in iss for iss in issues):
            cat = "Duplicate Email Conflict"
            if sno == 956:
                proposed_resolution = "vu.241fa04d35@gmail.com"
                resolution_status = "PROPOSED_UNAMBIGUOUS"
                rationale = (
                    f"Student roll {roll} matches 'vu.241fa04d35@gmail.com' exactly. "
                    "Legitimate verified owner of this university email."
                )
            elif sno == 111:
                proposed_resolution = "MANUAL_REVIEW"
                resolution_status = "MANUAL_REVIEW"
                rationale = (
                    f"Student roll {roll} ({name}) was erroneously listed with S.No 956's email. "
                    f"Recommended candidate proposal is 'vu.{roll.lower()}@gmail.com', pending student/department verification. "
                    "Must NOT be assigned S.No 956's email."
                )

        # 6. Lowercase registration number
        elif any("contains lowercase characters" in iss for iss in issues):
            cat = "Registration Number Casing Anomaly"
            proposed_resolution = f"vu.{roll.lower()}@gmail.com"
            resolution_status = "PROPOSED_UNAMBIGUOUS"
            rationale = (
                f"Source registration number '{roll}' contains lowercase characters. "
                f"Normalized string is '{norm_roll}', generating proposal 'vu.{roll.lower()}@gmail.com'."
            )

        # 7. Truncated or slight typo in roll part of university email
        elif any("Inconsistent roll number in university email" in iss for iss in issues):
            norm_email = email.lower()
            if (
                norm_email.startswith("vu.24fa")
                or norm_email.startswith("vu24fa")
                or norm_email.startswith("vu.241fa4")
                or norm_email.startswith("vu.241f0")
                or norm_email.startswith("vu.241fa0b")
                or norm_email.startswith("vu.241fa0c")
                or norm_email.startswith("vu.241fa0e")
                or norm_email.startswith("vu.241fa02")
                or norm_email.startswith("vu.241fa04b0@")
            ):
                cat = "Truncated/Typo in University Email Roll Number"
                proposed_resolution = f"vu.{roll.lower()}@gmail.com"
                resolution_status = "PROPOSED_UNAMBIGUOUS"
                rationale = (
                    f"University email '{email}' attempted to use student's roll number but dropped a character or digit. "
                    f"Unambiguously reconstructs to 'vu.{roll.lower()}@gmail.com'."
                )
            else:
                cat = "Mismatched Roll Number in University Email"
                proposed_resolution = "MANUAL_REVIEW"
                resolution_status = "MANUAL_REVIEW"
                rationale = (
                    f"University email '{email}' contains a completely different roll number, department code, or batch year "
                    f"than student's official registration number {roll}. Requires department manual review."
                )

        # 8. All other anomalies
        else:
            cat = "Syntax or Personal Name Embedded Anomaly"
            proposed_resolution = "MANUAL_REVIEW"
            resolution_status = "MANUAL_REVIEW"
            rationale = f"Email '{email}' has non-standard formatting. Requires manual administrator review."

        category_counts[cat] = category_counts.get(cat, 0) + 1

        reviewed_records.append(
            {
                "s_no": sno,
                "page": page,
                "section": sec,
                "registration_number_raw": roll,
                "registration_number_normalized": norm_roll,
                "student_name_raw": name,
                "email_raw": email,
                "issue_category": cat,
                "resolution_status": resolution_status,
                "proposed_resolution": proposed_resolution,
                "rationale": rationale,
                "original_issues": issues,
            }
        )

    return {
        "total_flagged_records": len(flagged_records),
        "category_counts": category_counts,
        "unambiguous_proposals_count": sum(
            1 for r in reviewed_records if r["resolution_status"] == "PROPOSED_UNAMBIGUOUS"
        ),
        "manual_review_required_count": sum(
            1 for r in reviewed_records if r["resolution_status"] == "MANUAL_REVIEW"
        ),
        "records": reviewed_records,
    }


def write_resolution_artifacts(preview_json_path: str, output_dir: str) -> Dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = generate_flagged_records_resolution(preview_json_path)

    json_out = out_dir / "flagged_records_resolution.json"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    md_out = out_dir / "flagged_roster_resolution_report.md"
    with open(md_out, "w", encoding="utf-8") as f:
        f.write("# CSE 2024–28 Batch Eligibility Roster Flagged Records Resolution Report\n\n")
        f.write("## Overview\n")
        f.write(f"- Total Flagged Records: {data['total_flagged_records']}\n")
        f.write(f"- Unambiguous Derived Proposals: {data['unambiguous_proposals_count']}\n")
        f.write(f"- Manual Review Required: {data['manual_review_required_count']}\n\n")

        f.write("## Issue Categories\n")
        for cat, cnt in sorted(data["category_counts"].items()):
            f.write(f"- **{cat}**: {cnt} record(s)\n")
        f.write("\n")

        f.write("## Detailed Flagged Records Review\n\n")
        f.write("| S.No | Page | Sec | Roll Number | Student Name | Raw Email | Issue Category | Proposed Resolution | Status |\n")
        f.write("|:---:|:---:|:---:|:---:|:---|:---|:---|:---|:---:|\n")
        for r in data["records"]:
            res_str = r["proposed_resolution"]
            f.write(
                f"| {r['s_no']} | {r['page']} | {r['section']} | `{r['registration_number_raw']}` | {r['student_name_raw']} | `{r['email_raw']}` | {r['issue_category']} | `{res_str}` | **{r['resolution_status']}** |\n"
            )

    return {"json": str(json_out), "markdown": str(md_out)}
