"""AI client module for the exam-variator pipeline.

Wraps litellm with proper retry logic, max_tokens enforcement,
fallback chains, and structured output extraction.
"""

import json
import re
import time
import base64
from typing import Any, Dict, List, Optional

import litellm
from litellm.exceptions import RateLimitError

from .config import (
    TOKEN_LIMITS, TEMPERATURES, RETRY_CONFIG,
    EXTRACTION_MODELS, TEXT_EXTRACTION_MODELS, VARIATION_MODELS,
    SOLUTION_MODELS, IMAGE_DESCRIPTION_MODELS, OCR_CLEANUP_MODELS,
    MATRIX_FORMATTING_RULES,
)


def is_daily_quota_error(error: Exception) -> bool:
    """Check if a RateLimitError is from an exhausted daily quota."""
    msg = str(getattr(error, "message", "") or error)
    return "PerDay" in msg or "per_day" in msg or "dailyLimitExceeded" in msg


def completion_with_retry(model: str, messages: List[Dict], status_callback=None,
                         max_tokens: int = None, temperature: float = None,
                         **kwargs) -> Any:
    """Call litellm.completion with retry and exponential backoff.

    Args:
        model: The model identifier.
        messages: Chat messages list.
        status_callback: Optional callable for UI status updates.
        max_tokens: Maximum output tokens. If None, uses task default.
        temperature: Sampling temperature. If None, uses task default.
        **kwargs: Additional kwargs passed to litellm.completion.

    Returns:
        The litellm completion response.

    Raises:
        RateLimitError: After exhausting retries on the same model.
        Other exceptions: Propagated immediately.
    """
    delay = RETRY_CONFIG.rate_limit_backoff_seconds
    for attempt in range(1, RETRY_CONFIG.rate_limit_max_retries + 1):
        try:
            call_kwargs = dict(kwargs)
            if max_tokens is not None:
                call_kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                call_kwargs["temperature"] = temperature
            return litellm.completion(model=model, messages=messages, **call_kwargs)
        except RateLimitError as e:
            if is_daily_quota_error(e):
                raise
            if attempt == RETRY_CONFIG.rate_limit_max_retries:
                raise
            msg = (
                f"Rate limited on {model} (attempt {attempt}/{RETRY_CONFIG.rate_limit_max_retries}); "
                f"retrying in {int(delay)}s..."
            )
            print(f"  {msg}")
            if status_callback:
                status_callback(msg)
            time.sleep(delay)
            delay *= 2

    raise RuntimeError("unreachable")


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extract the first JSON object from model output.

    Handles: bare JSON, markdown-fenced JSON, trailing text.
    """
    if not text:
        return None

    # Try markdown code fence first
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not match:
        # Try bare JSON
        match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).replace("'", '"'))
        except json.JSONDecodeError:
            return None
    return None


def extract_json_array(text: str) -> Optional[List[Any]]:
    """Extract a JSON array from model output."""
    if not text:
        return None

    match = re.search(r'```json\s*(\[.*?\])\s*```', text, re.DOTALL)
    if not match:
        match = re.search(r'(\[.*\])', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def encode_image(image_path: str) -> str:
    """Read an image file and return its base64 encoding."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_with_fallback(models: List[str], messages: List[Dict],
                      max_tokens: int = None, temperature: float = None,
                      min_keys: List[str] = None, expect_array: bool = False,
                      status_callback=None) -> Any:
    """Try multiple models in order until one returns valid output.

    Args:
        models: Ordered list of model identifiers to try.
        messages: Chat messages.
        max_tokens: Max output tokens per call.
        temperature: Sampling temperature.
        min_keys: Required keys in the JSON response (for dict responses).
        expect_array: If True, expect a JSON array instead of object.
        status_callback: Optional UI status callback.

    Returns:
        Parsed JSON response (dict or list).

    Raises:
        RuntimeError: If all models fail.
    """
    last_error = None
    for model in models:
        try:
            response = completion_with_retry(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                status_callback=status_callback,
            )
            raw = response.choices[0].message.content

            if expect_array:
                result = extract_json_array(raw)
            else:
                result = extract_json(raw)

            if result is None:
                print(f"  Warning: {model} returned unparseable output, trying next...")
                continue

            if min_keys and isinstance(result, dict):
                if any(k not in result for k in min_keys):
                    print(f"  Warning: {model} returned incomplete JSON (missing {min_keys}), trying next...")
                    continue

            return result

        except Exception as e:
            last_error = e
            print(f"  Warning: {model} failed: {e}, trying next...")

    raise RuntimeError(f"All models failed. Last error: {last_error}")


