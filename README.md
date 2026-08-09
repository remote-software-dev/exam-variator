# 🎓 Exam Variator (Generator Variasi Soal)

Automatically extracts math exam questions from PDF, generates easier and harder variations with AI, and exports the results to a Word document.

## Features

- **Extract all questions** — every PDF page is rendered to an image and processed by AI to extract *all* questions (not just one per page).
- **AI variations** — each question gets 2 variations: *easier* and *harder*, each with 5 answer options (A–E).
- **Batch processing (5-by-5)** — questions are processed in groups of 5. After each group a popup asks whether to continue with the next 5 questions or stop and keep the results so far.
- **Strict LaTeX matrix formatting** — the AI prompt enforces `\begin{bmatrix} ... \end{bmatrix}` (with a few-shot example) so matrices are never rendered as `|`, `||`, `∨`, or plain-text arrays.
- **Custom instructions** — add instructions like "provide solutions using the basic concept and a quick trick" to generate `solution_by_concept` and `solution_by_trick`.
- **Word export** — the DOCX is produced via pandoc (`--mathml`) so LaTeX becomes native Word equations; falls back to python-docx + latex2mathml when pandoc is unavailable.
- **Results preview** — preview the original questions and variations right in the UI (renders `$...$` LaTeX).

## Pipeline

```
PDF ──► PNG (per page) ──► Extract all questions (LLM vision)
       ──► 5-by-5 variations (LLM) ──► Export DOCX + JSON sidecar
```

## Installation

```bash
git clone git@github.com:remote-software-dev/exam-variator.git
cd exam-variator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API key (Streamlit Cloud secrets are also supported as a fallback):

```bash
GROQ_API_KEY=your-key-here
```

## Run the UI (Streamlit)

```bash
streamlit run app.py
```

1. Upload the exam PDF.
2. (Optional) add custom instructions.
3. Click **Buat Variasi** (Generate Variations).
4. After every 5 questions choose **Lanjutkan ➡️** (Continue) or **Selesai** (Finish).
5. Download the resulting Word document.

## Run via CLI

```bash
python -m src.exam_generator.pipeline
```

`run_pipeline()` can also be called directly and supports `batch_size` and a `continue_callback(processed, total) -> bool` to stop processing early.

## Project Structure

```
app.py                          # Streamlit UI (upload, 5-by-5 batching, preview)
src/exam_generator/
  pipeline.py                   # question extraction, variation generation, batch orchestration
  docx_exporter.py              # DOCX export (pandoc → python-docx fallback)
scripts/
  structure_questions.py        # utility to structure questions from PDF text
  render_pages.py               # render PDF pages to PNG
data/
  inputs/                       # input PDFs
  outputs/                      # DOCX, page PNGs, JSON sidecar
```

## AI Models (fallback chain)

- **Extraction:** `groq/qwen/qwen3.6-27b` → `groq/meta-llama/llama-4-scout-17b-16e-instruct` → `groq/meta-llama/llama-4-maverick-17b-128e-instruct`
- **Variation:** `groq/llama-3.3-70b-versatile` → `openai/gpt-4o-mini`

The model lists can be customized in `src/exam_generator/pipeline.py`.
