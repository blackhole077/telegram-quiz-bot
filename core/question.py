"""Question formatting, shuffling, answer normalisation, and problem utilities."""

from __future__ import annotations

import json
import random
from pathlib import Path

from core.constants import OPTION_PREFIX
from core.schemas.question_schemas import Problem, Question, QuestionType


def labels(question: Question) -> list[str]:
    """Return the label set for question.

    Args:
        question: The question to get labels for.

    Returns:
        ["A", "B", "C", "D"] for MULTIPLE_CHOICE, ["A", "B"] for all others.
    """
    return (
        ["A", "B", "C", "D"]
        if question.type is QuestionType.MULTIPLE_CHOICE
        else ["A", "B"]
    )


def shuffle_answers(question: Question) -> Question:
    """Return a copy of question with answer options shuffled and correct updated.

    Args:
        question: The question to shuffle.

    Returns:
        A new Question with options in a random order and correct updated to
        match. Returns question unchanged for TRUE_OR_FALSE or fewer than 2 options.

    Note:
        TRUE_OR_FALSE questions are never shuffled because normalise_answer
        hard-maps "True" -> "A" and "False" -> "B". Shuffling would break
        that mapping.
    """
    if question.type is QuestionType.TRUE_OR_FALSE or len(question.options) < 2:
        return question
    lbls = labels(question)
    correct_text = question.options[lbls.index(question.correct.upper())]
    shuffled = question.options.copy()
    random.shuffle(shuffled)
    return question.model_copy(
        update={"options": shuffled, "correct": lbls[shuffled.index(correct_text)]}
    )


def input_hint(question: Question) -> str:
    """Return the expected-input hint string for question's type.

    Args:
        question: The question being answered.

    Returns:
        A short string describing valid reply format, e.g. "A, B, C, or D".
    """
    if question.type is QuestionType.MULTIPLE_CHOICE:
        return "A, B, C, or D"
    if question.type is QuestionType.TRUE_OR_FALSE:
        return "True or False"
    return "A or B"


def _fmt_ref(question: Question) -> str:
    ref = question.references[0] if question.references else None
    return f"From {ref.authors} ({ref.year}) · {ref.section}" if ref else ""


def clean_option(opt: str) -> str:
    return OPTION_PREFIX.sub("", opt)


def fmt_question(question: Question, position: int, total: int) -> str:
    """Format question for display in a quiz session.

    Args:
        question: The question to display. Should already be shuffled if desired.
        position: 1-based position of this question in the session.
        total: Total number of questions in the session.

    Returns:
        A formatted string ready to send to the user.
    """
    lbls = labels(question)

    if question.type is QuestionType.TRUE_OR_FALSE:
        body = question.question
    else:
        opts = "\n".join(
            f"  {label}  {clean_option(opt)}"
            for label, opt in zip(lbls, question.options)
        )
        body = f"{question.question}\n\n{opts}"

    ref = _fmt_ref(question)
    hint = input_hint(question)
    footer = f"\n\n{ref}\n\n({hint})" if ref else f"\n\n({hint})"
    return f"[{position}/{total}] {body}{footer}"


def fmt_feedback(question: Question, correct: bool) -> str:
    """Format the post-answer feedback for question.

    Args:
        question: The displayed (possibly shuffled) question.
        correct: Whether the user's answer was correct.

    Returns:
        A formatted feedback string including the correct answer if wrong.
    """
    mark = "✓ Correct" if correct else "✗ Wrong"
    answer_text = ""
    if not correct:
        lbls = labels(question)
        if question.correct in lbls:
            idx = lbls.index(question.correct)
            answer_text = f"\nCorrect answer: {question.correct}  {clean_option(question.options[idx])}"
        else:
            answer_text = f"\nCorrect answer: {question.correct}"

    ref = _fmt_ref(question)
    ref_suffix = f"\n{ref}" if ref else ""
    return f"{mark}{answer_text} — {question.explanation}{ref_suffix}"


def merge_questions(existing: list[Question], new: list[Question]) -> list[Question]:
    """Return existing + any questions from new whose id is not already present."""
    existing_ids = {question.id for question in existing}
    return existing + [question for question in new if question.id not in existing_ids]


def load_problems(path: str | Path) -> list[Problem]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Problem.model_validate(item) for item in data]


def filter_by_topic(problems: list[Problem], topic: str) -> list[Problem]:
    key = topic.lower()
    return [problem for problem in problems if problem.topic.lower() == key]


def pick_random(problems: list[Problem], count: int = 1) -> list[Problem]:
    return random.sample(problems, min(count, len(problems)))


def normalise_answer(text: str, question: Question) -> str | None:
    """Return a normalised label from raw user input, or None if invalid.

    Args:
        text: Raw text from the user.
        question: The question being answered.

    Returns:
        An uppercase label string (e.g. "A") if valid, None otherwise.

    Note:
        For TRUE_OR_FALSE, "True"/"T" maps to "A" and "False"/"F" maps to
        "B". This mapping is fixed because true/false options are never
        shuffled (see shuffle_answers).
    """
    normalized = text.strip().upper()
    if question.type is QuestionType.TRUE_OR_FALSE:
        if normalized in ("TRUE", "T"):
            return "A"
        if normalized in ("FALSE", "F"):
            return "B"
        return None
    return normalized if normalized in labels(question) else None
