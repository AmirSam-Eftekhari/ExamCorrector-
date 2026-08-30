"""
Registration: maps a photographed/scanned sheet into the template's
normalized coordinate space via homography, and validates the result
before anything downstream trusts it (spec section 12/13).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core.config import RegistrationConfig
from app.cv.page_detect import MarkerDetectionResult


@dataclass
class RegistrationResult:
    ok: bool
    homography: np.ndarray | None
    warped: np.ndarray | None
    canvas_size: tuple
    reprojection_error_px: float
    method: str
    reason: str = ""
    # Structured confidence report (spec section 4) -- a homography that
    # merely *computed* is not the same as a trustworthy registration, so
    # this is never just "ok=True" with nothing behind it.
    confidence: float = 0.0
    marker_geometry_score: float = 0.0
    warnings: list = field(default_factory=list)


def _order(markers: dict) -> np.ndarray:
    return np.array([markers["tl"], markers["tr"], markers["br"], markers["bl"]], dtype=np.float32)


def _registration_confidence(geometry_score: float, reproj_err: float, max_err: float, method: str) -> float:
    geom_component = geometry_score  # already 0-100
    err_component = 100.0 * max(0.0, 1.0 - (reproj_err / max(1e-6, max_err)))
    method_component = 100.0 if method == "fiducial_markers" else 55.0
    return round(0.45 * geom_component + 0.35 * err_component + 0.20 * method_component, 1)


def register(
    image_bgr: np.ndarray,
    marker_result: MarkerDetectionResult,
    canvas_size: tuple[int, int],
    marker_margin_frac: float = 0.03,
    cfg: RegistrationConfig = RegistrationConfig(),
) -> RegistrationResult:
    if not marker_result.ok or len(marker_result.markers) < 4:
        return RegistrationResult(
            ok=False, homography=None, warped=None, canvas_size=canvas_size,
            reprojection_error_px=float("inf"), method=marker_result.method,
            reason=marker_result.reason or "Insufficient registration markers.",
            marker_geometry_score=marker_result.geometry_score,
            warnings=list(marker_result.warnings),
        )

    src = _order(marker_result.markers)
    cw, ch = canvas_size
    mx, my = cw * marker_margin_frac, ch * marker_margin_frac
    dst = np.array([[mx, my], [cw - mx, my], [cw - mx, ch - my], [mx, ch - my]], dtype=np.float32)

    H, _ = cv2.findHomography(src, dst, method=0)
    if H is None:
        return RegistrationResult(
            ok=False, homography=None, warped=None, canvas_size=canvas_size,
            reprojection_error_px=float("inf"), method=marker_result.method,
            reason="Homography computation failed (degenerate marker layout).",
            marker_geometry_score=marker_result.geometry_score,
            warnings=list(marker_result.warnings),
        )

    # Validate: reproject src points through H and measure error against dst.
    src_h = np.hstack([src, np.ones((4, 1))])
    proj = (H @ src_h.T).T
    proj = proj[:, :2] / proj[:, 2:3]
    err = float(np.sqrt(((proj - dst) ** 2).sum(axis=1)).mean())
    confidence = _registration_confidence(marker_result.geometry_score, err, cfg.max_reprojection_error_px, marker_result.method)

    if err > cfg.max_reprojection_error_px and marker_result.method == "fiducial_markers":
        return RegistrationResult(
            ok=False, homography=H, warped=None, canvas_size=canvas_size,
            reprojection_error_px=err, method=marker_result.method,
            reason=f"Homography reprojection error {err:.1f}px exceeds limit "
                   f"({cfg.max_reprojection_error_px}px) -- rejecting registration.",
            confidence=confidence, marker_geometry_score=marker_result.geometry_score,
            warnings=list(marker_result.warnings),
        )

    warped = cv2.warpPerspective(image_bgr, H, (cw, ch))
    return RegistrationResult(
        ok=True, homography=H, warped=warped, canvas_size=canvas_size,
        reprojection_error_px=err, method=marker_result.method,
        confidence=confidence, marker_geometry_score=marker_result.geometry_score,
        warnings=list(marker_result.warnings),
    )


def to_template_coords(H: np.ndarray, point_xy: tuple) -> tuple:
    """Map an original-image point into normalized template space."""
    p = np.array([point_xy[0], point_xy[1], 1.0])
    q = H @ p
    return (float(q[0] / q[2]), float(q[1] / q[2]))


def to_image_coords(H: np.ndarray, point_xy: tuple) -> tuple:
    """Map a normalized template-space point back into the original image
    (used so diagnostics/review can show the exact crop the decision came from)."""
    Hinv = np.linalg.inv(H)
    return to_template_coords(Hinv, point_xy)
