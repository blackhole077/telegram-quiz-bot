"""Question formatting, shuffling, and answer normalisation."""

from __future__ import annotations

import random
import re

from quiz.schemas import Question, QuestionType

OPTION_PREFIX = re.compile(r"^[A-Da-d][).]\s+")


def labels(q: Question) -> list[str]:
    """Return the label set for q.

    Args:
        q: The question to get labels for.

    Returns:
        ["A", "B", "C", "D"] for MULTIPLE_CHOICE, ["A", "B"] for all others.
    """
    return (
        ["A", "B", "C", "D"] if q.type is QuestionType.MULTIPLE_CHOICE else ["A", "B"]
    )


def shuffle(q: Question) -> Question:
    """Return a copy of q with options shuffled and correct updated.

    Args:
        q: The question to shuffle.

    Returns:
        A new Question with options in a random order and correct updated to
        match. Returns q unchanged for TRUE_OR_FALSE or fewer than 2 options.

    Note:
        TRUE_OR_FALSE questions are never shuffled because normalise_answer
        hard-maps "True" -> "A" and "False" -> "B". Shuffling would break
        that mapping.
    """
    if q.type is QuestionType.TRUE_OR_FALSE or len(q.options) < 2:
        return q
    lbls = labels(q)
    correct_text = q.options[lbls.index(q.correct.upper())]
    shuffled = q.options.copy()
    random.shuffle(shuffled)
    return q.model_copy(
        update={"options": shuffled, "correct": lbls[shuffled.index(correct_text)]}
    )


def input_hint(q: Question) -> str:
    """Return the expected-input hint string for q's type.

    Args:
        q: The question being answered.

    Returns:
        A short string describing valid reply format, e.g. "A, B, C, or D".
    """
    if q.type is QuestionType.MULTIPLE_CHOICE:
        return "A, B, C, or D"
    if q.type is QuestionType.TRUE_OR_FALSE:
        return "True or False"
    return "A or B"


def _fmt_ref(q: Question) -> str:
    ref = q.references[0] if q.references else None
    return f"From {ref.authors} ({ref.year}) · {ref.section}" if ref else ""


def _clean_option(opt: str) -> str:
    return OPTION_PREFIX.sub("", opt)


def fmt_question(q: Question, n: int, total: int) -> str:
    """Format q for display in a quiz session.

    Args:
        q: The question to display. Should already be shuffled if desired.
        n: 1-based position of this question in the session.
        total: Total number of questions in the session.

    Returns:
        A formatted string ready to send to the user.
    """
    lbls = labels(q)

    if q.type is QuestionType.TRUE_OR_FALSE:
        body = q.question
    else:
        opts = "\n".join(
            f"  {c}  {_clean_option(opt)}" for c, opt in zip(lbls, q.options)
        )
        body = f"{q.question}\n\n{opts}"

    ref = _fmt_ref(q)
    hint = input_hint(q)
    footer = f"\n\n{ref}\n\n({hint})" if ref else f"\n\n({hint})"
    return f"[{n}/{total}] {body}{footer}"


def fmt_feedback(q: Question, correct: bool) -> str:
    """Format the post-answer feedback for q.

    Args:
        q: The displayed (possibly shuffled) question.
        correct: Whether the user's answer was correct.

    Returns:
        A formatted feedback string including the correct answer if wrong.
    """
    mark = "✓ Correct" if correct else "✗ Wrong"
    answer_text = ""
    if not correct:
        lbls = labels(q)
        if q.correct in lbls:
            idx = lbls.index(q.correct)
            answer_text = (
                f"\nCorrect answer: {q.correct}  {_clean_option(q.options[idx])}"
            )
        else:
            answer_text = f"\nCorrect answer: {q.correct}"

    ref = _fmt_ref(q)
    ref_suffix = f"\n{ref}" if ref else ""
    return f"{mark}{answer_text} — {q.explanation}{ref_suffix}"


def normalise_answer(text: str, q: Question) -> str | None:
    """Return a normalised label from raw user input, or None if invalid.

    Args:
        text: Raw text from the user.
        q: The question being answered.

    Returns:
        An uppercase label string (e.g. "A") if valid, None otherwise.

    Note:
        For TRUE_OR_FALSE, "True"/"T" maps to "A" and "False"/"F" maps to
        "B". This mapping is fixed because true/false options are never
        shuffled (see shuffle).
    """
    t = text.strip().upper()
    if q.type is QuestionType.TRUE_OR_FALSE:
        if t in ("TRUE", "T"):
            return "A"
        if t in ("FALSE", "F"):
            return "B"
        return None
    return t if t in labels(q) else None
