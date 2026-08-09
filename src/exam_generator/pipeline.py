import os
import sys
import json
import base64
import re
import time
import litellm
from dotenv import load_dotenv

# Add the project root to the path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Import the Markdown-aware DOCX exporter (relative when run as a package,
# absolute when this file is executed directly as a script).
try:
    from .docx_exporter import export_docx
except ImportError:
    from docx_exporter import export_docx

load_dotenv()

# Fallback: load secrets from Streamlit Cloud if .env is missing
if "GROQ_API_KEY" not in os.environ:
    try:
        import streamlit as st
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
    except Exception:
        pass

# LiteLLM model fallback chain: tries models in order until one succeeds.
# Primary first, then widely-available Groq fallbacks.
EXTRACTION_MODELS = [
    "groq/qwen/qwen3.6-27b",
    "groq/llama-3.1-70b-versatile",
    "groq/llama3-8b-8192",
]

VARIATION_MODELS = [
    "groq/llama-3.3-70b-versatile",
    "openai/gpt-4o-mini",
]

# Pause between pages to stay under the Groq free-tier TPM rate limit.
EXTRACTION_DELAY_SECONDS = 2.0

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

MATRIX_FORMATTING_RULES = (
    "STRICT MATRIX FORMATTING RULES:\n"
    "1. NEVER use '|', '||', '∨', or plain text arrays for matrices.\n"
    "2. You MUST use standard LaTeX matrix environments: "
    "\\begin{bmatrix} ... \\end{bmatrix} (entries separated by &, "
    "rows separated by \\\\).\n"
    "3. FEW-SHOT EXAMPLE: If the matrix is F = [[2, 0], [0, 1/2]], "
    "you MUST output exactly: "
    "\\begin{bmatrix} 2 & 0 \\\\ 0 & \\frac{1}{2} \\end{bmatrix}"
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
            "You are an expert at extracting Indonesian math exam questions from scanned images.\n"
            "Return ONLY a valid JSON object with a single key 'questions', which is a list "
            "of question objects. Each question object has keys: 'id', 'question_text', "
            "'options' (list of strings).\n\n"
            "Extract EVERY complete question visible on the image — do not skip, merge, or "
            "leave out any question.\n\n"
        )
    else:
        intro = (
            "You are an expert at extracting Indonesian math exam questions from scanned images.\n"
            "Return ONLY a valid JSON object with keys: 'id', 'question_text', 'options' (list of strings).\n\n"
        )

    rules = (
        "RULES:\n"
        "- Use LaTeX math notation enclosed in $ delimiters for all formulas "
        "(e.g., $\\frac{a}{b}$, $x^2$, $\\sqrt{3}$).\n"
        f"- {MATRIX_FORMATTING_RULES}\n"
        "- 'id' must be the alphanumeric ID printed on the paper (e.g., '25MATBLGBRLM01SU-000000-0246').\n"
        "  If no ID is visible or the ID is just a number like '1', generate a unique one: "
        "'EXAM-<RANDOM8HEX>'.\n"
        "- Handle ALL question formats:\n"
        "  * Standard multiple choice (A/B/C/D/E) → put options in 'options' list.\n"
        "  * Benar/Salah (True/False) tables → 'options' should be a list of statements "
        "each prefixed with the table label, e.g. ['Pernyataan 1: Benar', 'Pernyataan 2: Salah'].\n"
        "  * Multi-part / stem questions (e.g., 'pernyataan (1), (2), (3)') → put each "
        "statement as a separate item in 'options'.\n"
        "- Preserve the original Indonesian language.\n"
        "- Use double quotes for all JSON keys and string values."
    )

    if custom_instruction and custom_instruction.strip():
        rules += (
            "\n\nADDITIONAL USER INSTRUCTIONS (keep them in mind and apply them "
            "when relevant, e.g. for solution styles):\n"
            f"{custom_instruction.strip()}"
        )

    return intro + rules


