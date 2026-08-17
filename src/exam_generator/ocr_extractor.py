"""OCR extractor for scanned PDF pages.

Provides a local OCR adapter using Tesseract (via pytesseract).
Falls back gracefully if OCR libraries are not installed.
After OCR, runs a quality confidence check.
"""

import os
import re
from typing import Optional, Tuple

from .config import OCR_CONFIG


def _check_tesseract_available() -> bool:
    """Check if Tesseract and pytesseract are available."""
    try:
        import pytesseract
        # Also check if tesseract binary exists
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _check_paddleocr_available() -> bool:
    """Check if PaddleOCR is available."""
    try:
        from paddleocr import PaddleOCR
        return True
    except ImportError:
        return False


def _check_easyocr_available() -> bool:
    """Check if EasyOCR is available."""
    try:
        import easyocr
        return True
    except ImportError:
        return False


# Detect available OCR engine
_TESSERACT_AVAILABLE = _check_tesseract_available()
_PADDLEOCR_AVAILABLE = _check_paddleocr_available()
_EASYOCR_AVAILABLE = _check_easyocr_available()

# Lazy-loaded OCR reader instances
_paddleocr_reader = None
_easyocr_reader = None


def is_ocr_available() -> bool:
    """Check if any OCR engine is available."""
    return _TESSERACT_AVAILABLE or _PADDLEOCR_AVAILABLE or _EASYOCR_AVAILABLE


def get_available_engine() -> str:
    """Return the name of the best available OCR engine."""
    if OCR_CONFIG.engine == "paddleocr" and _PADDLEOCR_AVAILABLE:
        return "paddleocr"
    if OCR_CONFIG.engine == "easyocr" and _EASYOCR_AVAILABLE:
        return "easyocr"
    if _TESSERACT_AVAILABLE:
        return "tesseract"
    if _PADDLEOCR_AVAILABLE:
        return "paddleocr"
    if _EASYOCR_AVAILABLE:
        return "easyocr"
    return "none"


def ocr_image_tesseract(image_path: str) -> Tuple[str, float]:
    """Run Tesseract OCR on an image.

    Returns (extracted_text, confidence_score).
    """
    import pytesseract
    from PIL import Image

    try:
        img = Image.open(image_path)
        # Get text with confidence data
        data = pytesseract.image_to_data(img, lang="ind+eng",
                                         output_type=pytesseract.Output.DICT)

        texts = []
        confidences = []
        for i, conf in enumerate(data["conf"]):
            if int(conf) > 0:  # Skip negative confidence (non-text)
                text = data["text"][i].strip()
                if text:
                    texts.append(text)
                    confidences.append(int(conf))

        text = " ".join(texts)
        avg_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0

        return text, avg_confidence
    except Exception as e:
        print(f"  Tesseract OCR failed: {e}")
        return "", 0.0


def ocr_image_paddleocr(image_path: str) -> Tuple[str, float]:
    """Run PaddleOCR on an image.

    Returns (extracted_text, confidence_score).
    """
    global _paddleocr_reader
    try:
        from paddleocr import PaddleOCR

        if _paddleocr_reader is None:
            _paddleocr_reader = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)

        result = _paddleocr_reader.ocr(image_path, cls=True)

        texts = []
        confidences = []
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                    conf = line[1][1] if isinstance(line[1], (list, tuple)) and len(line[1]) > 1 else 0.0
                    texts.append(text)
                    confidences.append(float(conf))

        full_text = " ".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return full_text, avg_confidence
    except Exception as e:
        print(f"  PaddleOCR failed: {e}")
        return "", 0.0


def ocr_image_easyocr(image_path: str) -> Tuple[str, float]:
    """Run EasyOCR on an image.

    Returns (extracted_text, confidence_score).
    """
    global _easyocr_reader
    try:
        import easyocr

        if _easyocr_reader is None:
            _easyocr_reader = easyocr.Reader(["id", "en"])

        result = _easyocr_reader.readtext(image_path)

        texts = []
        confidences = []
        for (bbox, text, conf) in result:
            texts.append(text)
            confidences.append(conf)

        full_text = " ".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return full_text, avg_confidence
    except Exception as e:
        print(f"  EasyOCR failed: {e}")
        return "", 0.0


def ocr_image(image_path: str, engine: str = None) -> Tuple[str, float]:
    """Run OCR on an image using the best available engine.

    Args:
        image_path: Path to the image file.
        engine: Preferred engine name. If None, uses config default.

    Returns:
        Tuple of (extracted_text, confidence_score).
        Confidence is 0.0-1.0.
    """
    engine = engine or OCR_CONFIG.engine

    if engine == "tesseract" and _TESSERACT_AVAILABLE:
        return ocr_image_tesseract(image_path)
    elif engine == "paddleocr" and _PADDLEOCR_AVAILABLE:
        return ocr_image_paddleocr(image_path)
    elif engine == "easyocr" and _EASYOCR_AVAILABLE:
        return ocr_image_easyocr(image_path)

    # Fallback: try any available engine
    if _TESSERACT_AVAILABLE:
        return ocr_image_tesseract(image_path)
    elif _PADDLEOCR_AVAILABLE:
        return ocr_image_paddleocr(image_path)
    elif _EASYOCR_AVAILABLE:
        return ocr_image_easyocr(image_path)

    return "", 0.0


def assess_ocr_quality(text: str, confidence: float) -> Tuple[bool, str]:
    """Assess whether OCR output is usable.

    Returns (is_usable, reason).
    """
    if not text or not text.strip():
        return False, "OCR produced no text"

    if confidence < OCR_CONFIG.confidence_threshold:
        return False, f"OCR confidence {confidence:.2f} below threshold {OCR_CONFIG.confidence_threshold}"

    text = text.strip()

    # Check for basic structure
    has_numbers = bool(re.search(r"\d", text))
    has_words = len(re.findall(r"[A-Za-z]{3,}", text)) >= 2

    if not has_numbers and not has_words:
        return False, "OCR text appears to be garbage"

    # Check for excessive special characters (garbled output)
    special_ratio = len(re.findall(r"[^A-Za-z0-9\s\.\,\;\:\!\?]", text)) / max(len(text), 1)
    if special_ratio > 0.3:
        return False, f"OCR text has {special_ratio:.0%} special characters (likely garbled)"

    return True, "OCR quality acceptable"


def ocr_page(pdf_path: str, page_number: int, output_dir: str,
             engine: str = None) -> Tuple[str, float, bool]:
    """OCR a full PDF page.

    Renders the page to image, runs OCR, and returns the result.

    Args:
        pdf_path: Path to the PDF.
        page_number: 1-based page number.
        output_dir: Directory to save the rendered page image.
        engine: Preferred OCR engine.

    Returns:
        Tuple of (extracted_text, confidence, is_usable).
    """
    import fitz

    # Render page to image
    try:
        os.makedirs(output_dir, exist_ok=True)
        page_image = os.path.join(output_dir, f"ocr_page_{page_number:02d}.png")

        with fitz.open(pdf_path) as doc:
            page = doc[page_number - 1]
            pix = page.get_pixmap(dpi=200)
            pix.save(page_image)
    except Exception as e:
        print(f"  Failed to render page {page_number} for OCR: {e}")
        return "", 0.0, False

    # Run OCR
    text, confidence = ocr_image(page_image, engine=engine)

    # Assess quality
    is_usable, reason = assess_ocr_quality(text, confidence)
    if not is_usable:
        print(f"  OCR quality check failed for page {page_number}: {reason}")

    return text, confidence, is_usable
