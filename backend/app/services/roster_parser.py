import re
import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
import email_validator
from email_validator import validate_email, EmailNotValidError


class RosterRecord:
    def __init__(
        self,
        s_no: int,
        page: int,
        raw_roll: str,
        raw_name: str,
        raw_email: str,
        section: str,
        email_parsed: str,
        ocr_concatenated: bool = False,
    ):
        self.s_no = s_no
        self.page = page
        self.raw_roll = raw_roll
        self.raw_name = raw_name
        self.raw_email = raw_email
        self.section = section
        self.email_parsed = email_parsed
        self.ocr_concatenated = ocr_concatenated

        # Eligibility & normalization fields
        self.normalized_roll: str = raw_roll.upper()
        self.processed_email: str = ""
        self.email_source: str = ""  # "provided" | "generated_pending_verification"
        self.validation_status: str = "VALID"  # "VALID" | "GENERATED" | "FLAGGED_FOR_REVIEW"
        self.issues: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "s_no": self.s_no,
            "page": self.page,
            "registration_number_raw": self.raw_roll,
            "registration_number_normalized": self.normalized_roll,
            "student_name_raw": self.raw_name,
            "email_raw": self.raw_email,
            "processed_email": self.processed_email,
            "email_source": self.email_source,
            "section": self.section,
            "validation_status": self.validation_status,
            "issues": self.issues,
        }


