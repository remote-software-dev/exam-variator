"""Tests for the pipeline module and its sub-modules.

Tests cover: JSON extraction, image encoding, daily quota detection,
local question parsing, validation, caching, question models, and more.
All tests run offline -- no API keys required.
"""

import base64
import json
import os

import pytest

from exam_generator import pipeline
from exam_generator import ai_client
from exam_generator import models
from exam_generator import validator
from exam_generator import question_parser
from exam_generator import cache
from exam_generator.config import CACHE_CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_question(idx):
    return models.Question(
        question_id=f"Q{idx}",
        page_number=1,
        question_text=f"Berapa $2+{idx}$?",
        options=["A", "B", "C", "D", "E"],
    )


def _fake_variations(original_q, custom_instruction=None, status_callback=None):
    return {
        "easy": {"question_text": "e"},
        "medium": {"question_text": "m"},
        "hard": {"question_text": "h"},
    }


def _make_pdf(tmp_path, page_texts):
    import fitz

    path = tmp_path / "exam.pdf"
    doc = fitz.open()
    for i, text in enumerate(page_texts):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()
    return str(path)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_Choice(content)]


# ---------------------------------------------------------------------------
# Tests: ai_client (extract_json, encode_image, etc.)
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_plain_json(self):
        assert ai_client.extract_json('{"a": 1}') == {"a": 1}

    def test_nested_braces(self):
        assert ai_client.extract_json('{"a": {"b": 1}}') == {"a": {"b": 1}}

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"easier": {"x": 1}}\n```'
        assert ai_client.extract_json(raw) == {"easier": {"x": 1}}

    def test_json_with_trailing_text(self):
        assert ai_client.extract_json('{"a": 1}\n\nDone') == {"a": 1}

    def test_single_quotes_replaced(self):
        assert ai_client.extract_json("{'a': 1}") == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert ai_client.extract_json("{oops}") is None

    def test_no_braces_returns_none(self):
        assert ai_client.extract_json("just plain text") is None

    def test_empty_returns_none(self):
        assert ai_client.extract_json("") is None


class TestEncodeImage:
    def test_round_trip(self, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"12345")
        encoded = ai_client.encode_image(str(img))
        assert base64.b64decode(encoded) == img.read_bytes()


class TestIsDailyQuotaError:
    def test_daily_quota_detected(self):
        from litellm.exceptions import RateLimitError
        err = RateLimitError(
            "Quota exceeded ... quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            llm_provider="gemini", model="gemini-3.6-flash",
        )
        assert ai_client.is_daily_quota_error(err) is True

    def test_per_minute_rate_limit_not_detected(self):
        from litellm.exceptions import RateLimitError
        err = RateLimitError(
            "Rate limit reached for model: requests per minute exceeded",
            llm_provider="groq", model="m",
        )
        assert ai_client.is_daily_quota_error(err) is False


# ---------------------------------------------------------------------------
# Tests: completion_with_retry (via ai_client)
# ---------------------------------------------------------------------------

class TestCompletionWithRetry:
    def test_success_on_first_try(self, monkeypatch):
        captured = {}

        def fake_completion(**kwargs):
            captured["kwargs"] = kwargs
            return _FakeResponse('{"ok": true}')

        monkeypatch.setattr(ai_client.litellm, "completion", fake_completion)
        result = ai_client.completion_with_retry(
            model="groq/m", messages=[{"role": "user", "content": "hi"}], temperature=0.1
        )
        assert result.choices[0].message.content == '{"ok": true}'
        assert captured["kwargs"]["model"] == "groq/m"
        assert captured["kwargs"]["temperature"] == 0.1

    def test_max_tokens_passed(self, monkeypatch):
        captured = {}

        def fake_completion(**kwargs):
            captured["kwargs"] = kwargs
            return _FakeResponse('{"ok": true}')

        monkeypatch.setattr(ai_client.litellm, "completion", fake_completion)
        ai_client.completion_with_retry(
            model="groq/m", messages=[], max_tokens=4096
        )
        assert captured["kwargs"]["max_tokens"] == 4096

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        from litellm.exceptions import RateLimitError
        calls = {"n": 0}

        def fake_completion(**kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RateLimitError("rate limited", llm_provider="groq", model="m")
            return _FakeResponse("done")

        monkeypatch.setattr(ai_client.litellm, "completion", fake_completion)
        monkeypatch.setattr(ai_client.RETRY_CONFIG, "rate_limit_max_retries", 3)
        monkeypatch.setattr(ai_client.RETRY_CONFIG, "rate_limit_backoff_seconds", 0.0)
        monkeypatch.setattr(ai_client.time, "sleep", lambda _: None)

        result = ai_client.completion_with_retry(model="groq/m", messages=[])
        assert result.choices[0].message.content == "done"
        assert calls["n"] == 3

    def test_reraises_rate_limit_after_max_retries(self, monkeypatch):
        from litellm.exceptions import RateLimitError

        def fake_completion(**kwargs):
            raise RateLimitError("still limited", llm_provider="groq", model="m")

        monkeypatch.setattr(ai_client.litellm, "completion", fake_completion)
        monkeypatch.setattr(ai_client.RETRY_CONFIG, "rate_limit_max_retries", 2)
        monkeypatch.setattr(ai_client.RETRY_CONFIG, "rate_limit_backoff_seconds", 0.0)
        monkeypatch.setattr(ai_client.time, "sleep", lambda _: None)

        with pytest.raises(RateLimitError):
            ai_client.completion_with_retry(model="groq/m", messages=[])

    def test_other_errors_propagate_immediately(self, monkeypatch):
        def fake_completion(**kwargs):
            raise ValueError("bad")

        monkeypatch.setattr(ai_client.litellm, "completion", fake_completion)
        with pytest.raises(ValueError):
            ai_client.completion_with_retry(model="groq/m", messages=[])


# ---------------------------------------------------------------------------
# Tests: extraction system prompts
# ---------------------------------------------------------------------------

class TestExtractionSystemPrompt:
    def test_all_questions_mode(self):
        prompt = ai_client.build_extraction_system_prompt(source="text", all_questions=True)
        assert '"questions"' in prompt
        assert "Extract EVERY complete question" in prompt
        assert "\\begin{bmatrix}" in prompt

    def test_single_mode_and_custom_instruction(self):
        prompt = ai_client.build_extraction_system_prompt(
            source="image", all_questions=False, custom_instruction="Gunakan cara cepat"
        )
        assert '"question_text"' in prompt
        assert "Gunakan cara cepat" in prompt
        assert "Extract EVERY" not in prompt


# ---------------------------------------------------------------------------
# Tests: extract_all_questions_from_image (pipeline backward compat)
# ---------------------------------------------------------------------------

class TestExtractAllQuestionsFromImage:
    def test_filters_invalid_entries(self, monkeypatch, tmp_path):
        # Create a tiny fake image
        from PIL import Image
        img_path = tmp_path / "fake.png"
        Image.new("RGB", (10, 10), "red").save(str(img_path))

        # Patch on pipeline module since it imports from ai_client
        monkeypatch.setattr(pipeline, "encode_image", lambda _: "base64")

        def fake_call(models, messages, max_tokens=None, temperature=None,
                      min_keys=None, expect_array=False, status_callback=None):
            return {
                "questions": [
                    {"question_id": "Q1", "question_text": "Soal 1?"},
                    {"question_id": "Q2"},  # missing question_text -> dropped
                    "garbage",  # not a dict -> dropped
                    {"question_id": "Q3", "question_text": "Soal 3?"},
                ]
            }

        monkeypatch.setattr(pipeline, "call_with_fallback", fake_call)
        result = pipeline.extract_all_questions_from_image(str(img_path))
        assert [q.question_id for q in result] == ["Q1", "Q3"]

    def test_raises_when_no_valid_questions(self, monkeypatch, tmp_path):
        from PIL import Image
        img_path = tmp_path / "fake.png"
        Image.new("RGB", (10, 10), "red").save(str(img_path))

        monkeypatch.setattr(pipeline, "encode_image", lambda _: "base64")

        def fake_call(models, messages, max_tokens=None, temperature=None,
                      min_keys=None, expect_array=False, status_callback=None):
            return {"questions": [{"question_id": "X"}]}

        monkeypatch.setattr(pipeline, "call_with_fallback", fake_call)
        with pytest.raises(RuntimeError, match="no valid questions"):
            pipeline.extract_all_questions_from_image(str(img_path))


# ---------------------------------------------------------------------------
# Tests: page text assessment
# ---------------------------------------------------------------------------

class TestAssessPageText:
    def test_empty_text_unusable(self):
        assert pipeline._assess_page_text("") == (False, False)

    def test_too_short_unusable(self):
        assert pipeline._assess_page_text("1. A. B.") == (False, False)

    def test_long_text_with_markers(self):
        text = "1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n" * 5
        assert pipeline._assess_page_text(text) == (True, True)

    def test_long_text_without_markers_but_with_words(self):
        text = ("Diketahui sebuah fungsi kuadrat dengan akar-akar yang "
                "berbeda dan grafiknya terbuka ke atas, maka koefisien utama "
                "berbentuk bilangan positif, sehingga grafik memotong sumbu "
                "di dua titik yang berlainan.")
        usable, has_markers = pipeline._assess_page_text(text)
        assert usable is True
        assert has_markers is False

    def test_long_garbage_unusable(self):
        text = "####....::;;;!!...---+++===___&&&%%%$$$@@@***###   " * 5
        assert pipeline._assess_page_text(text) == (False, False)

    def test_none_is_unusable(self):
        assert pipeline._assess_page_text(None) == (False, False)


# ---------------------------------------------------------------------------
# Tests: extract_all_questions_from_text (pipeline backward compat)
# ---------------------------------------------------------------------------

class TestExtractAllQuestionsFromText:
    def test_returns_filtered_questions(self, monkeypatch):
        called = {"models": None}

        def fake_call(models, messages, max_tokens=None, temperature=None,
                      min_keys=None, expect_array=False, status_callback=None):
            called["models"] = models
            return {
                "questions": [
                    {"question_id": "Q1", "question_text": "Soal 1?"},
                    {"question_id": "Q2"},  # missing question_text -> dropped
                    {"question_id": "Q3", "question_text": "Soal 3?"},
                ]
            }

        monkeypatch.setattr(pipeline, "call_with_fallback", fake_call)
        result = pipeline.extract_all_questions_from_text("raw page text")
        assert [q.question_id for q in result] == ["Q1", "Q3"]
        assert called["models"] is pipeline.TEXT_EXTRACTION_MODELS

    def test_raises_when_no_valid_questions(self, monkeypatch):
        def fake_call(models, messages, max_tokens=None, temperature=None,
                      min_keys=None, expect_array=False, status_callback=None):
            return {"questions": [{"question_id": "X"}]}

        monkeypatch.setattr(pipeline, "call_with_fallback", fake_call)
        with pytest.raises(RuntimeError, match="no valid questions"):
            pipeline.extract_all_questions_from_text("raw page text")


# ---------------------------------------------------------------------------
# Tests: question_parser (local parsing)
# ---------------------------------------------------------------------------

class TestParseQuestionsFromText:
    def test_numbered_mcq(self):
        text = ("1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n"
                "2. Berapa 3+3?\nA. 5\nB. 6\nC. 7\nD. 8\nE. 9\n")
        qs = question_parser.parse_questions_from_text(text)
        assert [q.question_id for q in qs] == ["1", "2"]
        assert qs[0].question_text == "Berapa 2+2?"
        assert qs[0].options == ["3", "4", "5", "6", "7"]
        assert qs[1].options == ["5", "6", "7", "8", "9"]

    def test_qid_delimited(self):
        qid = "25ABCDEFGHIJKLMN-123456-0001"
        text = (f"{qid}\nDiketahui $f(x)=2x+3$. Nilai $f(2)$ adalah ...\n"
                "A. 3\nB. 5\nC. 7\nD. 9\nE. 11\n")
        qs = question_parser.parse_questions_from_text(text)
        assert len(qs) == 1
        assert qs[0].question_id == qid
        assert qs[0].options == ["3", "5", "7", "9", "11"]
        assert "f(x)=2x+3" in qs[0].question_text

    def test_option_continuation_lines(self):
        text = ("1. Soal dengan opsi panjang?\n"
                "A. Nilai x adalah 2, dan nilai\n"
                "   y adalah 3\n"
                "B. 4\nC. 5\nD. 6\nE. 7\n")
        qs = question_parser.parse_questions_from_text(text)
        assert len(qs) == 1
        assert qs[0].options[0] == "Nilai x adalah 2, dan nilai y adalah 3"
        assert qs[0].options[1] == "4"

    def test_fewer_than_two_options_rejected(self):
        text = "1. Soal ini cuma punya satu opsi?\nA. Saja\n"
        assert question_parser.parse_questions_from_text(text) == []

    def test_short_stem_rejected(self):
        text = "1. A.\nB. 2\nC. 3\n"
        assert question_parser.parse_questions_from_text(text) == []

    def test_no_delimiters_returns_empty(self):
        assert question_parser.parse_questions_from_text("Hanya teks biasa tanpa nomor.") == []

    def test_jumbled_inline_options_rejected(self):
        text = ("1. Suatu segitiga panjang sisinya adalah 12 cm dan 8 cm. semua "
                "besaran berikut dapat menjadi keliling segitiga tersebut, "
                "kecuali....\n"
                "A. 24 cm B. 28 cm C. 34 cm - D. 36 cm\n"
                "E. 38 cm\n")
        assert question_parser.parse_questions_from_text(text) == []

    def test_partial_parse_of_whole_page_rejected(self):
        lines = []
        for n in range(1, 11):
            lines.append(f"{n}. Soal nomor {n} yang di sini adalah sebuah pernyataan?\n")
            if n in (1, 6):
                lines.append("A. 1\nB. 2\nC. 3\nD. 4\nE. 5\n")
        text = "\n".join(lines)
        assert question_parser.parse_questions_from_text(text) == []

    def test_empty_text_returns_empty(self):
        assert question_parser.parse_questions_from_text("") == []
        assert question_parser.parse_questions_from_text(None) == []


class TestDetectQuestionType:
    def test_pilihan_ganda(self):
        assert question_parser.detect_question_type("1. Berapa 2+2?") == models.QuestionType.PILIHAN_GANDA

    def test_benar_salah(self):
        assert question_parser.detect_question_type("Pernyataan benar atau salah") == models.QuestionType.BENAR_SALAH

    def test_kategori(self):
        assert question_parser.detect_question_type("Kategori sesuai dengan") == models.QuestionType.KATEGORI

    def test_mcma(self):
        assert question_parser.detect_question_type("Pilihan ganda kompleks, centang semua yang benar") == models.QuestionType.PILIHAN_GANDA_KOMPLEKS


class TestExtractFormulas:
    def test_inline_math(self):
        text = "Gradien = $\\frac{12-0}{5-1}$"
        formulas = question_parser.extract_formulas(text)
        assert len(formulas) == 1
        assert "frac" in formulas[0]

    def test_display_math(self):
        text = "$$x^2 + y^2 = r^2$$"
        formulas = question_parser.extract_formulas(text)
        assert len(formulas) == 1

    def test_no_formulas(self):
        text = "Hanya teks biasa"
        assert question_parser.extract_formulas(text) == []


# ---------------------------------------------------------------------------
# Tests: models (Question, VariationResult)
# ---------------------------------------------------------------------------

class TestQuestionModel:
    def test_to_dict_roundtrip(self):
        q = models.Question(
            question_id="Q1",
            page_number=3,
            question_text="Berapa 2+2?",
            options=["3", "4", "5", "6", "7"],
            question_type=models.QuestionType.PILIHAN_GANDA,
        )
        d = q.to_dict()
        q2 = models.Question.from_dict(d)
        assert q2.question_id == "Q1"
        assert q2.page_number == 3
        assert q2.options == ["3", "4", "5", "6", "7"]

    def test_content_hash(self):
        q1 = models.Question(question_text="Soal 1", options=["A", "B"])
        q2 = models.Question(question_text="Soal 1", options=["A", "B"])
        q3 = models.Question(question_text="Soal 2", options=["A", "B"])
        assert q1.content_hash == q2.content_hash
        assert q1.content_hash != q3.content_hash

    def test_is_multiple_choice(self):
        q = models.Question(question_type=models.QuestionType.PILIHAN_GANDA)
        assert q.is_multiple_choice() is True
        q2 = models.Question(question_type=models.QuestionType.BENAR_SALAH)
        assert q2.is_multiple_choice() is False

    def test_option_count(self):
        q = models.Question(options=["A", "B", "C", "D", "E"])
        assert q.option_count() == 5


class TestVariationResult:
    def test_to_dict_roundtrip(self):
        orig = models.Question(question_id="Q1", question_text="Soal?", options=["A", "B", "C", "D", "E"])
        easy = models.Question(question_text="Mudah?", options=["1", "2", "3", "4", "5"])
        vr = models.VariationResult(original=orig, easy=easy, page=1)
        d = vr.to_dict()
        vr2 = models.VariationResult.from_dict(d)
        assert vr2.original.question_id == "Q1"
        assert vr2.easy.question_text == "Mudah?"
        assert vr2.hard is None


# ---------------------------------------------------------------------------
# Tests: validator
# ---------------------------------------------------------------------------

class TestValidator:
    def test_valid_mcq(self):
        q = models.Question(
            question_id="Q1",
            question_text="Berapa 2+2?",
            options=["3", "4", "5", "6", "7"],
            question_type=models.QuestionType.PILIHAN_GANDA,
            correct_answer="B",
            confidence=0.9,
        )
        status, warnings = validator.validate_question(q)
        assert status == models.ValidationStatus.VALID
        assert warnings == []

    def test_missing_text(self):
        q = models.Question(question_id="Q1", question_text="")
        status, warnings = validator.validate_question(q)
        assert status == models.ValidationStatus.INVALID
        assert any("Missing question_text" in w for w in warnings)

    def test_too_few_options(self):
        q = models.Question(
            question_id="Q1",
            question_text="Soal?",
            options=["A"],
            question_type=models.QuestionType.PILIHAN_GANDA,
        )
        status, warnings = validator.validate_question(q)
        assert any("Too few options" in w for w in warnings)

    def test_invalid_answer_key(self):
        q = models.Question(
            question_id="Q1",
            question_text="Soal?",
            options=["3", "4", "5", "6", "7"],
            question_type=models.QuestionType.PILIHAN_GANDA,
            correct_answer="F",  # Not in A-E
        )
        status, warnings = validator.validate_question(q)
        assert any("correct_answer" in w for w in warnings)

    def test_validate_batch(self):
        questions = [
            models.Question(question_id="Q1", question_text="Soal 1?", options=["A", "B", "C", "D", "E"]),
            models.Question(question_id="Q2", question_text=""),  # invalid
        ]
        valid, warned, invalid = validator.validate_batch(questions)
        assert valid + warned + invalid == 2


# ---------------------------------------------------------------------------
# Tests: cache
# ---------------------------------------------------------------------------

class TestCache:
    def test_set_and_get(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CACHE_CONFIG, "cache_dir", str(tmp_path / "cache"))
        monkeypatch.setattr(CACHE_CONFIG, "enabled", True)

        cache.set_cache("test", "key1", {"data": "hello"})
        result = cache.get_cache("test", "key1")
        assert result == {"data": "hello"}

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CACHE_CONFIG, "cache_dir", str(tmp_path / "cache"))
        monkeypatch.setattr(CACHE_CONFIG, "enabled", True)

        cache.set_cache("test", "key2", {"data": "hello"})
        result = cache.get_cache("test", "key2", ttl_hours=0)
        assert result is None

    def test_disabled_cache(self, monkeypatch):
        monkeypatch.setattr(CACHE_CONFIG, "enabled", False)
        cache.set_cache("test", "key3", {"data": "hello"})
        assert cache.get_cache("test", "key3") is None

    def test_invalidate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CACHE_CONFIG, "cache_dir", str(tmp_path / "cache"))
        monkeypatch.setattr(CACHE_CONFIG, "enabled", True)

        cache.set_cache("test", "key4", {"data": "hello"})
        assert cache.invalidate_cache("test", "key4") is True
        assert cache.get_cache("test", "key4") is None

    def test_clear_namespace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CACHE_CONFIG, "cache_dir", str(tmp_path / "cache"))
        monkeypatch.setattr(CACHE_CONFIG, "enabled", True)

        cache.set_cache("ns1", "a", 1)
        cache.set_cache("ns1", "b", 2)
        cache.set_cache("ns2", "c", 3)
        count = cache.clear_namespace("ns1")
        assert count == 2
        assert cache.get_cache("ns1", "a") is None
        assert cache.get_cache("ns2", "c") == 3  # untouched


# ---------------------------------------------------------------------------
# Tests: image_processor
# ---------------------------------------------------------------------------

class TestImageProcessor:
    def test_compress_image(self, tmp_path):
        from exam_generator.image_processor import compress_image
        from PIL import Image

        # Create a test image
        img = Image.new("RGB", (2000, 1500), color="red")
        src = tmp_path / "large.png"
        img.save(str(src))

        dst = tmp_path / "compressed.jpg"
        result = compress_image(str(src), str(dst), max_dimension=1024, quality=85)
        assert result is not None
        assert os.path.exists(result)

        compressed = Image.open(result)
        assert max(compressed.size) <= 1024

    def test_classify_image_type(self):
        from exam_generator.image_processor import classify_image_type
        from exam_generator.models import ImageType

        assert classify_image_type("A line graph showing temperature over time") == ImageType.GRAPH
        assert classify_image_type("A data table with columns and rows") == ImageType.TABLE
        assert classify_image_type("A geometry figure showing a triangle") == ImageType.GEOMETRY
        assert classify_image_type("A clock showing 3:45") == ImageType.INSTRUMENT
        assert classify_image_type("Something random") == ImageType.UNKNOWN


# ---------------------------------------------------------------------------
# Tests: backward compatibility from pipeline
# ---------------------------------------------------------------------------

class TestTextExtractionModels:
    def test_cheap_model_heads_the_text_chain(self):
        assert pipeline.TEXT_EXTRACTION_MODELS[0] == "groq/llama-3.1-8b-instant"


class TestExtractPdfMarkdown:
    def test_converts_text_pdf_to_per_page_markdown(self, tmp_path):
        pdf = _make_pdf(tmp_path, ["Soal 1\nA. 1\nB. 2\nC. 3\nD. 4\nE. 5\n",
                                   "Soal 2\nA. 6\nB. 7\nC. 8\nD. 9\nE. 10\n"])
        pages = pipeline._extract_pdf_markdown(pdf)
        assert isinstance(pages, dict)
        assert set(pages) == {0, 1}
        assert "Soal 1" in pages[0]
        assert "Soal 2" in pages[1]

    def test_blank_page_yields_empty_text(self, tmp_path):
        pdf = _make_pdf(tmp_path, ["Some real text here on this page.\n" * 5, ""])
        pages = pipeline._extract_pdf_markdown(pdf)
        assert pages[1].strip() == ""


class TestGetPdfPageCount:
    def test_returns_page_count(self, tmp_path):
        pdf = _make_pdf(tmp_path, ["a\n" * 20] * 3)
        assert pipeline.get_pdf_page_count(pdf) == 3


class TestExtractPageQuestions:
    def test_extracts_only_requested_page_text_path(self, monkeypatch, tmp_path):
        pdf = _make_pdf(tmp_path, ["1. Soal 1?\nA. 1\nB. 2\nC. 3\nD. 4\nE. 5\n",
                                   "2. Soal 2?\nA. 1\nB. 2\nC. 3\nD. 4\nE. 5\n"])
        calls = {"text": 0, "image": 0}

        def fake_page_text(page_text, custom_instruction=None, status_callback=None):
            calls["text"] += 1
            return [models.Question(question_id="Q2", question_text="dari halaman 2",
                                   options=["A", "B", "C", "D", "E"])]

        def fail_image(*a, **k):
            calls["image"] += 1
            raise AssertionError("vision must not be used on a text page")

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fake_page_text)
        monkeypatch.setattr(pipeline, "extract_all_questions_from_image", fail_image)

        qs = pipeline.extract_page_questions(pdf, page_index=2)
        assert calls["text"] == 1
        assert calls["image"] == 0
        assert qs[0].page_number == 2


class TestBatching:
    def test_generate_variation_batch_slices(self, monkeypatch):
        from exam_generator import variation_generator

        def fake_generate_variations(q, custom_instruction=None, status_callback=None):
            return {
                "easy": {"question_text": "e", "options": ["1","2","3","4","5"]},
                "medium": {"question_text": "m", "options": ["1","2","3","4","5"]},
                "hard": {"question_text": "h", "options": ["1","2","3","4","5"]},
            }

        monkeypatch.setattr(variation_generator, "generate_variations",
                          fake_generate_variations)

        questions = [_sample_question(i) for i in range(5)]
        results = pipeline.generate_variation_batch(questions, start=2, batch_size=2)
        assert len(results) == 2
        assert results[0]["original"]["question_id"] == "Q2"
        assert results[0]["variations"]["easy"]["question_text"] == "e"

    def test_generate_variation_results_processes_all(self, monkeypatch):
        from exam_generator import variation_generator

        def fake_generate_variations(q, custom_instruction=None, status_callback=None):
            return {
                "easy": {"question_text": "e", "options": ["1","2","3","4","5"]},
                "medium": {"question_text": "m", "options": ["1","2","3","4","5"]},
                "hard": {"question_text": "h", "options": ["1","2","3","4","5"]},
            }

        monkeypatch.setattr(variation_generator, "generate_variations",
                          fake_generate_variations)

        questions = [_sample_question(i) for i in range(3)]
        results = pipeline.generate_variation_results(questions)
        assert [r["original"]["question_id"] for r in results] == ["Q0", "Q1", "Q2"]

    def test_empty_slice_returns_empty(self, monkeypatch):
        from exam_generator import variation_generator

        def fake_generate_variations(q, custom_instruction=None, status_callback=None):
            return {
                "easy": {"question_text": "e"},
                "medium": {"question_text": "m"},
                "hard": {"question_text": "h"},
            }

        monkeypatch.setattr(variation_generator, "generate_variations",
                          fake_generate_variations)
        assert pipeline.generate_variation_batch([], start=0, batch_size=2) == []
        assert pipeline.generate_variation_results([]) == []
