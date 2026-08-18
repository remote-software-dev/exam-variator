"""Local question parser for the exam-variator pipeline.

Parses questions from PDF text using regex and heuristics.
No AI calls needed for standard formatted exams.
Detects question types, extracts options, identifies metadata.
"""

import re
import uuid
from typing import List, Optional, Tuple

from .models import Question, QuestionType, ExtractionMethod


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Question ID pattern: 25ABC...-123456-1234
_QID_RE = re.compile(r"(?m)(25[A-Z0-9]{14}-\d{6}-\d{4})")

# Numbered question delimiter
_NUMBERED_RE = re.compile(r"(?m)^\s*(\d{1,3})\s*[\.\)]")

# Option labels
_OPTION_RE = re.compile(r"(?m)^\s*([A-E])\s*[\.\)]\s*(.*)")

# Question markers
_MARKER_RE = re.compile(
    r"(?m)(^\s*\d{1,3}\s*\.|\b[A-E]\s*[\.\)]|\bPernyataan\b|\(\s*\d\s*\))"
)

# Metadata patterns
_ELEMEN_RE = re.compile(r"(?:Elemen|Element)\s*[:=]\s*(.+)", re.IGNORECASE)
_SUBELEMEN_RE = re.compile(r"(?:Subelemen|Sub-element)\s*[:=]\s*(.+)", re.IGNORECASE)
_KOMPETENSI_RE = re.compile(r"(?:Kompetensi|Competency)\s*[:=]\s*(.+)", re.IGNORECASE)
_INDIKATOR_RE = re.compile(r"(?:Indikator|Indicator)\s*[:=]\s*(.+)", re.IGNORECASE)
_BENTUK_RE = re.compile(r"(?:Bentuk\s*Soal)\s*[:=]\s*(.+)", re.IGNORECASE)

# Statement patterns for Benar/Salah, Tepat/Tidak Tepat
_PERNYATAAN_RE = re.compile(r"\(\s*(\d+)\s*\)\s*(.+)")
_PERNYATAAN_LABEL_RE = re.compile(r"Pernyataan\s*(\d+)", re.IGNORECASE)

# Kategori table patterns
_KATEGORI_HEADER_RE = re.compile(r"(?:Kategori|Category)\s*[:=]", re.IGNORECASE)

# Answer key patterns
_ANSWER_KEY_RE = re.compile(
    r"(?:Kunci\s*Jawaban|Jawaban|Answer\s*Key)\s*[:=]\s*([A-E](?:\s*[,\s]\s*[A-E])*)",
    re.IGNORECASE
)

# Benar/Salah truth values
_BENAR_SALAH_RE = re.compile(r"\b(Benar|Salah|True|False|B|S)\b", re.IGNORECASE)


def detect_question_type(text: str) -> QuestionType:
    """Detect the question type from its text content.

    Checks for Benar/Salah, Tepat/Tidak Tepat, Kategori, MCMA patterns.
    """
    text_lower = text.lower()

    # Benar/Salah
    if "benar/salah" in text_lower or "benar atau salah" in text_lower:
        return QuestionType.BENAR_SALAH
    if re.search(r"pernyataan.*benar.*salah|salah.*benar", text_lower):
        return QuestionType.BENAR_SALAH

    # Tepat/Tidak Tepat
    if "tepat/tidak tepat" in text_lower or "tepat atau tidak tepat" in text_lower:
        return QuestionType.TEPAT_TIDAK_TEPAT

    # Kategori
    if "kategori" in text_lower and ("sesuai" in text_lower or "match" in text_lower):
        return QuestionType.KATEGORI
    if _KATEGORI_HEADER_RE.search(text):
        return QuestionType.KATEGORI

    # MCMA detection: look for "kompleks", "multichoice", checkbox indicators,
    # or "pilihan ganda kompleks"
    if any(kw in text_lower for kw in ["kompleks", "multichoice", "multiple choice",
                                         "lebih dari satu", "centang", "checkbox"]):
        return QuestionType.PILIHAN_GANDA_KOMPLEKS

    # Default to standard MCQ
    return QuestionType.PILIHAN_GANDA


