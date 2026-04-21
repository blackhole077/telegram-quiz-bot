"""Regression tests for data/questions.json integrity."""

from __future__ import annotations

import json
import re

import pytest

from quiz.constants import QUESTIONS_FILE
from quiz.question import OPTION_PREFIX

with QUESTIONS_FILE.open() as _f:
    _QUESTIONS = json.load(_f)

_OPTION_PARAMS = [
    pytest.param(q["id"], q.get("topic", ""), i, opt, id=f"{q['id'][:8]}-opt{i}")
    for q in _QUESTIONS
    for i, opt in enumerate(q.get("options", []))
]


class TestQuestionsData:
    @pytest.mark.parametrize("qid,topic,opt_idx,opt_text", _OPTION_PARAMS)
    def test_no_embedded_label_prefix(self, qid, topic, opt_idx, opt_text):
        """Option text must not start with A), B), C), or D) — labels are added at display time."""
        assert not OPTION_PREFIX.match(opt_text), (
            f"[{topic}] question {qid!r} option[{opt_idx}] has embedded label prefix: {opt_text!r}"
        )

    @pytest.mark.parametrize("qid,topic,opt_idx,opt_text", _OPTION_PARAMS)
    def test_no_parenthesised_label_prefix(self, qid, topic, opt_idx, opt_text):
        """Option text must not start with (A), (B), (C), or (D)."""
        assert not re.match(r"^\([A-Da-d]\)\s*", opt_text), (
            f"[{topic}] question {qid!r} option[{opt_idx}] has parenthesised label prefix: {opt_text!r}"
        )
