"""
Turns the raw ProcessingDiagnostics + AnswerResult list into the
human-readable checklist/explanation format described in spec sections 27
("processing diagnostic summary") and 46 ("explainability").
"""
from __future__ import annotations

from app.core.models import AnswerResult
from app.omr.pipeline import SubmissionResult


def format_diagnostic_summary(result: SubmissionResult) -> str:
    d = result.diagnostics
    lines = []
    lines.append(("✓" if d.page_detected else "✗") + " Page/markers detected"
                 + (f" ({d.registration_method})" if d.page_detected else ""))
    lines.append(("✓" if d.registration_ok else "✗") + " Registration"
                 + (f" successful (confidence {d.registration_confidence:.0f}%, "
                    f"geometry {d.registration_geometry_score:.0f}%, "
                    f"reprojection error {d.reprojection_error_px:.2f}px)" if d.registration_ok else " FAILED"))
    if d.quality:
        lines.append(f"  Image quality: {d.quality.overall:.0f}%  "
                      f"(resolution {d.quality.resolution:.0f}%, sharpness {d.quality.sharpness:.0f}%, "
                      f"lighting {d.quality.lighting:.0f}%, contrast {d.quality.contrast:.0f}%, "
                      f"illumination {d.quality.illumination_uniformity:.0f}%)")
    lines.append(f"✓ {d.questions_located}/{d.questions_expected} questions located")
    if result.student_id:
        sid = result.student_id
        mark = "✓" if not sid.needs_review else "⚠"
        lines.append(f"{mark} Student ID: {sid.partial_id or '(unreadable)'} "
                      f"(confidence {sid.overall_confidence:.0f}%)")
    for tf in result.text_fields:
        mark = "✓" if tf.status == "READ" else ("·" if tf.status == "EMPTY" else "⚠")
        lines.append(f"{mark} {tf.name}: {tf.text if tf.text else '(' + tf.status.lower() + ')'}")
    if d.warnings:
        lines.append("")
        for w in d.warnings:
            lines.append(f"⚠ {w}")
    return "\n".join(lines)


def explain_answer(answer: AnswerResult) -> str:
    """Human-readable version of spec 46's 'why did you choose B?' example."""
    exp = answer.explanation or {}
    candidates = exp.get("candidates", [])
    cand_str = ", ".join(f"{c['option']}={c['fill_ratio']:.2f}" for c in candidates)
    lines = [f"Q{answer.question_number:03d}: {answer.status.value}"
             f"{' -> ' + answer.detected_answer if answer.detected_answer else ''}"
             f" (confidence {answer.confidence:.1f}%)"]
    lines.append(f"  Candidate fill ratios: {cand_str}")
    if "winner_margin" in exp:
        lines.append(f"  Winner margin: {exp['winner_margin']:.3f}   "
                      f"Separability (std): {exp.get('separability_std', 0):.3f}   "
                      f"Methods agreeing: {exp.get('methods_agreeing', '?')}")
    if "image_quality" in exp:
        lines.append(f"  Image quality at capture time: {exp['image_quality']:.0f}%")
    if "reason" in exp:
        lines.append(f"  Reason: {exp['reason']}")
    return "\n".join(lines)
