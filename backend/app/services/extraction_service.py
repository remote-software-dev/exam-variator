"""Extraction service - wraps engine extraction for background processing."""

import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from ..database import SessionLocal, JobRecord, JobPhase
from . import job_service


def run_extraction(job_id: str):
    """Background task: extract questions from the uploaded PDF."""
    db = SessionLocal()
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            return

        job_service.set_job_phase(db, job, JobPhase.EXTRACTING)

        from exam_generator.pipeline import (
            extract_all_questions_from_pdf, get_pdf_page_count, solve_questions
        )

        pdf_path = job.pdf_path
        custom_instruction = job.custom_instruction or ""

        # Get page count
        total_pages = get_pdf_page_count(pdf_path)
        job_service.update_job(db, job, total_pages=total_pages)

        def on_progress(current, total, stage, message=None):
            if stage == "extract":
                progress = current / max(total, 1) * 0.6
            elif stage == "solve":
                progress = 0.6 + (current / max(total, 1)) * 0.4
            else:
                progress = 0.0
            job_service.update_job(db, job, progress=min(progress, 0.99))

        def on_status(message):
            pass  # Could log or store status messages

        # Extract questions
        questions, skipped = extract_all_questions_from_pdf(
            pdf_path,
            custom_instruction=custom_instruction,
            progress_callback=on_progress,
            status_callback=on_status,
        )

        if not questions:
            job_service.set_job_phase(db, job, JobPhase.FAILED,
                                       error="No questions found in PDF")
            return

        job_service.set_job_phase(db, job, JobPhase.EXTRACTED)

        # Solve questions
        job_service.set_job_phase(db, job, JobPhase.SOLVING)
        solve_questions(
            questions,
            custom_instruction=custom_instruction,
            status_callback=on_status,
        )

        # Store questions as dicts
        questions_data = [q.to_dict() for q in questions]
        job_service.set_questions(db, job, questions_data)

        # Default: select all questions
        job_service.select_questions(db, job, list(range(len(questions_data))))

        job_service.set_job_phase(db, job, JobPhase.SOLVED)
        job_service.update_job(db, job, progress=1.0)

    except Exception as e:
        job = job_service.get_job(db, job_id)
        if job:
            job_service.set_job_phase(db, job, JobPhase.FAILED, error=str(e))
    finally:
        db.close()


def run_variations(job_id: str):
    """Background task: generate variations for selected questions."""
    db = SessionLocal()
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            return

        job_service.set_job_phase(db, job, JobPhase.VARYING)

        from exam_generator.pipeline import generate_variation_results

        questions = job.questions_json or []
        selected = job.selected_indices or []
        custom_instruction = job.custom_instruction or ""

        selected_questions = [questions[i] for i in selected if i < len(questions)]

        if not selected_questions:
            job_service.set_job_phase(db, job, JobPhase.FAILED,
                                       error="No questions selected")
            return

        def on_progress(current, total, stage, message=None):
            if stage == "vary":
                progress = current / max(total, 1)
                job_service.update_job(db, job, progress=min(progress, 0.99))

        results = generate_variation_results(
            selected_questions,
            custom_instruction=custom_instruction,
            progress_callback=on_progress,
        )

        job_service.set_variations(db, job, results)
        job_service.set_job_phase(db, job, JobPhase.COMPLETED)
        job_service.update_job(db, job, progress=1.0)

    except Exception as e:
        job = job_service.get_job(db, job_id)
        if job:
            job_service.set_job_phase(db, job, JobPhase.FAILED, error=str(e))
    finally:
        db.close()


def run_export(job_id: str):
    """Background task: export variations to DOCX."""
    db = SessionLocal()
    try:
        job = job_service.get_job(db, job_id)
        if not job:
            return

        from exam_generator.pipeline import export_results

        variations = job.variations_json or []
        output_path = str(Path(job.pdf_path).parent / "result.docx")

        export_results(variations, output_path)
        job_service.set_docx_path(db, job, output_path)

    except Exception as e:
        job = job_service.get_job(db, job_id)
        if job:
            job_service.set_job_phase(db, job, JobPhase.FAILED, error=str(e))
    finally:
        db.close()
