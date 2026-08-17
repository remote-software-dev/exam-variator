"""Validation layer for the exam-variator pipeline.

Validates questions after extraction and after AI generation.
Marks invalid or questionable items for human review.
"""

import re
from typing import List, Tuple

from .models import (
    Question, QuestionType, ValidationStatus, VariationResult,
)


def validate_question(q: Question) -> Tuple[ValidationStatus, List[str]]:
    """Validate a single question. Returns (status, list_of_warnings)."""
    warnings = []

    # Required fields
    if not q.question_text or not q.question_text.strip():
        warnings.append("Missing question_text")

    if not q.question_id:
        warnings.append("Missing question_id")

    # Option validation for MCQ types
    if q.is_multiple_choice():
        if len(q.options) < 2:
            warnings.append(f"Too few options: {len(q.options)}")
        if len(q.options) > 5:
            warnings.append(f"Too many options: {len(q.options)}")

        # Check for empty options
        for i, opt in enumerate(q.options):
            if not opt or not opt.strip():
                warnings.append(f"Option {chr(65+i)} is empty")

        # Check option label consistency
        if q.option_labels and len(q.option_labels) != len(q.options):
            warnings.append("Option labels count mismatch")

    # Statement table validation
    if q.has_statement_table():
        if not q.statement_entries:
            warnings.append("Question type requires statement_entries but none found")

    # Category table validation
    if q.has_category_table():
        if not q.category_entries:
            warnings.append("Question type requires category_entries but none found")

    # Answer key validation
    if q.correct_answer:
        if q.is_multiple_choice() and q.correct_answer not in [chr(65+i) for i in range(len(q.options))]:
            warnings.append(f"correct_answer '{q.correct_answer}' not in option labels")

    if q.correct_answers and q.question_type == QuestionType.PILIHAN_GANDA_KOMPLEKS:
        valid_labels = [chr(65+i) for i in range(len(q.options))]
        for ans in q.correct_answers:
            if ans not in valid_labels:
                warnings.append(f"correct_answer '{ans}' not in option labels")

    # LaTeX validation (basic)
    for formula in q.formulas:
        if not _is_valid_latex(formula):
            warnings.append(f"Potentially invalid LaTeX: {formula[:50]}...")

    # Question text length
    if len(q.question_text) > 2000:
        warnings.append("Question text unusually long (>2000 chars)")

    # Confidence check
    if q.confidence < 0.5:
        warnings.append(f"Low extraction confidence: {q.confidence:.2f}")
        q.needs_human_review = True

    # Determine status
    if not warnings:
        status = ValidationStatus.VALID
    elif any("Missing" in w or "Too few" in w for w in warnings):
        status = ValidationStatus.INVALID
    else:
        status = ValidationStatus.WARNINGS

    return status, warnings


def validate_variation_result(result: VariationResult) -> Tuple[ValidationStatus, List[str]]:
    """Validate a complete variation result (original + 3 variations)."""
    all_warnings = []

    # Validate original
    status, warnings = validate_question(result.original)
    all_warnings.extend(f"[Original] {w}" for w in warnings)

    # Validate each variation
    for label, variation in [("easy", result.easy), ("medium", result.medium), ("hard", result.hard)]:
        if variation is None:
            all_warnings.append(f"[{label}] Missing variation")
            continue

        vstatus, vwarnings = validate_question(variation)
        all_warnings.extend(f"[{label}] {w}" for w in vwarnings)

        # Variation-specific checks
        if variation.options and len(variation.options) != 5:
            all_warnings.append(f"[{label}] Expected 5 options, got {len(variation.options)}")

        # Check that variation is different from original
        if variation.question_text == result.original.question_text:
            all_warnings.append(f"[{label}] Variation identical to original question")

    # Overall status
    if not all_warnings:
        overall_status = ValidationStatus.VALID
    elif any("[Original]" in w and "Missing" in w for w in all_warnings):
        overall_status = ValidationStatus.INVALID
    else:
        overall_status = ValidationStatus.WARNINGS

    return overall_status, all_warnings


def validate_json_structure(data: dict, required_keys: list) -> Tuple[bool, str]:
    """Validate that a dict has the required keys and basic structure."""
    if not isinstance(data, dict):
        return False, f"Expected dict, got {type(data).__name__}"

    missing = [k for k in required_keys if k not in data]
    if missing:
        return False, f"Missing required keys: {missing}"

    return True, "OK"


def validate_options_count(options: list, expected: int = 5) -> Tuple[bool, str]:
    """Validate that options list has the expected count."""
    if not isinstance(options, list):
        return False, f"Options should be a list, got {type(options).__name__}"

    if len(options) != expected:
        return False, f"Expected {expected} options, got {len(options)}"

    # Check all are strings
    non_str = [i for i, o in enumerate(options) if not isinstance(o, str)]
    if non_str:
        return False, f"Non-string options at indices: {non_str}"

    return True, "OK"


def mark_for_review(q: Question, reason: str) -> None:
    """Mark a question for human review with a reason."""
    q.needs_human_review = True
    q.validation_warnings.append(reason)


def _is_valid_latex(latex_str: str) -> bool:
    """Basic LaTeX syntax validation.

    Checks for balanced braces, common command patterns.
    """
    if not latex_str:
        return True

    # Check balanced braces
    depth = 0
    for ch in latex_str:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth < 0:
            return False
    if depth != 0:
        return False

    # Check for common broken patterns
    broken_patterns = [
        r"\\[a-zA-Z]+\{",  # Command without closing brace (very basic)
        r"\{\}",           # Empty braces
    ]
    for pattern in broken_patterns:
        if re.search(pattern, latex_str):
            return False

    return True


def validate_batch(questions: List[Question]) -> Tuple[int, int, int]:
    """Validate a batch of questions.

    Returns (valid_count, warning_count, invalid_count).
    """
    valid = 0
    warned = 0
    invalid = 0

    for q in questions:
        status, warnings = validate_question(q)
        q.validation_status = status
        q.validation_warnings = warnings

        if status == ValidationStatus.VALID:
            valid += 1
        elif status == ValidationStatus.WARNINGS:
            warned += 1
        else:
            invalid += 1

    return valid, warned, invalid
