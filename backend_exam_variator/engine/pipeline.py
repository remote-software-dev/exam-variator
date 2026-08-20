"""Pipeline orchestrator for the exam-variator.

This is the main entry point that coordinates all modules:
- PDF ingestion (local-first)
- Local question extraction
- OCR fallback for scanned pages
- AI solution generation
- AI variation generation
- Validation
- DOCX export

Backward-compatible: preserves the same public API as the original pipeline.
"""

import os
import sys
import json
import time
import argparse
from typing import Callable, List, Optional, Tuple

from .config import (
    RETRY_CONFIG, LOCAL_CONFIG, OUTPUT_CONFIG, IMAGE_CONFIG,
    EXTRACTION_MODELS, TEXT_EXTRACTION_MODELS,
    MATRIX_FORMATTING_RULES,
)
from .models import (
    Question, VariationResult, PageInfo, ExtractionMethod,
    ValidationStatus, ExtractedImage,
)
from .pdf_ingestion import (
    get_pdf_page_count, detect_page_type, extract_page_markdown,
    render_page_to_image, extract_embedded_images,
)
from .question_parser import extract_questions_from_markdown
from .ocr_extractor import is_ocr_available, ocr_page, assess_ocr_quality
from .image_processor import prepare_image_for_ai, classify_image_type
from .ai_client import (
    call_with_fallback, build_extraction_system_prompt,
    build_vision_message, encode_image,
)
from .solution_generator import generate_solution, solve_questions as _solve_questions
from .variation_generator import (
    generate_variation_batch as _generate_variation_batch,
    generate_all_variations,
)
from .validator import validate_batch, validate_question
from .cache import (
    cache_page_extraction, get_cached_page_extraction,
    cache_ocr_result, get_cached_ocr_result,
)

# Import DOCX exporter (backward-compatible)
try:
    from .docx_exporter import export_docx
except ImportError:
    from docx_exporter import export_docx


# ---------------------------------------------------------------------------
# Backward-compatible aliases for the old API
# ---------------------------------------------------------------------------

# These allow existing code that imports from pipeline to keep working.
# New code should use the new module interfaces directly.

# Re-export config values that were previously module-level constants
EXTRACTION_DELAY_SECONDS = RETRY_CONFIG.extraction_delay_seconds
RATE_LIMIT_MAX_RETRIES = RETRY_CONFIG.rate_limit_max_retries
RATE_LIMIT_BACKOFF_SECONDS = RETRY_CONFIG.rate_limit_backoff_seconds
PAGE_MAX_RETRIES = RETRY_CONFIG.page_max_retries
PAGE_BACKOFF_SECONDS = RETRY_CONFIG.page_backoff_seconds
MIN_TEXT_EXTRACTION_CHARS = LOCAL_CONFIG.min_text_chars
LOCAL_PARSING_ENABLED = LOCAL_CONFIG.local_parsing_enabled

# Re-export model chains
__all__ = [
    "run_pipeline", "extract_all_questions_from_pdf", "extract_page_questions",
    "get_pdf_page_count", "generate_variation_results", "generate_variation_batch",
    "export_results", "solve_questions", "generate_variations",
    "generate_solution", "encode_image", "_extract_json",
    "EXTRACTION_MODELS", "TEXT_EXTRACTION_MODELS", "VARIATION_MODELS", "SOLUTION_MODELS",
    "MATRIX_FORMATTING_RULES",
]


# ---------------------------------------------------------------------------
# Local extraction functions (backward-compatible)
# ---------------------------------------------------------------------------

def _extract_pdf_markdown(pdf_path: str, pages=None):
    """Convert PDF to per-page Markdown. Backward-compatible wrapper."""
    from .pdf_ingestion import extract_all_pages_markdown

    page_indices = None
    if pages is not None:
        page_indices = pages

    result = extract_all_pages_markdown(pdf_path, max_pages=None)
    if page_indices is not None:
        return {i: result.get(i, "") for i in page_indices}
    return result


