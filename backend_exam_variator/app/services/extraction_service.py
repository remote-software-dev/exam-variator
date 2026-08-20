"""Extraction service - wraps engine extraction for background processing."""

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from ..database import get_job, update_job, set_phase, JobPhase
from . import job_service


def run_extraction(job_id: str):
    """Background task: extract questions from the uploaded PDF."""
    try:
        job = get_job(job_id)
        if not job:
            return

        set_phase(job_id, JobPhase.EXTRACTING)

        from engine.pipeline import (
            extract_all_questions_from_pdf, get_pdf_page_count, solve_questions
        )

        pdf_path = job["pdf_path"]
        custom_instruction = job.get("custom_instruction") or ""

        total_pages = get_pdf_page_count(pdf_path)
        update_job(job_id, total_pages=total_pages)

        def on_progress(current, total, stage, message=None):
            if stage == "extract":
                progress = current / max(total, 1) * 0.6
            elif stage == "solve":
                progress = 0.6 + (current / max(total, 1)) * 0.4
            else:
                progress = 0.0
            update_job(job_id, progress=min(progress, 0.99))

        def on_status(message):
            pass

        questions, skipped = extract_all_questions_from_pdf(
            pdf_path,
            custom_instruction=custom_instruction,
            progress_callback=on_progress,
            status_callback=on_status,
        )

        if not questions:
            set_phase(job_id, JobPhase.FAILED, error="No questions found in PDF")
            return

        set_phase(job_id, JobPhase.EXTRACTED)

        set_phase(job_id, JobPhase.SOLVING)
        solve_questions(
            questions,
            custom_instruction=custom_instruction,
            status_callback=on_status,
        )

        questions_data = [q.to_dict() for q in questions]
        job_service.set_questions(job_id, questions_data)
        job_service.select_questions(job_id, list(range(len(questions_data))))

        set_phase(job_id, JobPhase.SOLVED)
        update_job(job_id, progress=1.0)

    except Exception as e:
        job = get_job(job_id)
        if job:
            set_phase(job_id, JobPhase.FAILED, error=str(e))


def run_variations(job_id: str):
    """Background task: generate variations for selected questions."""
    try:
        job = get_job(job_id)
        if not job:
            return

        set_phase(job_id, JobPhase.VARYING)

        from engine.pipeline import generate_variation_results

        questions = job.get("questions_json") or []
        selected = job.get("selected_indices") or []
        custom_instruction = job.get("custom_instruction") or ""

        selected_questions = [questions[i] for i in selected if i < len(questions)]

        if not selected_questions:
            set_phase(job_id, JobPhase.FAILED, error="No questions selected")
            return

        def on_progress(current, total, stage, message=None):
            if stage == "vary":
                progress = current / max(total, 1)
                update_job(job_id, progress=min(progress, 0.99))

        results = generate_variation_results(
            selected_questions,
            custom_instruction=custom_instruction,
            progress_callback=on_progress,
        )

        job_service.set_variations(job_id, results)
        set_phase(job_id, JobPhase.COMPLETED)
        update_job(job_id, progress=1.0)

    except Exception as e:
        job = get_job(job_id)
        if job:
            set_phase(job_id, JobPhase.FAILED, error=str(e))


def run_export(job_id: str):
    """Background task: export variations to DOCX."""
    try:
        job = get_job(job_id)
        if not job:
            return

        from engine.pipeline import export_results

        variations = job.get("variations_json") or []
        output_path = str(Path(job["pdf_path"]).parent / "result.docx")

        export_results(variations, output_path)
        job_service.set_docx_path(job_id, output_path)

    except Exception as e:
        job = get_job(job_id)
        if job:
            set_phase(job_id, JobPhase.FAILED, error=str(e))