def extract_metadata(text: str) -> dict:
    """Extract metadata fields from question text.

    Returns a dict with keys: element, subelement, competency, indicator, bentuk_soal.
    """
    meta = {}

    m = _ELEMEN_RE.search(text)
    if m:
        meta["element"] = m.group(1).strip()

    m = _SUBELEMEN_RE.search(text)
    if m:
        meta["subelement"] = m.group(1).strip()

    m = _KOMPETENSI_RE.search(text)
    if m:
        meta["competency"] = m.group(1).strip()

    m = _INDIKATOR_RE.search(text)
    if m:
        meta["indicator"] = m.group(1).strip()

    m = _BENTUK_RE.search(text)
    if m:
        meta["bentuk_soal"] = m.group(1).strip()

    return meta


def extract_answer_key(text: str) -> Optional[str]:
    """Try to extract an answer key from the text."""
    m = _ANSWER_KEY_RE.search(text)
    if m:
        return m.group(1).strip().replace(" ", "")
    return None


def extract_statements(text: str) -> List[Tuple[str, str]]:
    """Extract numbered statements from Benar/Salah or Tepat/Tidak Tepat questions.

    Returns list of (statement_number, statement_text) tuples.
    """
    statements = []
    for m in _PERNYATAAN_RE.finditer(text):
        num = m.group(1)
        stmt_text = m.group(2).strip()
        if len(stmt_text) > 5:  # Skip very short fragments
            statements.append((num, stmt_text))
    return statements


def extract_formulas(text: str) -> List[str]:
    """Extract LaTeX formulas from text."""
    formulas = []
    seen = set()
    # Match $$...$$ display math first (to avoid double-counting with inline)
    for m in re.finditer(r"\$\$([^$]+)\$\$", text):
        val = m.group(1)
        if val not in seen:
            formulas.append(val)
            seen.add(val)
    # Match $...$ inline math
    for m in re.finditer(r"(?<!\$)\$([^$]+)\$(?!\$)", text):
        val = m.group(1)
        if val not in seen:
            formulas.append(val)
            seen.add(val)
    # Match \(...\) and \[...\]
    for m in re.finditer(r"\\\((.+?)\\\)", text):
        val = m.group(1)
        if val not in seen:
            formulas.append(val)
            seen.add(val)
    for m in re.finditer(r"\\\[(.+?)\\\]", text):
        val = m.group(1)
        if val not in seen:
            formulas.append(val)
            seen.add(val)
    return formulas


def split_options(lines: List[str], start_idx: int) -> Tuple[List[str], int]:
    """Split option lines from a block of text lines.

    Starting from start_idx, extracts A-E options and returns
    (options_list, next_index). Skips stem lines before the first option.
    """
    options = []
    current_option_text = None
    idx = start_idx
    found_first_option = False

    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            continue

        m = _OPTION_RE.match(line)
        if m:
            found_first_option = True
            if current_option_text is not None:
                options.append(current_option_text)
            current_option_text = m.group(2).strip()
            idx += 1
        elif found_first_option and current_option_text is not None:
            # Continuation of current option
            current_option_text += " " + line
            idx += 1
        elif not found_first_option:
            # Skip stem lines before first option
            idx += 1
        else:
            break  # Not an option line after options started

    if current_option_text is not None:
        options.append(current_option_text)

    return options, idx


