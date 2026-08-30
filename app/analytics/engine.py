"""
Exam-level and question-level analytics. Pure aggregation over what's
already stored (AnswerResult + Submission + AnswerKey rows) -- no image
processing here, matching the "grading engine independent of CV" split
this project uses throughout.
"""
from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field

from app.database import repository as repo


@dataclass
class ExamStats:
    n_submissions: int
    n_scored: int
    average: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    std_dev: float | None
    distribution: list[tuple[str, int]] = field(default_factory=list)  # [("0-10%", 2), ...]


@dataclass
class QuestionStats:
    question_number: int
    correct_answer: str | None
    correct_pct: float
    wrong_pct: float
    blank_pct: float
    multiple_pct: float
    review_rate_pct: float
    avg_confidence: float
    n: int


def compute_exam_stats(conn: sqlite3.Connection, exam_id: int) -> ExamStats:
    submissions = repo.list_submissions(conn, exam_id)
    percentages = [s.percentage for s in submissions if s.percentage is not None]
    n = len(percentages)

    if n == 0:
        return ExamStats(len(submissions), 0, None, None, None, None, None, [])

    buckets = [(f"{lo}-{lo+9}%", 0) for lo in range(0, 100, 10)]
    buckets = {label: 0 for label, _ in buckets}
    for p in percentages:
        idx = min(9, int(p // 10))
        label = f"{idx*10}-{idx*10+9}%"
        buckets[label] = buckets.get(label, 0) + 1

    return ExamStats(
        n_submissions=len(submissions),
        n_scored=n,
        average=round(statistics.fmean(percentages), 2),
        median=round(statistics.median(percentages), 2),
        minimum=round(min(percentages), 2),
        maximum=round(max(percentages), 2),
        std_dev=round(statistics.pstdev(percentages), 2) if n > 1 else 0.0,
        distribution=list(buckets.items()),
    )


def compute_question_stats(conn: sqlite3.Connection, exam_id: int) -> list[QuestionStats]:
    rows = repo.get_all_answer_results_for_exam(conn, exam_id)
    by_question: dict[int, list[sqlite3.Row]] = {}
    for r in rows:
        by_question.setdefault(r["question_number"], []).append(r)

    out = []
    for q, items in sorted(by_question.items()):
        n = len(items)
        correct = wrong = blank = multiple = reviewed = 0
        confidences = []
        correct_answer = items[0]["correct_answer"]
        for r in items:
            given = r["final_answer"] if r["final_answer"] is not None else r["detected_answer"]
            status = r["status"]
            confidences.append(r["confidence"])
            if status == "MULTIPLE_MARK" and r["final_answer"] is None:
                multiple += 1
            elif given is None:
                blank += 1
            elif correct_answer and given in {c.strip() for c in correct_answer.split(",")}:
                correct += 1
            else:
                wrong += 1
            if status in ("LOW_CONFIDENCE", "MULTIPLE_MARK", "AMBIGUOUS", "UNREADABLE") or (r["confidence"] or 0) < 60:
                reviewed += 1

        out.append(QuestionStats(
            question_number=q,
            correct_answer=correct_answer,
            correct_pct=round(100 * correct / n, 1),
            wrong_pct=round(100 * wrong / n, 1),
            blank_pct=round(100 * blank / n, 1),
            multiple_pct=round(100 * multiple / n, 1),
            review_rate_pct=round(100 * reviewed / n, 1),
            avg_confidence=round(sum(confidences) / n, 1) if confidences else 0.0,
            n=n,
        ))
    return out
