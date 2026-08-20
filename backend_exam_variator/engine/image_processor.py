"""Image processing for the exam-variator pipeline.

Handles image extraction from PDFs, cropping per question, resizing,
compression, and classification before sending to AI.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from .config import IMAGE_CONFIG
from .models import ExtractedImage, ImageType


def compress_image(input_path: str, output_path: str,
                   max_dimension: int = None,
                   quality: int = None,
                   output_format: str = None) -> Optional[str]:
    """Compress and resize an image for AI API submission.

    Args:
        input_path: Path to the source image.
        output_path: Where to save the compressed image.
        max_dimension: Maximum width or height in pixels.
        quality: JPEG/WebP quality (1-100).
        output_format: Output format (JPEG, WEBP, PNG).

    Returns:
        The output path if successful, None otherwise.
    """
    max_dim = max_dimension or IMAGE_CONFIG.max_dimension
    qual = quality or IMAGE_CONFIG.jpeg_quality
    fmt = output_format or IMAGE_CONFIG.output_format

    try:
        img = Image.open(input_path)

        # Convert to RGB if necessary (RGBA, P, etc.)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Resize if exceeds max dimension
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        img.save(output_path, format=fmt, quality=qual, optimize=True)
        return output_path
    except Exception:
        return None


def get_image_info(image_path: str) -> Optional[Dict[str, Any]]:
    """Get basic info about an image file."""
    try:
        with Image.open(image_path) as img:
            return {
                "width": img.size[0],
                "height": img.size[1],
                "mode": img.mode,
                "format": img.format,
                "size_bytes": os.path.getsize(image_path),
            }
    except Exception:
        return None


def crop_region(image_path: str, bbox: Tuple[float, float, float, float],
                output_path: str, padding: int = 10) -> Optional[str]:
    """Crop a specific region from an image.

    Args:
        image_path: Source image path.
        bbox: (x0, y0, x1, y1) bounding box in pixels.
        output_path: Where to save the cropped image.
        padding: Extra pixels around the crop region.

    Returns:
        Output path if successful, None otherwise.
    """
    try:
        img = Image.open(image_path)
        x0, y0, x1, y1 = bbox

        # Apply padding, clamped to image bounds
        w, h = img.size
        x0 = max(0, int(x0) - padding)
        y0 = max(0, int(y0) - padding)
        x1 = min(w, int(x1) + padding)
        y1 = min(h, int(y1) + padding)

        cropped = img.crop((x0, y0, x1, y1))
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        cropped.save(output_path, optimize=True)
        return output_path
    except Exception:
        return None


def classify_image_type(description: str) -> ImageType:
    """Classify an image's type based on its AI-generated description.

    This is a heuristic classifier used when AI describes the image content.
    """
    desc_lower = description.lower()

    if any(kw in desc_lower for kw in ["grafik", "graph", "chart", "plot", "kurv", "diagram batang", "diagram garis"]):
        return ImageType.GRAPH
    if any(kw in desc_lower for kw in ["tabel", "table", "baris", "kolom", "data"]):
        return ImageType.TABLE
    if any(kw in desc_lower for kw in ["diagram", "skema", "rancang", "alur", "flowchart", "peta konsep"]):
        return ImageType.DIAGRAM
    if any(kw in desc_lower for kw in ["jam", "thermometer", "drometer", "multimeter", "alat ukur", "instrument", "clock", "speedometer"]):
        return ImageType.INSTRUMENT
    if any(kw in desc_lower for kw in ["segitiga", "lingkaran", "perseg", "geometri", "geometr", "sudut", "garis", "titik", "bangun", "kubus", "tabung", "kerucut", "prisma", "triangle", "figure", "polygon"]):
        return ImageType.GEOMETRY

    return ImageType.UNKNOWN


def prepare_image_for_ai(image_path: str, output_dir: str,
                        image_id: str = "") -> Optional[str]:
    """Prepare an image for AI submission: compress + resize.

    Returns the path to the processed image, or None on failure.
    """
    if not image_id:
        image_id = os.path.splitext(os.path.basename(image_path))[0]

    output_path = os.path.join(output_dir, f"{image_id}_ai_input.jpg")
    return compress_image(image_path, output_path)


def batch_prepare_images(image_paths: List[str], output_dir: str) -> Dict[str, str]:
    """Prepare multiple images for AI submission.

    Returns a dict mapping original path to processed path.
    """
    results = {}
    for path in image_paths:
        processed = prepare_image_for_ai(path, output_dir)
        if processed:
            results[path] = processed
    return results


def estimate_image_tokens(image_path: str) -> int:
    """Rough estimate of tokens for an image in an AI API call.

    Based on OpenAI's token calculation: ~85 tokens per 512x512 tile.
    """
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            # Number of 512x512 tiles
            tiles = ((w + 511) // 512) * ((h + 511) // 512)
            return tiles * 85
    except Exception:
        return 1000  # conservative default
