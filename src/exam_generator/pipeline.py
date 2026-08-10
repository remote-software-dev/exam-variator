import os
import sys
import json
import base64
import re
import time
import litellm
from dotenv import load_dotenv
from litellm.exceptions import RateLimitError

# Add the project root to the path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import the Markdown-aware DOCX exporter (relative when run as a package,
# absolute when this file is executed directly as a script).
try:
    from .docx_exporter import export_docx
except ImportError:
    from docx_exporter import export_docx

load_dotenv()

# Fallback: load secrets from Streamlit Cloud if .env is missing.
# LiteLLM reads the provider keys from the environment automatically, so we
# just make sure GROQ (and Gemini, via GEMINI_API_KEY or GOOGLE_API_KEY) are set.
def _ensure_api_key(env_name):
    if env_name in os.environ:
        return
    try:
        import streamlit as st
        os.environ[env_name] = st.secrets[env_name]
    except Exception:
        pass

_ensure_api_key("GROQ_API_KEY")
_ensure_api_key("GEMINI_API_KEY")
_ensure_api_key("GOOGLE_API_KEY")

# Hybrid model fallback chain: tries models in order until one succeeds.
# Extraction REQUIRES a vision model — currently only qwen3.6-27b on Groq
# accepts image input (llama-3.3/3.1-8b and gpt-oss are text-only; the old
# vision previews are decommissioned). Gemini is the safety net: huge free
# tier, so a Groq rate limit falls through instead of stalling the pipeline.
EXTRACTION_MODELS = [
    "groq/qwen/qwen3.6-27b",
    "gemini/gemini-2.0-flash",
]

VARIATION_MODELS = [
    "groq/llama-3.3-70b-versatile",
    "gemini/gemini-2.0-flash",
    "groq/openai/gpt-oss-120b",
]

# Models used to generate the solution discussion (pembahasan) shown in the
# preview so the user can verify how the AI solves each question.
SOLUTION_MODELS = [
    "groq/llama-3.3-70b-versatile",
    "gemini/gemini-2.0-flash",
    "groq/openai/gpt-oss-120b",
]

# Pause between pages to stay under the Groq free-tier TPM rate limit.
EXTRACTION_DELAY_SECONDS = 10.0

# On a RateLimitError, retry the SAME model briefly with exponential backoff
# (15s -> 30s), then re-raise so the caller falls through to the NEXT model
# (e.g. Gemini) instead of being stuck on a rate-limited provider.
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = 15.0

# Hard cap on retrying the exact same page before logging a clear warning and
# moving on. Page waits use exponential backoff: 15s, 30s, 60s, 120s.
PAGE_MAX_RETRIES = 5
PAGE_BACKOFF_SECONDS = 15.0


def _completion_with_retry(model, messages, status_callback=None, **kwargs):
    """Call litellm.completion, briefly retrying the same model on RateLimitError.

    Waits are exponential (15s -> 30s). After RATE_LIMIT_MAX_RETRIES the
    RateLimitError is re-raised so the caller's fallback chain moves to the
    NEXT model (e.g. from rate-limited Groq to Gemini) rather than stalling on
    a single provider. Any non-rate-limit exception propagates immediately so
    the same fallback logic applies.

    status_callback: optional callable(message) notified before each wait so
    the UI can show that the app is still working.
    """
    delay = RATE_LIMIT_BACKOFF_SECONDS
    for attempt in range(1, RATE_LIMIT_MAX_RETRIES + 1):
        try:
            return litellm.completion(model=model, messages=messages, **kwargs)
        except RateLimitError as e:
            if attempt == RATE_LIMIT_MAX_RETRIES:
                raise
            message = (
                f"⏳ Menunggu batas rate limit... (Mencoba lagi dalam {int(delay)} "
                f"detik, percobaan {attempt}/{RATE_LIMIT_MAX_RETRIES})"
            )
            print(f"  {message} — {model}")
            if status_callback:
                status_callback(message)
            time.sleep(delay)
            delay *= 2

    raise RuntimeError("unreachable")

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

