import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from app.models.eligibility import (
    ApprovalDecision,
    ApprovalMetadata,
    ReviewGroup,
    utc_now,
)
from app.services.roster_resolver import generate_flagged_records_resolution


class AdminReviewManager:
    """Manages administrative review, approval, and audit trails for flagged roster records."""

    def __init__(self, manifest_path: Optional[str] = None):
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.entries: Dict[int, Dict[str, Any]] = {}

    @classmethod
    def create_initial_manifest(
        cls,
        preview_json_path: str,
        output_manifest_path: str,
    ) -> "AdminReviewManager":
        """
        Generates an initial review manifest from preview records.
        All 64 flagged records start with decision: PENDING and null admin identity.
        """
        resolution_data = generate_flagged_records_resolution(preview_json_path)
        manifest_entries = {}

        for rec in resolution_data["records"]:
            sno = rec["s_no"]
            group = (
                ReviewGroup.PROPOSED_UNAMBIGUOUS.value
                if rec["resolution_status"] == "PROPOSED_UNAMBIGUOUS"
                else ReviewGroup.MANUAL_REVIEW.value
            )

            manifest_entries[sno] = {
                "s_no": sno,
                "page": rec["page"],
                "section": rec["section"],
                "registration_number": rec["registration_number_normalized"],
                "student_name": rec["student_name_raw"],
                "review_group": group,
                "issue_category": rec["issue_category"],
                "source_roster_value": rec["email_raw"],
                "proposed_value": rec["proposed_resolution"],
                "administrator_decision": ApprovalDecision.PENDING.value,
                "reviewed_by_admin_id": None,
                "reason": None,
                "timestamp": None,
                "effective_value": None,
            }

        mgr = cls(output_manifest_path)
        mgr.entries = manifest_entries
        mgr.save()
        return mgr

    def load(self) -> None:
        if not self.manifest_path or not self.manifest_path.exists():
            raise FileNotFoundError(f"Review manifest file not found: {self.manifest_path}")

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.entries = {item["s_no"]: item for item in data.get("reviews", [])}

    def save(self) -> None:
        if not self.manifest_path:
            raise ValueError("Manifest path not set.")

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": "1.0",
            "institution_id": "VFSTR",
            "batch_cohort": "2024-2028",
            "total_reviewable_records": len(self.entries),
            "approved_count": len(self.get_approved_records()),
            "rejected_count": len(self.get_rejected_records()),
            "pending_count": len(self.get_pending_records()),
            "updated_at": utc_now().isoformat(),
            "reviews": list(self.entries.values()),
        }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record_decision(
        self,
        s_no: int,
        admin_id: str,
        decision: ApprovalDecision,
        reason: str,
        approved_value: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records an administrator's explicit decision on a flagged row.
        Rejects empty administrator identity or missing rationale.
        """
        if s_no not in self.entries:
            raise KeyError(f"Record with S.No {s_no} not found in review manifest.")

        if not admin_id or not admin_id.strip():
            raise ValueError("Administrator ID is mandatory. Cannot record anonymous approval.")

        if not reason or not reason.strip():
            raise ValueError("Justification reason is mandatory for every review decision.")

        entry = self.entries[s_no]
        now_iso = utc_now().isoformat()

        entry["administrator_decision"] = decision.value
        entry["reviewed_by_admin_id"] = admin_id.strip()
        entry["reason"] = reason.strip()
        entry["timestamp"] = now_iso

        if decision == ApprovalDecision.APPROVED:
            # If approved_value not specified, fallback to proposed_value
            val = approved_value.strip() if approved_value else entry["proposed_value"].strip()
            # Clean up candidate proposal notes if present
            if "(" in val:
                val = val.split("(")[0].strip()
            entry["effective_value"] = val
        else:
            entry["effective_value"] = None

        return entry

    def validate_decisions(self) -> List[str]:
        """Validates all recorded decisions for audit compliance."""
        errors = []
        for sno, item in self.entries.items():
            dec = item.get("administrator_decision")
            if dec in (ApprovalDecision.APPROVED.value, ApprovalDecision.REJECTED.value):
                if not item.get("reviewed_by_admin_id"):
                    errors.append(f"S.No {sno}: {dec} without administrator identity.")
                if not item.get("reason"):
                    errors.append(f"S.No {sno}: {dec} without documented rationale reason.")
                if not item.get("timestamp"):
                    errors.append(f"S.No {sno}: {dec} without audit timestamp.")
                if dec == ApprovalDecision.APPROVED.value and not item.get("effective_value"):
                    errors.append(f"S.No {sno}: Approved record missing effective_value email.")
        return errors

    def get_approved_records(self) -> List[Dict[str, Any]]:
        return [
            r for r in self.entries.values()
            if r.get("administrator_decision") == ApprovalDecision.APPROVED.value
        ]

    def get_rejected_records(self) -> List[Dict[str, Any]]:
        return [
            r for r in self.entries.values()
            if r.get("administrator_decision") == ApprovalDecision.REJECTED.value
        ]

    def get_pending_records(self) -> List[Dict[str, Any]]:
        return [
            r for r in self.entries.values()
            if r.get("administrator_decision") == ApprovalDecision.PENDING.value
        ]
