"""Central configuration for the exam-variator pipeline.

All tunable constants live here. No magic numbers in other modules.
Environment variables override defaults; never hardcode secrets.
"""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _ensure_api_key(env_name: str) -> None:
    """Load API key from Streamlit secrets if not already in env."""
    if env_name in os.environ:
        return
    try:
        import streamlit as st
        os.environ[env_name] = st.secrets[env_name]
    except Exception:
        pass


_ensure_api_key("GROQ_API_KEY")
_ensure_api_key("GEMINI_API_KEY")
_ensure_api_key("GOOGLE_API_KEY")


# ---------------------------------------------------------------------------
# Model chains (ordered by priority; first wins)
# ---------------------------------------------------------------------------

EXTRACTION_MODELS: List[str] = [
    "groq/qwen/qwen3.6-27b",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3.1-flash-lite",
]

TEXT_EXTRACTION_MODELS: List[str] = [
    "groq/llama-3.1-8b-instant",
    "groq/llama-3.3-70b-versatile",
    "groq/openai/gpt-oss-120b",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3.1-flash-lite",
]

VARIATION_MODELS: List[str] = [
    "groq/llama-3.3-70b-versatile",
    "groq/openai/gpt-oss-120b",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3.1-flash-lite",
]

SOLUTION_MODELS: List[str] = [
    "groq/llama-3.3-70b-versatile",
    "groq/openai/gpt-oss-120b",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3.1-flash-lite",
]

IMAGE_DESCRIPTION_MODELS: List[str] = [
    "groq/qwen/qwen3.6-27b",
    "gemini/gemini-3.6-flash",
    "gemini/gemini-3-flash-preview",
]

OCR_CLEANUP_MODELS: List[str] = [
    "groq/llama-3.1-8b-instant",
    "groq/llama-3.3-70b-versatile",
]


# ---------------------------------------------------------------------------
# Max tokens per task
# ---------------------------------------------------------------------------

@dataclass
class TokenLimits:
    extraction: int = 2048
    text_extraction: int = 2048
    solution: int = 3072
    variation: int = 4096
    image_description: int = 1024
    ocr_cleanup: int = 2048


TOKEN_LIMITS = TokenLimits()


# ---------------------------------------------------------------------------
# Temperature per task
# ---------------------------------------------------------------------------

@dataclass
class TemperatureConfig:
    extraction: float = 0.1
    solution: float = 0.3
    variation: float = 0.7
    image_description: float = 0.2
    ocr_cleanup: float = 0.1


TEMPERATURES = TemperatureConfig()


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

@dataclass
class ImageConfig:
    max_dimension: int = 1024
    jpeg_quality: int = 85
    render_dpi: int = 200
    output_format: str = "JPEG"


IMAGE_CONFIG = ImageConfig()


# ---------------------------------------------------------------------------
# Rate limiting & retry
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    rate_limit_max_retries: int = 3
    rate_limit_backoff_seconds: float = 15.0
    page_max_retries: int = 5
    page_backoff_seconds: float = 15.0
    extraction_delay_seconds: float = 10.0


RETRY_CONFIG = RetryConfig()


# ---------------------------------------------------------------------------
# Local extraction
# ---------------------------------------------------------------------------

@dataclass
class LocalExtractionConfig:
    min_text_chars: int = 50
    local_parsing_enabled: bool = True
    min_words_for_usable: int = 3
    min_word_length: int = 4


LOCAL_CONFIG = LocalExtractionConfig()


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

@dataclass
class OCRConfig:
    enabled: bool = True
    confidence_threshold: float = 0.6
    engine: str = "tesseract"  # "tesseract" | "paddleocr" | "easyocr"


OCR_CONFIG = OCRConfig()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class CacheConfig:
    enabled: bool = True
    cache_dir: str = "data/cache"
    page_cache_ttl_hours: int = 24
    solution_cache_ttl_hours: int = 72
    variation_cache_ttl_hours: int = 72


CACHE_CONFIG = CacheConfig()


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass
class OutputConfig:
    output_dir: str = "data/outputs"
    pages_dir: str = "data/outputs/pages"
    images_dir: str = "data/outputs/extracted_images"
    cache_dir: str = "data/cache"


OUTPUT_CONFIG = OutputConfig()


# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------

MAX_PDF_UPLOAD_SIZE_MB: int = 50
MAX_PDF_PAGES: int = 100


# ---------------------------------------------------------------------------
# Prompt formatting rules
# ---------------------------------------------------------------------------

MATRIX_FORMATTING_RULES = (
    "MATRICES: always use $\\begin{bmatrix} ... \\end{bmatrix}$ LaTeX "
    "(entries separated by &, rows by \\\\); NEVER '|', '||', '\\u2228', or plain text "
    "arrays. Example: [[2,0],[0,1/2]] -> $\\begin{bmatrix} 2 & 0 \\\\ "
    "0 & \\frac{1}{2} \\end{bmatrix}$"
)
