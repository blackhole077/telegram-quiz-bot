import re

# When a LLM emits LaTeX inside JSON without double-escaping backslashes,
# json.loads silently converts \b→backspace, \f→form feed, \r→CR, \t→tab.
# These are the LaTeX commands most commonly affected.
_CONTROL_REPAIRS = str.maketrans({
    '\x08': '\\b',  # \boldsymbol, \beta, \bar, \binom ...
    '\x0c': '\\f',  # \frac, \forall, \phi ...
    '\r':   '\\r',  # \rho, \rightarrow, \rm ...
    '\t':   '\\t',  # \theta, \tau, \times, \text ...
})
# \n is intentionally excluded: real newlines are valid in problem text.

# Matches pmatrix, bmatrix, Bmatrix, vmatrix, Vmatrix, matrix, and * variants.
_MATRIX_ENV_RE = re.compile(
    r'(\\begin\{[pbBvV]?matrix\*?\})(.*?)(\\end\{[pbBvV]?matrix\*?\})',
    re.DOTALL,
)


def _fix_matrix_row_seps(match: re.Match) -> str:
    """Double single-backslash row separators inside a matrix environment.

    The LLM often writes \\\\ in JSON for the LaTeX row separator \\, which
    json.loads reduces to a single \\. This restores it to \\\\ so KaTeX can
    parse it. LaTeX commands (\\alpha, \\frac, etc.) are unaffected because
    they are followed by letters, not whitespace.
    """
    body = match.group(2)
    # Match \ followed by whitespace, but not \\ (already doubled).
    body = re.sub(r'(?<!\\)\\(?=\s)', r'\\\\', body)
    return match.group(1) + body + match.group(3)


def normalise_latex(text: str) -> str:
    """Fix JSON-escape corruption and convert $...$ delimiters to KaTeX \\(...\\) form."""
    text = text.translate(_CONTROL_REPAIRS)
    text = re.sub(r'\$\$(.+?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)
    text = re.sub(r'\$(.+?)\$', r'\\(\1\\)', text, flags=re.DOTALL)
    text = _MATRIX_ENV_RE.sub(_fix_matrix_row_seps, text)
    return text
