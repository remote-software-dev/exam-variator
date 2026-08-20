"""Pydantic schemas for API request/response models."""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobPhase(str, Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SOLVING = "solving"
    SOLVED = "solved"
    VARYING = "varying"
    COMPLETED = "completed"
    FAILED = "failed"


class QuestionType(str, Enum):
    PILIHAN_GANDA = "Pilihan Ganda"
    PILIHAN_GANDA_KOMPLEKS = "Pilihan Ganda Kompleks"
    KATEGORI = "Kategori"
    BENAR_SALAH = "Benar/Salah"
    TEPAT_TIDAK_TEPAT = "Tepat/Tidak Tepat"
    ESSAY = "Essay"
    UNKNOWN = "Unknown"


class ValidationStatus(str, Enum):
    VALID = "valid"
    WARNINGS = "warnings"
    INVALID = "invalid"
    UNCHECKED = "unchecked"


# ---------------------------------------------------------------------------
# Question schema
# ---------------------------------------------------------------------------

class StatementEntry(BaseModel):
    statement_text: str = ""
    truth_values: Optional[dict[str, bool]] = None
    category: str = ""


class CategoryEntry(BaseModel):
    item: str = ""
    categories: dict[str, str] = {}


class ExtractedImage(BaseModel):
    image_id: str = ""
    image_path: str = ""
    width: int = 0
    height: int = 0
    page_number: int = 0


class QuestionSchema(BaseModel):
    question_id: str = ""
    page_number: int = 0
    source_pdf: str = ""
    extraction_index: int = 0
    subject: str = ""
    element: str = ""
    subelement: str = ""
    competency: str = ""
    indicator: str = ""
    bentuk_soal: str = ""
    question_type: QuestionType = QuestionType.UNKNOWN
    stimulus: str = ""
    question_text: str = ""
    options: list[str] = []
    option_labels: list[str] = []
    correct_answer: str = ""
    correct_answers: list[str] = []
    statement_entries: list[StatementEntry] = []
    category_entries: list[CategoryEntry] = []
    formulas: list[str] = []
    images: list[ExtractedImage] = []
    image_descriptions: dict[str, Any] = {}
    solution_by_concept: str = ""
    solution_by_trick: str = ""
    physics_scene: str = ""
    extraction_method: str = "unknown"
    confidence: float = 0.0
    needs_human_review: bool = False
    validation_status: ValidationStatus = ValidationStatus.UNCHECKED
    validation_warnings: list[str] = []
    is_verified_answer: bool = False

    class Config:
        json_schema_extra = {
            "example": {
                "question_id": "Q1",
                "question_text": "Berapa hasil dari 2+2?",
                "options": ["3", "4", "5", "6"],
                "question_type": "Pilihan Ganda",
            }
        }


# ---------------------------------------------------------------------------
# Variation schema
# ---------------------------------------------------------------------------

class VariationSchema(BaseModel):
    easy: Optional[QuestionSchema] = None
    medium: Optional[QuestionSchema] = None
    hard: Optional[QuestionSchema] = None


class VariationResultSchema(BaseModel):
    original: QuestionSchema
    variations: VariationSchema
    page: int = 0


# ---------------------------------------------------------------------------
# Job schemas
# ---------------------------------------------------------------------------

class JobCreate(BaseModel):
    custom_instruction: str = ""


class JobResponse(BaseModel):
    id: str
    filename: str
    phase: JobPhase
    progress: float
    total_pages: Optional[int] = None
    question_count: int = 0
    variation_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobDetail(JobResponse):
    custom_instruction: str = ""
    docx_path: Optional[str] = None


class QuestionListResponse(BaseModel):
    questions: list[QuestionSchema]
    total: int


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    options: Optional[list[str]] = None
    correct_answer: Optional[str] = None
    stimulus: Optional[str] = None


class SelectQuestionsRequest(BaseModel):
    selected_indices: list[int]


class VariationTriggerRequest(BaseModel):
    custom_instruction: str = ""


class VariationListResponse(BaseModel):
    variations: list[VariationResultSchema]
    total: int


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    detail: str
    code: str = "error"
