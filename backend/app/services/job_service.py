"""Job service - wraps engine logic for job lifecycle management."""

import os
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Add engine to path
ENGINE_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from sqlalchemy.orm import Session

from ..database import JobRecord, JobPhase
from ..config import JOBS_DIR


def create_job(db: Session, filename: str, pdf_path: str, custom_instruction: str = "") -> JobRecord:
    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Copy PDF to job directory
    dest_pdf = job_dir / filename
    import shutil
    shutil.copy2(pdf_path, str(dest_pdf))

    job = JobRecord(
        id=job_id,
        filename=filename,
        pdf_path=str(dest_pdf),
        phase=JobPhase.UPLOADED,
        progress=0.0,
        custom_instruction=custom_instruction,
        questions_json=[],
        selected_indices=[],
        variations_json=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> JobRecord | None:
    return db.query(JobRecord).filter(JobRecord.id == job_id).first()


def list_jobs(db: Session, limit: int = 50, offset: int = 0) -> list[JobRecord]:
    return db.query(JobRecord).order_by(JobRecord.created_at.desc()).offset(offset).limit(limit).all()


def update_job(db: Session, job: JobRecord, **kwargs) -> JobRecord:
    for key, value in kwargs.items():
        setattr(job, key, value)
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def set_job_phase(db: Session, job: JobRecord, phase: JobPhase, error: str = None) -> JobRecord:
    job.phase = phase
    if error:
        job.error_message = error
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def get_questions(job: JobRecord) -> list[dict]:
    return job.questions_json or []


def set_questions(db: Session, job: JobRecord, questions: list[dict]) -> JobRecord:
    job.questions_json = questions
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def update_question(db: Session, job: JobRecord, qid: str, updates: dict) -> dict | None:
    questions = job.questions_json or []
    for i, q in enumerate(questions):
        if q.get("question_id") == qid:
            questions[i] = {**q, **updates}
            job.questions_json = questions
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(job)
            return questions[i]
    return None


def select_questions(db: Session, job: JobRecord, indices: list[int]) -> JobRecord:
    job.selected_indices = indices
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def get_variations(job: JobRecord) -> list[dict]:
    return job.variations_json or []


def set_variations(db: Session, job: JobRecord, variations: list[dict]) -> JobRecord:
    job.variations_json = variations
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def get_docx_path(job: JobRecord) -> str | None:
    return job.docx_path


def set_docx_path(db: Session, job: JobRecord, docx_path: str) -> JobRecord:
    job.docx_path = docx_path
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job
