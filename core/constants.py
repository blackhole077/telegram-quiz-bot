import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
LLM_ROOT = REPO_ROOT / "core" / "data"
DATA_ROOT = REPO_ROOT / "data"
QUESTIONS_FILE = DATA_ROOT / "questions.json"
ANSWERS_FILE = DATA_ROOT / "answers.jsonl"
# Days until next review keyed by post-correct level.
# Roughly geometric spacing inspired by SM-2, but four fixed levels
# instead of a dynamic ease factor.
SRS_INTERVALS: dict[int, int] = {1: 1, 2: 7, 3: 16, 4: 35}
OPTION_PREFIX = re.compile(r"^[A-Da-d][).:]\s+")

### Exam Template Constants
TEMPLATE = Path(__file__).parent / "data" / "exam_template.tex"
REMEDIAL_TEMPLATE = Path(__file__).parent / "data" / "remedial_exam_template.tex"
TEMPLATE_SRC = TEMPLATE.read_text()
REMEDIAL_TEMPLATE_SRC = REMEDIAL_TEMPLATE.read_text()
TECTONIC = shutil.which("tectonic") or "tectonic"

PLACEHOLDER_TITLE = "VAR_TITLE"
PLACEHOLDER_DATE = "VAR_DATE"


ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# When a LLM emits LaTeX inside JSON without double-escaping backslashes,
# json.loads silently converts \b→backspace, \f→form feed, \r→CR, \t→tab.
# These are the LaTeX commands most commonly affected.
CONTROL_REPAIRS = str.maketrans(
    {
        "\x08": "\\b",  # \boldsymbol, \beta, \bar, \binom ...
        "\x0c": "\\f",  # \frac, \forall, \phi ...
        "\r": "\\r",  # \rho, \rightarrow, \rm ...
        "\t": "\\t",  # \theta, \tau, \times, \text ...
    }
)
# \n is intentionally excluded: real newlines are valid in problem text.

# Matches pmatrix, bmatrix, Bmatrix, vmatrix, Vmatrix, matrix, and * variants.
MATRIX_ENV_RE = re.compile(
    r"(\\begin\{[pbBvV]?matrix\*?\})(.*?)(\\end\{[pbBvV]?matrix\*?\})",
    re.DOTALL,
)
