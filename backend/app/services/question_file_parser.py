import io
import json
import csv
import re
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pypdf import PdfReader

from app.models.interview_session import QuestionDifficulty


ROLE_CANONICAL_NAMES = {
    "associate_software_engineer": "Associate Software Engineer",
    "software_development_engineer": "Software Development Engineer",
    "product_engineer": "Product Engineer",
    "system_engineer": "System Engineer",
    "testing_engineer": "Testing Engineer",
}


def _detect_difficulty(text: str) -> Optional[QuestionDifficulty]:
    lower = text.lower()
    # Explicit bracket tags e.g. [Easy], [Medium], [Hard]
    if re.search(r"\[(easy|basic|beginner|introductory)\]", lower):
        return QuestionDifficulty.EASY
    elif re.search(r"\[(hard|advanced|complex|expert)\]", lower):
        return QuestionDifficulty.HARD
    elif re.search(r"\[(medium|intermediate)\]", lower):
        return QuestionDifficulty.MEDIUM
    return None


def _clean_question_text(raw_text: str) -> str:
    cleaned = re.sub(r"^(?:Q\d+[:.]?|\d+[\.)]|Question\s*\d+[:.]?)\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\[(Easy|Medium|Hard|Beginner|Advanced)\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def is_role_set_pdf(reader: PdfReader) -> bool:
    """Detects whether a PDF conforms to the structured 25-set role question bank format."""
    if len(reader.pages) < 2:
        return False
    # Check cover page or page 2
    sample_text = (reader.pages[0].extract_text() or "") + "\n" + (reader.pages[1].extract_text() or "")
    if re.search(r"Problem Statement 3|Additional Technical Question Bank|SET\s*\d+|13 concept-based questions", sample_text, re.IGNORECASE):
        return True
    return False


def detect_role_from_pdf(reader: PdfReader, filename: str) -> str:
    """Resolves canonical role name from cover page text or filename."""
    p0_text = reader.pages[0].extract_text() or ""
    for canonical in ROLE_CANONICAL_NAMES.values():
        if canonical.lower() in p0_text.lower():
            return canonical

    lower_file = Path(filename).stem.lower()
    for key, canonical in ROLE_CANONICAL_NAMES.items():
        if key in lower_file or _slugify(canonical) in lower_file:
            return canonical

    # Fallback to normalized filename
    clean_name = Path(filename).stem.replace("_Additional_25_Sets", "").replace("_", " ").title()
    return clean_name


def parse_role_pdf_questions(
    file_input: Union[bytes, Path, str, PdfReader],
    filename: str
) -> List[Dict[str, Any]]:
    """
    Parses a role-specific 25-set PDF.
    Extracts exactly 15 questions per set (13 conceptual + 2 coding).
    Cleanly separates question prompt from answer guide / expected approach.
    Does NOT fabricate difficulty tags when unstated in the source.
    """
    if isinstance(file_input, PdfReader):
        reader = file_input
    elif isinstance(file_input, (str, Path)):
        reader = PdfReader(str(file_input))
        filename = Path(file_input).name
    else:
        reader = PdfReader(io.BytesIO(file_input))

    role = detect_role_from_pdf(reader, filename)
    role_slug = _slugify(role)
    questions: List[Dict[str, Any]] = []

    # Pages 1 to 25 (0-indexed: pages[1] to pages[25]) correspond to Set 1 to 25
    for p_idx in range(1, len(reader.pages)):
        page_text = reader.pages[p_idx].extract_text() or ""
        set_match = re.search(r"SET\s*(\d+)", page_text)
        set_num = int(set_match.group(1)) if set_match else p_idx

        # Regex matching Q<num>. [<bracket>] <question_prompt>\n[ \t]*(Answer guide|Expected approach): <answer_text>
        pattern = r"Q(\d+)\.\s*\[([^\]]+)\]\s*(.*?)\n[ \t]*(?:Answer guide|Expected approach):\s*(.*?)(?=\n[ \t]*Q\d+\.|\Z)"
        matches = list(re.finditer(pattern, page_text, re.DOTALL))

        for m in matches:
            q_num = int(m.group(1))
            raw_bracket = m.group(2).strip()
            q_text = " ".join(m.group(3).strip().split())
            ans_text = " ".join(m.group(4).strip().split())

            is_coding = "CODING" in raw_bracket.upper() or q_num in [14, 15]
            q_type = "coding" if is_coding else "conceptual"
            topic = "Coding" if is_coding else raw_bracket

            # Difficulty is only populated if source explicitly specified it in brackets or prompt
            source_diff = _detect_difficulty(raw_bracket) or _detect_difficulty(q_text)
            diff_val = source_diff.value if source_diff else None

            # Deterministic, unique set-slot identifier
            stable_id = f"{role_slug}-set{set_num:02d}-q{q_num:02d}"

            keywords = [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", q_text)[:6]]

            questions.append({
                "question_id": stable_id,
                "role": role,
                "set_number": set_num,
                "question_number": q_num,
                "question_type": q_type,
                "topic": topic,
                "difficulty": diff_val,  # None when unstated in source
                "question_text": q_text,
                "expected_answer": ans_text,  # Kept strictly internal
                "keywords": keywords,
                "source_filename": filename,
            })

    return questions


def parse_pdf_text_to_questions(
    raw_text: str,
    default_topic: str = "Technical Interview",
    source_name: str = "document.pdf"
) -> List[Dict[str, Any]]:
    """
    Parses plain text extracted from a generic PDF into individual questions.
    Ignores headers before the first question delimiter.
    """
    questions: List[Dict[str, Any]] = []

    # Pattern splitting: Q1., Question 1:, 1. Question...
    pattern = r"(?:^|\n)[ \t]*(?:Q(?:uestion)?\s*\d+[\.:\)]|\d+[\.)])\s+"
    parts = re.split(pattern, raw_text, flags=re.IGNORECASE)

    if len(parts) > 1:
        # parts[0] is preamble before first question delimiter
        for idx in range(1, len(parts)):
            part = parts[idx]
            if not part.strip():
                continue
            lines = [l.strip() for l in part.split("\n") if l.strip()]
            if not lines:
                continue

            first_block = " ".join(lines)
            difficulty = _detect_difficulty(first_block) or QuestionDifficulty.MEDIUM

            # Extract topic if present (e.g. Topic: Networking)
            topic = default_topic
            topic_match = re.search(r"Topic:\s*([^,\n\[\]]+)", first_block, re.IGNORECASE)
            if topic_match:
                topic = topic_match.group(1).strip()
                first_block = re.sub(r"Topic:\s*[^,\n\[\]]+", "", first_block, flags=re.IGNORECASE).strip()

            cleaned_text = _clean_question_text(first_block)

            if len(cleaned_text) >= 15:
                questions.append({
                    "question_id": f"q-{len(questions)+1}",
                    "role": None,
                    "set_number": None,
                    "question_number": len(questions) + 1,
                    "question_type": "conceptual",
                    "question_text": cleaned_text,
                    "expected_answer": None,
                    "topic": topic,
                    "difficulty": difficulty.value,
                    "keywords": [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", cleaned_text)[:6]],
                    "source_filename": source_name,
                })
    else:
        # Fallback: Split by paragraphs ending with '?'
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        for para in paragraphs:
            if "?" in para and len(para) >= 15:
                difficulty = _detect_difficulty(para) or QuestionDifficulty.MEDIUM
                cleaned_text = _clean_question_text(para)
                if len(cleaned_text) >= 15:
                    questions.append({
                        "question_id": f"q-{len(questions)+1}",
                        "role": None,
                        "set_number": None,
                        "question_number": len(questions) + 1,
                        "question_type": "conceptual",
                        "question_text": cleaned_text,
                        "expected_answer": None,
                        "topic": default_topic,
                        "difficulty": difficulty.value,
                        "keywords": [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", cleaned_text)[:6]],
                        "source_filename": source_name,
                    })

    return questions


def extract_questions_from_pdf(
    file_input: Union[bytes, Path, str],
    default_topic: str = "Technical Interview",
    source_name: str = "file.pdf"
) -> List[Dict[str, Any]]:
    """Extracts questions from a PDF byte buffer or file path."""
    if isinstance(file_input, (str, Path)):
        reader = PdfReader(str(file_input))
        source_name = Path(file_input).name
    else:
        reader = PdfReader(io.BytesIO(file_input))

    if is_role_set_pdf(reader):
        return parse_role_pdf_questions(reader, source_name)

    full_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text.append(text)

    combined_text = "\n".join(full_text)
    return parse_pdf_text_to_questions(combined_text, default_topic=default_topic, source_name=source_name)


def extract_questions_from_json(
    file_input: Union[bytes, str],
    default_topic: str = "Technical Interview",
    source_name: str = "file.json"
) -> List[Dict[str, Any]]:
    """Extracts questions from JSON byte buffer or text."""
    if isinstance(file_input, bytes):
        raw_text = file_input.decode("utf-8", errors="replace")
    else:
        raw_text = file_input

    data = json.loads(raw_text)
    raw_list = data if isinstance(data, list) else data.get("questions", data.get("items", []))

    questions = []
    for idx, item in enumerate(raw_list, 1):
        if isinstance(item, str):
            q_text = _clean_question_text(item)
            diff = _detect_difficulty(item) or QuestionDifficulty.MEDIUM
            topic = default_topic
            role = None
            ans = None
            q_type = "conceptual"
        elif isinstance(item, dict):
            q_text = _clean_question_text(item.get("question", item.get("question_text", item.get("text", ""))))
            raw_diff = str(item.get("difficulty", "")).lower()
            if "easy" in raw_diff:
                diff = QuestionDifficulty.EASY
            elif "hard" in raw_diff:
                diff = QuestionDifficulty.HARD
            elif "medium" in raw_diff:
                diff = QuestionDifficulty.MEDIUM
            else:
                diff = _detect_difficulty(q_text) or QuestionDifficulty.MEDIUM
            topic = item.get("topic", item.get("category", default_topic))
            role = item.get("role")
            ans = item.get("expected_answer", item.get("answer_guide"))
            q_type = item.get("question_type", "conceptual")
        else:
            continue

        if len(q_text) >= 10:
            questions.append({
                "question_id": f"json-{idx}",
                "role": role,
                "set_number": None,
                "question_number": idx,
                "question_type": q_type,
                "question_text": q_text,
                "expected_answer": ans,
                "topic": topic,
                "difficulty": diff.value if diff else None,
                "keywords": [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", q_text)[:6]],
                "source_filename": source_name,
            })
    return questions


def extract_questions_from_csv(
    file_input: Union[bytes, str],
    default_topic: str = "Technical Interview",
    source_name: str = "file.csv"
) -> List[Dict[str, Any]]:
    """Extracts questions from CSV byte buffer or text."""
    if isinstance(file_input, bytes):
        raw_text = file_input.decode("utf-8", errors="replace")
    else:
        raw_text = file_input

    reader = csv.DictReader(io.StringIO(raw_text))
    questions = []
    for idx, row in enumerate(reader, 1):
        q_text = ""
        for key in ["question", "question_text", "problem", "prompt", "text", "Question"]:
            if key in row and row[key]:
                q_text = row[key].strip()
                break

        if not q_text:
            continue

        topic = default_topic
        for key in ["topic", "category", "subject", "Topic"]:
            if key in row and row[key]:
                topic = row[key].strip()
                break

        diff = QuestionDifficulty.MEDIUM
        for key in ["difficulty", "level", "Difficulty"]:
            if key in row and row[key]:
                detected = _detect_difficulty(row[key])
                if detected:
                    diff = detected
                break

        ans = None
        for key in ["answer", "expected_answer", "answer_guide", "Expected approach"]:
            if key in row and row[key]:
                ans = row[key].strip()
                break

        role = row.get("role")
        q_type = row.get("question_type", "conceptual")

        cleaned = _clean_question_text(q_text)
        if len(cleaned) >= 10:
            questions.append({
                "question_id": f"csv-{idx}",
                "role": role,
                "set_number": None,
                "question_number": idx,
                "question_type": q_type,
                "question_text": cleaned,
                "expected_answer": ans,
                "topic": topic,
                "difficulty": diff.value if diff else None,
                "keywords": [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", cleaned)[:6]],
                "source_filename": source_name,
            })
    return questions


def extract_questions_from_zip(
    file_input: Union[bytes, Path, str],
    default_topic: str = "Technical Interview"
) -> List[Dict[str, Any]]:
    """
    Inspects and extracts interview questions from a ZIP archive containing
    PDF, TXT, JSON, or CSV question sources.
    Safely ignores meta-documentation such as README.txt.
    """
    if isinstance(file_input, (str, Path)):
        zfile = zipfile.ZipFile(str(file_input), "r")
    else:
        zfile = zipfile.ZipFile(io.BytesIO(file_input), "r")

    all_questions: List[Dict[str, Any]] = []
    with zfile:
        for name in sorted(zfile.namelist()):
            # Skip directories, system metadata, and documentation
            if name.endswith("/") or name.startswith("__MACOSX") or Path(name).name.startswith("."):
                continue

            lower_name = name.lower()
            if lower_name in ["readme.txt", "readme.md", "notes.txt"]:
                continue

            file_bytes = zfile.read(name)
            sub_source_name = Path(name).name

            try:
                if lower_name.endswith(".pdf"):
                    parsed = extract_questions_from_pdf(file_bytes, default_topic=default_topic, source_name=sub_source_name)
                    all_questions.extend(parsed)
                elif lower_name.endswith(".json"):
                    parsed = extract_questions_from_json(file_bytes, default_topic=default_topic, source_name=sub_source_name)
                    all_questions.extend(parsed)
                elif lower_name.endswith(".csv"):
                    parsed = extract_questions_from_csv(file_bytes, default_topic=default_topic, source_name=sub_source_name)
                    all_questions.extend(parsed)
                elif lower_name.endswith((".txt", ".md")):
                    text_str = file_bytes.decode("utf-8", errors="replace")
                    parsed = parse_pdf_text_to_questions(text_str, default_topic=default_topic, source_name=sub_source_name)
                    all_questions.extend(parsed)
            except Exception:
                continue

    return all_questions


def parse_question_file(
    file_bytes_or_path: Union[bytes, Path, str],
    filename: str,
    default_topic: str = "Technical Assessment"
) -> List[Dict[str, Any]]:
    """
    Main entrypoint: parses questions from either a PDF or ZIP file.
    """
    lower = filename.lower()
    if lower.endswith(".zip"):
        return extract_questions_from_zip(file_bytes_or_path, default_topic=default_topic)
    elif lower.endswith(".pdf"):
        return extract_questions_from_pdf(file_bytes_or_path, default_topic=default_topic, source_name=filename)
    elif lower.endswith(".json"):
        raw = file_bytes_or_path if isinstance(file_bytes_or_path, bytes) else Path(file_bytes_or_path).read_bytes()
        return extract_questions_from_json(raw, default_topic=default_topic, source_name=filename)
    elif lower.endswith(".csv"):
        raw = file_bytes_or_path if isinstance(file_bytes_or_path, bytes) else Path(file_bytes_or_path).read_bytes()
        return extract_questions_from_csv(raw, default_topic=default_topic, source_name=filename)
    elif lower.endswith((".txt", ".md")):
        text = file_bytes_or_path.decode("utf-8", errors="replace") if isinstance(file_bytes_or_path, bytes) else Path(file_bytes_or_path).read_text(encoding="utf-8", errors="replace")
        return parse_pdf_text_to_questions(text, default_topic=default_topic, source_name=filename)
    else:
        raise ValueError(f"Unsupported file format '{filename}'. Only PDF and ZIP (containing PDF/JSON/CSV/TXT) are supported.")
