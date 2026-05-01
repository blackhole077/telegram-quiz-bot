from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

WEB_ROOT = Path(__file__).parent


def _format_solution(text: str) -> Markup:
    if not text:
        return Markup("")
    paragraphs = text.split("\n\n")
    parts = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        escaped = escape(para).replace("\n", Markup("<br>"))
        parts.append(
            Markup('<p class="explanation" style="margin-top:8px">')
            + escaped
            + Markup("</p>")
        )
    return Markup("").join(parts)


TEMPLATES = Jinja2Templates(directory=str(WEB_ROOT / "templates"))
TEMPLATES.env.filters["format_solution"] = _format_solution
