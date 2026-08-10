# 🎓 Exam Variator (Generator Variasi Soal)

Automatically extracts math exam questions from PDF, generates easier and harder variations with AI, and exports the results to a Word document.

## Features

- **Extract all questions** — every page is processed **TEXT-first**: the text is pulled straight out of the PDF with PyMuPDF and extracted via the cheap text model chain (no image, no vision rate limits). Only pages whose text is missing or garbled (empty, or no question markers like `1.` / `A.` / `B.`) are rendered to PNG and sent to the vision model. Each page is retried with exponential backoff until it succeeds, so a transient failure never silently skips a page.
- **AI pembahasan (solutions)** — each question gets a step-by-step solution in two styles: `solution_by_concept` (basic concept) and `solution_by_trick` (quick trick), previewed in the UI so you can verify the AI solves each question correctly.
- **Two-phase selection flow** — phase 1 extracts + solves everything; phase 2 lets you review and check the questions you actually want to vary before generating variations.
- **AI variations** — each selected question gets 2 variations: *easier* and *harder*, each with 5 answer options (A–E).
- **Hybrid LLM fallback chain** — every LLM call tries models in order (Groq first, Gemini as the safety net) and rate limits are retried with exponential backoff before falling through to the next provider.
- **Strict LaTeX matrix formatting** — the AI prompt enforces `\begin{bmatrix} ... \end{bmatrix}` (with a few-shot example) so matrices are never rendered as `|`, `||`, `∨`, or plain-text arrays.
- **Custom instructions** — add instructions like "provide solutions using the basic concept and a quick trick" to steer the pembahasan and variation output.
- **Word export** — the DOCX is produced via pandoc (`--mathml`) so LaTeX becomes native Word equations; falls back to python-docx + latex2mathml when pandoc is unavailable.
- **Results preview** — preview the original questions, the AI solutions, and the variations right in the UI (renders `$...$` LaTeX).

## Pipeline

```
PDF ──► TEXT-first per page (PyMuPDF, cheap text model)
       ──► VISION fallback (render PNG) only if text missing/garbled
       ──► Pembahasan per soal (LLM)
       ──► User reviews & selects questions
       ──► Variations per selected question (LLM)
       ──► Export DOCX + JSON sidecar
```

## Installation

```bash
git clone git@github.com:remote-software-dev/exam-variator.git
cd exam-variator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API keys (Streamlit Cloud secrets are also supported as a fallback):

```bash
GROQ_API_KEY=your-key-here        # primary provider
GEMINI_API_KEY=your-key-here      # fallback (or GOOGLE_API_KEY)
```

## Run the UI (Streamlit)

```bash
streamlit run app.py
```

1. Upload the exam PDF.
2. (Optional) add custom instructions.
3. (Optional) set a **page limit** to process only the first few pages — useful for a quick test that avoids burning your free-tier quota on a large scanned exam.
4. Click **Ekstrak & Selesaikan Soal** — all questions are extracted and solved with an AI pembahasan.
5. Review the questions and their solutions, then check the ones you want to vary.
6. Click **Buat Variasi Terpilih** and download the resulting Word document.

## Run via CLI

```bash
python -m src.exam_generator.pipeline --max-pages 3 --output data/outputs/test_3pages.docx
```

`--max-pages N` processes only the first N pages (great for testing). `run_pipeline()` can also be called directly and supports `batch_size`, `max_pages`, and a `continue_callback(processed, total) -> bool` to stop processing early and export partial results.

## Run the tests

```bash
python -m pytest
```

The suite covers the pure logic (JSON extraction from model output, markdown/DOCX building, OMML conversion, batching) with no API keys or network needed.

## Project Structure

```
app.py                          # Streamlit UI (two-phase flow, live progress, preview)
pytest.ini                      # pytest config (src on path, tests dir)
src/exam_generator/
  pipeline.py                   # question extraction, pembahasan + variation generation, batching
  docx_exporter.py              # DOCX export (pandoc → python-docx fallback)
tests/                          # pytest suite (offline, no API keys needed)
scripts/
  structure_questions.py        # utility to structure questions from PDF text
  render_pages.py               # render PDF pages to PNG
data/
  inputs/                       # input PDFs
  outputs/                      # DOCX, page PNGs, JSON sidecar
```

## AI Models (fallback chain)

- **Extraction:** `groq/qwen/qwen3.6-27b` → `gemini/gemini-3.6-flash` → `gemini/gemini-3-flash-preview` → `gemini/gemini-3.1-flash-lite`
- **Text extraction / Variation / Solution:** `groq/llama-3.3-70b-versatile` → `groq/openai/gpt-oss-120b` → `gemini/gemini-3.6-flash` → `gemini/gemini-3-flash-preview` → `gemini/gemini-3.1-flash-lite`

Extraction requires a vision model (currently only `qwen3.6-27b` on Groq accepts image input). Gemini acts as the safety net — its large free tier means a Groq rate limit falls through to it instead of stalling the pipeline. Note the Gemini free tier caps usage at **20 requests/day per model**; the chain spans several Gemini models because each has its own separate daily budget. When a model's daily quota is exhausted the app fails fast (no backoff wait) and moves to the next model.

The model lists can be customized in `src/exam_generator/pipeline.py`.
