"""Normalize LaTeX in AI-generated text for reliable rendering.

Streamlit's st.markdown renders math only when it is wrapped in ``$...$``
(inline) or ``$$...$$`` (display math on its own lines).  Models sometimes
forget those delimiters and emit bare commands such as ``\frac{12-0}{5-1}``,
which Markdown then mangles (e.g. ``\f`` is swallowed and the result is shown
as ``rac{12-0}{5-1}``).  ``normalize_latex`` guarantees every LaTeX expression
is wrapped in the right delimiters.
"""

import re

_DELIMITED_MATH_RE = re.compile(
    r"(\$\$[^$]*\$\$"
    r"|\\\[.*?\\\]"
    r"|\$[^$]*\$"
    r"|\\\(.*?\\\)"
    r"|\\begin\{[^{}]*\}.*?\\end\{[^{}]*\})",
    re.DOTALL,
)

_CMD_RE = re.compile(r"\\[a-zA-Z]+")
_END_ENV_RE = re.compile(r"\\end\s*\{[^{}]*\}")


def _closing_brace(s, start):
    """Return the index of the ``}`` matching the ``{`` at ``s[start]``."""
    depth = 0
    i = start
    while i < len(s):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _re_delimit(part):
    """Rewrite a captured math token with canonical ``$...$``/``$$...$$``."""
    if part.startswith("\\begin"):
        return f"$$\n{part}\n$$"
    if part.startswith("\\["):
        return f"$$\n{part[2:-2]}\n$$"
    if part.startswith("\\("):
        return f"${part[2:-2]}$"
    return part


def _wrap_bare_commands(prose):
    """Wrap bare LaTeX commands (no delimiters) in ``$...$``."""
    out = []
    i = 0
    while i < len(prose):
        m = _CMD_RE.search(prose, i)
        if not m:
            out.append(prose[i:])
            break
        out.append(prose[i:m.start()])
        start = m.start()
        j = m.end()
        if m.group(0) == "\\begin":
            if j < len(prose) and prose[j] == "{":
                k = _closing_brace(prose, j)
                if k != -1:
                    j = k + 1
            end = _END_ENV_RE.search(prose[j:])
            if end:
                j += end.end()
        else:
            while j < len(prose) and prose[j] == "[":
                k = prose.find("]", j)
                if k == -1:
                    break
                j = k + 1
            while j < len(prose) and prose[j] == "{":
                k = _closing_brace(prose, j)
                if k == -1:
                    break
                j = k + 1
        out.append("$" + prose[start:j] + "$")
        i = j
    return "".join(out)


def _collapse_double_backslashes(text):
    """Undo model double-escaping (``\\\\frac`` -> ``\\frac``) without touching
    real LaTeX line breaks such as the row separators in ``\\begin{bmatrix}``.

    A ``\\\\`` is collapsed only when followed by a letter, ``(``/``[``/``)``/``]``
    or another ``\\`` (i.e. the start/end of another LaTeX command or delimiter).
    A ``\\\\`` followed by a space or newline is a genuine row separator and is
    kept.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] == "\\":
            nxt = text[i + 2] if i + 2 < n else ""
            if nxt in "\\([)]\\" or nxt.isalpha():
                out.append("\\")
                i += 2
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def normalize_latex(text):
    """Return ``text`` with every LaTeX expression properly delimited.

    Already-delimited math (``$...$``, ``$$...$$``, ``\\(...\\)``,
    ``\\[...\\]``, ``\\begin...\\end``) is normalized; bare commands such as
    ``\\frac{...}{...}`` are wrapped in ``$...$``.  Model double-escaping
    (``\\\\frac``) is collapsed to a single backslash first, since KaTeX
    otherwise misreads ``\\\\`` as a line break and renders ``rac`` as letters.
    """
    if not text:
        return text
    text = _collapse_double_backslashes(text)
    parts = _DELIMITED_MATH_RE.split(text)
    out = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            out.append(_re_delimit(part))
        else:
            out.append(_wrap_bare_commands(part))
    return "".join(out)