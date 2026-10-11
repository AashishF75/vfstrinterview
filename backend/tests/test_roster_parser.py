import pytest
import json
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.roster_parser import RosterParser, RosterRecord


@pytest.fixture
def parser():
    roster_path = Path(__file__).resolve().parent.parent / "data" / "raw_roster.txt"
    return RosterParser(str(roster_path))


@pytest.fixture
def parsed_records(parser):
    return parser.parse()


def test_full_roster_extraction_page_counts_and_zero_gaps(parser, parsed_records):
    """Verify all 23 pages and 1512 rows are extracted with zero serial number gaps."""
    assert len(parsed_records) == 1512
    summary = parser.get_summary_statistics()

    assert summary["total_rows_extracted"] == 1512
    assert len(summary["page_counts"]) == 23

    # Verify exact page breakdown
    assert summary["page_counts"][1] == 66
    for p in range(2, 23):
        assert summary["page_counts"][p] == 67
    assert summary["page_counts"][23] == 39

    # Verify zero extraction gaps
    assert summary["extraction_gaps"] == []

    # Verify serial numbers are exactly 1 to 1512
    for idx, record in enumerate(parsed_records, start=1):
        assert record.s_no == idx


def test_na_email_generation_and_pending_verification(parser, parsed_records):
    """Verify explicit NA emails generate vu.{roll}@gmail.com marked as generated_pending_verification."""
    summary = parser.get_summary_statistics()
    assert summary["explicit_na_emails"] == 38
    assert summary["email_collisions"] == []

    na_records = [r for r in parsed_records if r.email_source == "generated_pending_verification"]
    assert len(na_records) == 38

    for r in na_records:
        assert r.raw_email == "NA"
        expected_email = f"vu.{r.raw_roll.lower()}@gmail.com"
        assert r.processed_email == expected_email
        assert r.email_source == "generated_pending_verification"

    # Specific check on known NA row (S.No 8: VADRANAPU SAIRAM)
    rec8 = parsed_records[7]
    assert rec8.s_no == 8
    assert rec8.raw_roll == "241FA04124"
    assert rec8.raw_name == "VADRANAPU SAIRAM"
    assert rec8.raw_email == "NA"
    assert rec8.processed_email == "vu.241fa04124@gmail.com"
    assert rec8.validation_status == "GENERATED"


def test_duplicate_detection(parser, parsed_records):
    """Verify duplicate roll numbers and duplicate email detection."""
    summary = parser.get_summary_statistics()

    # All 1512 registration numbers must be strictly unique
    assert summary["duplicate_registration_numbers"] == {}

    # Exactly one duplicate email in the roster (S.No 111 and S.No 956)
    assert len(summary["duplicate_emails"]) == 1
    assert "vu.241fa04d35@gmail.com" in summary["duplicate_emails"]
    dup_snos = summary["duplicate_emails"]["vu.241fa04d35@gmail.com"]
    assert sorted(dup_snos) == [111, 956]

    rec111 = parsed_records[110]
    rec956 = parsed_records[955]
    assert rec111.raw_roll == "241FA04886"
    assert rec956.raw_roll == "241FA04D35"
    assert rec111.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("Duplicate email address" in iss for iss in rec111.issues)
    assert any("Duplicate email address" in iss for iss in rec956.issues)


def test_ocr_concatenation_handling(parsed_records):
    """Verify OCR merged name tokens in S.No 1098 and S.No 1462 are cleanly split."""
    # Row 1098: BABUpusuluridhanush@gmail.com
    rec1098 = parsed_records[1097]
    assert rec1098.s_no == 1098
    assert rec1098.raw_email == "BABUpusuluridhanush@gmail.com"
    assert "BABU" in rec1098.raw_name
    assert rec1098.email_parsed == "pusuluridhanush@gmail.com"
    assert rec1098.ocr_concatenated is True
    assert rec1098.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("PDF OCR extraction anomaly" in iss for iss in rec1098.issues)

    # Row 1462: JAYANTHvu241fa04658@gmail.com
    rec1462 = parsed_records[1461]
    assert rec1462.s_no == 1462
    assert rec1462.raw_email == "JAYANTHvu241fa04658@gmail.com"
    assert "JAYANTH" in rec1462.raw_name
    assert rec1462.email_parsed == "vu241fa04658@gmail.com"
    assert rec1462.ocr_concatenated is True
    assert rec1462.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("PDF OCR extraction anomaly" in iss for iss in rec1462.issues)