def _extract_via_llm(system_prompt, user_text, models, min_keys=None):
    """Run the extraction prompt against the model fallback chain."""
    last_error = None
    for model in models:
        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                temperature=0.1,
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


def extract_question_from_image(image_path, custom_instruction=None):
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
    )


def extract_all_questions_from_image(image_path, custom_instruction=None):
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
    )

    if isinstance(result.get("questions"), list):
        questions = [q for q in result["questions"]
                     if isinstance(q, dict) and q.get("question_text")]
        if questions:
            return questions

    raise RuntimeError(
        "Extraction model returned no valid questions for this image."
    )

def generate_variations(original_q, custom_instruction=None):
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
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
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

def extract_all_questions_from_pdf(pdf_path, custom_instruction=None, progress_callback=None):
    """Render each page to PNG and extract ALL questions from every page.

    Args:
        pdf_path: Path to the input PDF exam paper.
        custom_instruction: Optional user-provided instructions for the LLM.
        progress_callback: Optional callable(current, total, stage, message).
            Called after each page is extracted; stage is "extract".

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

            page_questions = extract_all_questions_from_image(
                page_png, custom_instruction=custom_instruction
            )
            for q in page_questions:
                q.setdefault("page", i + 1)
            print(f"  ✅ Extracted {len(page_questions)} question(s) from page {i + 1}")
            questions.extend(page_questions)

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
                print(f"  ⏳ Waiting {EXTRACTION_DELAY_SECONDS}s to respect the rate limit...")
                time.sleep(EXTRACTION_DELAY_SECONDS)
        except Exception as e:
            skipped_pages.append(i + 1)
            print(f"  ❌ Page {i + 1} failed: {e} — skipping to the next page...")
    doc.close()

    return questions, skipped_pages


def generate_variation_batch(questions, start, batch_size, custom_instruction=None,
                             progress_callback=None):
    """Generate easier/harder variations for questions[start:start + batch_size].

    Args:
        progress_callback: Optional callable(current, total, stage, message).
            Called after every question; stage is "vary" and current is the
            global question index across the whole exam.

    Returns a list of result items with the same shape the DOCX exporter expects:
    {"page": ..., "original": ..., "variations": ...}.
    """
    results = []
    total = len(questions)
    for offset, original_q in enumerate(questions[start:start + batch_size]):
        variations = generate_variations(original_q, custom_instruction=custom_instruction)
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


def run_pipeline(pdf_path, output_docx, custom_instruction=None,
                 batch_size=5, continue_callback=None, progress_callback=None):
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

    Every page is processed independently inside a try/except so a single
    failing page (e.g. a blank page or a bad scan) is logged and skipped
    instead of crashing the whole run.
    """
    print("🚀 Starting End-to-End Exam Generator Pipeline...\n")

    all_questions, skipped_pages = extract_all_questions_from_pdf(
        pdf_path,
        custom_instruction=custom_instruction,
        progress_callback=progress_callback,
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
        ))
        processed = len(questions)
        print(f"  ✅ Variations generated for {processed}/{total} question(s).")
        if continue_callback and processed < total:
            if not continue_callback(processed, total):
                print("  ⏹ Processing stopped by user callback — exporting partial results.")
                break

    # 4. Export every collected question to a single Word document
    export_docx(questions, output_docx)

    # Save a JSON sidecar so the Streamlit UI can render a live preview.
    results_path = output_docx.rsplit(".", 1)[0] + ".json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"questions": questions}, f, ensure_ascii=False, indent=2)

    print(f"  [4/4] DOCX saved to: {output_docx}")
    print(f"✅ Success! {len(questions)}/{total} question(s) exported to: {output_docx}")

    return output_docx


def main():
    run_pipeline(
        pdf_path="data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf",
        output_docx="data/outputs/final_pipeline_test.docx",
    )

if __name__ == "__main__":
    main()
