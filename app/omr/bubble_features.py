"""
Multi-feature extraction for a single bubble ROI. Never reduces a mark to
one number at this stage -- callers (analysis.py) combine these features
and compare bubbles *relative to each other*, per spec sections 20-21.

Redesigned to compare each bubble's interior against a local background
ring rather than fixed global paper/ink intensity constants (spec sections
7-9). A shadow that darkens both the bubble AND the paper right around it
mostly cancels out in `local_darkness = ring_mean - inner_mean`; the old
approach (interior intensity vs. a fixed white/black constant) would read
a shadowed *empty* bubble as partially filled.
"""
from __future__ import annotations

import cv2
import numpy as np

from app.core.config import BubbleConfig, DEFAULT_CONFIG
from app.core.models import BubbleScore


def _annulus_mask(shape, cx: float, cy: float, r_inner: float, r_outer: float) -> np.ndarray:
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    return (d2 >= r_inner ** 2) & (d2 <= r_outer ** 2)


def _disk_mask(shape, cx: float, cy: float, r: float) -> np.ndarray:
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2


def extract_bubble_features(
    gray: np.ndarray, cx: float, cy: float, radius: float, option: str,
    cfg: BubbleConfig = DEFAULT_CONFIG.bubble,
) -> BubbleScore:
    """
    gray: full (registered) grayscale page.
    cx, cy, radius: bubble geometry in the same pixel space as `gray`.
    """
    h, w = gray.shape[:2]
    r = max(2.0, float(radius))
    r_outer = r * cfg.ring_outer_factor
    crop_r = int(np.ceil(r_outer)) + 1

    x0, x1 = max(0, int(cx - crop_r)), min(w, int(cx + crop_r))
    y0, y1 = max(0, int(cy - crop_r)), min(h, int(cy + crop_r))
    if x1 <= x0 or y1 <= y0:
        return BubbleScore(option=option, fill_ratio=0.0, mean_intensity=255.0,
                            dark_pixel_ratio=0.0, edge_density=0.0)

    roi = gray[y0:y1, x0:x1]
    local_cx, local_cy = cx - x0, cy - y0

    inner_mask = _disk_mask(roi.shape, local_cx, local_cy, r * cfg.inner_radius_factor)
    ring_mask = _annulus_mask(roi.shape, local_cx, local_cy, r * cfg.ring_inner_factor, r_outer)

    if inner_mask.sum() == 0:
        inner_mask = _disk_mask(roi.shape, local_cx, local_cy, r)
    if ring_mask.sum() < 6:
        # ROI got clipped by the page edge and there's no room for a ring --
        # fall back to treating the whole crop minus the interior as "ring".
        ring_mask = (~inner_mask)

    inner_pixels = roi[inner_mask]
    ring_pixels = roi[ring_mask]

    inner_mean = float(inner_pixels.mean())
    interior_std = float(inner_pixels.std())
    ring_mean = float(ring_pixels.mean())

    # The core signal: how much darker is the interior than its own local
    # surroundings, robust to page-wide or regional shadow.
    local_darkness_raw = ring_mean - inner_mean
    fill_ratio = float(np.clip(local_darkness_raw / cfg.full_mark_local_contrast, 0.0, 1.0))

    # Otsu on the ROI itself (secondary, page-local-but-not-ring-relative signal;
    # used by the confidence engine as an independent cross-check method).
    try:
        otsu_thresh, _ = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    except cv2.error:
        otsu_thresh = 180.0
    dark_pixel_ratio = float((inner_pixels < min(otsu_thresh, 200)).mean())

    # Adaptive threshold gives a third, differently-biased vote -- useful for
    # telling a solid fill apart from a check-mark/X/partial scribble, since
    # it reacts to local structure rather than a single ROI-wide split.
    try:
        adaptive = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY_INV, 21, 6)
        adaptive_dark_ratio = float((adaptive[inner_mask] > 0).mean())
    except cv2.error:
        adaptive_dark_ratio = dark_pixel_ratio

    edges = cv2.Canny(roi, 50, 150)
    edge_density = float((edges[inner_mask] > 0).mean())

    return BubbleScore(
        option=option,
        fill_ratio=round(fill_ratio, 4),
        mean_intensity=round(inner_mean, 2),
        dark_pixel_ratio=round(dark_pixel_ratio, 4),
        edge_density=round(edge_density, 4),
        ring_mean=round(ring_mean, 2),
        local_darkness=round(local_darkness_raw, 2),
        adaptive_dark_ratio=round(adaptive_dark_ratio, 4),
        interior_std=round(interior_std, 2),
    )
