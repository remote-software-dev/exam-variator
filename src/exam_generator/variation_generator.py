"""Variation generator module.

Generates Easy/Medium/Hard variations of questions using AI.
Uses cached results to avoid redundant API calls.
"""

import json
from typing import Callable, List, Optional

from .config import VARIATION_MODELS, TOKEN_LIMITS, TEMPERATURES
from .models import Question, VariationResult
from .ai_client import call_with_fallback, build_variation_system_prompt
from .cache import cache_variation, get_cached_variation


def generate_variations(question: Question, custom_instruction: str = None,
                       status_callback: Optional[Callable] = None) -> dict:
    """Generate easy/medium/hard variations for a single question.

    Returns dict with 'easy', 'medium', 'hard' keys.
    Each contains question_text, options, and optional solution fields.
    """
    # Check cache
    cached = get_cached_variation(question.content_hash, custom_instruction or "")
    if cached:
        print(f"  Cache hit for variations of '{question.question_id}'")
        return cached

    system_prompt = build_variation_system_prompt(custom_instruction)

    user_prompt = (
        f"Original question:\n{question.to_json(indent=2)}\n\n"
        "Generate the 'easy', 'medium' and 'hard' variations now."
    )

    result = call_with_fallback(
        models=VARIATION_MODELS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=TOKEN_LIMITS.variation,
        temperature=TEMPERATURES.variation,
        min_keys=["easy", "medium", "hard"],
        status_callback=status_callback,
    )

    # Cache the result
    if result:
        cache_variation(question.content_hash, custom_instruction or "", result)

    return result


def _variation_dict_to_question(var_data: dict, difficulty: str) -> Question:
    """Convert a variation dict from AI output to a Question object."""
    if not var_data:
        return None

    q = Question(
        question_text=var_data.get("question_text", ""),
        options=var_data.get("options", []),
        option_labels=[chr(65 + i) for i in range(len(var_data.get("options", [])))],
        solution_by_concept=var_data.get("solution_by_concept", ""),
        solution_by_trick=var_data.get("solution_by_trick", ""),
    )
    return q


def generate_variation_for_question(question: Question, custom_instruction: str = None,
                                    status_callback: Optional[Callable] = None) -> VariationResult:
    """Generate variations for a single question and return a VariationResult."""
    raw = generate_variations(question, custom_instruction=custom_instruction,
                             status_callback=status_callback)

    result = VariationResult(
        original=question,
        easy=_variation_dict_to_question(raw.get("easy"), "easy"),
        medium=_variation_dict_to_question(raw.get("medium"), "medium"),
        hard=_variation_dict_to_question(raw.get("hard"), "hard"),
        page=question.page_number,
    )

    return result


def generate_variation_batch(questions: List[Question], start: int, batch_size: int,
                            custom_instruction: str = None,
                            progress_callback: Optional[Callable] = None,
                            status_callback: Optional[Callable] = None) -> List[VariationResult]:
    """Generate variations for a batch of questions.

    Args:
        questions: Full list of questions.
        start: Starting index in the list.
        batch_size: How many questions to process.
        custom_instruction: Optional user instructions.
        progress_callback: Called with (current, total, stage, message).
        status_callback: Called with status messages.

    Returns:
        List of VariationResult objects.
    """
    results = []
    total = len(questions)

    for offset, question in enumerate(questions[start:start + batch_size]):
        try:
            result = generate_variation_for_question(
                question, custom_instruction=custom_instruction,
                status_callback=status_callback,
            )
            results.append(result)
            print(f"  Variations generated for '{question.question_id}'")
        except Exception as e:
            print(f"  Failed to generate variations for '{question.question_id}': {e}")
            # Create a result with only the original question
            results.append(VariationResult(original=question, page=question.page_number))

        if progress_callback:
            done = start + offset + 1
            progress_callback(done, total, "vary",
                            f"Generating variation {done}/{total}...")

    return results


def generate_all_variations(questions: List[Question], custom_instruction: str = None,
                           progress_callback: Optional[Callable] = None,
                           status_callback: Optional[Callable] = None) -> List[VariationResult]:
    """Generate variations for all questions.

    Thin wrapper that processes the whole list.
    """
    return generate_variation_batch(
        questions, start=0, batch_size=len(questions),
        custom_instruction=custom_instruction,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
