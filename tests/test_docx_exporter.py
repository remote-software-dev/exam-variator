import pytest

pytest.importorskip("lxml")
from lxml import etree

from exam_generator import docx_exporter as exporter


class TestSanitizeOption:
    def test_collapses_newlines(self):
        assert exporter._sanitize_option("a\nb\n c") == "a b c"

    def test_strips_whitespace(self):
        assert exporter._sanitize_option("   text   ") == "text"

    def test_none_becomes_empty(self):
        assert exporter._sanitize_option(None) == ""


class TestSplitInline:
    def test_plain_text(self):
        assert exporter._split_inline("hello world") == [
            {"type": "run", "text": "hello world", "bold": False, "italic": False}
        ]

    def test_mixed_markdown_and_math(self):
        parts = exporter._split_inline("a **bold** *it* $x^2$ $$y$$ b")
        assert [p["type"] for p in parts] == [
            "run", "run", "run", "run", "run", "math", "run", "math", "run",
        ]
        assert parts[1] == {"type": "run", "text": "bold", "bold": True, "italic": False}
        assert parts[3] == {"type": "run", "text": "it", "bold": False, "italic": True}
        assert parts[5] == {"type": "math", "text": "x^2"}
        assert parts[7] == {"type": "math", "text": "y"}

    def test_empty_text(self):
        assert exporter._split_inline("") == []

    def test_whitespace_only(self):
        assert exporter._split_inline("   ") == [
            {"type": "run", "text": "   ", "bold": False, "italic": False}
        ]


class TestBuildMarkdown:
    def _item(self):
        return {
            "page": 2,
            "original": {
                "id": "Q1",
                "question_text": "Soal asli?",
                "options": ["o1", "o2", "o3", "o4", "o5"],
            },
            "variations": {
                "easy": {
                    "question_text": "Soal mudah?",
                    "options": ["op1", "op2", "op3", "op4", "op5"],
                    "solution_by_concept": "Langkah 1",
                    "solution_by_trick": "Trik cepat",
                },
                "medium": {
                    "question_text": "Soal sedang?",
                    "options": ["m1", "m2", "m3", "m4", "m5"],
                    "solution_by_concept": "Langkah sedang",
                },
                "hard": {
                    "question_text": "Soal sulit?",
                    "options": ["a", "b", "c", "d", "e"],
                    "solution_by_concept": "Langkah sulit",
                },
            },
        }

    def test_full_structure(self):
        md = exporter.build_markdown([self._item()])
        assert md.startswith("# Bank Soal & Variasi Matematika")
        assert "## Soal 1 (Halaman 2)" in md
        assert "**ID:** Q1" in md
        assert "### Soal Asli" in md
        assert "Soal asli?" in md
        assert "- **A.** o1" in md
        assert "### Variasi Mudah" in md
        assert "Soal mudah?" in md
        assert "### Variasi Sedang" in md
        assert "Soal sedang?" in md
        assert "### Variasi Sulit" in md
        assert "**Penyelesaian (Konsep Dasar):**" in md
        assert "Langkah 1" in md
        assert "**Penyelesaian (Cara Cepat/Trik):**" in md
        assert "Trik cepat" in md
        assert md.count("---") == 1

    def test_no_page_note_when_missing(self):
        item = self._item()
        item["page"] = None
        md = exporter.build_markdown([item])
        assert "## Soal 1\n" in md
        assert "Halaman" not in md

    def test_missing_variations_are_skipped(self):
        item = self._item()
        item["variations"] = {}
        md = exporter.build_markdown([item])
        assert "### Variasi" not in md

    def test_empty_solutions_are_omitted(self):
        item = self._item()
        item["variations"]["easy"]["solution_by_concept"] = "  "
        item["variations"]["easy"]["solution_by_trick"] = ""
        md = exporter.build_markdown([item])
        assert "Langkah 1" not in md
        assert "Trik cepat" not in md
        assert "Langkah sulit" in md

    def test_original_without_options(self):
        item = self._item()
        item["original"]["options"] = []
        md = exporter.build_markdown([item])
        assert "Opsi Jawaban" not in md


class TestOmmlFromMathml:
    def test_fraction_produces_omml(self):
        mathml = (
            '<math xmlns="http://www.w3.org/1998/Math/MathML">'
            "<mfrac><mn>1</mn><mn>2</mn></mfrac></math>"
        )
        omath = exporter._omml_from_mathml(mathml)
        assert omath.tag == f"{{{exporter._M_NS}}}oMath"
        assert [etree.QName(c).localname for c in omath] == ["f"]

    def test_matrix_produces_bracketed_oMath(self):
        mathml = (
            '<math xmlns="http://www.w3.org/1998/Math/MathML">'
            "<mrow><mo>[</mo><mtable><mtr><mtd><mn>1</mn></mtd>"
            "<mtd><mn>2</mn></mtd></mtr></mtable><mo>]</mo></mrow></math>"
        )
        omath = exporter._omml_from_mathml(mathml)
        assert omath.tag == f"{{{exporter._M_NS}}}oMath"
        assert [etree.QName(c).localname for c in omath] == ["m"]
