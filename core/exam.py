"""PDF exam generation via LaTeX/tectonic."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from core.constants import (ESCAPE_MAP, PLACEHOLDER_DATE, PLACEHOLDER_TITLE,
                            REMEDIAL_TEMPLATE_SRC, TECTONIC, TEMPLATE_SRC)
from core.schemas.llm_schemas import ExamProblem


def _escape(text: str) -> str:
    """Escape LaTeX special characters in plain text (single-pass)."""
    return "".join(ESCAPE_MAP.get(ch, ch) for ch in text)


def _build_content(problems: list[ExamProblem]) -> str:
    lines: list[str] = []

    for p in problems:
        cmd = r"\rproblem" if p.is_remedial else r"\problem"
        lines.append(rf"{cmd}{{{_escape(p.topic)}}}")
        lines.append(p.prompt)
        lines.append(r"\vspace{5cm}")
        lines.append("")

    lines.append(r"\newpage")
    lines.append(r"\section*{Answer Key}")
    lines.append("")

    for p in problems:
        cmd = r"\rsolution" if p.is_remedial else r"\solution"
        lines.append(rf"{cmd}{{{_escape(p.topic)}}}")
        lines.append(p.solution)
        lines.append(r"\vspace{0.3cm}")
        lines.append("")

    return "\n".join(lines)


def render_exam_pdf(problems: list[ExamProblem], category: str, date: str) -> bytes:
    """Compile an exam to PDF bytes using tectonic.

    Writes a content.tex into a temp directory alongside the template,
    then invokes tectonic to produce the PDF.
    """
    remedial = bool(problems) and all(p.is_remedial for p in problems)
    template_src = REMEDIAL_TEMPLATE_SRC if remedial else TEMPLATE_SRC
    template_src = template_src.replace(PLACEHOLDER_TITLE, _escape(category))
    template_src = template_src.replace(PLACEHOLDER_DATE, _escape(date))

    content_tex = _build_content(problems)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "main.tex").write_text(template_src)
        (tmp_path / "content.tex").write_text(content_tex)

        result = subprocess.run(
            [TECTONIC, "main.tex"],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tectonic failed (exit {result.returncode}):\n{result.stderr}"
            )

        return (tmp_path / "main.pdf").read_bytes()
