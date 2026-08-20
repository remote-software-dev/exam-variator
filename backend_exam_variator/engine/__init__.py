"""Exam Generator - Indonesian exam question variation generator.

Modules:
    config          - Central configuration
    models          - Question schema and dataclasses
    cache           - File-based caching
    pdf_ingestion   - PDF reading and digital page detection
    question_parser - Local regex-based question parsing
    ocr_extractor   - OCR adapter for scanned pages
    image_processor - Image crop, resize, compress
    ai_client       - LLM calls with retry, fallback, max_tokens
    validator       - Question validation layer
    solution_generator  - AI solution generation
    variation_generator - AI variation generation
    docx_exporter   - DOCX export (pandoc / python-docx)
    latex_utils     - LaTeX normalization
    pipeline        - Pipeline orchestrator
"""
