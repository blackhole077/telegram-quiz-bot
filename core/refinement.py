"""Analyze answer log to identify weak topics and questions needing attention."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field

from core.schemas.answer_schemas import AnswerLogEntry
from core.schemas.question_schemas import DifficultQuestion, Question


@dataclass
class RefinementReport:
    """Aggregated quality signals derived from the answer log.

    ``rewrite_ids``: wrong 2+ times total.
    ``simplify_ids``: subset of ``rewrite_ids`` still at level 1 —
        stuck at level 1 despite multiple failures suggests too-hard
        or ambiguous wording.
        Note: ``rewrite_ids`` is derived from the answer log (lifetime
        wrong-answer totals), while ``simplify_ids`` reflects current
        pool state (``level == 1``).  The two can be out of sync if the
        pool was edited — e.g. a question reset or removed — after the
        log entries were written.
    ``flagged_topics``: >50 % error rate with at least 3 attempts
        (threshold prevents a single wrong answer triggering a flag).
    ``retire_ids``: level >= 4 with last 3 history entries all correct.
        The ``>= 4`` check is defensive; logically level never exceeds 4.
    """

    rewrite_ids: list[str] = field(default_factory=list)
    simplify_ids: list[str] = field(default_factory=list)
    flagged_topics: list[str] = field(default_factory=list)
    retire_ids: list[str] = field(default_factory=list)
    difficult_questions: list[DifficultQuestion] = field(default_factory=list)


def _extract_difficult_questions(
    qmap: dict[str, Question],
    min_attempts: int = 3,
    max_rate: float = 0.5,
) -> list[DifficultQuestion]:
    result = []
    for q in qmap.values():
        if len(q.history) < min_attempts:
            continue
        rate = sum(h.correct for h in q.history) / len(q.history)
        if rate < max_rate:
            result.append(
                DifficultQuestion(
                    question=q,
                    correct_answer_rate=rate,
                    reference_material=q.references[0] if q.references else None,
                )
            )
    return result


def analyze_gaps(
    answer_log: list[AnswerLogEntry],
    questions: list[Question],
) -> RefinementReport:
    """Compute a ``RefinementReport`` from the full answer history.

    Stateless: produces a fresh report on every call without modifying
    inputs. Returns an empty report if either input is empty.
    """
    report = RefinementReport()

    if not answer_log or not questions:
        return report

    qmap = {q.id: q for q in questions}

    wrong_counts: dict[str, int] = defaultdict(int)
    topic_correct: dict[str, list[bool]] = defaultdict(list)
    for entry in answer_log:
        if not entry.correct:
            wrong_counts[entry.qid] += 1
        topic_correct[entry.topic].append(entry.correct)

    report.rewrite_ids = [qid for qid, count in wrong_counts.items() if count >= 2]

    report.simplify_ids = [
        qid for qid in report.rewrite_ids if qid in qmap and qmap[qid].level == 1
    ]

    report.flagged_topics = [
        topic
        for topic, results in topic_correct.items()
        if len(results) >= 3 and (results.count(False) / len(results)) > 0.5
    ]

    for q in questions:
        if q.level >= 4 and len(q.history) >= 3:
            if all(h.correct for h in q.history[-3:]):
                report.retire_ids.append(q.id)

    report.difficult_questions = _extract_difficult_questions(qmap)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze quiz gaps from answer log.")
    parser.add_argument("--log", default="data/answers.jsonl")
    parser.add_argument("--pool", default="data/questions.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    from pathlib import Path

    from backend.backends import FilesystemBackend

    storage = FilesystemBackend(Path(args.pool), Path(args.log))
    answer_log = storage.load_answers()
    questions = storage.load_questions()
    report = analyze_gaps(answer_log, questions)

    if args.json:
        print(
            json.dumps(
                {
                    "rewrite_ids": report.rewrite_ids,
                    "simplify_ids": report.simplify_ids,
                    "flagged_topics": report.flagged_topics,
                    "retire_ids": report.retire_ids,
                },
                indent=2,
            )
        )
    else:
        if report.flagged_topics:
            print(f"Weak topics (>50% error rate): {', '.join(report.flagged_topics)}")
        if report.rewrite_ids:
            print(
                f"Questions to rewrite ({len(report.rewrite_ids)}): {', '.join(report.rewrite_ids)}"
            )
        if report.simplify_ids:
            print(
                f"Questions to simplify ({len(report.simplify_ids)}): {', '.join(report.simplify_ids)}"
            )
        if report.retire_ids:
            print(
                f"Questions to retire ({len(report.retire_ids)}): {', '.join(report.retire_ids)}"
            )
        if not any(
            [
                report.flagged_topics,
                report.rewrite_ids,
                report.simplify_ids,
                report.retire_ids,
            ]
        ):
            print("No gaps detected.")


if __name__ == "__main__":
    main()
