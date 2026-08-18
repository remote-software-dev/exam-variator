"""File-based caching for the exam-variator pipeline.

Caches extraction results, AI responses, and computed data to avoid
redundant processing. Uses JSON files keyed by content hash.
"""

import json
import os
import time
import hashlib
from typing import Any, Optional

from .config import CACHE_CONFIG


def _cache_path(namespace: str, key: str) -> str:
    """Return the filesystem path for a cache entry."""
    cache_dir = os.path.join(CACHE_CONFIG.cache_dir, namespace)
    os.makedirs(cache_dir, exist_ok=True)
    safe_key = hashlib.sha256(key.encode()).hexdigest()[:32]
    return os.path.join(cache_dir, f"{safe_key}.json")


def get_cache(namespace: str, key: str, ttl_hours: Optional[float] = None) -> Optional[Any]:
    """Retrieve a cached value if it exists and hasn't expired.

    Args:
        namespace: Category prefix (e.g. 'pages', 'solutions', 'variations').
        key: The cache key (typically a content hash or path).
        ttl_hours: Time-to-live in hours. None uses the default for the namespace.

    Returns:
        The cached value, or None if missing/expired.
    """
    if not CACHE_CONFIG.enabled:
        return None

    path = _cache_path(namespace, key)
    if not os.path.exists(path):
        return None

    if ttl_hours is None:
        ttl_hours = _default_ttl(namespace)

    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
        created = entry.get("_cached_at", 0)
        age_hours = (time.time() - created) / 3600
        if age_hours > ttl_hours:
            return None
        return entry.get("data")
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def set_cache(namespace: str, key: str, data: Any) -> None:
    """Store a value in the cache.

    Args:
        namespace: Category prefix.
        key: The cache key.
        data: JSON-serializable data to cache.
    """
    if not CACHE_CONFIG.enabled:
        return

    path = _cache_path(namespace, key)
    entry = {
        "_cached_at": time.time(),
        "data": data,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # Cache writes are best-effort


def invalidate_cache(namespace: str, key: str) -> bool:
    """Remove a specific cache entry. Returns True if it existed."""
    path = _cache_path(namespace, key)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            pass
    return False


def clear_namespace(namespace: str) -> int:
    """Remove all cache entries in a namespace. Returns count removed."""
    cache_dir = os.path.join(CACHE_CONFIG.cache_dir, namespace)
    if not os.path.isdir(cache_dir):
        return 0
    count = 0
    for fname in os.listdir(cache_dir):
        if fname.endswith(".json"):
            try:
                os.remove(os.path.join(cache_dir, fname))
                count += 1
            except OSError:
                pass
    return count


def clear_all_caches() -> int:
    """Remove all cache entries. Returns count removed."""
    if not os.path.isdir(CACHE_CONFIG.cache_dir):
        return 0
    count = 0
    for ns in os.listdir(CACHE_CONFIG.cache_dir):
        count += clear_namespace(ns)
    return count


def cache_page_extraction(pdf_path: str, page_number: int, data: Any) -> None:
    """Cache extraction results for a specific PDF page."""
    key = f"{pdf_path}:page:{page_number}"
    set_cache("pages", key, data)


def get_cached_page_extraction(pdf_path: str, page_number: int) -> Optional[Any]:
    """Retrieve cached extraction results for a PDF page."""
    key = f"{pdf_path}:page:{page_number}"
    return get_cache("pages", key)


def cache_solution(question_hash: str, data: Any) -> None:
    """Cache AI-generated solution for a question."""
    set_cache("solutions", question_hash, data)


def get_cached_solution(question_hash: str) -> Optional[Any]:
    """Retrieve cached solution for a question."""
    return get_cache("solutions", question_hash)


def cache_variation(question_hash: str, custom_instruction: str, data: Any) -> None:
    """Cache AI-generated variations for a question."""
    key = f"{question_hash}:{hashlib.sha256(custom_instruction.encode()).hexdigest()[:8]}"
    set_cache("variations", key, data)


def get_cached_variation(question_hash: str, custom_instruction: str) -> Optional[Any]:
    """Retrieve cached variations for a question."""
    key = f"{question_hash}:{hashlib.sha256(custom_instruction.encode()).hexdigest()[:8]}"
    return get_cache("variations", key)


def cache_image_description(image_path: str, data: Any) -> None:
    """Cache AI-generated image description."""
    key = os.path.basename(image_path)
    set_cache("images", key, data)


def get_cached_image_description(image_path: str) -> Optional[Any]:
    """Retrieve cached image description."""
    key = os.path.basename(image_path)
    return get_cache("images", key)


def cache_ocr_result(pdf_path: str, page_number: int, data: Any) -> None:
    """Cache OCR results for a scanned page."""
    key = f"{pdf_path}:ocr:{page_number}"
    set_cache("ocr", key, data)


def get_cached_ocr_result(pdf_path: str, page_number: int) -> Optional[Any]:
    """Retrieve cached OCR results."""
    key = f"{pdf_path}:ocr:{page_number}"
    return get_cache("ocr", key)


def _default_ttl(namespace: str) -> float:
    """Return the default TTL in hours for a namespace."""
    ttl_map = {
        "pages": CACHE_CONFIG.page_cache_ttl_hours,
        "solutions": CACHE_CONFIG.solution_cache_ttl_hours,
        "variations": CACHE_CONFIG.variation_cache_ttl_hours,
        "images": 168,  # 7 days
        "ocr": CACHE_CONFIG.page_cache_ttl_hours,
    }
    return ttl_map.get(namespace, 24)
