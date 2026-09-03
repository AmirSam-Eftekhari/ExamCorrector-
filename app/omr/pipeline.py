"""
End-to-end orchestration for a single submission:

Image -> Quality Analysis -> Page/Registration -> Template Coordinate Space
-> Question ROI -> Option ROI -> Mark Feature Extraction -> Confidence
-> AnswerResult list (+ Student ID + best-effort text fields + diagnostics)

Per spec section 19, this does NOT scan the whole image for circles --
bubble positions come directly from the template's stored geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core.config import AppConfig, DEFAULT_CONFIG
from app.core.models import AnswerResult, AnswerStatus, BubbleScore, SubmissionStatus
from app.cv.quality import analyze_quality, QualityReport
from app.cv.page_detect import detect_markers
from app.cv.registration import register, RegistrationResult
from app.cv.preprocessing import select_best_pipeline, per_bubble_fill
from app.omr.bubble_features import extract_bubble_features
from app.omr.analysis import analyze_question
from app.omr.student_id import read_student_id, StudentIdResult
from app.ocr.text_fields import read_all_text_fields, TextFieldResult
from app.templates.schema import Template


@dataclass
class ProcessingDiagnostics:
    page_detected: bool = False
    registration_method: str = ""
    registration_ok: bool = False
    reprojection_error_px: float = 0.0
    registration_confidence: float = 0.0
    registration_geometry_score: float = 0.0
    registration_warnings: list = field(default_factory=list)
    quality: QualityReport | None = None
    questions_located: int = 0
    questions_expected: int = 0
    warnings: list[str] = field(default_factory=list)
    selected_preprocessing_pipeline: str = ""
    preprocessing_pipeline_scores: dict = field(default_factory=dict)


@dataclass
class SubmissionResult:
    status: SubmissionStatus
    answers: list[AnswerResult] = field(default_factory=list)
    student_id: StudentIdResult | None = None
    text_fields: list[TextFieldResult] = field(default_factory=list)
    diagnostics: ProcessingDiagnostics = field(default_factory=ProcessingDiagnostics)
    failure_reason: str = ""
    warped_image: np.ndarray | None = None   # registered/normalized page, for review-UI overlays
    canvas_size: tuple = (0, 0)


def process_submission(
    image_bgr: np.ndarray,
    template: Template,
    cfg: AppConfig = DEFAULT_CONFIG,
    submission_id: int | None = None,
) -> SubmissionResult:
    diag = ProcessingDiagnostics(questions_expected=template.question_count)

    gray_full = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    diag.quality = analyze_quality(gray_full, cfg.quality)

    marker_result = detect_markers(gray_full, cfg.registration)
    diag.page_detected = marker_result.ok
    reg_result = register(image_bgr, marker_result, template.canvas_size, cfg=cfg.registration)
    diag.registration_method = reg_result.method
    diag.registration_ok = reg_result.ok
    diag.reprojection_error_px = reg_result.reprojection_error_px
    diag.registration_confidence = reg_result.confidence
    diag.registration_geometry_score = reg_result.marker_geometry_score
    diag.registration_warnings = reg_result.warnings

    if not reg_result.ok:
        diag.warnings.append(f"Registration failed: {reg_result.reason}")
        return SubmissionResult(
            status=SubmissionStatus.FAILED,
            diagnostics=diag,
            failure_reason=reg_result.reason,
        )

    if reg_result.confidence < cfg.registration.min_trusted_confidence:
        diag.warnings.append(
            f"REGISTRATION_CONFIDENCE {reg_result.confidence:.0f}% -- below the trusted threshold; "
            f"answers on this page should be treated with extra caution."
        )
    for w in reg_result.warnings:
        diag.warnings.append(f"REGISTRATION: {w}")

    warped_gray = cv2.cvtColor(reg_result.warped, cv2.COLOR_BGR2GRAY)
    cw, ch = template.canvas_size

    # Run and score every candidate preprocessing pipeline (spec section 6)
    # against the template's own known bubble ROIs, and keep the winning
    # pipeline's output as an extra, independent vote in the confidence
    # engine's consensus below -- not just a diagnostic that's computed and
    # then ignored.
    all_bubble_geometry = [
        (*block.bubble_center(q, i, template.canvas_size), block.bubble_radius * cw)
        for block in template.blocks
        for q in range(block.question_start, block.question_end + 1)
        for i in range(len(block.option_labels))
    ]
    best_pipeline = None
    if all_bubble_geometry:
        try:
            best_pipeline, prep_diag = select_best_pipeline(warped_gray, all_bubble_geometry)
            diag.selected_preprocessing_pipeline = prep_diag.get("selected", "")
            diag.preprocessing_pipeline_scores = prep_diag.get("scores", {})
        except Exception:
            best_pipeline = None  # never let a preprocessing hiccup take down the whole submission

    answers: list[AnswerResult] = []
    for block in template.blocks:
        for q in range(block.question_start, block.question_end + 1):
            scores: list[BubbleScore] = []
            for opt_idx, opt_label in enumerate(block.option_labels):
                cx, cy = block.bubble_center(q, opt_idx, template.canvas_size)
                radius_px = block.bubble_radius * cw
                s = extract_bubble_features(warped_gray, cx, cy, radius_px, option=opt_label, cfg=cfg.bubble)
                if best_pipeline is not None:
                    s.preprocessing_vote = round(per_bubble_fill(best_pipeline.output, cx, cy, radius_px), 4)
                scores.append(s)

            result = analyze_question(scores, quality_overall_0_100=diag.quality.overall, cfg=cfg.confidence)
            answers.append(AnswerResult(
                submission_id=submission_id,
                question_number=q,
                detected_answer=result["detected_answer"],
                confidence=result["confidence"],
                status=result["status"],
                raw_scores=scores,
                explanation=result["explanation"],
            ))

    diag.questions_located = len(answers)
    review_confidence_floor = 60.0
    for a in answers:
        flagged_status = a.status in (
            AnswerStatus.LOW_CONFIDENCE, AnswerStatus.MULTIPLE_MARK,
            AnswerStatus.AMBIGUOUS, AnswerStatus.UNREADABLE,
        )
        # Even a BLANK/HIGH_CONFIDENCE call gets a second look if its own
        # confidence number is weak -- the status label alone isn't the only
        # signal that a human should check this one.
        if flagged_status or a.confidence < review_confidence_floor:
            diag.warnings.append(f"Q{a.question_number:03d} {a.status.value} ({a.confidence:.0f}%)")

    student_id_result = None
    if template.student_id.present:
        student_id_result = read_student_id(warped_gray, template.student_id, template.canvas_size, cfg=cfg)
        if student_id_result.needs_review:
            diag.warnings.append("STUDENT_ID needs review")

    text_field_results = []
    if template.text_fields:
        text_field_results = read_all_text_fields(warped_gray, template.text_fields, template.canvas_size)
        if any(t.status == "ENGINE_UNAVAILABLE" for t in text_field_results):
            diag.warnings.append(
                "OCR_ENGINE_UNAVAILABLE: Tesseract is not installed or not on PATH on this "
                "machine -- Name/Class/Date/etc. fields cannot be read until it's set up "
                "(bubbles and Student ID are unaffected, since those don't use OCR). "
                "See Settings for install instructions."
            )

    needs_review = bool(diag.warnings)
    status = SubmissionStatus.NEEDS_REVIEW if needs_review else SubmissionStatus.COMPLETED

    return SubmissionResult(
        status=status,
        answers=answers,
        student_id=student_id_result,
        text_fields=text_field_results,
        diagnostics=diag,
        warped_image=reg_result.warped,
        canvas_size=template.canvas_size,
    )
