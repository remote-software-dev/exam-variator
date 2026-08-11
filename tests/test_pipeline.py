import base64

import pytest

from exam_generator import pipeline


def _sample_question(idx):
    return {
        "id": f"Q{idx}",
        "page": 1,
        "question_text": f"Berapa $2+{idx}$?",
        "options": ["A", "B", "C", "D", "E"],
    }


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


class TestExtractJson:
    def test_plain_json(self):
        assert pipeline._extract_json('{"a": 1}') == {"a": 1}

    def test_nested_braces(self):
        assert pipeline._extract_json('{"a": {"b": 1}}') == {"a": {"b": 1}}

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"easier": {"x": 1}}\n```'
        assert pipeline._extract_json(raw) == {"easier": {"x": 1}}

    def test_json_with_trailing_text(self):
        assert pipeline._extract_json('{"a": 1}\n\nDone') == {"a": 1}

    def test_single_quotes_replaced(self):
        assert pipeline._extract_json("{'a': 1}") == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert pipeline._extract_json("{oops}") is None

    def test_no_braces_returns_none(self):
        assert pipeline._extract_json("just plain text") is None

    def test_empty_returns_none(self):
        assert pipeline._extract_json("") is None


class TestEncodeImage:
    def test_round_trip(self, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"12345")
        encoded = pipeline.encode_image(str(img))
        assert base64.b64decode(encoded) == img.read_bytes()


class TestIsDailyQuotaError:
    def test_daily_quota_detected(self):
        err = pipeline.RateLimitError(
            "Quota exceeded ... quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            llm_provider="gemini", model="gemini-3.6-flash",
        )
        assert pipeline._is_daily_quota_error(err) is True

    def test_per_minute_rate_limit_not_detected(self):
        err = pipeline.RateLimitError(
            "Rate limit reached for model: requests per minute exceeded",
            llm_provider="groq", model="m",
        )
        assert pipeline._is_daily_quota_error(err) is False


class TestCompletionDailyQuota:
    def test_daily_quota_fails_fast_without_backoff(self, monkeypatch):
        calls = {"n": 0}

        def fake_completion(**kwargs):
            calls["n"] += 1
            raise pipeline.RateLimitError(
                "Quota exceeded ... quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                llm_provider="gemini", model="gemini-3.6-flash",
            )

        monkeypatch.setattr(pipeline.litellm, "completion", fake_completion)
        monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
        with pytest.raises(pipeline.RateLimitError):
            pipeline._completion_with_retry(model="gemini/gemini-3.6-flash", messages=[])
        assert calls["n"] == 1  # no backoff retries on daily-exhaustion


class TestCompletionWithRetry:
    def test_success_on_first_try(self, monkeypatch):
        captured = {}

        def fake_completion(**kwargs):
            captured["kwargs"] = kwargs
            return _FakeResponse('{"ok": true}')

        monkeypatch.setattr(pipeline.litellm, "completion", fake_completion)
        result = pipeline._completion_with_retry(
            model="groq/m", messages=[{"role": "user", "content": "hi"}], temperature=0.1
        )
        assert result.choices[0].message.content == '{"ok": true}'
        assert captured["kwargs"]["model"] == "groq/m"
        assert captured["kwargs"]["temperature"] == 0.1

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        calls = {"n": 0}

        def fake_completion(**kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise pipeline.RateLimitError("rate limited", llm_provider="groq", model="m")
            return _FakeResponse("done")

        monkeypatch.setattr(pipeline.litellm, "completion", fake_completion)
        monkeypatch.setattr(pipeline, "RATE_LIMIT_MAX_RETRIES", 3)
        monkeypatch.setattr(pipeline, "RATE_LIMIT_BACKOFF_SECONDS", 0.0)
        monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)

        result = pipeline._completion_with_retry(model="groq/m", messages=[])
        assert result.choices[0].message.content == "done"
        assert calls["n"] == 3

    def test_reraises_rate_limit_after_max_retries(self, monkeypatch):
        def fake_completion(**kwargs):
            raise pipeline.RateLimitError("still limited", llm_provider="groq", model="m")

        monkeypatch.setattr(pipeline.litellm, "completion", fake_completion)
        monkeypatch.setattr(pipeline, "RATE_LIMIT_MAX_RETRIES", 2)
        monkeypatch.setattr(pipeline, "RATE_LIMIT_BACKOFF_SECONDS", 0.0)
        monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)

        with pytest.raises(pipeline.RateLimitError):
            pipeline._completion_with_retry(model="groq/m", messages=[])

    def test_other_errors_propagate_immediately(self, monkeypatch):
        def fake_completion(**kwargs):
            raise ValueError("bad")

        monkeypatch.setattr(pipeline.litellm, "completion", fake_completion)
        with pytest.raises(ValueError):
            pipeline._completion_with_retry(model="groq/m", messages=[])


class TestExtractionSystemPrompt:
    def test_all_questions_mode(self):
        prompt = pipeline._extraction_system_prompt(None, all_questions=True)
        assert '"questions"' in prompt
        assert "Extract EVERY complete question" in prompt
        assert "\\begin{bmatrix}" in prompt

    def test_single_mode_and_custom_instruction(self):
        prompt = pipeline._extraction_system_prompt("Gunakan cara cepat", all_questions=False)
        assert '"question_text"' in prompt
        assert "Gunakan cara cepat" in prompt
        assert "Extract EVERY" not in prompt


class TestExtractAllQuestionsFromImage:
    def test_filters_invalid_entries(self, monkeypatch):
        monkeypatch.setattr(pipeline, "encode_image", lambda _: "base64")
        monkeypatch.setattr(
            pipeline,
            "_extract_via_llm",
            lambda *a, **k: {
                "questions": [
                    {"id": "Q1", "question_text": "Soal 1?"},
                    {"id": "Q2"},  # missing question_text -> dropped
                    "garbage",  # not a dict -> dropped
                    {"id": "Q3", "question_text": "Soal 3?"},
                ]
            },
        )
        result = pipeline.extract_all_questions_from_image("fake.png")
        assert [q["id"] for q in result] == ["Q1", "Q3"]

    def test_raises_when_no_valid_questions(self, monkeypatch):
        monkeypatch.setattr(pipeline, "encode_image", lambda _: "base64")
        monkeypatch.setattr(
            pipeline,
            "_extract_via_llm",
            lambda *a, **k: {"questions": [{"id": "X"}]},
        )
        with pytest.raises(RuntimeError, match="no valid questions"):
            pipeline.extract_all_questions_from_image("fake.png")


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


class TestExtractAllQuestionsFromText:
    def test_returns_filtered_questions(self, monkeypatch):
        called = {"source": None, "models": None}

        def fake_via_llm(system_prompt, user_text, models, min_keys=None, status_callback=None):
            called["source"] = system_prompt
            called["models"] = models
            return {
                "questions": [
                    {"id": "Q1", "question_text": "Soal 1?"},
                    {"id": "Q2"},  # missing question_text -> dropped
                    {"id": "Q3", "question_text": "Soal 3?"},
                ]
            }

        monkeypatch.setattr(pipeline, "_extract_via_llm", fake_via_llm)
        result = pipeline.extract_all_questions_from_text("raw page text")
        assert [q["id"] for q in result] == ["Q1", "Q3"]
        assert "clean Markdown text of a PDF page" in called["source"]
        assert called["models"] is pipeline.TEXT_EXTRACTION_MODELS

    def test_raises_when_no_valid_questions(self, monkeypatch):
        monkeypatch.setattr(
            pipeline,
            "_extract_via_llm",
            lambda *a, **k: {"questions": [{"id": "X"}]},
        )
        with pytest.raises(RuntimeError, match="no valid questions"):
            pipeline.extract_all_questions_from_text("raw page text")


class TestParseQuestionsFromText:
    def test_numbered_mcq(self):
        text = ("1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n"
                "2. Berapa 3+3?\nA. 5\nB. 6\nC. 7\nD. 8\nE. 9\n")
        qs = pipeline.parse_questions_from_text(text)
        assert [q["id"] for q in qs] == ["1", "2"]
        assert qs[0]["question_text"] == "Berapa 2+2?"
        assert qs[0]["options"] == ["3", "4", "5", "6", "7"]
        assert qs[1]["options"] == ["5", "6", "7", "8", "9"]

    def test_qid_delimited(self):
        qid = "25ABCDEFGHIJKLMN-123456-0001"
        text = (f"{qid}\nDiketahui $f(x)=2x+3$. Nilai $f(2)$ adalah ...\n"
                "A. 3\nB. 5\nC. 7\nD. 9\nE. 11\n")
        qs = pipeline.parse_questions_from_text(text)
        assert len(qs) == 1
        assert qs[0]["id"] == qid
        assert qs[0]["options"] == ["3", "5", "7", "9", "11"]
        assert "f(x)=2x+3" in qs[0]["question_text"]

    def test_option_continuation_lines(self):
        text = ("1. Soal dengan opsi panjang?\n"
                "A. Nilai x adalah 2, dan nilai\n"
                "   y adalah 3\n"
                "B. 4\nC. 5\nD. 6\nE. 7\n")
        qs = pipeline.parse_questions_from_text(text)
        assert len(qs) == 1
        assert qs[0]["options"][0] == "Nilai x adalah 2, dan nilai y adalah 3"
        assert qs[0]["options"][1] == "4"

    def test_fewer_than_two_options_rejected(self):
        text = "1. Soal ini cuma punya satu opsi?\nA. Saja\n"
        assert pipeline.parse_questions_from_text(text) == []

    def test_short_stem_rejected(self):
        text = "1. A.\nB. 2\nC. 3\n"
        assert pipeline.parse_questions_from_text(text) == []

    def test_no_delimiters_returns_empty(self):
        assert pipeline.parse_questions_from_text("Hanya teks biasa tanpa nomor.") == []

    def test_jumbled_inline_options_rejected(self):
        text = ("1. Suatu segitiga panjang sisinya adalah 12 cm dan 8 cm. semua "
                "besaran berikut dapat menjadi keliling segitiga tersebut, "
                "kecuali….\n"
                "A. 24 cm B. 28 cm C. 34 cm - D. 36 cm\n"
                "E. 38 cm\n")
        assert pipeline.parse_questions_from_text(text) == []

    def test_partial_parse_of_whole_page_rejected(self):
        # 10 numbered blocks but only 2 carry A-E options (< half) -> the layout
        # isn't being understood, so reject the whole page and let the LLM try.
        lines = []
        for n in range(1, 11):
            lines.append(f"{n}. Soal nomor {n} yang di sini adalah sebuah pernyataan?\n")
            if n in (1, 6):
                lines.append("A. 1\nB. 2\nC. 3\nD. 4\nE. 5\n")
        text = "\n".join(lines)
        assert pipeline.parse_questions_from_text(text) == []

    def test_empty_text_returns_empty(self):
        assert pipeline.parse_questions_from_text("") == []
        assert pipeline.parse_questions_from_text(None) == []


class TestExtractAllQuestionsFromPageText:
    def test_local_parser_used_without_llm(self, monkeypatch):
        text = "1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n"

        def fail_llm(*a, **k):
            raise AssertionError("LLM must not be called when local parse succeeds")

        monkeypatch.setattr(pipeline, "extract_all_questions_from_text", fail_llm)
        qs = pipeline.extract_all_questions_from_page_text(text)
        assert len(qs) == 1
        assert qs[0]["question_text"] == "Berapa 2+2?"

    def test_falls_back_to_llm_when_parse_fails(self, monkeypatch):
        monkeypatch.setattr(pipeline, "parse_questions_from_text",
                            lambda t, qid_regex=None: [])
        called = {"n": 0}

        def fake_llm(page_text, custom_instruction=None, status_callback=None):
            called["n"] += 1
            return [{"id": "Q1", "question_text": page_text.strip()}]

        monkeypatch.setattr(pipeline, "extract_all_questions_from_text", fake_llm)
        qs = pipeline.extract_all_questions_from_page_text("1. Text\nA. 1\nB. 2\nC. 3")
        assert called["n"] == 1
        assert qs[0]["id"] == "Q1"

    def test_llm_used_when_local_disabled(self, monkeypatch):
        monkeypatch.setattr(pipeline, "LOCAL_PARSING_ENABLED", False)
        monkeypatch.setattr(pipeline, "parse_questions_from_text",
                            lambda t, qid_regex=None: [{"id": "X"}])
        called = {"n": 0}

        def fake_llm(page_text, custom_instruction=None, status_callback=None):
            called["n"] += 1
            return [{"id": "Q1", "question_text": page_text.strip()}]

        monkeypatch.setattr(pipeline, "extract_all_questions_from_text", fake_llm)
        pipeline.extract_all_questions_from_page_text("1. Text\nA. 1\nB. 2\nC. 3")
        assert called["n"] == 1


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

    def test_conversion_failure_returns_empty_dict(self, monkeypatch, tmp_path):
        def fail(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(pipeline.pymupdf4llm, "to_markdown", fail)
        assert pipeline._extract_pdf_markdown(str(tmp_path / "x.pdf")) == {}


class TestExtractAllQuestionsFromPdf:
    def _make_pdf(self, tmp_path, page_texts):
        return _make_pdf(tmp_path, page_texts)

    def test_text_first_path_skips_vision(self, monkeypatch, tmp_path):
        pdf = self._make_pdf(
            tmp_path,
            ["1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n2. Berapa 3+3?\n"
             "A. 5\nB. 6\nC. 7\nD. 8\nE. 9\n"],
        )
        calls = {"text": 0, "vision": 0}

        def fake_text(page_text, custom_instruction=None, status_callback=None):
            calls["text"] += 1
            return [{"id": "Q1", "question_text": page_text.strip()}]

        def fail_vision(*a, **k):
            calls["vision"] += 1
            raise AssertionError("vision must not be used on a text page")

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fake_text)
        monkeypatch.setattr(pipeline, "extract_all_questions_from_image", fail_vision)

        questions, skipped = pipeline.extract_all_questions_from_pdf(pdf)
        assert calls["text"] == 1
        assert calls["vision"] == 0
        assert skipped == []
        assert len(questions) == 1
        assert questions[0]["page"] == 1

    def test_blank_page_uses_vision(self, monkeypatch, tmp_path):
        pdf = self._make_pdf(tmp_path, [""])  # blank page -> no text
        calls = {"text": 0, "vision": 0}

        def fail_text(*a, **k):
            calls["text"] += 1
            raise AssertionError("text must not be used on a blank page")

        def fake_vision(image_path, custom_instruction=None, status_callback=None):
            calls["vision"] += 1
            return [{"id": "Q1", "question_text": "from image"}]

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fail_text)
        monkeypatch.setattr(pipeline, "extract_all_questions_from_image", fake_vision)

        questions, skipped = pipeline.extract_all_questions_from_pdf(pdf)
        assert calls["text"] == 0
        assert calls["vision"] == 1
        assert skipped == []
        assert len(questions) == 1
        assert questions[0]["page"] == 1

    def test_max_pages_limits_processing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "EXTRACTION_DELAY_SECONDS", 0.0)
        page_text = ("1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n"
                     "2. Berapa 3+3?\nA. 5\nB. 6\nC. 7\nD. 8\nE. 9\n")
        pdf = self._make_pdf(tmp_path, [page_text] * 4)
        calls = {"n": 0}

        def fake_text(page_text, custom_instruction=None, status_callback=None):
            calls["n"] += 1
            return [{"id": f"Q{calls['n']}", "question_text": page_text.strip()}]

        def fail_vision(*a, **k):
            raise AssertionError("vision must not be used on a text page")

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fake_text)
        monkeypatch.setattr(pipeline, "extract_all_questions_from_image", fail_vision)

        questions, skipped = pipeline.extract_all_questions_from_pdf(pdf, max_pages=2)
        assert calls["n"] == 2
        assert skipped == []
        assert [q["page"] for q in questions] == [1, 2]

    def test_max_pages_larger_than_pdf_is_clamped(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "EXTRACTION_DELAY_SECONDS", 0.0)
        page_text = ("1. Berapa 2+2?\nA. 3\nB. 4\nC. 5\nD. 6\nE. 7\n"
                     "2. Berapa 3+3?\nA. 5\nB. 6\nC. 7\nD. 8\nE. 9\n")
        pdf = self._make_pdf(tmp_path, [page_text] * 2)
        calls = {"n": 0}

        def fake_text(page_text, custom_instruction=None, status_callback=None):
            calls["n"] += 1
            return [{"id": f"Q{calls['n']}", "question_text": page_text.strip()}]

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fake_text)
        monkeypatch.setattr(
            pipeline, "extract_all_questions_from_image",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("vision used")),
        )

        questions, _ = pipeline.extract_all_questions_from_pdf(pdf, max_pages=10)
        assert calls["n"] == 2  # clamped to the PDF's actual page count
        assert [q["page"] for q in questions] == [1, 2]


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
            return [{"id": "Q2", "question_text": "dari halaman 2"}]

        def fail_image(*a, **k):
            calls["image"] += 1
            raise AssertionError("vision must not be used on a text page")

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fake_page_text)
        monkeypatch.setattr(pipeline, "extract_all_questions_from_image", fail_image)

        qs = pipeline.extract_page_questions(pdf, page_index=2)
        assert calls["text"] == 1
        assert calls["image"] == 0
        assert qs[0]["page"] == 2

    def test_empty_page_uses_vision(self, monkeypatch, tmp_path):
        pdf = _make_pdf(tmp_path, ["", "1. Soal 1?\nA. 1\nB. 2\nC. 3\nD. 4\nE. 5\n"])

        def fail_text(*a, **k):
            raise AssertionError("text must not be used on a blank page")

        def fake_image(image_path, custom_instruction=None, status_callback=None):
            assert image_path.endswith("page_01.png")
            return [{"id": "Q1", "question_text": "dari gambar"}]

        monkeypatch.setattr(pipeline, "extract_all_questions_from_page_text", fail_text)
        monkeypatch.setattr(pipeline, "extract_all_questions_from_image", fake_image)

        qs = pipeline.extract_page_questions(pdf, page_index=1)
        assert qs[0]["page"] == 1


class TestBatching:
    def test_generate_variation_batch_slices(self, monkeypatch):
        monkeypatch.setattr(pipeline, "generate_variations", _fake_variations)
        questions = [_sample_question(i) for i in range(5)]
        results = pipeline.generate_variation_batch(questions, start=2, batch_size=2)
        assert [r["original"]["id"] for r in results] == ["Q2", "Q3"]
        assert results[0]["page"] == 1
        assert results[0]["variations"]["easy"]["question_text"] == "e"

    def test_generate_variation_batch_progress_uses_global_index(self, monkeypatch):
        monkeypatch.setattr(pipeline, "generate_variations", _fake_variations)
        questions = [_sample_question(i) for i in range(5)]
        seen = []
        pipeline.generate_variation_batch(
            questions,
            start=2,
            batch_size=2,
            progress_callback=lambda c, t, s, m: seen.append((c, t, s)),
        )
        assert seen == [(3, 5, "vary"), (4, 5, "vary")]

    def test_generate_variation_results_processes_all(self, monkeypatch):
        monkeypatch.setattr(pipeline, "generate_variations", _fake_variations)
        questions = [_sample_question(i) for i in range(3)]
        results = pipeline.generate_variation_results(questions)
        assert [r["original"]["id"] for r in results] == ["Q0", "Q1", "Q2"]

    def test_generate_variation_results_progress_counts_from_one(self, monkeypatch):
        monkeypatch.setattr(pipeline, "generate_variations", _fake_variations)
        questions = [_sample_question(i) for i in range(3)]
        seen = []
        pipeline.generate_variation_results(
            questions, progress_callback=lambda c, t, s, m: seen.append((c, t))
        )
        assert seen == [(1, 3), (2, 3), (3, 3)]

    def test_empty_slice_returns_empty(self, monkeypatch):
        monkeypatch.setattr(pipeline, "generate_variations", _fake_variations)
        assert pipeline.generate_variation_batch([], start=0, batch_size=2) == []
        assert pipeline.generate_variation_results([]) == []

    def test_batch_size_none_means_rest(self, monkeypatch):
        monkeypatch.setattr(pipeline, "generate_variations", _fake_variations)
        questions = [_sample_question(i) for i in range(4)]
        results = pipeline._generate_variation_results(questions, start=1, batch_size=None)
        assert [r["original"]["id"] for r in results] == ["Q1", "Q2", "Q3"]
