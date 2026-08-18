"""Structured question schema for the exam-variator pipeline.

Every question passes through the pipeline as a Question dataclass.
This ensures consistency across extraction, validation, and export.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class QuestionType(str, Enum):
    PILIHAN_GANDA = "Pilihan Ganda"
    PILIHAN_GANDA_KOMPLEKS = "Pilihan Ganda Kompleks"
    KATEGORI = "Kategori"
    BENAR_SALAH = "Benar/Salah"
    TEPAT_TIDAK_TEPAT = "Tepat/Tidak Tepat"
    ESSAY = "Essay"
    UNKNOWN = "Unknown"


class ExtractionMethod(str, Enum):
    UNKNOWN = "unknown"
    LOCAL_TEXT = "local_text"
    LOCAL_PARSE = "local_parse"
    TEXT_LLM = "text_llm"
    VISION_LLM = "vision_llm"
    LOCAL_OCR = "local_ocr"
    HYBRID = "hybrid"


class ValidationStatus(str, Enum):
    VALID = "valid"
    WARNINGS = "warnings"
    INVALID = "invalid"
    UNCHECKED = "unchecked"


class ImageType(str, Enum):
    GRAPH = "graph"
    TABLE = "table"
    DIAGRAM = "diagram"
    INSTRUMENT = "instrument"
    GEOMETRY = "geometry"
    UNKNOWN = "unknown"


@dataclass
class ExtractedImage:
    """An image extracted from the PDF, associated with a question."""
    image_id: str = ""
    image_path: str = ""
    image_type: ImageType = ImageType.UNKNOWN
    width: int = 0
    height: int = 0
    page_number: int = 0
    question_index: int = -1
    description: str = ""
    bbox: Optional[List[float]] = None  # [x0, y0, x1, y1] if cropped


@dataclass
class StatementEntry:
    """A single row in a Benar/Salah or Kategori statement table."""
    statement_text: str = ""
    truth_values: Optional[Dict[str, bool]] = None  # {"Pernyataan 1": True, ...}
    category: str = ""  # For Kategori questions


@dataclass
class CategoryEntry:
    """A single row in a Kategori matching table."""
    item: str = ""
    categories: Dict[str, str] = field(default_factory=dict)


@dataclass
class Question:
    """The canonical question object used throughout the pipeline."""

    # Identity
    question_id: str = ""
    page_number: int = 0
    source_pdf: str = ""
    extraction_index: int = 0  # order within page

    # Metadata (extracted from PDF if available)
    subject: str = ""
    element: str = ""
    subelement: str = ""
    competency: str = ""
    indicator: str = ""
    bentuk_soal: str = ""

    # Content
    question_type: QuestionType = QuestionType.UNKNOWN
    stimulus: str = ""
    question_text: str = ""
    options: List[str] = field(default_factory=list)
    option_labels: List[str] = field(default_factory=list)

    # Answer keys
    correct_answer: str = ""  # single answer (A-E or text)
    correct_answers: List[str] = field(default_factory=list)  # MCMA
    statement_entries: List[StatementEntry] = field(default_factory=list)
    category_entries: List[CategoryEntry] = field(default_factory=list)

    # Formulas extracted from question
    formulas: List[str] = field(default_factory=list)

    # Images
    images: List[ExtractedImage] = field(default_factory=list)
    image_descriptions: Dict[str, str] = field(default_factory=dict)

    # AI-generated content
    solution_by_concept: str = ""
    solution_by_trick: str = ""
    physics_scene: str = ""

    # Variations (generated later)
    variations: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Processing metadata
    extraction_method: ExtractionMethod = ExtractionMethod.UNKNOWN
    confidence: float = 0.0
    needs_human_review: bool = False
    validation_status: ValidationStatus = ValidationStatus.UNCHECKED
    validation_warnings: List[str] = field(default_factory=list)
    is_verified_answer: bool = False  # False = draft/unverified

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, handling enums and nested dataclasses."""
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Enum):
                d[k] = v.value
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # Handle lists of dataclasses (StatementEntry, etc.)
                pass  # asdict already handles these
        return d

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Question":
        """Deserialize from dict, handling enums and nested structures."""
        if not data:
            return cls()
        # Handle enum conversions
        for enum_field in ("question_type", "extraction_method", "validation_status"):
            val = data.get(enum_field)
            if isinstance(val, str):
                try:
                    enum_cls = {
                        "question_type": QuestionType,
                        "extraction_method": ExtractionMethod,
                        "validation_status": ValidationStatus,
                    }[enum_field]
                    data[enum_field] = enum_cls(val)
                except (ValueError, KeyError):
                    pass
        # Handle StatementEntry list
        stmts = data.get("statement_entries", [])
        if stmts and isinstance(stmts[0], dict):
            data["statement_entries"] = [StatementEntry(**s) for s in stmts]
        # Handle CategoryEntry list
        cats = data.get("category_entries", [])
        if cats and isinstance(cats[0], dict):
            data["category_entries"] = [CategoryEntry(**c) for c in cats]
        # Handle ExtractedImage list
        imgs = data.get("images", [])
        if imgs and isinstance(imgs[0], dict):
            data["images"] = [ExtractedImage(**i) for i in imgs]
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @property
    def content_hash(self) -> str:
        """Hash of question text + options for cache key generation."""
        content = json.dumps({
            "text": self.question_text,
            "options": self.options,
        }, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def is_multiple_choice(self) -> bool:
        return self.question_type in (
            QuestionType.PILIHAN_GANDA,
            QuestionType.PILIHAN_GANDA_KOMPLEKS,
        )

    def has_statement_table(self) -> bool:
        return self.question_type in (
            QuestionType.BENAR_SALAH,
            QuestionType.TEPAT_TIDAK_TEPAT,
            QuestionType.KATEGORI,
        ) and bool(self.statement_entries)

    def has_category_table(self) -> bool:
        return self.question_type == QuestionType.KATEGORI and bool(self.category_entries)

    def option_count(self) -> int:
        return len(self.options)


@dataclass
class VariationResult:
    """Result of generating Easy/Medium/Hard variations for one question."""
    original: Question = field(default_factory=Question)
    easy: Optional[Question] = None
    medium: Optional[Question] = None
    hard: Optional[Question] = None
    page: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "original": self.original.to_dict(),
            "variations": {
                "easy": self.easy.to_dict() if self.easy else None,
                "medium": self.medium.to_dict() if self.medium else None,
                "hard": self.hard.to_dict() if self.hard else None,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariationResult":
        if not data:
            return cls()
        orig = data.get("original", {})
        varis = data.get("variations", {})
        return cls(
            original=Question.from_dict(orig) if orig else Question(),
            easy=Question.from_dict(varis.get("easy")) if varis.get("easy") else None,
            medium=Question.from_dict(varis.get("medium")) if varis.get("medium") else None,
            hard=Question.from_dict(varis.get("hard")) if varis.get("hard") else None,
            page=data.get("page", 0),
        )


@dataclass
class PageInfo:
    """Metadata about a PDF page."""
    page_number: int = 0
    is_digital: bool = True
    text_length: int = 0
    has_question_markers: bool = False
    extraction_method: ExtractionMethod = ExtractionMethod.UNKNOWN
    question_count: int = 0
    skipped: bool = False
    skip_reason: str = ""