def test_malformed_and_suspicious_email_flagging(parsed_records):
    """Verify various suspicious, OCR typo, and malformed email patterns are flagged."""
    # Letter 'o' substituted for '0' in roll inside email (S.No 199)
    rec199 = parsed_records[198]
    assert "fao" in rec199.raw_email
    assert rec199.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("letter 'o' substituted for digit '0'" in iss for iss in rec199.issues)

    # Stray leading digit (S.No 389: 1vu.241fa04b56@gmail.com)
    rec389 = parsed_records[388]
    assert rec389.raw_email == "1vu.241fa04b56@gmail.com"
    assert rec389.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("Suspicious leading digit" in iss for iss in rec389.issues)

    # Syntax quirk .com inside local-part (S.No 198: vani8688969419.com@gmail.com)
    rec198 = parsed_records[197]
    assert rec198.raw_email == "vani8688969419.com@gmail.com"
    assert rec198.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("contains '.com' inside local-part" in iss for iss in rec198.issues)

    # Mismatched roll number in university email (S.No 191: roll 241FA04878 vs email vu.241fa0688@gmail.com)
    rec191 = parsed_records[190]
    assert rec191.raw_roll == "241FA04878"
    assert rec191.raw_email == "vu.241fa0688@gmail.com"
    assert rec191.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("does not contain student registration number" in iss for iss in rec191.issues)


def test_registration_number_casing_and_preservation(parsed_records):
    """Verify raw registration numbers are preserved as strings and casing anomalies flagged."""
    # S.No 977 has lowercase 'fa' in roll number: 241fa04G02
    rec977 = parsed_records[976]
    assert rec977.s_no == 977
    assert rec977.raw_roll == "241fa04G02"
    assert rec977.normalized_roll == "241FA04G02"
    assert rec977.validation_status == "FLAGGED_FOR_REVIEW"
    assert any("contains lowercase characters" in iss for iss in rec977.issues)

    # Batch prefix distribution: 1498 regular, 11 lateral entry, 3 senior/re-admitted
    prefixes = [r.normalized_roll[:5] for r in parsed_records]
    assert prefixes.count("241FA") == 1498
    assert prefixes.count("251LA") == 11
    assert prefixes.count("231FA") == 3


def test_synthetic_extraction_failures():
    """Verify error handling on non-existent files, corrupt headers, and missing lines."""
    # Non-existent file
    with pytest.raises(FileNotFoundError):
        RosterParser("non_existent_file.txt").parse()

    # Corrupt format without Page headers
    with TemporaryDirectory() as tmp_dir:
        bad_file = Path(tmp_dir) / "bad.txt"
        bad_file.write_text("1 241FA04001 TEST USER test@gmail.com 1", encoding="utf-8")
        with pytest.raises(ValueError, match="could not detect Page headers"):
            RosterParser(str(bad_file)).parse()

    # Artificial gap detection
    with TemporaryDirectory() as tmp_dir:
        gap_file = Path(tmp_dir) / "gap.txt"
        gap_content = (
            "Page 1:\n"
            "1 241FA04001 STUDENT ONE vu.241fa04001@gmail.com 1\n"
            "3 241FA04003 STUDENT THREE vu.241fa04003@gmail.com 1\n"
        )
        gap_file.write_text(gap_content, encoding="utf-8")
        gap_parser = RosterParser(str(gap_file))
        records = gap_parser.parse()
        assert len(records) == 2
        assert len(gap_parser.extraction_gaps) == 1
        assert gap_parser.extraction_gaps[0]["expected"] == 2
        assert gap_parser.extraction_gaps[0]["found"] == 3


def test_synthetic_collision_and_duplicate_rolls():
    """Verify detection of duplicate roll numbers and collisions between generated and existing emails."""
    with TemporaryDirectory() as tmp_dir:
        dup_file = Path(tmp_dir) / "dup.txt"
        content = (
            "Page 1:\n"
            "1 241FA04001 STUDENT ONE vu.241fa04001@gmail.com 1\n"
            "2 241FA04001 STUDENT DUPLICATE_ROLL vu.other@gmail.com 1\n"
            "3 241FA04002 STUDENT WITH_NA NA 1\n"
            "4 241FA04099 STUDENT PRE_EXISTING vu.241fa04002@gmail.com 1\n"
        )
        dup_file.write_text(content, encoding="utf-8")
        p = RosterParser(str(dup_file))
        recs = p.parse()

        # Check duplicate roll detection
        assert "241FA04001" in p.duplicate_rolls
        assert p.duplicate_rolls["241FA04001"] == [1, 2]

        # Check collision detection between generated vu.241fa04002@gmail.com and rec 4
        assert len(p.email_collisions) == 1
        assert p.email_collisions[0]["s_no"] == 3
        assert p.email_collisions[0]["generated_email"] == "vu.241fa04002@gmail.com"
        assert p.email_collisions[0]["collides_with_s_nos"] == [4]


def test_preview_export_files_integrity(parser, parsed_records):
    """Verify that export_json and export_csv produce complete, valid datasets."""
    with TemporaryDirectory() as tmp_dir:
        json_path = Path(tmp_dir) / "preview.json"
        csv_path = Path(tmp_dir) / "preview.csv"

        parser.export_json(str(json_path))
        parser.export_csv(str(csv_path))

        assert json_path.exists()
        assert csv_path.exists()

        # Verify JSON
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1512
        assert data[0]["s_no"] == 1
        assert data[0]["registration_number_raw"] == "241FA04035"
        assert "password" not in data[0]
        assert "token" not in data[0]

        # Verify CSV
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        assert len(reader) == 1512
        assert reader[0]["registration_number_raw"] == "241FA04035"
