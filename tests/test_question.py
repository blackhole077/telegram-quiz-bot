"""Tests for quiz/question.py — formatting, shuffling, answer normalisation."""

from __future__ import annotations

import pytest

from core.question import (fmt_feedback, fmt_question, input_hint, labels,
                           merge_questions, normalise_answer, shuffle_answers)
from core.schemas.question_schemas import QuestionType
from tests.conftest import make_question


class TestLabels:
    def test_mcq_returns_four(self, mcq):
        assert labels(mcq) == ["A", "B", "C", "D"]

    def test_tof_returns_two(self, tof):
        assert labels(tof) == ["A", "B"]

    def test_binary_returns_two(self, binary):
        assert labels(binary) == ["A", "B"]


class TestInputHint:
    def test_mcq_hint(self, mcq):
        assert input_hint(mcq) == "A, B, C, or D"

    def test_tof_hint(self, tof):
        assert input_hint(tof) == "True or False"

    def test_binary_hint(self, binary):
        assert input_hint(binary) == "A or B"


class TestShuffle:
    def test_tof_never_shuffled(self, tof):
        original_options = tof.options[:]
        for _ in range(10):
            result = shuffle_answers(tof)
            assert result.options == original_options
            assert result is tof

    def test_mcq_correct_answer_text_preserved(self):
        q = make_question(
            options=["alpha", "beta", "gamma", "delta"],
            correct="B",
        )
        for _ in range(20):
            shuffled = shuffle_answers(q)
            correct_idx = labels(shuffled).index(shuffled.correct)
            assert shuffled.options[correct_idx] == "beta"

    def test_mcq_shuffled_has_same_options_set(self):
        q = make_question(options=["alpha", "beta", "gamma", "delta"], correct="A")
        shuffled = shuffle_answers(q)
        assert sorted(shuffled.options) == sorted(q.options)

    def test_mcq_correct_label_updated(self):
        q = make_question(options=["A_txt", "B_txt", "C_txt", "D_txt"], correct="A")
        shuffled = shuffle_answers(q)
        correct_text_in_shuffled = shuffled.options[
            labels(shuffled).index(shuffled.correct)
        ]
        assert correct_text_in_shuffled == "A_txt"

    def test_binary_is_shuffled(self):
        q = make_question(
            qtype=QuestionType.BINARY_CHOICE, options=["Yes", "No"], correct="A"
        )
        results = {shuffle_answers(q).correct for _ in range(30)}
        assert len(results) == 2

    def test_fewer_than_two_options_returns_unchanged(self):
        q = make_question(options=["only"], correct="A")
        result = shuffle_answers(q)
        assert result is q

    def test_does_not_mutate_original(self):
        q = make_question(options=["alpha", "beta", "gamma", "delta"], correct="C")
        original_options = q.options[:]
        shuffle_answers(q)
        assert q.options == original_options


class TestNormaliseAnswer:
    # ---- TRUE_OR_FALSE ----
    @pytest.mark.parametrize("text", ["True", "true", "TRUE", "T", "t"])
    def test_tof_true_variants(self, tof, text):
        assert normalise_answer(text, tof) == "A"

    @pytest.mark.parametrize("text", ["False", "false", "FALSE", "F", "f"])
    def test_tof_false_variants(self, tof, text):
        assert normalise_answer(text, tof) == "B"

    def test_tof_invalid_returns_none(self, tof):
        assert normalise_answer("maybe", tof) is None
        assert normalise_answer("", tof) is None
        assert normalise_answer("A", tof) is None

    # ---- MULTIPLE_CHOICE ----
    @pytest.mark.parametrize("text", ["A", "a", " A ", "B", "C", "D"])
    def test_mcq_valid_labels(self, mcq, text):
        result = normalise_answer(text, mcq)
        assert result == text.strip().upper()

    def test_mcq_invalid_label_returns_none(self, mcq):
        assert normalise_answer("E", mcq) is None
        assert normalise_answer("X", mcq) is None
        assert normalise_answer("", mcq) is None

    # ---- BINARY_CHOICE ----
    def test_binary_valid(self, binary):
        assert normalise_answer("A", binary) == "A"
        assert normalise_answer("B", binary) == "B"

    def test_binary_invalid(self, binary):
        assert normalise_answer("C", binary) is None
        assert normalise_answer("Yes", binary) is None  # text, not label


