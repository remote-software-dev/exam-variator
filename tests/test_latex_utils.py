from exam_generator.latex_utils import normalize_latex


class TestNormalizeLatex:
    def test_bare_fraction_wrapped_inline(self):
        assert normalize_latex(r"Gradien = \frac{12-0}{5-1}") == (
            r"Gradien = $\frac{12-0}{5-1}$"
        )

    def test_double_backslash_fraction_collapsed(self):
        assert normalize_latex(r"Gradien = \\frac{12-0}{5-1}") == (
            r"Gradien = $\frac{12-0}{5-1}$"
        )

    def test_double_backslash_inside_dollars_collapsed(self):
        assert normalize_latex(r"Gradien = $\\frac{12-0}{5-1}$") == (
            r"Gradien = $\frac{12-0}{5-1}$"
        )

    def test_double_backslash_escaped_delimiters_collapsed(self):
        assert normalize_latex(r"Gradien = \\(\\frac{12-0}{5-1}\\)") == (
            r"Gradien = $\frac{12-0}{5-1}$"
        )

    def test_matrix_row_separator_after_newline_preserved(self):
        matrix = r"\begin{bmatrix} 1 \\ 2 \end{bmatrix}"
        assert normalize_latex(matrix) == f"$$\n{matrix}\n$$"

    def test_already_delimited_unchanged(self):
        text = r"Gradien = $\frac{12-0}{5-1}$"
        assert normalize_latex(text) == text

    def test_display_math_unchanged(self):
        text = "$$d_{dalam}=d_{luar}-2t$$"
        assert normalize_latex(text) == text

    def test_parenthesized_inline_rewritten(self):
        assert normalize_latex(r"Gradien = \(\frac{12-0}{5-1}\)") == (
            r"Gradien = $\frac{12-0}{5-1}$"
        )

    def test_bracket_display_rewritten(self):
        assert normalize_latex(r"\[x^2\]") == "$$\nx^2\n$$"

    def test_nested_braces_wrapped(self):
        assert normalize_latex(r"\frac{\frac{1}{2}}{3}") == (
            r"$\frac{\frac{1}{2}}{3}$"
        )

    def test_sqrt_wrapped(self):
        assert normalize_latex(r"\sqrt{2}") == r"$\sqrt{2}$"

    def test_symbol_without_braces_wrapped(self):
        assert normalize_latex(r"3 \times 4") == r"3 $\times$ 4"

    def test_environment_wrapped_as_display(self):
        matrix = r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}"
        assert normalize_latex(matrix) == f"$$\n{matrix}\n$$"

    def test_bare_environment_wrapped(self):
        matrix = r"\begin{bmatrix} 1 & 2 \end{bmatrix} done"
        assert normalize_latex(matrix) == (
            "$$\n\\begin{bmatrix} 1 & 2 \\end{bmatrix}\n$$ done"
        )

    def test_mixed_prose_and_math(self):
        text = ("Hitung gradien dari titik (1, 0) dan (5, 12): "
                r"\frac{12-0}{5-1} = 3, jadi $\frac{12}{4}=3$.")
        expected = ("Hitung gradien dari titik (1, 0) dan (5, 12): "
                    r"$\frac{12-0}{5-1}$ = 3, jadi $\frac{12}{4}=3$.")
        assert normalize_latex(text) == expected

    def test_empty_and_none(self):
        assert normalize_latex("") == ""
        assert normalize_latex(None) is None

    def test_plain_prose_untouched(self):
        text = "Hanya teks biasa tanpa rumus."
        assert normalize_latex(text) == text
