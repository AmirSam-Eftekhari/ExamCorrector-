"""
Multiple candidate preprocessing pipelines, each producing a grayscale
"markedness map" (higher = more likely ink) from the registered/normalized
page. The pipeline that gives the best bubble separability is selected --
never the one that simply produces the most black pixels (spec 18).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np


@dataclass
class PipelineResult:
    name: str
    output: np.ndarray   # single-channel, higher value = darker/more marked


def pipeline_a_denoise_contrast(gray: np.ndarray) -> np.ndarray:
    # A median blur removes salt-and-pepper/JPEG-artifact noise nearly as
    # well as non-local-means denoising for this purpose (separating a
    # bubble's fill from paper texture) at a small fraction of the cost --
    # fastNlMeansDenoising takes ~3-4s on a full page, which is fine for a
    # one-off template calibration but far too slow to run on every one of
    # potentially hundreds of submissions in a batch.
    den = cv2.medianBlur(gray, 3)
    return cv2.equalizeHist(den)


def pipeline_b_clahe_adaptive(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    th = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 8
    )
    return th


def pipeline_c_gaussian_otsu(gray: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return th


def pipeline_d_illumination_correct(gray: np.ndarray) -> np.ndarray:
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=25)
    corrected = cv2.subtract(bg, gray)
    corrected = cv2.normalize(corrected, None, 0, 255, cv2.NORM_MINMAX)
    _, th = cv2.threshold(corrected.astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th


def pipeline_e_bilateral_local_contrast(gray: np.ndarray) -> np.ndarray:
    bil = cv2.bilateralFilter(gray, 9, 50, 50)
    th = cv2.adaptiveThreshold(
        bil, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 10
    )
    return th


PIPELINES: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "A_denoise_contrast": pipeline_a_denoise_contrast,
    "B_clahe_adaptive": pipeline_b_clahe_adaptive,
    "C_gaussian_otsu": pipeline_c_gaussian_otsu,
    "D_illumination_correct": pipeline_d_illumination_correct,
    "E_bilateral_local_contrast": pipeline_e_bilateral_local_contrast,
}


def per_bubble_fill(pipeline_output: np.ndarray, cx: float, cy: float, r: float, inner_factor: float = 0.68) -> float:
    """Fraction of 'on' pixels inside a bubble's interior for one pipeline's
    output -- used as an independent 4th vote in the confidence engine's
    consensus (spec section 6: preprocessing pipelines must actually feed
    the OMR decision, not just exist)."""
    h, w = pipeline_output.shape[:2]
    x0, x1 = max(0, int(cx - r)), min(w, int(cx + r))
    y0, y1 = max(0, int(cy - r)), min(h, int(cy + r))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    roi = pipeline_output[y0:y1, x0:x1]
    yy, xx = np.ogrid[:roi.shape[0], :roi.shape[1]]
    local_cx, local_cy = cx - x0, cy - y0
    mask = (xx - local_cx) ** 2 + (yy - local_cy) ** 2 <= (r * inner_factor) ** 2
    if mask.sum() == 0:
        return 0.0
    is_binary = set(np.unique(roi).tolist()) <= {0, 255}
    if is_binary:
        return float((roi[mask] > 0).mean())
    return float(1.0 - roi[mask].mean() / 255.0)  # grayscale: darker = higher fill


def run_all_pipelines(gray: np.ndarray) -> list[PipelineResult]:
    results = []
    for name, fn in PIPELINES.items():
        try:
            out = fn(gray)
            results.append(PipelineResult(name=name, output=out))
        except cv2.error:
            # A pipeline failing on unusual input must not take down the batch.
            continue
    return results


def score_pipeline_for_bubbles(pipeline_output: np.ndarray, bubble_centers_radii: list[tuple]) -> float:
    """
    Score = how well this representation separates filled vs unfilled bubbles,
    using the *known* bubble ROIs from the template (not raw black-pixel count).
    bubble_centers_radii: list of (cx, cy, r) in the same coordinate space as pipeline_output.
    Returns a 0..1 separability score (std-dev of per-bubble fill ratios, normalized).
    """
    if not bubble_centers_radii:
        return 0.0
    fills = []
    h, w = pipeline_output.shape[:2]
    is_binary = set(np.unique(pipeline_output).tolist()) <= {0, 255}
    for cx, cy, r in bubble_centers_radii:
        x0, x1 = max(0, int(cx - r)), min(w, int(cx + r))
        y0, y1 = max(0, int(cy - r)), min(h, int(cy + r))
        if x1 <= x0 or y1 <= y0:
            continue
        roi = pipeline_output[y0:y1, x0:x1]
        if is_binary:
            fills.append(float((roi > 0).mean()))
        else:
            fills.append(float(roi.mean()) / 255.0)
    if len(fills) < 2:
        return 0.0
    fills_arr = np.array(fills)
    # Good separability = bimodal spread (some bubbles clearly darker than others).
    spread = float(fills_arr.std())
    return max(0.0, min(1.0, spread * 3.0))


def select_best_pipeline(
    gray: np.ndarray, bubble_centers_radii: list[tuple]
) -> tuple[PipelineResult, dict]:
    results = run_all_pipelines(gray)
    scored = []
    for r in results:
        s = score_pipeline_for_bubbles(r.output, bubble_centers_radii)
        scored.append((s, r))
    scored.sort(key=lambda t: -t[0])
    best_score, best = scored[0]
    diagnostics = {"scores": {r.name: round(s, 4) for s, r in scored}, "selected": best.name}
    return best, diagnostics
