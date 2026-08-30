"""
Page and registration-marker detection.

Strategy (per spec section 13/14, upgraded per the CV-robustness spec):
look for the four solid corner squares every ExamCorrector template carries
as fiducial markers. A SINGLE fixed dark threshold is fragile under
shadow/uneven lighting -- a marker under a shadow can fail to separate from
its now-also-darker background at one threshold while showing up cleanly at
another. So candidates are generated from several different binarizations
(a range of fixed thresholds, Otsu, and adaptive thresholding) and merged,
rather than committing to one threshold up front.

Once four marker points are chosen, their geometry is scored (convexity,
side-length ratios, diagonal ratio, marker-size consistency) instead of
just trusting "we found something in each quadrant" -- a homography that
computes successfully is not automatically a trustworthy registration
(spec section 4).

If corner markers cannot be found at all, a fallback "largest quadrilateral"
page-contour detector is used so the pipeline can still attempt perspective
correction instead of failing outright.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from app.core.config import RegistrationConfig


@dataclass
class MarkerCandidate:
    cx: float
    cy: float
    w: float
    h: float
    fill_ratio: float
    source: str = ""   # which binarization method produced this candidate (diagnostics)


@dataclass
class MarkerDetectionResult:
    ok: bool
    markers: dict                       # {"tl": (x,y), "tr": (x,y), "bl": (x,y), "br": (x,y)}
    method: str                         # "fiducial_markers" | "page_contour" | "none"
    reason: str = ""
    geometry_score: float = 0.0          # 0-100: how plausible the 4-marker quadrilateral is
    candidate_counts: dict = field(default_factory=dict)   # per-quadrant candidate counts (diagnostics)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------- candidates

def _binarizations(gray: np.ndarray, fixed_thresholds: list[int]) -> list[tuple[str, np.ndarray]]:
    """Several independent binary views of the same page. A marker sitting
    under a shadow may only cleanly separate from its background in one or
    two of these -- generating all of them (spec section 2, methods A-C) is
    what makes detection robust instead of betting on a single threshold."""
    variants = []
    for t in fixed_thresholds:
        _, th = cv2.threshold(gray, t, 255, cv2.THRESH_BINARY_INV)
        variants.append((f"fixed_{t}", th))

    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 10
    )
    variants.append(("adaptive", adaptive))
    return variants


def _candidates_from_binary(binary: np.ndarray, source: str, img_area: int, cfg: RegistrationConfig) -> list[MarkerCandidate]:
    # Opening (erode then dilate) first: shadows/uneven lighting can bridge a
    # marker to unrelated nearby dark structures via thin anti-aliased
    # connections, merging them into one huge low-fill-ratio contour that
    # then fails every shape filter below. A genuine solid ~40px marker
    # survives a small opening; a 1-2px bridge does not.
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    lo_frac, hi_frac = cfg.marker_area_frac_range
    ar_lo, ar_hi = cfg.marker_aspect_ratio_range
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if area == 0:
            continue
        area_frac = area / img_area
        if not (lo_frac <= area_frac <= hi_frac):
            continue
        aspect = bw / float(bh)
        if not (ar_lo <= aspect <= ar_hi):
            continue
        fill_ratio = cv2.contourArea(c) / area
        if fill_ratio < cfg.marker_fill_ratio_min:
            continue
        candidates.append(MarkerCandidate(cx=x + bw / 2, cy=y + bh / 2, w=bw, h=bh,
                                           fill_ratio=fill_ratio, source=source))
    return candidates


def _dedupe_candidates(candidates: list[MarkerCandidate], merge_dist: float) -> list[MarkerCandidate]:
    """The same physical marker typically gets rediscovered by several
    binarizations -- collapse near-duplicates, keeping the highest-fill_ratio
    instance (usually the cleanest separation) at each location."""
    kept: list[MarkerCandidate] = []
    for cand in sorted(candidates, key=lambda c: -c.fill_ratio):
        if any((cand.cx - k.cx) ** 2 + (cand.cy - k.cy) ** 2 < merge_dist ** 2 for k in kept):
            continue
        kept.append(cand)
    return kept


def _find_all_marker_candidates(gray: np.ndarray, cfg: RegistrationConfig) -> list[MarkerCandidate]:
    h, w = gray.shape[:2]
    img_area = h * w
    fixed_thresholds = [50, 70, 90, 110, 140, 170, 200]
    all_candidates: list[MarkerCandidate] = []
    for source, binary in _binarizations(gray, fixed_thresholds):
        all_candidates.extend(_candidates_from_binary(binary, source, img_area, cfg))
    # merge distance: a fraction of the expected marker size
    approx_marker_size = (min(w, h) ** 2 * sum(cfg.marker_area_frac_range) / 2) ** 0.5
    return _dedupe_candidates(all_candidates, merge_dist=max(6.0, approx_marker_size * 0.6))


def _assign_to_quadrants(candidates: list[MarkerCandidate], img_w: int, img_h: int) -> tuple[dict, dict]:
    cx_mid, cy_mid = img_w / 2, img_h / 2
    quadrants = {"tl": [], "tr": [], "bl": [], "br": []}
    for c in candidates:
        key = ("t" if c.cy < cy_mid else "b") + ("l" if c.cx < cx_mid else "r")
        quadrants[key].append(c)

    result = {}
    counts = {k: len(v) for k, v in quadrants.items()}
    for key, items in quadrants.items():
        if not items:
            continue
        corner_x = 0 if "l" in key else img_w
        corner_y = 0 if "t" in key else img_h
        items.sort(key=lambda c: (-c.fill_ratio, (c.cx - corner_x) ** 2 + (c.cy - corner_y) ** 2))
        best = items[0]
        result[key] = (best.cx, best.cy)
    return result, counts


# ------------------------------------------------------------- geometry score

def _score_geometry(markers: dict) -> tuple[float, list[str]]:
    """0-100 plausibility score for a 4-point marker configuration -- a
    homography can be computed from almost any 4 points, so this is what
    catches a degenerate/wrong marker set before anything downstream trusts
    it (spec section 3-4)."""
    warnings: list[str] = []
    required = ("tl", "tr", "bl", "br")
    if not all(k in markers for k in required):
        return 0.0, ["Fewer than 4 markers -- cannot score geometry."]

    tl, tr, bl, br = (np.array(markers[k], dtype=float) for k in required)

    # Convexity: going tl -> tr -> br -> bl should turn consistently one way.
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    turns = [
        cross(tl, tr, br), cross(tr, br, bl), cross(br, bl, tl), cross(bl, tl, tr),
    ]
    convex = all(t >= 0 for t in turns) or all(t <= 0 for t in turns)
    if not convex:
        warnings.append("Marker quadrilateral is not convex -- likely a bad match.")

    top_len = np.linalg.norm(tr - tl)
    bottom_len = np.linalg.norm(br - bl)
    left_len = np.linalg.norm(bl - tl)
    right_len = np.linalg.norm(br - tr)
    side_lengths = [top_len, bottom_len, left_len, right_len]
    if min(side_lengths) < 1e-3:
        return 0.0, ["Degenerate marker geometry (near-zero side length)."]

    horiz_ratio = max(top_len, bottom_len) / max(1e-6, min(top_len, bottom_len))
    vert_ratio = max(left_len, right_len) / max(1e-6, min(left_len, right_len))

    diag1 = np.linalg.norm(br - tl)
    diag2 = np.linalg.norm(bl - tr)
    diag_ratio = max(diag1, diag2) / max(1e-6, min(diag1, diag2))

    # Score components, each 0-1, then blended.
    convex_score = 1.0 if convex else 0.0
    horiz_score = float(np.clip(1.0 - (horiz_ratio - 1.0) / 0.6, 0.0, 1.0))
    vert_score = float(np.clip(1.0 - (vert_ratio - 1.0) / 0.6, 0.0, 1.0))
    diag_score = float(np.clip(1.0 - (diag_ratio - 1.0) / 0.5, 0.0, 1.0))

    if horiz_ratio > 1.6:
        warnings.append(f"Top/bottom marker-edge lengths differ a lot (ratio {horiz_ratio:.2f}).")
    if vert_ratio > 1.6:
        warnings.append(f"Left/right marker-edge lengths differ a lot (ratio {vert_ratio:.2f}).")
    if diag_ratio > 1.5:
        warnings.append(f"Marker diagonals differ a lot (ratio {diag_ratio:.2f}) -- possible mismatched marker.")

    score = 100.0 * (0.30 * convex_score + 0.20 * horiz_score + 0.20 * vert_score + 0.30 * diag_score)
    return round(score, 1), warnings


# ------------------------------------------------------------------- public

def detect_markers(gray: np.ndarray, cfg: RegistrationConfig = RegistrationConfig()) -> MarkerDetectionResult:
    h, w = gray.shape[:2]
    candidates = _find_all_marker_candidates(gray, cfg)
    quadrant_points, counts = _assign_to_quadrants(candidates, w, h)

    if len(quadrant_points) >= cfg.min_markers_required:
        geometry_score, geom_warnings = _score_geometry(quadrant_points)
        if geometry_score < cfg.min_geometry_score:
            # Don't just trust "found 4 dark squares" -- if their arrangement
            # isn't a plausible page rectangle, treat this like a failure and
            # let the page-contour fallback (or an honest failure) take over.
            fallback = _detect_page_contour(gray)
            if fallback is not None:
                fb_score, fb_warnings = _score_geometry(fallback)
                return MarkerDetectionResult(
                    ok=True, markers=fallback, method="page_contour",
                    geometry_score=fb_score, candidate_counts=counts,
                    warnings=[f"Fiducial markers found but geometry score too low ({geometry_score}); "
                              f"used page-contour fallback instead."] + fb_warnings,
                )
            return MarkerDetectionResult(
                ok=False, markers=quadrant_points, method="none",
                reason=f"Marker geometry implausible (score {geometry_score}/100).",
                geometry_score=geometry_score, candidate_counts=counts, warnings=geom_warnings,
            )
        return MarkerDetectionResult(
            ok=True, markers=quadrant_points, method="fiducial_markers",
            geometry_score=geometry_score, candidate_counts=counts, warnings=geom_warnings,
        )

    # Fallback: largest 4-point contour approximating the whole page.
    fallback = _detect_page_contour(gray)
    if fallback is not None:
        fb_score, fb_warnings = _score_geometry(fallback)
        return MarkerDetectionResult(
            ok=True, markers=fallback, method="page_contour",
            geometry_score=fb_score, candidate_counts=counts, warnings=fb_warnings,
        )

    return MarkerDetectionResult(
        ok=False,
        markers=quadrant_points,
        method="none",
        reason=f"Only found {len(quadrant_points)}/4 registration markers and no page contour.",
        candidate_counts=counts,
    )


def _detect_page_contour(gray: np.ndarray) -> Optional[dict]:
    h, w = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.25 * w * h:
            pts = approx.reshape(4, 2).astype(float)
            s = pts.sum(axis=1)
            d = np.diff(pts, axis=1).flatten()
            tl = tuple(pts[np.argmin(s)])
            br = tuple(pts[np.argmax(s)])
            tr = tuple(pts[np.argmin(d)])
            bl = tuple(pts[np.argmax(d)])
            return {"tl": tl, "tr": tr, "bl": bl, "br": br}
    return None
