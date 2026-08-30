"""
The core OMR decision engine.

Absolute thresholds alone are not trusted (spec 21): every question is
evaluated by comparing its own options against each other (relative
analysis), cross-checking two independent scoring methods (consensus,
spec 25), and folding in image/registration quality before a confidence
number is produced. Nothing here ever forces a single-answer guess when
the evidence doesn't support one -- BLANK, MULTIPLE_MARK, and
LOW_CONFIDENCE are first-class outcomes, not error states.
"""
from __future__ import annotations

import statistics

from app.core.config import ConfidenceConfig, DEFAULT_CONFIG
from app.core.models import AnswerStatus, BubbleScore


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def analyze_question(
    scores: list[BubbleScore],
    quality_overall_0_100: float = 100.0,
    cfg: ConfidenceConfig = DEFAULT_CONFIG.confidence,
) -> dict:
    """
    Returns a dict with: status, detected_answer, confidence (0-100),
    candidates (list of {option, fill_ratio}), explanation (dict).
    """
    if not scores:
        return {
            "status": AnswerStatus.UNREADABLE,
            "detected_answer": None,
            "confidence": 0.0,
            "candidates": [],
            "explanation": {"reason": "No bubble ROIs available for this question."},
        }

    by_fill = sorted(scores, key=lambda s: -s.fill_ratio)
    by_dark = sorted(scores, key=lambda s: -s.dark_pixel_ratio)
    by_adaptive = sorted(scores, key=lambda s: -s.adaptive_dark_ratio)
    fills = [s.fill_ratio for s in scores]
    std_fill = statistics.pstdev(fills) if len(fills) > 1 else 0.0

    top = by_fill[0]
    second = by_fill[1] if len(by_fill) > 1 else None
    margin = (top.fill_ratio - second.fill_ratio) if second else top.fill_ratio

    quality_factor = 0.55 + 0.45 * (_clip(quality_overall_0_100) / 100.0)
    # Independently-computed methods vote on the winner (spec 25): ring-
    # relative local darkness, Otsu dark-pixel ratio, an adaptive-threshold
    # vote, and (when available) the page's auto-selected preprocessing
    # pipeline's own fill reading.
    votes = [top.option, by_dark[0].option, by_adaptive[0].option]
    has_preprocessing_vote = all(s.preprocessing_vote is not None for s in scores)
    if has_preprocessing_vote:
        by_prep = sorted(scores, key=lambda s: -(s.preprocessing_vote or 0.0))
        votes.append(by_prep[0].option)
    n_methods = len(votes)
    agree_count = max(votes.count(v) for v in set(votes))
    methods_agree = agree_count >= (3 if n_methods == 4 else 2)

    explanation = {
        "candidates": [{"option": s.option, "fill_ratio": s.fill_ratio, "dark_pixel_ratio": s.dark_pixel_ratio,
                         "adaptive_dark_ratio": s.adaptive_dark_ratio,
                         **({"preprocessing_vote": s.preprocessing_vote} if s.preprocessing_vote is not None else {})}
                        for s in sorted(scores, key=lambda s: s.option)],
        "winner_margin": round(margin, 4),
        "separability_std": round(std_fill, 4),
        "image_quality": round(quality_overall_0_100, 1),
        "methods_agreeing": f"{agree_count}/{n_methods}",
    }

    # ---- BLANK: nothing crosses the "this is a mark at all" floor ----
    if top.fill_ratio < cfg.min_fill_for_mark:
        # A blank is confidently blank when the top option is *well* below
        # the mark threshold AND all options look alike (no isolated option
        # that's merely faint rather than absent). Distance-from-threshold
        # alone would under-rate a totally clean blank just because the
        # printed bubble outline itself contributes a small constant amount
        # of "ink" inside every ROI.
        distance_margin = _clip((cfg.min_fill_for_mark - top.fill_ratio) / max(1e-6, cfg.min_fill_for_mark), 0.0, 1.0)
        uniformity = _clip(1.0 - std_fill / 0.05, 0.0, 1.0)
        confidence = _clip((0.5 * distance_margin + 0.5 * uniformity) * 100.0 * quality_factor)
        explanation["reason"] = "No option's fill strength reaches the minimum mark threshold."

        # Erasure/residue check (spec 13): a bubble that's below the mark
        # floor but has an unusually non-uniform interior (eraser smudging,
        # partial ink fragments) isn't quite as clean a blank as one whose
        # interior is uniform paper -- flag it rather than calling it clean.
        if top.interior_std >= cfg.erasure_interior_std_threshold:
            confidence = _clip(confidence * 0.6)
            explanation["reason"] = "Below the mark threshold, but the interior isn't uniform -- possible erased/partial mark."
            return {
                "status": AnswerStatus.LOW_CONFIDENCE,
                "detected_answer": None,
                "confidence": round(confidence, 1),
                "candidates": explanation["candidates"],
                "explanation": explanation,
            }

        return {
            "status": AnswerStatus.BLANK,
            "detected_answer": None,
            "confidence": round(confidence, 1),
            "candidates": explanation["candidates"],
            "explanation": explanation,
        }

    # ---- MULTIPLE_MARK: two (not all) options are genuinely both marked ----
    # If literally every option crossed the mark threshold at similar strength,
    # that's much more likely uniform shadow/lighting than a student filling in
    # every bubble -- the low-separability branch below handles that case
    # instead of mislabeling it as a deliberate multi-mark.
    marked = [s for s in scores if s.fill_ratio >= cfg.multi_mark_min_fill]
    if 2 <= len(marked) < len(scores):
        marked_sorted = sorted(marked, key=lambda s: -s.fill_ratio)
        top2_margin = marked_sorted[0].fill_ratio - marked_sorted[1].fill_ratio
        if top2_margin <= cfg.multi_mark_margin_ceiling:
            confidence = _clip(100.0 * (1.0 - top2_margin / max(1e-6, cfg.multi_mark_margin_ceiling)) * quality_factor)
            explanation["reason"] = (
                f"{len(marked)} options are marked with comparable strength "
                f"({[m.option for m in marked_sorted]}); not selecting one arbitrarily."
            )
            return {
                "status": AnswerStatus.MULTIPLE_MARK,
                "detected_answer": None,
                "confidence": round(confidence, 1),
                "candidates": explanation["candidates"],
                "explanation": explanation,
            }

    # ---- Low separability: everything is similarly dark (e.g. a shadow) ----
    if std_fill < cfg.low_separability_std:
        confidence = _clip(40.0 * quality_factor)
        explanation["reason"] = "All options have similar fill strength -- likely uneven lighting/shadow, not a clear mark."
        return {
            "status": AnswerStatus.LOW_CONFIDENCE,
            "detected_answer": top.option,
            "confidence": round(confidence, 1),
            "candidates": explanation["candidates"],
            "explanation": explanation,
        }

    # ---- Ambiguous margin between the top two options ----
    if margin < cfg.ambiguous_margin:
        span = max(1e-6, cfg.min_margin_for_high_confidence - 0.0)
        confidence = _clip((cfg.low_confidence_ceiling * (margin / max(1e-6, cfg.ambiguous_margin))) * 100.0 * quality_factor)
        explanation["reason"] = f"Winner margin ({margin:.3f}) is below the ambiguity threshold."
        return {
            "status": AnswerStatus.LOW_CONFIDENCE,
            "detected_answer": top.option,
            "confidence": round(confidence, 1),
            "candidates": explanation["candidates"],
            "explanation": explanation,
        }

    # ---- High confidence: clear winner, healthy margin ----
    if margin >= cfg.min_margin_for_high_confidence and methods_agree:
        base = cfg.high_confidence_floor * 100.0
        bonus = min(100.0 - base, (margin - cfg.min_margin_for_high_confidence) * 40.0)
        confidence = _clip((base + bonus) * quality_factor)
        explanation["reason"] = f"Clear single mark; {agree_count}/{n_methods} scoring methods agree on the winner."
        return {
            "status": AnswerStatus.HIGH_CONFIDENCE,
            "detected_answer": top.option,
            "confidence": round(confidence, 1),
            "candidates": explanation["candidates"],
            "explanation": explanation,
        }

    # ---- Everything in between: real margin, but methods disagree or margin is modest ----
    interp = (margin - cfg.ambiguous_margin) / max(1e-6, cfg.min_margin_for_high_confidence - cfg.ambiguous_margin)
    confidence = _clip((cfg.low_confidence_ceiling + interp * (cfg.high_confidence_floor - cfg.low_confidence_ceiling)) * 100.0 * quality_factor)
    status = AnswerStatus.HIGH_CONFIDENCE if confidence >= cfg.high_confidence_floor * 100.0 and methods_agree else AnswerStatus.LOW_CONFIDENCE
    if not methods_agree:
        explanation["reason"] = f"Scoring methods disagree on the winning option ({agree_count}/{n_methods} agree)."
    else:
        explanation["reason"] = "Moderate winner margin."
    return {
        "status": status,
        "detected_answer": top.option,
        "confidence": round(confidence, 1),
        "candidates": explanation["candidates"],
        "explanation": explanation,
    }
