"""
Student ID extraction from the OMR digit grid (not OCR -- the ID is a set of
bubbled digit columns, so we run the same bubble/analysis engine used for
answers on each column, per spec section 28).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.config import AppConfig, DEFAULT_CONFIG
from app.core.models import AnswerStatus, BubbleScore
from app.omr.bubble_features import extract_bubble_features
from app.omr.analysis import analyze_question
from app.templates.schema import StudentIdRegion


@dataclass
class DigitResult:
    column: int
    digit: str | None
    status: AnswerStatus
    confidence: float


@dataclass
class StudentIdResult:
    student_id: str | None       # None if any digit is unreadable/blank/ambiguous
    partial_id: str               # best-effort string, using '?' for uncertain digits
    overall_confidence: float
    digits: list[DigitResult] = field(default_factory=list)
    needs_review: bool = True


def read_student_id(
    gray: np.ndarray,
    region: StudentIdRegion,
    canvas_size: tuple,
    cfg: AppConfig = DEFAULT_CONFIG,
) -> StudentIdResult:
    if not region.present:
        return StudentIdResult(student_id=None, partial_id="", overall_confidence=0.0, digits=[], needs_review=True)

    cw, ch = canvas_size
    bubble_radius_px = region.bubble_radius * cw

    digit_results: list[DigitResult] = []
    for col in range(region.n_digits):
        scores: list[BubbleScore] = []
        for digit_value in range(region.digits_per_column):
            cx, cy = region.bubble_center(col, digit_value, canvas_size)
            scores.append(extract_bubble_features(gray, cx, cy, bubble_radius_px, option=str(digit_value), cfg=cfg.bubble))
        result = analyze_question(scores, quality_overall_0_100=100.0, cfg=cfg.confidence)
        digit_results.append(DigitResult(
            column=col,
            digit=result["detected_answer"],
            status=result["status"],
            confidence=result["confidence"],
        ))

    confidences = [d.confidence for d in digit_results]
    overall_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    all_high = all(d.status == AnswerStatus.HIGH_CONFIDENCE for d in digit_results)
    partial_id = "".join(d.digit if d.digit is not None else "?" for d in digit_results)
    student_id = partial_id if all_high else None

    return StudentIdResult(
        student_id=student_id,
        partial_id=partial_id,
        overall_confidence=overall_confidence,
        digits=digit_results,
        needs_review=not all_high,
    )