MATRIX_FORMATTING_RULES = (
    "MATRICES: always use $\\begin{bmatrix} ... \\end{bmatrix}$ LaTeX "
    "(entries separated by &, rows by \\\\); NEVER '|', '||', '∨', or plain text "
    "arrays. Example: [[2,0],[0,1/2]] → $\\begin{bmatrix} 2 & 0 \\\\ "
    "0 & \\frac{1}{2} \\end{bmatrix}$"
)

def _extract_json(text):
    """Robustly extract the first JSON object from model output."""
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if not match:
        match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).replace("'", '"'))
        except json.JSONDecodeError:
            return None
    return None

def _extraction_system_prompt(custom_instruction, all_questions):
    """Build the shared system prompt for the (single/all) extraction tasks."""
    if all_questions:
        intro = (
            "You extract Indonesian math exam questions from scanned images.\n"
            "Return ONLY a JSON object: {\"questions\": [{\"id\": str, "
            "\"question_text\": str, \"options\": [str]}]}. Extract EVERY "
            "complete question visible — do not skip, merge, or omit any.\n\n"
        )
    else:
        intro = (
            "You extract Indonesian math exam questions from scanned images.\n"
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
            "\n\nADDITIONAL USER INSTRUCTIONS (apply when relevant, e.g. for "
            "solution styles):\n"
            f"{custom_instruction.strip()}"
        )

    return intro + rules


def _extract_via_llm(system_prompt, user_text, models, min_keys=None, status_callback=None):
    """Run the extraction prompt against the model fallback chain."""
    last_error = None
    for model in models:
        try:
            response = _completion_with_retry(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.1,
                status_callback=status_callback,
            )
            raw = response.choices[0].message.content
            result = _extract_json(raw)
            if result:
                if min_keys and any(k not in result for k in min_keys):
                    print(f"  ⚠ {model} returned incomplete JSON, trying next...")
                    continue
                return result
            print(f"  ⚠ {model} returned unparseable JSON, trying next...")
        except Exception as e:
            last_error = e
            print(f"  ⚠ {model} failed: {e}, trying next...")

    raise RuntimeError(f"All extraction models failed. Last error: {last_error}")