def parse_questions_from_text(page_text: str, qid_regex: Optional[re.Pattern] = None,
                              page_number: int = 0) -> List[Question]:
    """Parse MCQ questions from a page's text using local heuristics.

    No LLM calls. Conservative: returns empty list if layout is unclear.

    Args:
        page_text: The raw text from a PDF page.
        qid_regex: Optional custom regex for question IDs.
        page_number: Page number for metadata.

    Returns:
        List of Question objects.
    """
    text = (page_text or "").strip()
    if not text:
        return []

    qid_re = qid_regex or _QID_RE
    qid_matches = list(qid_re.finditer(text))

    if qid_matches:
        delimiters = qid_matches
        def get_id(m):
            return m.group(0)
    else:
        numbered = list(_NUMBERED_RE.finditer(text))
        if not numbered:
            return []
        delimiters = numbered
        def get_id(m):
            return m.group(1)

    # Split text into blocks at delimiters
    blocks = []
    for idx, m in enumerate(delimiters):
        start = m.end()
        end = delimiters[idx + 1].start() if idx + 1 < len(delimiters) else len(text)
        blocks.append((get_id(m), text[start:end]))

    questions = []
    for qid, body in blocks:
        lines = body.splitlines()

        # Try to extract options
        options, _ = split_options(lines, 0)

        # Reject if options look jumbled (two-column layout flattened)
        for opt in options:
            if re.search(r"(?i)[A-E]\s*[\.\)]\s*\S", opt):
                return []

        # Extract stem (everything before options)
        stem_lines = []
        for line in lines:
            line_s = line.strip()
            if not line_s:
                continue
            if _OPTION_RE.match(line_s):
                break
            stem_lines.append(line_s)

        qtext = " ".join(stem_lines).strip()

        # Minimum quality checks
        if len(qtext) < 10:
            continue
        if len(options) < 2:
            continue

        # Detect question type
        full_text = qtext + " " + " ".join(options)
        q_type = detect_question_type(full_text)

        # Extract metadata
        meta = extract_metadata(full_text)

        # Extract answer key if present
        answer = extract_answer_key(full_text)

        # Extract statements for Benar/Salah
        statements = extract_statements(full_text) if q_type in (
            QuestionType.BENAR_SALAH, QuestionType.TEPAT_TIDAK_TEPAT
        ) else []

        # Extract formulas
        formulas = extract_formulas(full_text)

        question = Question(
            question_id=qid,
            page_number=page_number,
            question_text=qtext,
            options=options,
            option_labels=[chr(65 + i) for i in range(len(options))],
            question_type=q_type,
            correct_answer=answer or "",
            formulas=formulas,
            extraction_method=ExtractionMethod.LOCAL_PARSE,
            confidence=0.9 if qid_matches else 0.7,
        )

        # Add metadata if found
        if meta.get("element"):
            question.element = meta["element"]
        if meta.get("subelement"):
            question.subelement = meta["subelement"]
        if meta.get("competency"):
            question.competency = meta["competency"]
        if meta.get("indicator"):
            question.indicator = meta["indicator"]
        if meta.get("bentuk_soal"):
            question.bentuk_soal = meta["bentuk_soal"]

        questions.append(question)

    # Only trust the parse when we understood most of the page
    if questions and len(questions) * 2 < len(delimiters):
        return []

    return questions


def extract_questions_from_markdown(page_text: str, page_number: int = 0) -> List[Question]:
    """Higher-level extraction: try local parse first, then basic fallback.

    This is the main entry point for local question extraction.
    """
    questions = parse_questions_from_text(page_text, page_number=page_number)
    if questions:
        return questions

    # Fallback: try with numbered-only delimiter
    questions = parse_questions_from_text(page_text, qid_regex=_NUMBERED_RE,
                                          page_number=page_number)
    return questions


def merge_short_options(options: List[str], min_length: int = 3) -> List[str]:
    """Merge very short options that might be split by OCR artifacts.

    E.g., ["1", "2", "3", "4", "5"] stays as-is, but
    ["1", "cm", "B. 28 cm", "C. 34 cm"] might be jumbled.
    """
    if not options:
        return options

    # Check if any option contains another option label (jumbled)
    jumbled = False
    for opt in options:
        if re.search(r"(?i)\b[A-E]\s*[\.\)]\s*\S", opt):
            jumbled = True
            break

    if jumbled:
        # Try to re-split by A-E labels
        combined = " ".join(options)
        resplit = []
        for m in _OPTION_RE.finditer(combined):
            resplit.append(m.group(2).strip())
        if len(resplit) >= 2:
            return resplit[:5]  # Max 5 options

    return options
