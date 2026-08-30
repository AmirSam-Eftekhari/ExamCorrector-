"""
Deterministic scoring engine. Operates purely on AnswerResult + AnswerKey
data -- it never touches pixels, and the same inputs always produce the
same outputs (spec section 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models import AnswerResult, AnswerStatus, ScoringRule


@dataclass
class QuestionGrade:
    question_number: int
    correct_answer: str
    given_answer: str | None
    outcome: str        # "CORRECT" | "WRONG" | "BLANK" | "MULTIPLE" | "UNSCORED_REVIEW"
    points: float


@dataclass
class ExamGrade:
    total_score: float
    max_score: float
    percentage: float
    correct: int
    wrong: int
    blank: int
    multiple_or_invalid: int
    unscored_pending_review: int
    per_question: list[QuestionGrade] = field(default_factory=list)


def grade_submission(
    answers: list[AnswerResult],
    answer_key: dict[int, str],
    rule: ScoringRule = ScoringRule(),
) -> ExamGrade:
    """
    answers: one AnswerResult per question (use `final_answer` if a human has
        reviewed/corrected it, otherwise falls back to `detected_answer`).
    answer_key: {question_number: "A"} (or "A,B" style is treated as any-of
        those letters counting correct, for exams that allow multiple keys).
    """
    per_question: list[QuestionGrade] = []
    correct = wrong = blank = multi = pending = 0
    total = 0.0
    max_score = 0.0

    for a in sorted(answers, key=lambda x: x.question_number):
        key = answer_key.get(a.question_number)
        if key is None:
            continue  # question not in this exam's key -- skip, don't fabricate a grade
        max_score += rule.correct

        given = a.final_answer if a.final_answer is not None else a.detected_answer
        human_reviewed = a.final_answer is not None

        if a.status == AnswerStatus.MULTIPLE_MARK and not human_reviewed:
            multi += 1
            points = _multi_mark_points(rule)
            outcome = "MULTIPLE" if rule.multiple_mark_policy != "manual_review" else "UNSCORED_REVIEW"
            if rule.multiple_mark_policy == "manual_review":
                pending += 1
            per_question.append(QuestionGrade(a.question_number, key, given, outcome, points))
            total += points
            continue

        if given is None:
            blank += 1
            per_question.append(QuestionGrade(a.question_number, key, None, "BLANK", rule.blank))
            total += rule.blank
            continue

        allowed = {c.strip() for c in key.split(",")}
        if given in allowed:
            correct += 1
            per_question.append(QuestionGrade(a.question_number, key, given, "CORRECT", rule.correct))
            total += rule.correct
        else:
            wrong += 1
            per_question.append(QuestionGrade(a.question_number, key, given, "WRONG", rule.wrong))
            total += rule.wrong

    percentage = round(100.0 * total / max_score, 2) if max_score > 0 else 0.0
    return ExamGrade(
        total_score=round(total, 4),
        max_score=round(max_score, 4),
        percentage=percentage,
        correct=correct,
        wrong=wrong,
        blank=blank,
        multiple_or_invalid=multi,
        unscored_pending_review=pending,
        per_question=per_question,
    )


def _multi_mark_points(rule: ScoringRule) -> float:
    if rule.multiple_mark_policy == "wrong":
        return rule.wrong
    if rule.multiple_mark_policy == "invalid":
        return rule.multiple_mark_score
    if rule.multiple_mark_policy == "manual_review":
        return 0.0
    return rule.multiple_mark_score
