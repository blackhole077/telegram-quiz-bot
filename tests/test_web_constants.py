"""Tests for frontend/web/constants.py — _format_solution filter."""

from __future__ import annotations

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")

from markupsafe import Markup

from frontend.web.constants import _format_solution


class TestFormatSolution:
    def test_empty_string_returns_markup_empty(self):
        result = _format_solution("")
        assert result == Markup("")

    def test_single_paragraph_wraps_in_p_tag(self):
        result = _format_solution("Hello world")
        assert result == Markup(
            '<p class="explanation" style="margin-top:8px">Hello world</p>'
        )

    def test_double_newline_splits_into_two_paragraphs(self):
        result = _format_solution("First paragraph\n\nSecond paragraph")
        assert '<p class="explanation"' in result
        assert result.count('<p class="explanation"') == 2
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_single_newline_becomes_br(self):
        result = _format_solution("Line one\nLine two")
        assert "<br>" in result
        assert "Line one" in result
        assert "Line two" in result

    def test_html_special_chars_are_escaped(self):
        result = _format_solution("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_ampersand_escaped(self):
        result = _format_solution("A & B")
        assert "&amp;" in result

    def test_math_delimiters_preserved(self):
        result = _format_solution(r"The answer is \(x^2 + y^2\)")
        assert r"\(x^2 + y^2\)" in result

    def test_display_math_delimiters_preserved(self):
        result = _format_solution(r"See \[E = mc^2\]")
        assert r"\[E = mc^2\]" in result

    def test_math_with_paragraph_breaks(self):
        text = r"Step 1: \(x = 1\)" + "\n\n" + r"Step 2: \(y = 2\)"
        result = _format_solution(text)
        assert r"\(x = 1\)" in result
        assert r"\(y = 2\)" in result
        assert result.count('<p class="explanation"') == 2

    def test_returns_markup_type(self):
        result = _format_solution("text")
        assert isinstance(result, Markup)

    def test_whitespace_only_paragraphs_skipped(self):
        result = _format_solution("Para one\n\n\n\nPara two")
        assert result.count('<p class="explanation"') == 2
