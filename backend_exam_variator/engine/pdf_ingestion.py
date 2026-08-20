"""PDF ingestion and digital page detection.

Reads the PDF, detects which pages are digital (have extractable text)
versus scanned (image-only), and extracts raw Markdown/text locally.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymupdf4llm
    _PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    pymupdf4llm = None
    _PYMUPDF4LLM_AVAILABLE = False

import fitz  # PyMuPDF

from .config import LOCAL_CONFIG
from .models import ExtractionMethod, PageInfo


def get_pdf_page_count(pdf_path: str) -> int:
    """Return the total number of pages in a PDF."""
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def detect_page_type(pdf_path: str, page_number: int) -> PageInfo:
    """Detect whether a page is digital or scanned.

    Returns a PageInfo with is_digital=True if the page has extractable text,
    is_digital=False if it's a scanned/image-only page.
    """
    with fitz.open(pdf_path) as doc:
        page = doc[page_number - 1]  # 0-based
        text = page.get_text().strip()
        text_length = len(text)

        has_markers = bool(_QUESTION_MARKER_RE.search(text))
        has_words = len(re.findall(r"[A-Za-z]{4,}", text)) >= LOCAL_CONFIG.min_words_for_usable

        # A page is "digital" if it has extractable text that looks like content
        if text_length < max(LOCAL_CONFIG.min_text_chars // 5, 10):
            is_digital = False
        elif has_markers:
            is_digital = True
        elif text_length < LOCAL_CONFIG.min_text_chars:
            is_digital = False
        else:
            is_digital = has_words

        return PageInfo(
            page_number=page_number,
            is_digital=is_digital,
            text_length=text_length,
            has_question_markers=has_markers,
        )


def detect_all_page_types(pdf_path: str, max_pages: Optional[int] = None) -> List[PageInfo]:
    """Detect page types for all pages in the PDF.

    Returns a list of PageInfo objects, one per page.
    """
    page_count = get_pdf_page_count(pdf_path)
    limit = min(max_pages, page_count) if max_pages else page_count

    results = []
    for i in range(limit):
        info = detect_page_type(pdf_path, i + 1)
        results.append(info)
    return results


def extract_page_markdown(pdf_path: str, page_number: int) -> str:
    """Extract clean Markdown text from a single page using pymupdf4llm.

    Returns empty string if extraction fails.
    """
    if _PYMUPDF4LLM_AVAILABLE:
        try:
            chunks = pymupdf4llm.to_markdown(
                pdf_path, page_chunks=True, pages=[page_number - 1]
            )
            if chunks:
                return chunks[0].get("text", "")
        except Exception:
            pass

    # Fallback: raw PyMuPDF text
    try:
        with fitz.open(pdf_path) as doc:
            return doc[page_number - 1].get_text()
    except Exception:
        return ""


def extract_all_pages_markdown(pdf_path: str, max_pages: Optional[int] = None) -> Dict[int, str]:
    """Extract Markdown text from all pages.

    Returns a dict mapping 0-based page index to text content.
    """
    if _PYMUPDF4LLM_AVAILABLE:
        try:
            pages_range = list(range(max_pages)) if max_pages else None
            chunks = pymupdf4llm.to_markdown(
                pdf_path, page_chunks=True, pages=pages_range
            )
            result = {}
            if pages_range:
                for idx, chunk in enumerate(chunks or []):
                    result[pages_range[idx]] = chunk.get("text", "")
            else:
                for idx, chunk in enumerate(chunks or []):
                    result[idx] = chunk.get("text", "")
            return result
        except Exception:
            pass

    # Fallback
    try:
        with fitz.open(pdf_path) as doc:
            count = min(max_pages, doc.page_count) if max_pages else doc.page_count
            return {i: doc[i].get_text() for i in range(count)}
    except Exception:
        return {}


def render_page_to_image(pdf_path: str, page_number: int, output_path: str,
                         dpi: int = 200) -> Optional[str]:
    """Render a PDF page to a PNG image at the specified DPI.

    Returns the output path if successful, None otherwise.
    """
    try:
        with fitz.open(pdf_path) as doc:
            page = doc[page_number - 1]
            pix = page.get_pixmap(dpi=dpi)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            pix.save(output_path)
            return output_path
    except Exception:
        return None


def extract_embedded_images(pdf_path: str, page_number: int,
                           output_dir: str) -> List[Dict[str, Any]]:
    """Extract embedded images from a PDF page.

    Returns a list of dicts with keys: path, width, height, ext, xref.
    """
    results = []
    try:
        with fitz.open(pdf_path) as doc:
            page = doc[page_number - 1]
            image_list = page.get_images(full=True)

            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                filename = f"page{page_number}_img{img_index + 1}.{image_ext}"
                filepath = os.path.join(output_dir, filename)
                os.makedirs(output_dir, exist_ok=True)

                with open(filepath, "wb") as f:
                    f.write(image_bytes)

                pix = fitz.Pixmap(doc, xref)
                results.append({
                    "path": filepath,
                    "width": pix.width,
                    "height": pix.height,
                    "ext": image_ext,
                    "xref": xref,
                    "page_number": page_number,
                    "index": img_index,
                })
    except Exception:
        pass

    return results


def get_page_bbox(pdf_path: str, page_number: int) -> Optional[Tuple[float, float, float, float]]:
    """Return the page bounding box (x0, y0, x1, y1) in points."""
    try:
        with fitz.open(pdf_path) as doc:
            page = doc[page_number - 1]
            rect = page.rect
            return (rect.x0, rect.y0, rect.x1, rect.y1)
    except Exception:
        return None


# Regex for detecting question markers in page text
_QUESTION_MARKER_RE = re.compile(
    r"(?m)(^\s*\d{1,3}\s*\.|\b[A-E]\s*[\.\)]|\bPernyataan\b|\(\s*\d\s*\))"
)
