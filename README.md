# Exam Variator (Generator Variasi Soal)

Automatically extracts math exam questions from PDF, generates easy, medium and hard variations with AI, and exports the results to a Word document.

## Architecture

```
/frontend (Next.js, TypeScript, Tailwind)  ──► /backend (FastAPI, SQLite)
                                                  │
                                                  └──► /src/exam_generator (engine)
```

- **Frontend**: Next.js App Router, TypeScript, Tailwind CSS
- **Backend**: FastAPI, SQLAlchemy (SQLite), Pydantic schemas
- **Engine**: `src/exam_generator/` — UI-agnostic Python modules (100% unchanged)

## Quick Start

### 1. Engine (existing)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill API keys
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
# or from project root:
pip install -r backend/requirements.txt

# Run the API server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

### 4. Run Tests

```bash
# Engine tests (100 tests)
python -m pytest tests/ -v

# Backend API tests (16 tests)
cd backend && python -m pytest tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/jobs` | Upload PDF, start extraction |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/jobs/{id}` | Job status + phase + progress |
| GET | `/api/jobs/{id}/questions` | Questions with type/validation badges |
| GET | `/api/jobs/{id}/questions/{qid}` | Single question |
| PATCH | `/api/jobs/{id}/questions/{qid}` | Teacher edits question |
| POST | `/api/jobs/{id}/questions/{qid}/select` | Toggle question selection |
| POST | `/api/jobs/{id}/select` | Bulk select questions |
| POST | `/api/jobs/{id}/variations` | Trigger variation generation |
| GET | `/api/jobs/{id}/variations` | Get Easy/Medium/Hard variations |
| POST | `/api/jobs/{id}/export` | Build DOCX |
| GET | `/api/jobs/{id}/export` | Download DOCX |
| GET | `/health` | Health check |

## Project Structure

```
backend/
  app/
    main.py           # FastAPI app factory
    config.py         # Backend settings
    database.py       # SQLAlchemy models + engine
    schemas.py        # Pydantic request/response schemas
    routers/
      jobs.py         # All /api/jobs endpoints
      health.py       # Health check
    services/
      job_service.py          # Job CRUD + lifecycle
      extraction_service.py   # Background extraction + variation
  tests/
    test_api.py       # Backend tests (mocked LLM, no API keys)

frontend/
  app/
    page.tsx                    # Upload page (drag-and-drop)
    layout.tsx                  # Root layout with nav
    jobs/page.tsx               # Job dashboard (polls every 3s)
    jobs/[id]/page.tsx          # Question review (type badges, edit, select)
    jobs/[id]/variations/page.tsx  # Variation generation + display
    jobs/[id]/export/page.tsx   # DOCX export + download
  lib/
    api.ts           # API client (env-based base URL)
    types.ts         # TypeScript types

src/exam_generator/           # Engine (unchanged)
  config.py, models.py, cache.py, pdf_ingestion.py,
  question_parser.py, ocr_extractor.py, image_processor.py,
  ai_client.py, validator.py, solution_generator.py,
  variation_generator.py, pipeline.py, docx_exporter.py,
  latex_utils.py
```

## AI Models (fallback chain)

- **Extraction:** `groq/qwen/qwen3.6-27b` -> `gemini/gemini-3.6-flash` -> ...
- **Text extraction / Variation / Solution:** `groq/llama-3.3-70b-versatile` -> `groq/openai/gpt-oss-120b` -> ...

## Environment Variables

### Backend

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///data/jobs.db` | SQLAlchemy database URL |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max PDF upload size |

### Engine (same as before)

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key (primary) |
| `GEMINI_API_KEY` | Google Gemini API key (fallback) |
| `GOOGLE_API_KEY` | Alternative for Gemini |