def _assess_page_text(text):
    """Assess page text quality. Backward-compatible wrapper."""
    text = (text or "").strip()
    has_markers = bool(_QUESTION_MARKER_RE.search(text))
    if len(text) < max(MIN_TEXT_EXTRACTION_CHARS // 5, 10):
        return False, False
    if has_markers:
        return True, True
    if len(text) < MIN_TEXT_EXTRACTION_CHARS:
        return False, False
    import re
    has_words = len(re.findall(r"[A-Za-z]{4,}", text)) >= 3
    return has_words, has_markers


def parse_questions_from_text(page_text, qid_regex=None):
    """Parse questions from text. Backward-compatible wrapper."""
    from .question_parser import parse_questions_from_text as _parse
    return _parse(page_text, qid_regex=qid_regex)


# Import the regex for backward compatibility
import re as _re
_QUESTION_MARKER_RE = _re.compile(
    r"(?m)(^\s*\d{1,3}\s*\.|\b[A-E]\s*[\.\)]|\bPernyataan\b|\(\s*\d\s*\))"
)


# ---------------------------------------------------------------------------
# Image extraction and AI enrichment
# ---------------------------------------------------------------------------

def _extract_image_descriptions(image_paths: List[str], output_dir: str,
                                status_callback=None) -> dict:
    """Describe images using AI. Only called when local methods fail."""
    from .config import IMAGE_DESCRIPTION_MODELS, TOKEN_LIMITS, TEMPERATURES
    from .ai_client import build_image_description_prompt

    descriptions = {}
    system_prompt = build_image_description_prompt()

    for img_path in image_paths:
        # Check cache first
        from .cache import get_cached_image_description, cache_image_description
        cached = get_cached_image_description(img_path)
        if cached:
            descriptions[os.path.basename(img_path)] = cached
            continue

        processed = prepare_image_for_ai(img_path, output_dir)
        if not processed:
            continue

        try:
            user_content = build_vision_message(
                processed,
                "Describe this image from an Indonesian math exam."
            )
            result = call_with_fallback(
                models=IMAGE_DESCRIPTION_MODELS,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=TOKEN_LIMITS.image_description,
                temperature=TEMPERATURES.image_description,
                min_keys=["description", "image_type"],
                status_callback=status_callback,
            )
            descriptions[os.path.basename(img_path)] = result
            cache_image_description(img_path, result)
        except Exception as e:
            print(f"  Failed to describe image {img_path}: {e}")

    return descriptions


# ---------------------------------------------------------------------------
# Core extraction functions
# ---------------------------------------------------------------------------

def extract_all_questions_from_image(image_path, custom_instruction=None,
                                     status_callback=None):
    """Extract ALL questions from a page image via vision LLM.

    Backward-compatible: same signature as the original.
    """
    system_prompt = build_extraction_system_prompt(source="image", all_questions=True,
                                                    custom_instruction=custom_instruction)
    user_content = build_vision_message(
        image_path,
        "Extract ALL complete questions from this image as JSON."
    )

    result = call_with_fallback(
        models=EXTRACTION_MODELS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=2048,
        temperature=0.1,
        min_keys=["questions"],
        status_callback=status_callback,
    )

    if isinstance(result.get("questions"), list):
        questions_data = [q for q in result["questions"]
                         if isinstance(q, dict) and q.get("question_text")]
        if questions_data:
            from .models import Question, ExtractionMethod
            return [
                Question.from_dict({
                    **q,
                    "extraction_method": ExtractionMethod.VISION_LLM.value,
                    "confidence": 0.8,
                })
                for q in questions_data
            ]

    raise RuntimeError("Extraction model returned no valid questions for this image.")


def extract_all_questions_from_text(page_text, custom_instruction=None,
                                    status_callback=None):
    """Extract ALL questions from page text via text LLM.

    Backward-compatible: same signature as the original.
    """
    system_prompt = build_extraction_system_prompt(source="text", all_questions=True,
                                                    custom_instruction=custom_instruction)

    result = call_with_fallback(
        models=TEXT_EXTRACTION_MODELS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": page_text},
        ],
        max_tokens=2048,
        temperature=0.1,
        min_keys=["questions"],
        status_callback=status_callback,
    )

    if isinstance(result.get("questions"), list):
        questions_data = [q for q in result["questions"]
                         if isinstance(q, dict) and q.get("question_text")]
        if questions_data:
            from .models import Question, ExtractionMethod
            return [
                Question.from_dict({
                    **q,
                    "extraction_method": ExtractionMethod.TEXT_LLM.value,
                    "confidence": 0.85,
                })
                for q in questions_data
            ]

    raise RuntimeError("Text extraction model returned no valid questions for this page.")


