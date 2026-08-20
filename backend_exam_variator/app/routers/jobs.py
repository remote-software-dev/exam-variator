"""Job endpoints - CRUD and lifecycle management."""

import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from ..database import get_job, list_jobs as _list_jobs, update_job, JobPhase
from ..schemas import (
    JobResponse, JobDetail, QuestionListResponse, QuestionSchema,
    QuestionUpdate, SelectQuestionsRequest, VariationTriggerRequest,
)
from ..services import job_service, extraction_service
from ..config import settings

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    custom_instruction: str = Form(""),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max: {settings.max_upload_size_mb}MB",
        )

    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        job = job_service.create_job(file.filename, tmp_path, custom_instruction)
    finally:
        os.unlink(tmp_path)

    background_tasks.add_task(extraction_service.run_extraction, job["id"])

    return _job_response(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(limit: int = 50, offset: int = 0):
    jobs = _list_jobs(limit=limit, offset=offset)
    return [_job_response(j) for j in jobs]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_detail(job)


@router.get("/{job_id}/questions", response_model=QuestionListResponse)
async def get_questions(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    questions = job_service.get_questions(job)
    return QuestionListResponse(
        questions=[QuestionSchema(**q) for q in questions],
        total=len(questions),
    )


@router.get("/{job_id}/questions/{qid}", response_model=QuestionSchema)
async def get_question(job_id: str, qid: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    questions = job_service.get_questions(job)
    for q in questions:
        if q.get("question_id") == qid:
            return QuestionSchema(**q)

    raise HTTPException(status_code=404, detail="Question not found")


@router.patch("/{job_id}/questions/{qid}", response_model=QuestionSchema)
async def update_question(job_id: str, qid: str, update: QuestionUpdate):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = update.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = job_service.update_question(job_id, qid, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Question not found")

    return QuestionSchema(**updated)


@router.post("/{job_id}/questions/{qid}/select")
async def select_question(job_id: str, qid: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    questions = job_service.get_questions(job)
    selected = job.get("selected_indices") or []

    for i, q in enumerate(questions):
        if q.get("question_id") == qid:
            if i not in selected:
                selected.append(i)
                job_service.select_questions(job_id, selected)
            return {"status": "selected", "index": i}

    raise HTTPException(status_code=404, detail="Question not found")


@router.post("/{job_id}/select", response_model=JobResponse)
async def bulk_select_questions(job_id: str, req: SelectQuestionsRequest):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_service.select_questions(job_id, req.selected_indices)
    return _job_response(get_job(job_id))


@router.post("/{job_id}/variations", status_code=202)
async def trigger_variations(
    job_id: str,
    background_tasks: BackgroundTasks,
    req: VariationTriggerRequest = VariationTriggerRequest(),
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    phase = job["phase"]
    if phase not in (JobPhase.SOLVED, JobPhase.COMPLETED, JobPhase.FAILED):
        raise HTTPException(status_code=409, detail=f"Job is in phase '{phase}', not ready for variations")

    if req.custom_instruction:
        update_job(job_id, custom_instruction=req.custom_instruction)

    background_tasks.add_task(extraction_service.run_variations, job_id)
    return {"status": "variations_queued", "job_id": job_id}


@router.get("/{job_id}/variations")
async def get_variations(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from ..schemas import VariationResultSchema, VariationSchema
    variations = job_service.get_variations(job)
    result = []
    for v in variations:
        try:
            orig = QuestionSchema(**v.get("original", {}))
            varis = v.get("variations", {})
            easy = QuestionSchema(**varis["easy"]) if varis.get("easy") else None
            medium = QuestionSchema(**varis["medium"]) if varis.get("medium") else None
            hard = QuestionSchema(**varis["hard"]) if varis.get("hard") else None
            result.append(VariationResultSchema(
                original=orig,
                variations=VariationSchema(easy=easy, medium=medium, hard=hard),
                page=v.get("page", 0),
            ))
        except Exception:
            continue

    return {"variations": [v.model_dump() for v in result], "total": len(result)}


@router.post("/{job_id}/export", status_code=202)
async def trigger_export(job_id: str, background_tasks: BackgroundTasks):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.get("variations_json"):
        raise HTTPException(status_code=409, detail="No variations generated yet")

    background_tasks.add_task(extraction_service.run_export, job_id)
    return {"status": "export_queued", "job_id": job_id}


@router.get("/{job_id}/export")
async def download_export(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    docx_path = job_service.get_docx_path(job)
    if not docx_path or not os.path.exists(docx_path):
        raise HTTPException(status_code=404, detail="DOCX not ready yet")

    return FileResponse(
        docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"Bank_Soal_{job['filename'].replace('.pdf', '')}.docx",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_response(job: dict) -> JobResponse:
    questions = job.get("questions_json") or []
    variations = job.get("variations_json") or []
    return JobResponse(
        id=job["id"],
        filename=job["filename"],
        phase=job["phase"],
        progress=job["progress"],
        total_pages=job.get("total_pages"),
        question_count=len(questions),
        variation_count=len(variations),
        error_message=job.get("error_message"),
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


def _job_detail(job: dict) -> JobDetail:
    base = _job_response(job)
    return JobDetail(
        **base.model_dump(),
        custom_instruction=job.get("custom_instruction") or "",
        docx_path=job.get("docx_path"),
    )
