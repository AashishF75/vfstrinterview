import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from pypdf import PdfReader
from email_validator import validate_email, EmailNotValidError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NetworkingAssessmentRecord:
    def __init__(
        self,
        s_no: int,
        source_page: int,
        source_row: int,
        source_file: str,
        raw_reg_no: str,
        raw_email: str,
        raw_section: str,
    ):
        self.s_no = s_no
        self.source_page = source_page
        self.source_row = source_row
        self.source_file = source_file
        self.raw_reg_no = raw_reg_no
        self.raw_email = raw_email
        self.raw_section = raw_section

        # Normalized values
        self.registration_number: str = ""
        self.email: str = raw_email.strip().lower()
        self.section: str = raw_section.strip()
        
        # Audit & categorization
        self.email_status: str = "provided_unverified"  # provided_unverified | missing | invalid
        self.review_status: str = "approved"            # approved | needs_review | pending
        self.interview_eligible: bool = True
        self.interview_assignment_status: str = "unassigned"
        self.batch_cohort: str = "2024-2028"
        self.department: str = "CSE"
        self.review_reasons: List[str] = []

        self._validate_and_classify()

    def _validate_and_classify(self):
        clean_reg = self.raw_reg_no.strip()

        # 1. Registration Number validation
        if not clean_reg or clean_reg.upper() in ["#N/A", "NA", "N/A"]:
            self.registration_number = "#N/A"
            self.batch_cohort = "UNKNOWN"
            self.review_status = "needs_review"
            self.interview_eligible = False
            self.review_reasons.append("MISSING_REGISTRATION_NUMBER")
        else:
            self.registration_number = clean_reg.upper()
            
            # Batch identification
            if self.registration_number.startswith("241FA"):
                self.batch_cohort = "2024-2028"
            elif self.registration_number.startswith("231FA"):
                self.batch_cohort = "2023-2027"
                self.review_status = "needs_review"
                self.interview_eligible = False
                self.review_reasons.append("UNEXPECTED_BATCH_2023")
            elif self.registration_number.startswith("251LA"):
                self.batch_cohort = "2024-2028_LATERAL"
                self.review_status = "needs_review"
                self.interview_eligible = False
                self.review_reasons.append("LATERAL_ENTRY_BATCH_2025")
            else:
                self.review_status = "needs_review"
                self.interview_eligible = False
                self.review_reasons.append("NON_STANDARD_ROLL_FORMAT")

        # 2. Section validation
        clean_sec = self.raw_section.strip()
        if clean_sec in ["#N/A", "NA", "N/A", ""]:
            self.section = "#N/A"
            if "MISSING_SECTION" not in self.review_reasons:
                self.review_reasons.append("MISSING_SECTION")
        else:
            self.section = clean_sec

        # 3. Email syntax validation
        if not self.email or self.email in ["#n/a", "na", "n/a"]:
            self.email_status = "missing"
            self.review_status = "needs_review"
            self.interview_eligible = False
            self.review_reasons.append("MISSING_EMAIL")
        else:
            try:
                validate_email(self.email, check_deliverability=False)
                self.email_status = "provided_unverified"
            except EmailNotValidError as e:
                self.email_status = "invalid"
                self.review_status = "needs_review"
                self.interview_eligible = False
                self.review_reasons.append(f"MALFORMED_EMAIL: {str(e)}")

    def to_mongo_doc(self, import_batch_id: str) -> Dict[str, Any]:
        """
        Converts the record into the required MongoDB document schema.
        Scores and grades are intentionally excluded to satisfy privacy & governance requirements.
        """
        now = utc_now()
        return {
            "registration_number": self.registration_number,
            "email": self.email,
            "section": self.section,
            "source_file": self.source_file,
            "source_page": self.source_page,
            "source_row": self.source_row,
            "email_status": self.email_status,
            "review_status": self.review_status,
            "interview_eligible": self.interview_eligible,
            "interview_assignment_status": self.interview_assignment_status,
            "import_batch_id": import_batch_id,
            "created_at": now,
            "updated_at": now,
            # Audit metadata
            "s_no": self.s_no,
            "raw_registration_number": self.raw_reg_no,
            "raw_email": self.raw_email,
            "batch_cohort": self.batch_cohort,
            "department": self.department,
            "review_reasons": self.review_reasons,
        }


class NetworkingAssessmentParser:
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.records: List[NetworkingAssessmentRecord] = []
        self.page_counts: Dict[int, int] = {}

    def parse(self) -> List[NetworkingAssessmentRecord]:
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF roster file not found at: {self.pdf_path}")

        reader = PdfReader(str(self.pdf_path))
        self.records = []
        self.page_counts = {}

        source_filename = self.pdf_path.name

        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            text = page.extract_text()
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            row_on_page = 0
            page_records_count = 0

            for line in lines:
                parts = line.split()
                if not parts:
                    continue

                # Data rows start with an integer S.No.
                if not parts[0].isdigit():
                    continue

                row_on_page += 1
                s_no = int(parts[0])

                reg_no_raw = parts[1] if len(parts) > 1 else ""
                email_raw = parts[2] if len(parts) > 2 else ""
                section_raw = parts[3] if len(parts) > 3 else ""

                record = NetworkingAssessmentRecord(
                    s_no=s_no,
                    source_page=page_num,
                    source_row=row_on_page,
                    source_file=source_filename,
                    raw_reg_no=reg_no_raw,
                    raw_email=email_raw,
                    raw_section=section_raw,
                )
                self.records.append(record)
                page_records_count += 1

            self.page_counts[page_num] = page_records_count

        return self.records

    def get_summary_metrics(self) -> Dict[str, Any]:
        total = len(self.records)
        approved = sum(1 for r in self.records if r.review_status == "approved")
        needs_review = sum(1 for r in self.records if r.review_status == "needs_review")
        eligible = sum(1 for r in self.records if r.interview_eligible)

        batch_counts: Dict[str, int] = {}
        for r in self.records:
            batch_counts[r.batch_cohort] = batch_counts.get(r.batch_cohort, 0) + 1

        review_reason_counts: Dict[str, int] = {}
        for r in self.records:
            for reason in r.review_reasons:
                review_reason_counts[reason] = review_reason_counts.get(reason, 0) + 1

        missing_reg_nos = sum(1 for r in self.records if r.registration_number == "#N/A")

        return {
            "total_extracted_rows": total,
            "total_pages": len(self.page_counts),
            "approved_records": approved,
            "needs_review_records": needs_review,
            "interview_eligible_records": eligible,
            "missing_registration_numbers": missing_reg_nos,
            "batch_breakdown": batch_counts,
            "review_reasons": review_reason_counts,
            "page_counts": self.page_counts,
        }
