"""In-memory job store — no database needed."""

import enum
from datetime import datetime, timezone
from typing import Optional


class JobPhase(str, enum.Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SOLVING = "solving"
    SOLVED = "solved"
    VARYING = "varying"
    COMPLETED = "completed"
    FAILED = "failed"


_jobs: dict[str, dict] = {}


def create_job(
    job_id: str,
    filename: str,
    pdf_path: str,
    custom_instruction: str = "",
) -> dict:
    now = datetime.now(timezone.utc)
    job = {
        "id": job_id,
        "filename": filename,
        "pdf_path": pdf_path,
        "docx_path": None,
        "phase": JobPhase.UPLOADED,
        "progress": 0.0,
        "total_pages": None,
        "error_message": None,
        "questions_json": [],
        "selected_indices": [],
        "variations_json": [],
        "custom_instruction": custom_instruction,
        "created_at": now,
        "updated_at": now,
    }
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def list_jobs(limit: int = 50, offset: int = 0) -> list[dict]:
    sorted_jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return sorted_jobs[offset : offset + limit]


def update_job(job_id: str, **kwargs) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None
    for key, value in kwargs.items():
        job[key] = value
    job["updated_at"] = datetime.now(timezone.utc)
    return job


def set_phase(job_id: str, phase: JobPhase, error: str = None) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None
    job["phase"] = phase
    if error:
        job["error_message"] = error
    job["updated_at"] = datetime.now(timezone.utc)
    return job


def delete_job(job_id: str) -> bool:
    return _jobs.pop(job_id, None) is not None
