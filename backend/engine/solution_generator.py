"""Solution generator module.

Generates pembahasan (solutions) for questions using AI.
Only calls AI when local methods cannot produce the solution.
"""

import json
from typing import Callable, List, Optional

from .config import SOLUTION_MODELS, TOKEN_LIMITS, TEMPERATURES
from .models import Question
from .ai_client import call_with_fallback, build_solution_system_prompt
from .cache import cache_solution, get_cached_solution


def generate_solution(question: Question, custom_instruction: str = None,
                     status_callback: Optional[Callable] = None) -> dict:
    """Generate a solution (pembahasan) for a single question.

    Returns dict with 'solution_by_concept' and 'solution_by_trick' keys.
    Checks cache first to avoid redundant AI calls.
    """
    # Check cache
    cached = get_cached_solution(question.content_hash)
    if cached:
        print(f"  Cache hit for solution of '{question.question_id}'")
        return cached

    system_prompt = build_solution_system_prompt(custom_instruction)

    user_prompt = (
        f"Question:\n{question.to_json(indent=2)}\n\n"
        "Generate the solution discussion (pembahasan) now."
    )

    result = call_with_fallback(
        models=SOLUTION_MODELS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=TOKEN_LIMITS.solution,
        temperature=TEMPERATURES.solution,
        min_keys=["solution_by_concept", "solution_by_trick"],
        status_callback=status_callback,
    )

    # Cache the result
    if result:
        cache_solution(question.content_hash, result)

    return result


def solve_questions(questions: List[Question], custom_instruction: str = None,
                   progress_callback: Optional[Callable] = None,
                   status_callback: Optional[Callable] = None) -> List[Question]:
    """Generate solutions for a list of questions in place.

    Each question gets solution_by_concept and solution_by_trick.
    Returns the same (mutated) list.
    """
    total = len(questions)
    for done, q in enumerate(questions, 1):
        try:
            solution = generate_solution(
                q,
                custom_instruction=custom_instruction,
                status_callback=status_callback,
            )
            q.solution_by_concept = solution.get("solution_by_concept", "")
            q.solution_by_trick = solution.get("solution_by_trick", "")
            print(f"  Solution generated for '{q.question_id}'")
        except Exception as e:
            print(f"  Failed to generate solution for '{q.question_id}': {e}")
            q.solution_by_concept = ""
            q.solution_by_trick = ""

        if progress_callback:
            progress_callback(done, total, "solve",
                            f"Generating solution {done}/{total}...")

    return questions
