import os
import sys
import json
import base64
import re
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

# LiteLLM model fallback chain: tries models in order until one succeeds
EXTRACTION_MODELS = [
    "groq/qwen/qwen3.6-27b",
    "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    "groq/meta-llama/llama-4-maverick-17b-128e-instruct",
]

VARIATION_MODELS = [
    "groq/llama-3.3-70b-versatile",
    "openai/gpt-4o-mini",
]

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

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

def extract_question_from_image(image_path, custom_instruction=None):
    print("  [1/4] Extracting question from image via LiteLLM (with fallbacks)...")
    base64_image = encode_image(image_path)

    system_prompt = (
        "You are an expert at extracting Indonesian math exam questions from scanned images.\n"
        "Return ONLY a valid JSON object with keys: 'id', 'question_text', 'options' (list of strings).\n\n"
        "RULES:\n"
        "- Use LaTeX math notation enclosed in $ delimiters for all formulas "
        "(e.g., $\\frac{a}{b}$, $x^2$, $\\sqrt{3}$).\n"
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
        system_prompt += (
            "\n\nADDITIONAL USER INSTRUCTIONS (keep them in mind and apply them "
            "when relevant, e.g. for solution styles):\n"
            f"{custom_instruction.strip()}"
        )

    user_content = [
        {"type": "text", "text": "Extract the first complete question from this image as JSON."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
    ]

    last_error = None
    for model in EXTRACTION_MODELS:
        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
            )
            raw = response.choices[0].message.content
            result = _extract_json(raw)
            if result:
                return result
            print(f"  ⚠ {model} returned unparseable JSON, trying next...")
        except Exception as e:
            last_error = e
            print(f"  ⚠ {model} failed: {e}, trying next...")

    raise RuntimeError(f"All extraction models failed. Last error: {last_error}")

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

def run_pipeline(pdf_path, output_docx, custom_instruction=None):
    """Run the full pipeline: PDF -> PNG -> Extract -> Vary -> DOCX.

    Args:
        pdf_path: Path to the input PDF exam paper.
        output_docx: Where to save the generated Word document.
        custom_instruction: Optional user-provided instructions for the LLM
            (e.g. "Buat penyelesaian dengan konsep dasar dan cara cepat").

    Every page is processed independently inside a try/except so a single
    failing page (e.g. a blank page or a bad scan) is logged and skipped
    instead of crashing the whole run.
    """
    import fitz  # PyMuPDF

    print("🚀 Starting End-to-End Exam Generator Pipeline...\n")

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
            # 1. Render the page to PNG
            pix = doc[i].get_pixmap(dpi=200)
            page_png = os.path.join(pages_dir, f"{page_label}.png")
            pix.save(page_png)
            print(f"  ✅ Rendered page {i + 1} to {page_png}")

            # 2. Extract the question from the rendered page
            original_q = extract_question_from_image(
                page_png, custom_instruction=custom_instruction
            )
            print(f"  ✅ Extracted: {original_q.get('id', 'Unknown ID')}")

            # 3. Generate easier/harder variations (plus any custom solutions)
            variations = generate_variations(original_q, custom_instruction=custom_instruction)
            print("  ✅ Variations generated.")

            questions.append({
                "page": i + 1,
                "original": original_q,
                "variations": variations,
            })
        except Exception as e:
            skipped_pages.append(i + 1)
            print(f"  ❌ Page {i + 1} failed: {e} — skipping to the next page...")
    doc.close()

    if not questions:
        last = f" Last error was on page {skipped_pages[-1]}." if skipped_pages else ""
        raise RuntimeError(
            f"Pipeline produced no questions — every page failed.{last} "
            "Check the logs above."
        )

    print(f"\n  ✅ Processed {len(questions)}/{page_count} page(s) successfully.")
    if skipped_pages:
        print(f"  ⚠ Skipped page(s): {skipped_pages}")

    # 4. Export every collected question to a single Word document
    export_docx(questions, output_docx)
    print(f"  [4/4] DOCX saved to: {output_docx}")
    print(f"✅ Success! Output saved to: {output_docx}")

    return output_docx


def main():
    run_pipeline(
        pdf_path="data/inputs/SOAL TKA Matematika SMA 2025 Umum.pdf",
        output_docx="data/outputs/final_pipeline_test.docx",
    )

if __name__ == "__main__":
    main()
