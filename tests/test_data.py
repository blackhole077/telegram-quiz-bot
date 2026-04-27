"""Regression tests for data/questions.json integrity."""

from __future__ import annotations

import json
import re

from core.constants import QUESTIONS_FILE
from core.question import OPTION_PREFIX

with QUESTIONS_FILE.open() as _f:
    _QUESTIONS = json.load(_f)


class TestQuestionsData:
    def test_no_embedded_label_prefix(self):
        """Option text must not start with A), A., or A: prefixes - labels are added at display time."""
        violations = [
            f"[{q.get('topic', '')}] question {q['id']!r} option[{i}]: {opt!r}"
            for q in _QUESTIONS
            for i, opt in enumerate(q.get("options", []))
            if OPTION_PREFIX.match(opt)
        ]
        assert not violations, "Options with embedded label prefixes:\n" + "\n".join(violations)

    def test_no_parenthesised_label_prefix(self):
        """Option text must not start with (A), (B), (C), or (D)."""
        violations = [
            f"[{q.get('topic', '')}] question {q['id']!r} option[{i}]: {opt!r}"
            for q in _QUESTIONS
            for i, opt in enumerate(q.get("options", []))
            if re.match(r"^\([A-Da-d]\)\s*", opt)
        ]
        assert not violations, "Options with parenthesised label prefixes:\n" + "\n".join(violations)