def extract_question_from_image(image_path, custom_instruction=None, status_callback=None):
    print("  [1/4] Extracting question from image via LiteLLM (with fallbacks)...")
    base64_image = encode_image(image_path)

    system_prompt = _extraction_system_prompt(custom_instruction, all_questions=False)

    user_content = [
        {"type": "text", "text": "Extract the first complete question from this image as JSON."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
    ]

    return _extract_via_llm(
        system_prompt,
        user_content,
        EXTRACTION_MODELS,
        min_keys=["id", "question_text"],
        status_callback=status_callback,
    )


def extract_all_questions_from_image(image_path, custom_instruction=None, status_callback=None):
    """Extract ALL complete questions from an image. Returns a list of question dicts."""
    print("  Extracting ALL questions from image via LiteLLM (with fallbacks)...")
    base64_image = encode_image(image_path)

    system_prompt = _extraction_system_prompt(custom_instruction, all_questions=True)

    user_content = [
        {"type": "text", "text": "Extract ALL complete questions from this image as JSON."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
    ]

    result = _extract_via_llm(
        system_prompt,
        user_content,
        EXTRACTION_MODELS,
        min_keys=["questions"],
        status_callback=status_callback,
    )

    if isinstance(result.get("questions"), list):
        questions = [q for q in result["questions"]
                     if isinstance(q, dict) and q.get("question_text")]
        if questions:
            return questions

    raise RuntimeError(
        "Extraction model returned no valid questions for this image."
    )

def generate_variations(original_q, custom_instruction=None, status_callback=None):
    print("  [2/4] Generating easier and harder variations via LiteLLM (with fallbacks)...")

    system_prompt = (
        "You are a math exam question writer for Indonesian secondary schools.\n"
        "Given an original multiple-choice question, produce two variations: 'easier' and 'harder'.\n\n"
        "STRICT FORMAT RULES:\n"
        "- Return ONLY a valid JSON object.\n"
        "- Top-level keys: 'easier' and 'harder'.\n"
        "- Each variation must contain:\n"
        "  * 'question_text': string (the question stem)\n"
        "  * 'options': array of exactly 5 strings (labeled A through E in the output)\n"
        "  * 'solution_by_concept': string (optional) — the solution using the basic "
        "concept/method, written as detailed markdown.\n"
        "  * 'solution_by_trick': string (optional) — a quick/shortcut way to solve "
        "it, written as detailed markdown.\n"
        "- Only include 'solution_by_concept' / 'solution_by_trick' when the "
        "ADDITIONAL USER INSTRUCTIONS ask for solution methods.\n"
        "- Do NOT convert multiple-choice into essay or fill-in-the-blank questions.\n"
        "- Do NOT change the number of options. Every variation MUST have exactly 5 options.\n"
        "- Do NOT include option labels (A., B., etc.) inside the option strings — just the answer text.\n"
        "- Use LaTeX math notation enclosed in $ delimiters for all formulas.\n"
        f"- {MATRIX_FORMATTING_RULES}\n"
        "- Keep the same mathematical topic and difficulty relative to the label (easier = simpler numbers/steps, "
        "harder = more complex numbers/steps or additional concepts).\n"
        "- Preserve the original Indonesian language.\n"
        "- Use double quotes for all JSON keys and string values.\n"
        "- Do NOT wrap the JSON in markdown code fences."
    )

    if custom_instruction and custom_instruction.strip():
        system_prompt += (
            "\n\nADDITIONAL USER INSTRUCTIONS (follow them exactly for every variation):\n"
            f"{custom_instruction.strip()}\n"
            "If these instructions ask for solution methods (e.g. 'by concept' or "
            "'trick/cara cepat'), produce them under 'solution_by_concept' and "
            "'solution_by_trick' using markdown (bold, lists, $LaTeX$ math)."
        )

    user_prompt = (
        f"Original question:\n{json.dumps(original_q, ensure_ascii=False, indent=2)}\n\n"
        "Generate the 'easier' and 'harder' variations now."
    )

    last_error = None
    for model in VARIATION_MODELS:
        try:
            response = _completion_with_retry(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                status_callback=status_callback,
            )
            raw = response.choices[0].message.content
            result = _extract_json(raw)
            if result and "easier" in result and "harder" in result:
                return result
            print(f"  ⚠ {model} returned invalid variation structure, trying next...")
        except Exception as e:
            last_error = e
            print(f"  ⚠ {model} failed: {e}, trying next...")

    raise RuntimeError(f"All variation models failed. Last error: {last_error}")

def generate_solution(original_q, custom_instruction=None, status_callback=None):
    """Generate a solution discussion (pembahasan) for a single question.

    Returns a dict with 'solution_by_concept' and 'solution_by_trick' keys
    (mirroring the variation format so rendering can be reused).
    """
    print("  Generating solution discussion (pembahasan) via LiteLLM (with fallbacks)...")

    system_prompt = (
        "You are an expert math teacher for Indonesian secondary schools.\n"
        "Given a question, produce a clear, step-by-step solution discussion "
        "(pembahasan) that teaches the student HOW to solve it.\n\n"
        "STRICT FORMAT RULES:\n"
        "- Return ONLY a valid JSON object.\n"
        "- Top-level keys: 'solution_by_concept' and 'solution_by_trick'.\n"
        "  * 'solution_by_concept': string — the full solution using the basic "
        "concept/method, step by step, written as detailed markdown.\n"
        "  * 'solution_by_trick': string — a quick/shortcut way to solve it, "
        "written as detailed markdown. If no real shortcut exists, restate the "
        "most efficient approach.\n"
        "- Explain every step and the reasoning behind each transformation; "
        "state the final answer (key answer) explicitly.\n"
        "- Use LaTeX math notation enclosed in $ delimiters for all formulas.\n"
        f"- {MATRIX_FORMATTING_RULES}\n"
        "- Preserve the original Indonesian language.\n"
        "- Use double quotes for all JSON keys and string values.\n"
        "- Do NOT wrap the JSON in markdown code fences."
    )

    if custom_instruction and custom_instruction.strip():
        system_prompt += (
            "\n\nADDITIONAL USER INSTRUCTIONS (follow them exactly):\n"
            f"{custom_instruction.strip()}\n"
            "If these instructions ask for a specific solution style (e.g. 'by "
            "concept' or 'trick/cara cepat'), emphasize and clearly label that "
            "style in the corresponding field."
        )

    user_prompt = (
        f"Question:\n{json.dumps(original_q, ensure_ascii=False, indent=2)}\n\n"
        "Generate the solution discussion (pembahasan) now."
    )

    last_error = None
    for model in SOLUTION_MODELS:
        try:
            response = _completion_with_retry(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                status_callback=status_callback,
            )
            raw = response.choices[0].message.content
            result = _extract_json(raw)
            if result and any(
                k in result for k in ("solution_by_concept", "solution_by_trick")
            ):
                return result
            print(f"  ⚠ {model} returned invalid solution structure, trying next...")
        except Exception as e:
            last_error = e
            print(f"  ⚠ {model} failed: {e}, trying next...")

    raise RuntimeError(f"All solution models failed. Last error: {last_error}")

def solve_questions(questions, custom_instruction=None, progress_callback=None,
                    status_callback=None):
    """Generate a solution discussion (pembahasan) for every question in place.

    Each question dict gains 'solution_by_concept' and 'solution_by_trick' keys
    so the preview can show the AI explanation next to the raw question text.

    Args:
        progress_callback: Optional callable(current, total, stage, message).
            Called after every question; stage is "solve".
        status_callback: Optional callable(message) for waiting/retry feedback.

    Returns the same (mutated) list of questions.
    """
    total = len(questions)
    for done, q in enumerate(questions, 1):
        solution = generate_solution(
            q,
            custom_instruction=custom_instruction,
            status_callback=status_callback,
        )
        q["solution_by_concept"] = solution.get("solution_by_concept", "")
        q["solution_by_trick"] = solution.get("solution_by_trick", "")
        print(f"  ✅ Solution generated for '{q.get('id', 'Unknown ID')}'")
        if progress_callback:
            progress_callback(
                done,
                total,
                "solve",
                f"Membuat pembahasan soal {done} dari {total}...",
            )
    return questions

def extract_all_questions_from_pdf(pdf_path, custom_instruction=None,
                                   progress_callback=None, status_callback=None):
    """Render each page to PNG and extract ALL questions from every page.

    The page loop is "unbreakable": every page is retried (same page, same
    image) with exponential backoff until extraction succeeds. A page is only
    abandoned after PAGE_MAX_RETRIES attempts, and a clear warning is logged
    (never silently skipped). RateLimitErrors are retried with their own
    backoff inside _completion_with_retry.

    Args:
        pdf_path: Path to the input PDF exam paper.
        custom_instruction: Optional user-provided instructions for the LLM.
        progress_callback: Optional callable(current, total, stage, message).
            Called after each page is extracted; stage is "extract".
        status_callback: Optional callable(message) for waiting/retry feedback.

    Returns (questions, skipped_pages). Each question dict carries its page number
    under the 'page' key so batching can keep results page-aware.
    """
    import fitz  # PyMuPDF

    print("  📄 Rendering pages and extracting ALL questions...")

    pages_dir = "data/outputs/pages"
    os.makedirs(pages_dir, exist_ok=True)

    questions = []
    skipped_pages = []

    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    print(f"  📄 PDF has {page_count} page(s).")

    for i in range(page_count):
        page_label = f"page_{i + 1:02d}"
        try:
            pix = doc[i].get_pixmap(dpi=200)
            page_png = os.path.join(pages_dir, f"{page_label}.png")
            pix.save(page_png)
            print(f"  ✅ Rendered page {i + 1} to {page_png}")
        except Exception as e:
            skipped_pages.append(i + 1)
            print(f"  ⚠️ Page {i + 1} could not be rendered: {e}")
            continue

        extracted = False
        for attempt in range(1, PAGE_MAX_RETRIES + 1):
            try:
                page_questions = extract_all_questions_from_image(
                    page_png,
                    custom_instruction=custom_instruction,
                    status_callback=status_callback,
                )
                for q in page_questions:
                    q.setdefault("page", i + 1)
                print(f"  ✅ Extracted {len(page_questions)} question(s) from page {i + 1}")
                questions.extend(page_questions)
                extracted = True
                break
            except Exception as e:
                if attempt == PAGE_MAX_RETRIES:
                    skipped_pages.append(i + 1)
                    print(f"  ⚠️ Page {i + 1} failed after {PAGE_MAX_RETRIES} attempts: {e}")
                    if status_callback:
                        status_callback(
                            f"⚠️ Halaman {i + 1} gagal setelah {PAGE_MAX_RETRIES} percobaan."
                        )
                    break
                delay = PAGE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                message = (
                    f"⏳ Halaman {i + 1} gagal (percobaan {attempt}/{PAGE_MAX_RETRIES}); "
                    f"mencoba lagi dalam {int(delay)} detik..."
                )
                print(f"  {message}\n  Error: {e}")
                if status_callback:
                    status_callback(message)
                time.sleep(delay)

        if not extracted:
            continue

        if progress_callback:
            progress_callback(
                i + 1,
                page_count,
                "extract",
                f"Sedang mengekstrak soal dari halaman {i + 1} dari {page_count}...",
            )

        # Throttle between pages to avoid hitting the Groq free-tier
        # 8000 TPM rate limit when processing many pages.
        if i + 1 < page_count:
            throttle_message = (
                f"⏳ Menunggu {int(EXTRACTION_DELAY_SECONDS)} detik untuk menghormati "
                f"batas rate limit..."
            )
            print(f"  {throttle_message}")
            if status_callback:
                status_callback(throttle_message)
            time.sleep(EXTRACTION_DELAY_SECONDS)
    doc.close()

    return questions, skipped_pages


def generate_variation_batch(questions, start, batch_size, custom_instruction=None,
                             progress_callback=None, status_callback=None):
    """Generate easier/harder variations for questions[start:start + batch_size].

    Args:
        progress_callback: Optional callable(current, total, stage, message).
            Called after every question; stage is "vary" and current is the
            global question index across the whole exam.
        status_callback: Optional callable(message) for waiting/retry feedback.

    Returns a list of result items with the same shape the DOCX exporter expects:
    {"page": ..., "original": ..., "variations": ...}.
    """
    results = []
    total = len(questions)
    for offset, original_q in enumerate(questions[start:start + batch_size]):
        variations = generate_variations(
            original_q,
            custom_instruction=custom_instruction,
            status_callback=status_callback,
        )
        results.append({
            "page": original_q.get("page"),
            "original": original_q,
            "variations": variations,
        })
        print(f"  ✅ Variations generated for '{original_q.get('id', 'Unknown ID')}'")
        if progress_callback:
            done = start + offset + 1
            progress_callback(
                done,
                total,
                "vary",
                f"Membuat variasi soal {done} dari {total}...",
            )
    return results


def generate_variation_results(questions, custom_instruction=None, progress_callback=None,
                               status_callback=None):
    """Generate easier/harder variations for an already-selected list of questions.

    Args:
        questions: The questions (already selected by the user) to process.
        custom_instruction: Optional user-provided instructions for the LLM.
        progress_callback: Optional callable(current, total, stage, message).
            Called after every question; stage is "vary".
        status_callback: Optional callable(message) for waiting/retry feedback.

    Returns a list of result items with the same shape the DOCX exporter expects:
    {"page": ..., "original": ..., "variations": ...}.
    """
    results = []
    total = len(questions)
    for done, original_q in enumerate(questions, 1):
        variations = generate_variations(
            original_q,
            custom_instruction=custom_instruction,
            status_callback=status_callback,
        )
        results.append({
            "page": original_q.get("page"),
            "original": original_q,
            "variations": variations,
        })
        print(f"  ✅ Variations generated for '{original_q.get('id', 'Unknown ID')}'")
        if progress_callback:
            progress_callback(
                done,
                total,
                "vary",
                f"Membuat variasi soal {done} dari {total}...",
            )
    return results


def export_results(results, output_docx):
    """Export collected results to DOCX and write the JSON preview sidecar."""
    export_docx(results, output_docx)

    results_path = output_docx.rsplit(".", 1)[0] + ".json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"questions": results}, f, ensure_ascii=False, indent=2)

    print(f"  [4/4] DOCX saved to: {output_docx}")
    return output_docx


def run_pipeline(pdf_path, output_docx, custom_instruction=None,
                 batch_size=5, continue_callback=None, progress_callback=None,
                 status_callback=None):
    """Run the full pipeline: PDF -> PNG -> Extract (all questions) -> Vary -> DOCX.

    Args:
        pdf_path: Path to the input PDF exam paper.
        output_docx: Where to save the generated Word document.
        custom_instruction: Optional user-provided instructions for the LLM
            (e.g. "Buat penyelesaian dengan konsep dasar dan cara cepat").
        batch_size: How many questions are varied per batch.
        continue_callback: Optional callable(processed_count, total_count) -> bool.
            Called after every batch once at least one batch has completed; return
            False to stop early and export only the questions processed so far.
            When None (e.g. CLI), the whole exam is processed without pausing.
        progress_callback: Optional callable(current, total, stage, message) where
            stage is "extract" (current/total = page X of N) or "vary"
            (current/total = question X of N). Used by the UI to drive a live
            progress bar.
        status_callback: Optional callable(message) for waiting/retry feedback.

    Every page is retried with exponential backoff until it succeeds, or until
    a hard maximum of retries is hit — in which case a clear warning is logged.
    """
    print("🚀 Starting End-to-End Exam Generator Pipeline...\n")

    all_questions, skipped_pages = extract_all_questions_from_pdf(
        pdf_path,
        custom_instruction=custom_instruction,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )

    if not all_questions:
        last = f" Last error was on page {skipped_pages[-1]}." if skipped_pages else ""
        raise RuntimeError(
            f"Pipeline produced no questions — every page failed.{last} "
            "Check the logs above."
        )

    total = len(all_questions)
    print(f"\n  ✅ Extracted {total} question(s). "
          f"Generating variations in batches of {batch_size}...")
    if skipped_pages:
        print(f"  ⚠ Skipped page(s): {skipped_pages}")

    questions = []
    for start in range(0, total, batch_size):
        questions.extend(generate_variation_batch(
            all_questions, start, batch_size,
            custom_instruction=custom_instruction,
            progress_callback=progress_callback,
            status_callback=status_callback,
        ))
        processed = len(questions)
        print(f"  ✅ Variations generated for {processed}/{total} question(s).")
        if continue_callback and processed < total:
            if not continue_callback(processed, total):
                print("  ⏹ Processing stopped by user callback — exporting partial results.")
                break

    # 4. Export every collected question to a single Word document
    export_results(questions, output_docx)
    print(f"✅ Success! {len(questions)}/{total} question(s) exported to: {output_docx}")

    return output_docx


def main():
    run_pipeline(
        pdf_path="data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf",
        output_docx="data/outputs/final_pipeline_test.docx",
    )

if __name__ == "__main__":
    main()