def build_vision_message(image_path: str, text_prompt: str) -> List[Dict]:
    """Build a multimodal message with an image and text prompt."""
    base64_image = encode_image(image_path)
    return [
        {"type": "text", "text": text_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
    ]


def build_extraction_system_prompt(source: str = "text", all_questions: bool = True,
                                   custom_instruction: str = None) -> str:
    """Build the system prompt for question extraction."""
    source_phrase = (
        "the clean Markdown text of a PDF page" if source == "text"
        else "scanned images of a PDF page"
    )

    if all_questions:
        intro = (
            f"You extract Indonesian math exam questions from {source_phrase}.\n"
            "Return ONLY a JSON object: {\"questions\": [{\"id\": str, "
            "\"question_text\": str, \"options\": [str]}]}. Extract EVERY "
            "complete question visible -- do not skip, merge, or omit any.\n\n"
        )
    else:
        intro = (
            f"You extract Indonesian math exam questions from {source_phrase}.\n"
            "Return ONLY a JSON object: {\"id\": str, \"question_text\": str, "
            "\"options\": [str]}.\n\n"
        )

    rules = (
        "RULES:\n"
        "- Formulas in $LaTeX$ (e.g. $\\frac{a}{b}$, $x^2$, $\\sqrt{3}$).\n"
        f"- {MATRIX_FORMATTING_RULES}\n"
        "- 'id': the alphanumeric ID printed on the paper; if absent or just a "
        "number, use 'EXAM-<RANDOM8HEX>'.\n"
        "- 'options': A/B/C/D/E choices, OR per-statement items for Benar/Salah "
        "tables (prefix 'Pernyataan N: Benar/Salah') and multi-part stems "
        "(pernyataan (1),(2),(3)).\n"
        "- Preserve the original Indonesian language.\n"
        "- Use double quotes for all JSON keys and string values."
    )

    if custom_instruction and custom_instruction.strip():
        rules += (
            "\n\nADDITIONAL USER INSTRUCTIONS (apply when relevant):\n"
            f"{custom_instruction.strip()}"
        )

    return intro + rules


def build_variation_system_prompt(custom_instruction: str = None) -> str:
    """Build the system prompt for variation generation."""
    prompt = (
        "You are a math exam question writer for Indonesian secondary schools.\n"
        "Given an original multiple-choice question, produce three variations: "
        "'easy', 'medium', and 'hard'.\n\n"
        "STRICT FORMAT RULES:\n"
        "- Return ONLY a valid JSON object.\n"
        "- Top-level keys: 'easy', 'medium' and 'hard'.\n"
        "- Each variation must contain:\n"
        "  * 'question_text': string (the question stem)\n"
        "  * 'options': array of exactly 5 strings (labeled A through E in the output)\n"
        "  * 'solution_by_concept': string (optional) -- the solution using the basic "
        "concept/method, written as detailed plain text.\n"
        "  * 'solution_by_trick': string (optional) -- a quick/shortcut way to solve "
        "it, written as detailed plain text.\n"
        "- Only include 'solution_by_concept' / 'solution_by_trick' when the "
        "ADDITIONAL USER INSTRUCTIONS ask for solution methods.\n"
        "- Do NOT convert multiple-choice into essay or fill-in-the-blank questions.\n"
        "- Do NOT change the number of options. Every variation MUST have exactly 5 options.\n"
        "- Do NOT include option labels (A., B., etc.) inside the option strings.\n"
        "- Keep the same mathematical topic and difficulty relative to the label.\n"
        "- Preserve the original Indonesian language.\n"
        "- Use double quotes for all JSON keys and string values.\n"
        "- Do NOT wrap the JSON in markdown code fences.\n\n"
        "PLAIN TEXT FORMATTING (CRITICAL):\n"
        "- NEVER use LaTeX commands like \\frac, \\sqrt, \\times, \\cdot, \\begin, "
        "$, ^, _, \\, or any other LaTeX markup.\n"
        "- NEVER use markdown headers like ### or ##.\n"
        "- ALWAYS use plain Unicode text and symbols:\n"
        "  * Use '1/2' or '½' instead of '\\frac{1}{2}'\n"
        "  * Use '√' instead of '\\sqrt'\n"
        "  * Use '×' instead of '\\times'\n"
        "  * Use '²' and '³' for powers instead of x^2, x^3\n"
        "  * Use 'H₂O' style subscripts for chemical formulas\n"
        "  * Use '30°' instead of '30^\\circ'\n"
        "  * Use '±' instead of '\\pm'\n"
        "  * Use '≤' and '≥' instead of '\\leq' and '\\geq'\n"
        "- For matrices, use plain text like: [2, 0; 0, ½] or describe them in words.\n"
        "- Format explanations in simple paragraphs, no markdown headers or bullet "
        "symbols like ##, **, or ```. Just plain readable text."
    )

    if custom_instruction and custom_instruction.strip():
        prompt += (
            "\n\nADDITIONAL USER INSTRUCTIONS (follow them exactly for every variation):\n"
            f"{custom_instruction.strip()}\n"
            "If these instructions ask for solution methods (e.g. 'by concept' or "
            "'trick/cara cepat'), produce them under 'solution_by_concept' and "
            "'solution_by_trick' using PLAIN TEXT only (no LaTeX, no markdown headers)."
        )

    return prompt


def build_solution_system_prompt(custom_instruction: str = None) -> str:
    """Build the system prompt for solution generation."""
    prompt = (
        "You are an expert math teacher for Indonesian secondary schools.\n"
        "Given a question, produce a clear, step-by-step solution discussion "
        "(pembahasan) that teaches the student HOW to solve it.\n\n"
        "STRICT FORMAT RULES:\n"
        "- Return ONLY a valid JSON object.\n"
        "- Top-level keys: 'solution_by_concept' and 'solution_by_trick'.\n"
        "  * 'solution_by_concept': string -- the full solution using the basic "
        "concept/method, step by step, written as detailed plain text.\n"
        "  * 'solution_by_trick': string -- a quick/shortcut way to solve it, "
        "written as detailed plain text. If no real shortcut exists, restate the "
        "most efficient approach.\n"
        "- Explain every step and the reasoning behind each transformation; "
        "state the final answer (key answer) explicitly.\n"
        "- Preserve the original Indonesian language.\n"
        "- Use double quotes for all JSON keys and string values.\n"
        "- Do NOT wrap the JSON in markdown code fences.\n\n"
        "PLAIN TEXT FORMATTING (CRITICAL):\n"
        "- NEVER use LaTeX commands like \\frac, \\sqrt, \\times, \\cdot, \\begin, "
        "$, ^, _, \\, or any other LaTeX markup.\n"
        "- NEVER use markdown headers like ### or ##.\n"
        "- ALWAYS use plain Unicode text and symbols:\n"
        "  * Use '1/2' or '½' instead of '\\frac{1}{2}'\n"
        "  * Use '√' instead of '\\sqrt'\n"
        "  * Use '×' instead of '\\times'\n"
        "  * Use '²' and '³' for powers instead of x^2, x^3\n"
        "  * Use 'H₂O' style subscripts for chemical formulas\n"
        "  * Use '30°' instead of '30^\\circ'\n"
        "  * Use '±' instead of '\\pm'\n"
        "  * Use '≤' and '≥' instead of '\\leq' and '\\geq'\n"
        "- For matrices, use plain text like: [2, 0; 0, ½] or describe them in words.\n"
        "- Format explanations in simple paragraphs, no markdown headers or bullet "
        "symbols like ##, **, or ```. Just plain readable text."
    )

    if custom_instruction and custom_instruction.strip():
        prompt += (
            "\n\nADDITIONAL USER INSTRUCTIONS (follow them exactly):\n"
            f"{custom_instruction.strip()}\n"
            "If these instructions ask for a specific solution style (e.g. 'by "
            "concept' or 'trick/cara cepat'), emphasize and clearly label that "
            "style in the corresponding field. Still use PLAIN TEXT formatting."
        )

    return prompt


def build_image_description_prompt() -> str:
    """Build the system prompt for describing images in exam questions."""
    return (
        "You are analyzing an image from an Indonesian math exam paper.\n"
        "Describe what the image shows in detail, focusing on:\n"
        "- If it's a graph: axes, labels, data points, trend\n"
        "- If it's a table: headers, data values, structure\n"
        "- If it's a diagram: components, labels, connections\n"
        "- If it's a geometry figure: shapes, measurements, labels\n"
        "- If it's an instrument reading: type of instrument, reading value\n\n"
        "Return ONLY a JSON object:\n"
        "{\"description\": \"<detailed description>\", \"image_type\": \"<graph|table|diagram|instrument|geometry|unknown>\", "
        "\"key_data\": \"<any numerical data or measurements visible>\"}\n"
        "Use double quotes. Do NOT wrap in markdown code fences."
    )


def build_ocr_cleanup_prompt() -> str:
    """Build the system prompt for cleaning OCR output."""
    return (
        "You are cleaning up garbled OCR text from an Indonesian math exam.\n"
        "The text below was extracted by OCR and may contain errors.\n"
        "Fix obvious OCR errors while preserving the original content.\n"
        "Focus on:\n"
        "- Fixing misrecognized characters (e.g. '0' vs 'O', 'l' vs '1')\n"
        "- Restoring LaTeX formulas that were broken by OCR\n"
        "- Preserving question structure (numbering, options)\n\n"
        "Return ONLY a JSON object:\n"
        "{\"cleaned_text\": \"<the corrected text>\", \"confidence\": <0.0-1.0>}\n"
        "Use double quotes. Do NOT wrap in markdown code fences."
    )
