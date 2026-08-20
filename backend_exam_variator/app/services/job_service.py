"""Job service - wraps engine logic for job lifecycle management."""

import os
import sys
import shutil
import uuid
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from ..database import create_job as _create, get_job, update_job, set_phase, JobPhase
from ..config import JOBS_DIR


def create_job(filename: str, pdf_path: str, custom_instruction: str = "") -> dict:
    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    dest_pdf = job_dir / filename
    shutil.copy2(pdf_path, str(dest_pdf))

    return _create(job_id, filename, str(dest_pdf), custom_instruction)


def get_questions(job: dict) -> list[dict]:
    return job.get("questions_json") or []


def set_questions(job_id: str, questions: list[dict]) -> dict:
    return update_job(job_id, questions_json=questions)


def update_question(job_id: str, qid: str, updates: dict) -> dict | None:
    job = get_job(job_id)
    if not job:
        return None
    questions = job.get("questions_json") or []
    for i, q in enumerate(questions):
        if q.get("question_id") == qid:
            questions[i] = {**q, **updates}
            update_job(job_id, questions_json=questions)
            return questions[i]
    return None


def select_questions(job_id: str, indices: list[int]) -> dict:
    return update_job(job_id, selected_indices=indices)


def get_variations(job: dict) -> list[dict]:
    return job.get("variations_json") or []


def set_variations(job_id: str, variations: list[dict]) -> dict:
    return update_job(job_id, variations_json=variations)


def get_docx_path(job: dict) -> str | None:
    return job.get("docx_path")


def set_docx_path(job_id: str, docx_path: str) -> dict:
    return update_job(job_id, docx_path=docx_path)