def extract_all_questions_from_page_text(page_text, custom_instruction=None,
                                         status_callback=None):
    """Extract questions from page text: local parse first, LLM fallback.

    Backward-compatible.
    """
    if LOCAL_PARSING_ENABLED:
        local = parse_questions_from_text(page_text)
        if local:
            print(f"  Parsed {len(local)} question(s) locally (no LLM call).")
            return local
        print("  Local parsing found no questions -- falling back to TEXT LLM.")

    return extract_all_questions_from_text(
        page_text, custom_instruction=custom_instruction,
        status_callback=status_callback,
    )


def extract_page_questions(pdf_path, page_index, custom_instruction=None,
                           status_callback=None):
    """Extract ALL questions from ONE page (1-based page_index).

    Backward-compatible: same signature as the original.
    LOCAL-FIRST: text extraction -> local parse -> LLM fallback -> OCR -> vision.
    """
    pages_dir = OUTPUT_CONFIG.pages_dir
    os.makedirs(pages_dir, exist_ok=True)

    # Check cache
    cached = get_cached_page_extraction(pdf_path, page_index)
    if cached:
        print(f"  Cache hit for page {page_index}")
        from .models import Question
        return [Question.from_dict(q) for q in cached.get("questions", [])]

    # Step 1: Try local text extraction
    markdown = _extract_pdf_markdown(pdf_path, pages=[page_index - 1])
    text = markdown.get(page_index - 1, "")
    usable, has_markers = _assess_page_text(text)

    if usable:
        print(f"  Page {page_index}: {len(text)} chars, markers={has_markers}. Using local/TEXT LLM.")
        try:
            questions = extract_all_questions_from_page_text(
                text, custom_instruction=custom_instruction,
                status_callback=status_callback,
            )
        except RuntimeError:
            print(f"  Page {page_index}: no questions found in text -- treating as empty.")
            return []
    else:
        # Step 2: Try OCR for scanned pages
        if is_ocr_available():
            print(f"  Page {page_index}: no extractable text. Trying local OCR...")
            ocr_text, ocr_conf, ocr_usable = ocr_page(
                pdf_path, page_index, pages_dir
            )

            if ocr_usable and ocr_text:
                # Try local parse on OCR text first
                local = parse_questions_from_text(ocr_text, page_number=page_index)
                if local:
                    print(f"  Page {page_index}: OCR + local parse found {len(local)} questions.")
                    questions = local
                else:
                    # Use LLM to clean OCR text
                    try:
                        from .config import OCR_CLEANUP_MODELS, TOKEN_LIMITS, TEMPERATURES
                        from .ai_client import build_ocr_cleanup_prompt

                        cleanup_result = call_with_fallback(
                            models=OCR_CLEANUP_MODELS,
                            messages=[
                                {"role": "system", "content": build_ocr_cleanup_prompt()},
                                {"role": "user", "content": ocr_text},
                            ],
                            max_tokens=TOKEN_LIMITS.ocr_cleanup,
                            temperature=TEMPERATURES.ocr_cleanup,
                        )
                        cleaned = cleanup_result.get("cleaned_text", ocr_text)
                        questions = extract_questions_from_markdown(cleaned, page_number=page_index)
                        if questions:
                            for q in questions:
                                q.extraction_method = ExtractionMethod.HYBRID
                    except Exception:
                        questions = []

                if not questions:
                    # Step 3: Vision model fallback for this page
                    print(f"  Page {page_index}: OCR insufficient. Rendering and using vision model.")
                    page_png = os.path.join(pages_dir, f"page_{page_index:02d}.png")
                    rendered = render_page_to_image(pdf_path, page_index, page_png,
                                                    dpi=IMAGE_CONFIG.render_dpi)
                    if rendered:
                        questions = extract_all_questions_from_image(
                            page_png, custom_instruction=custom_instruction,
                            status_callback=status_callback,
                        )
                    else:
                        print(f"  Page {page_index}: could not render. Skipping.")
                        return []
            else:
                # OCR not usable, fall through to vision
                print(f"  Page {page_index}: OCR quality insufficient. Using vision model.")
                page_png = os.path.join(pages_dir, f"page_{page_index:02d}.png")
                rendered = render_page_to_image(pdf_path, page_index, page_png,
                                                dpi=IMAGE_CONFIG.render_dpi)
                if rendered:
                    questions = extract_all_questions_from_image(
                        page_png, custom_instruction=custom_instruction,
                        status_callback=status_callback,
                    )
                else:
                    return []
        else:
            # No OCR available, go straight to vision
            print(f"  Page {page_index}: No OCR engine available. Using vision model.")
            page_png = os.path.join(pages_dir, f"page_{page_index:02d}.png")
            rendered = render_page_to_image(pdf_path, page_index, page_png,
                                            dpi=IMAGE_CONFIG.render_dpi)
            if rendered:
                questions = extract_all_questions_from_image(
                    page_png, custom_instruction=custom_instruction,
                    status_callback=status_callback,
                )
            else:
                return []

    # Set page numbers and metadata
    for q in questions:
        q.page_number = page_index
        q.source_pdf = os.path.basename(pdf_path)

    # Try to extract embedded images for the page
    try:
        images_dir = OUTPUT_CONFIG.images_dir
        embedded = extract_embedded_images(pdf_path, page_index, images_dir)
        for img_info in embedded:
            img = ExtractedImage(
                image_id=os.path.basename(img_info["path"]),
                image_path=img_info["path"],
                width=img_info["width"],
                height=img_info["height"],
                page_number=page_index,
            )
            # Associate image with nearest question
            if questions:
                idx = min(img_info["index"], len(questions) - 1)
                questions[idx].images.append(img)
    except Exception:
        pass  # Image extraction is best-effort

    # Cache the results
    cache_page_extraction(pdf_path, page_index, {
        "questions": [q.to_dict() for q in questions]
    })

    return questions