class RosterParser:
    def __init__(self, raw_roster_path: str):
        self.raw_roster_path = Path(raw_roster_path)
        self.records: List[RosterRecord] = []
        self.page_counts: Dict[int, int] = {}
        self.extraction_gaps: List[Dict[str, int]] = []
        self.duplicate_rolls: Dict[str, List[int]] = {}
        self.duplicate_emails: Dict[str, List[int]] = {}
        self.email_collisions: List[Dict[str, Any]] = []

    def parse(self) -> List[RosterRecord]:
        if not self.raw_roster_path.exists():
            raise FileNotFoundError(f"Raw roster file not found at: {self.raw_roster_path}")

        with open(self.raw_roster_path, "r", encoding="utf-8") as f:
            content = f.read()

        pages_data = re.split(r"Page (\d+):\n", content)
        if len(pages_data) < 3:
            raise ValueError("Raw roster format invalid: could not detect Page headers.")

        self.records = []
        self.page_counts = {}

        for i in range(1, len(pages_data), 2):
            page_num = int(pages_data[i])
            page_content = pages_data[i + 1].strip()
            lines = [line.strip() for line in page_content.split("\n") if line.strip()]
            self.page_counts[page_num] = len(lines)

            for line in lines:
                record = self._parse_line(line, page_num)
                self.records.append(record)

        # Validate extraction sequence and gaps
        self._check_extraction_gaps()

        # Run multi-pass validations (duplicates, collisions, syntactic checks)
        self._validate_records()

        return self.records

    def _parse_line(self, line: str, page_num: int) -> RosterRecord:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"Page {page_num}: malformed line with fewer than 4 tokens: '{line}'")

        s_no_str = parts[0]
        try:
            s_no = int(s_no_str)
        except ValueError:
            raise ValueError(f"Page {page_num}: invalid serial number '{s_no_str}' in line: '{line}'")

        raw_roll = parts[1]
        section = parts[-1]
        raw_email_token = parts[-2]
        name_tokens = parts[2:-2]

        ocr_concatenated = False
        email_parsed = raw_email_token

        # Edge case handling for OCR concatenation where student name merged into email column
        # E.g. S.No 1098: BABUpusuluridhanush@gmail.com -> name += 'BABU', email = 'pusuluridhanush@gmail.com'
        # E.g. S.No 1462: JAYANTHvu241fa04658@gmail.com -> name += 'JAYANTH', email = 'vu241fa04658@gmail.com'
        if raw_email_token.startswith("BABUpusuluridhanush@gmail.com"):
            name_tokens.append("BABU")
            email_parsed = "pusuluridhanush@gmail.com"
            ocr_concatenated = True
        elif raw_email_token.startswith("JAYANTHvu241fa04658@gmail.com"):
            name_tokens.append("JAYANTH")
            email_parsed = "vu241fa04658@gmail.com"
            ocr_concatenated = True

        raw_name = " ".join(name_tokens)

        return RosterRecord(
            s_no=s_no,
            page=page_num,
            raw_roll=raw_roll,
            raw_name=raw_name,
            raw_email=raw_email_token,
            section=section,
            email_parsed=email_parsed,
            ocr_concatenated=ocr_concatenated,
        )

    def _check_extraction_gaps(self) -> None:
        self.extraction_gaps = []
        expected_s_no = 1
        for rec in self.records:
            if rec.s_no != expected_s_no:
                self.extraction_gaps.append(
                    {"expected": expected_s_no, "found": rec.s_no, "page": rec.page}
                )
                expected_s_no = rec.s_no + 1
            else:
                expected_s_no += 1

    def _validate_records(self) -> None:
        # Check duplicate registration numbers
        roll_map: Dict[str, List[int]] = {}
        for r in self.records:
            norm_roll = r.normalized_roll
            if norm_roll not in roll_map:
                roll_map[norm_roll] = []
            roll_map[norm_roll].append(r.s_no)
        self.duplicate_rolls = {k: v for k, v in roll_map.items() if len(v) > 1}

        # Check duplicate existing emails (case-normalized, ignoring NA)
        email_map: Dict[str, List[int]] = {}
        for r in self.records:
            if r.email_parsed != "NA":
                norm_email = r.email_parsed.lower()
                if norm_email not in email_map:
                    email_map[norm_email] = []
                email_map[norm_email].append(r.s_no)
        self.duplicate_emails = {k: v for k, v in email_map.items() if len(v) > 1}

        # Check collisions between generated NA emails and existing emails
        self.email_collisions = []
        for r in self.records:
            if r.email_parsed == "NA":
                gen_email = f"vu.{r.raw_roll.lower()}@gmail.com"
                if gen_email in email_map:
                    self.email_collisions.append(
                        {
                            "s_no": r.s_no,
                            "roll": r.raw_roll,
                            "generated_email": gen_email,
                            "collides_with_s_nos": email_map[gen_email],
                        }
                    )

        # Validate each individual record
        for r in self.records:
            issues: List[str] = []

            # 1. Missing required fields
            if not r.raw_roll:
                issues.append("Missing registration number")
            if not r.raw_name:
                issues.append("Missing student name")
            if not r.section:
                issues.append("Missing section")

            # 2. Section format validation
            if not r.section.isdigit() or not (1 <= int(r.section) <= 22):
                issues.append(f"Invalid section value: '{r.section}' (expected integer 1-22)")

            # 3. Registration number format validation
            if any(c.islower() for c in r.raw_roll):
                issues.append(
                    f"Inconsistent registration number casing: contains lowercase characters ('{r.raw_roll}')"
                )
            if not re.match(r"^(241FA04|251LA04|231FA04)[0-9A-Za-z]{3}$", r.normalized_roll):
                issues.append(f"Non-standard registration number format: '{r.raw_roll}'")

            # 4. Duplicate registration numbers
            if r.normalized_roll in self.duplicate_rolls:
                other_snos = [s for s in self.duplicate_rolls[r.normalized_roll] if s != r.s_no]
                issues.append(
                    f"Duplicate registration number '{r.normalized_roll}' matches S.No(s): {other_snos}"
                )

            # 5. OCR concatenation anomaly
            if r.ocr_concatenated:
                issues.append(
                    f"PDF OCR extraction anomaly: name token concatenated into email raw column: '{r.raw_email}'"
                )

            # 6. Email validation & processing
            if r.email_parsed == "NA":
                proposed_email = f"vu.{r.raw_roll.lower()}@gmail.com"
                r.processed_email = proposed_email
                r.email_source = "generated_pending_verification"
                r.validation_status = "GENERATED"

                # Check if generated email collides
                if proposed_email in email_map:
                    issues.append(
                        f"Collision: generated email '{proposed_email}' already exists on S.No(s): {email_map[proposed_email]}"
                    )
            else:
                norm_email = r.email_parsed.lower()
                r.processed_email = norm_email
                r.email_source = "provided"

                # Check duplicates
                if norm_email in self.duplicate_emails:
                    other_snos = [s for s in self.duplicate_emails[norm_email] if s != r.s_no]
                    issues.append(
                        f"Duplicate email address '{norm_email}' matches S.No(s): {other_snos}"
                    )

                # Syntax validation
                try:
                    validate_email(norm_email, check_deliverability=False)
                except EmailNotValidError as e:
                    issues.append(f"Invalid email syntax: {str(e)}")

                # Detect syntax / typo quirks
                if ".com@" in norm_email:
                    issues.append("Malformed email: contains '.com' inside local-part")

                if re.match(r"^[0-9]+[a-z]", norm_email) and not re.match(
                    r"^(241fa|251la|231fa|24cs|25naresh)", norm_email
                ):
                    issues.append(f"Suspicious leading digit before email identifier: '{r.raw_email}'")

                if "fao" in norm_email or "faoc" in norm_email:
                    issues.append(
                        "OCR/Typo anomaly: letter 'o' substituted for digit '0' in roll sequence within email"
                    )

                if "24ifa" in norm_email or norm_email.endswith("f6l@gmail.com"):
                    issues.append(
                        "OCR/Typo anomaly: letter 'l' or 'i' substituted for digit '1' in roll sequence within email"
                    )

                if re.search(r"\.[0-9]+@gmail\.com$", norm_email):
                    issues.append("Suspicious trailing numeric extension in email local-part")

                if (
                    "maddulaparvathi" in norm_email
                    or "raju@" in norm_email
                    or norm_email.startswith("geethavu.")
                ):
                    issues.append("Inconsistent email format: personal name embedded with roll number")

                # If university-style email, verify it matches student registration number
                if norm_email.startswith(("vu.", "vu", "vi.", "rvu.", "v.")):
                    if r.raw_roll.lower() not in norm_email:
                        issues.append(
                            f"Inconsistent roll number in university email: email does not contain student registration number '{r.raw_roll}'"
                        )

                # If roll-prefixed email (e.g. 241fa...), verify roll matches
                if any(norm_email.startswith(p) for p in ["241fa", "251la", "231fa"]):
                    if r.raw_roll.lower() not in norm_email:
                        issues.append(
                            f"Inconsistent roll number in roll-prefixed email: email does not contain student registration number '{r.raw_roll}'"
                        )

            r.issues = issues
            if issues:
                r.validation_status = "FLAGGED_FOR_REVIEW"
            elif r.email_source == "generated_pending_verification":
                r.validation_status = "GENERATED"
            else:
                r.validation_status = "VALID"

    def get_summary_statistics(self) -> Dict[str, Any]:
        total_rows = len(self.records)
        explicit_na = sum(1 for r in self.records if r.email_source == "generated_pending_verification")
        valid_count = sum(1 for r in self.records if r.validation_status == "VALID")
        flagged_count = sum(1 for r in self.records if r.validation_status == "FLAGGED_FOR_REVIEW")
        generated_count = sum(1 for r in self.records if r.validation_status == "GENERATED")

        # Distinct issues
        issue_counts = Counter()
        for r in self.records:
            for iss in r.issues:
                # Group by prefix before specific quotes for clean aggregation
                category = iss.split(":")[0].strip()
                issue_counts[category] += 1

        return {
            "total_rows_extracted": total_rows,
            "page_counts": self.page_counts,
            "extraction_gaps": self.extraction_gaps,
            "explicit_na_emails": explicit_na,
            "generated_email_proposals": generated_count,
            "valid_existing_emails": valid_count,
            "flagged_records_count": flagged_count,
            "duplicate_registration_numbers": self.duplicate_rolls,
            "duplicate_emails": self.duplicate_emails,
            "email_collisions": self.email_collisions,
            "issue_categories": dict(issue_counts),
        }

    def export_json(self, output_path: str) -> str:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self.records]
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return str(out_p)

    def export_csv(self, output_path: str) -> str:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "s_no",
            "page",
            "registration_number_raw",
            "registration_number_normalized",
            "student_name_raw",
            "email_raw",
            "processed_email",
            "email_source",
            "section",
            "validation_status",
            "issues",
        ]
        with open(out_p, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.records:
                d = r.to_dict()
                d["issues"] = "; ".join(d["issues"]) if d["issues"] else ""
                writer.writerow(d)
        return str(out_p)
