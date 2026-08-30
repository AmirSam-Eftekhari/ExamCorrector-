"""
Diagnostic image-quality analysis.

IMPORTANT: this module never rejects an image. It only scores it. A low
score should lower downstream confidence and surface a warning -- it must
never silently block a submission from being processed (per spec section 16).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import cv2
import numpy as np

from app.core.config import QualityConfig


@dataclass
class QualityReport:
    resolution: float
    sharpness: float
    lighting: float
    contrast: float
    illumination_uniformity: float
    overall: float

    def as_dict(self) -> dict:
        return asdict(self)


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def analyze_quality(gray: np.ndarray, cfg: QualityConfig = QualityConfig()) -> QualityReport:
    h, w = gray.shape[:2]
    short_side = min(h, w)

    # --- Resolution ---
    resolution = _clip01(short_side / cfg.min_short_side_px)

    # --- Sharpness (variance of Laplacian) ---
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharpness = _clip01(
        (lap_var - cfg.blur_laplacian_low)
        / max(1e-6, (cfg.blur_laplacian_high - cfg.blur_laplacian_low))
    )

    # --- Lighting / exposure: penalize over/under-exposed histograms ---
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    hist /= max(1.0, hist.sum())
    dark_clip = hist[:10].sum()      # near-black pixels
    bright_clip = hist[246:].sum()   # near-white (blown-out) pixels
    mean_val = float(gray.mean())
    mean_score = 1.0 - abs(mean_val - 190.0) / 190.0   # paper should read light gray/white
    lighting = _clip01(mean_score - 0.5 * dark_clip - 0.5 * bright_clip)

    # --- Contrast: std deviation of intensities ---
    contrast = _clip01(float(gray.std()) / 70.0)

    # --- Illumination uniformity: compare mean brightness across a 4x4 grid ---
    gh, gw = h // 4, w // 4
    means = []
    for i in range(4):
        for j in range(4):
            tile = gray[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw]
            if tile.size:
                means.append(float(tile.mean()))
    if len(means) >= 2:
        spread = (max(means) - min(means)) / 255.0
        illumination_uniformity = _clip01(1.0 - spread)
    else:
        illumination_uniformity = 1.0

    overall = _clip01(
        0.20 * resolution
        + 0.30 * sharpness
        + 0.20 * lighting
        + 0.15 * contrast
        + 0.15 * illumination_uniformity
    )

    return QualityReport(
        resolution=round(resolution * 100, 1),
        sharpness=round(sharpness * 100, 1),
        lighting=round(lighting * 100, 1),
        contrast=round(contrast * 100, 1),
        illumination_uniformity=round(illumination_uniformity * 100, 1),
        overall=round(overall * 100, 1),
    )