def _extract_page_with_retries(extractor, page_num, questions, skipped_pages,
                               status_callback=None):
    """Run a page's extractor with exponential-backoff retries.

    Backward-compatible wrapper.
    """
    for attempt in range(1, PAGE_MAX_RETRIES + 1):
        try:
            page_questions = extractor()
            for q in page_questions:
                if not q.page_number:
                    q.page_number = page_num
                questions.append(q)
            print(f"  Extracted {len(page_questions)} question(s) from page {page_num}")
            return True
        except Exception as e:
            if attempt == PAGE_MAX_RETRIES:
                skipped_pages.append(page_num)
                print(f"  Page {page_num} failed after {PAGE_MAX_RETRIES} attempts: {e}")
                if status_callback:
                    status_callback(f"Page {page_num} failed after {PAGE_MAX_RETRIES} attempts.")
                return False
            delay = PAGE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            msg = f"Page {page_num} failed (attempt {attempt}/{PAGE_MAX_RETRIES}); retrying in {int(delay)}s..."
            print(f"  {msg}")
            if status_callback:
                status_callback(msg)
            time.sleep(delay)
    return False


def extract_all_questions_from_pdf(pdf_path, custom_instruction=None,
                                   progress_callback=None, status_callback=None,
                                   max_pages=None):
    """Extract ALL questions from every page. LOCAL-FIRST strategy.

    Backward-compatible: same signature and return type as the original.
    """
    print("  Extracting ALL questions (LOCAL-FIRST strategy)...")

    pages_dir = OUTPUT_CONFIG.pages_dir
    os.makedirs(pages_dir, exist_ok=True)

    questions = []
    skipped_pages = []

    page_count = get_pdf_page_count(pdf_path)
    pages_to_process = page_count if max_pages is None else min(max_pages, page_count)
    print(f"  PDF has {page_count} page(s). Processing {pages_to_process}.")

    for i in range(pages_to_process):
        page_num = i + 1

        extracted = _extract_page_with_retries(
            lambda p=page_num: extract_page_questions(
                pdf_path, p,
                custom_instruction=custom_instruction,
                status_callback=status_callback,
            ),
            page_num=i + 1,
            questions=questions,
            skipped_pages=skipped_pages,
            status_callback=status_callback,
        )

        if not extracted:
            continue

        if progress_callback:
            progress_callback(
                i + 1, pages_to_process, "extract",
                f"Extracting page {i + 1} of {pages_to_process}...",
            )

        # Throttle between pages
        if i + 1 < pages_to_process:
            throttle_msg = f"Waiting {int(EXTRACTION_DELAY_SECONDS)}s for rate limit..."
            print(f"  {throttle_msg}")
            if status_callback:
                status_callback(throttle_msg)
            time.sleep(EXTRACTION_DELAY_SECONDS)

    # Validate all extracted questions
    valid, warned, invalid = validate_batch(questions)
    print(f"  Validation: {valid} valid, {warned} warnings, {invalid} invalid")

    return questions, skipped_pages


# ---------------------------------------------------------------------------
# Variation generation (backward-compatible)
# ---------------------------------------------------------------------------

def generate_variations(original_q, custom_instruction=None, status_callback=None):
    """Generate easy/medium/hard variations. Backward-compatible."""
    from .variation_generator import generate_variations as _gen
    return _gen(original_q, custom_instruction=custom_instruction,
                status_callback=status_callback)