class TestFmtQuestion:
    def test_header_shows_position(self, mcq):
        text = fmt_question(mcq, 2, 5)
        assert text.startswith("[2/5]")

    def test_mcq_includes_all_options(self, mcq):
        q = make_question(options=["alpha", "beta", "gamma", "delta"])
        text = fmt_question(q, 1, 3)
        for opt in ["alpha", "beta", "gamma", "delta"]:
            assert opt in text

    def test_tof_body_is_just_question(self, tof):
        text = fmt_question(tof, 1, 1)
        # For TRUE_OR_FALSE the body is just the question text; no option list.
        assert "opt A" not in text
        assert tof.question in text

    def test_reference_footer_present(self, mcq):
        text = fmt_question(mcq, 1, 1)
        assert "Author A" in text
        assert "2020" in text

    def test_no_ref_omits_footer_emoji(self):
        q = make_question(references=[])
        text = fmt_question(q, 1, 1)
        assert "📄" not in text

    def test_option_prefix_stripped(self):
        q = make_question(options=["A) first", "B) second", "C) third", "D) fourth"])
        text = fmt_question(q, 1, 1)
        assert "first" in text
        assert "A) first" not in text

    def test_colon_option_prefix_stripped(self):
        q = make_question(options=["A: first", "B: second", "C: third", "D: fourth"])
        text = fmt_question(q, 1, 1)
        assert "first" in text
        assert "A: first" not in text


class TestFmtFeedback:
    def test_correct_shows_checkmark(self, mcq):
        text = fmt_feedback(mcq, True)
        assert text.startswith("✓ Correct")

    def test_wrong_shows_cross(self, mcq):
        text = fmt_feedback(mcq, False)
        assert text.startswith("✗ Wrong")

    def test_wrong_includes_correct_answer(self):
        q = make_question(options=["alpha", "beta", "gamma", "delta"], correct="B")
        text = fmt_feedback(q, False)
        assert "B" in text
        assert "beta" in text

    def test_correct_does_not_reveal_answer(self, mcq):
        # When correct, there's no "Correct answer:" line.
        text = fmt_feedback(mcq, True)
        assert "Correct answer:" not in text

    def test_explanation_always_present(self, mcq):
        assert "Because X." in fmt_feedback(mcq, True)
        assert "Because X." in fmt_feedback(mcq, False)

    def test_ref_appended_to_feedback(self, mcq):
        text = fmt_feedback(mcq, True)
        assert "Author A" in text

    def test_no_ref_omits_footer(self):
        q = make_question(references=[])
        assert "📄" not in fmt_feedback(q, False)


class TestMergeQuestions:
    def test_adds_new_questions(self):
        result = merge_questions([make_question(id="q1")], [make_question(id="q2")])
        assert len(result) == 2

    def test_skips_duplicate_ids(self):
        existing = make_question(id="q1", level=1)
        duplicate = make_question(id="q1", level=3)
        result = merge_questions([existing], [duplicate])
        assert len(result) == 1
        assert result[0].level == 1

    def test_empty_existing(self):
        result = merge_questions([], [make_question(id="q1")])
        assert len(result) == 1

    def test_empty_new(self):
        result = merge_questions([make_question(id="q1")], [])
        assert len(result) == 1

    def test_both_empty(self):
        assert merge_questions([], []) == []

    def test_partial_overlap(self):
        existing = [make_question(id="q1"), make_question(id="q2")]
        new = [make_question(id="q2"), make_question(id="q3")]
        result = merge_questions(existing, new)
        assert sorted(question.id for question in result) == ["q1", "q2", "q3"]