def generate_solution(original_q, custom_instruction=None, status_callback=None):
    """Generate solution. Backward-compatible."""
    from .solution_generator import generate_solution as _gen
    return _gen(original_q, custom_instruction=custom_instruction,
                status_callback=status_callback)


def solve_questions(questions, custom_instruction=None, progress_callback=None,
                    status_callback=None):
    """Solve questions. Backward-compatible."""
    return _solve_questions(questions, custom_instruction=custom_instruction,
                           progress_callback=progress_callback,
                           status_callback=status_callback)


def generate_variation_batch(questions, start, batch_size, custom_instruction=None,
                             progress_callback=None, status_callback=None):
    """Generate variation batch. Backward-compatible.

    Returns list of VariationResult dicts (for backward compat with old format).
    """
    results = _generate_variation_batch(
        questions, start=start, batch_size=batch_size,
        custom_instruction=custom_instruction,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
    # Convert to old dict format for backward compatibility
    return [r.to_dict() for r in results]


def generate_variation_results(questions, custom_instruction=None,
                               progress_callback=None, status_callback=None):
    """Generate variations for all questions. Backward-compatible."""
    results = generate_all_variations(
        questions, custom_instruction=custom_instruction,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
    return [r.to_dict() for r in results]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_results(results, output_docx):
    """Export results to DOCX and JSON sidecar. Backward-compatible."""
    # Build the questions list in the format docx_exporter expects
    questions_for_export = []
    for item in results:
        if isinstance(item, dict):
            # Already in dict format (from variation results)
            questions_for_export.append(item)
        elif isinstance(item, VariationResult):
            questions_for_export.append(item.to_dict())
        elif isinstance(item, Question):
            # Single question without variations
            questions_for_export.append({
                "page": item.page_number,
                "original": item.to_dict(),
                "variations": {},
            })

    export_docx(questions_for_export, output_docx)

    results_path = output_docx.rsplit(".", 1)[0] + ".json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"questions": questions_for_export}, f, ensure_ascii=False, indent=2)

    print(f"  DOCX saved to: {output_docx}")
    return output_docx


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(pdf_path, output_docx, custom_instruction=None,
                 batch_size=5, continue_callback=None, progress_callback=None,
                 status_callback=None, max_pages=None):
    """Run the full pipeline: PDF -> Extract -> Vary -> DOCX.

    Backward-compatible: same signature as the original.
    """
    print("Starting End-to-End Exam Generator Pipeline...\n")

    all_questions, skipped_pages = extract_all_questions_from_pdf(
        pdf_path,
        custom_instruction=custom_instruction,
        progress_callback=progress_callback,
        status_callback=status_callback,
        max_pages=max_pages,
    )

    if not all_questions:
        last = f" Last error was on page {skipped_pages[-1]}." if skipped_pages else ""
        raise RuntimeError(
            f"Pipeline produced no questions -- every page failed.{last} "
            "Check the logs above."
        )

    total = len(all_questions)
    print(f"\n  Extracted {total} question(s). "
          f"Generating variations in batches of {batch_size}...")
    if skipped_pages:
        print(f"  Skipped page(s): {skipped_pages}")

    # Convert Questions to dicts for variation generation
    questions_as_dicts = [q.to_dict() for q in all_questions]

    results = []
    for start in range(0, total, batch_size):
        batch_results = generate_variation_batch(
            questions_as_dicts, start, batch_size,
            custom_instruction=custom_instruction,
            progress_callback=progress_callback,
            status_callback=status_callback,
        )
        results.extend(batch_results)
        processed = len(results)
        print(f"  Variations generated for {processed}/{total} question(s).")
        if continue_callback and processed < total:
            if not continue_callback(processed, total):
                print("  Processing stopped by user -- exporting partial results.")
                break

    export_results(results, output_docx)
    print(f"Success! {len(results)}/{total} question(s) exported to: {output_docx}")

    return output_docx


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract questions from a PDF, generate variations, export DOCX."
    )
    parser.add_argument("--pdf", default="data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf",
                        help="Path to the input exam PDF.")
    parser.add_argument("--output", default="data/outputs/final_pipeline_test.docx",
                        help="Where to save the generated DOCX.")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Only process the first N pages.")
    args = parser.parse_args()

    run_pipeline(
        pdf_path=args.pdf,
        output_docx=args.output,
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
