"""
Central configuration for ExamCorrector.

Nothing algorithmic should hard-code a magic number that belongs here.
All thresholds are grouped so they can later be exposed in a Settings UI
and/or overridden per-template without touching code.
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Where the app's own bundled files live: the source tree when running from
# source, or PyInstaller's extracted temp folder when running as a compiled
# .exe (sys._MEIPASS). That temp folder is wiped after the process exits, so
# it must never be where we WRITE user data (new templates, the database) --
# only where we read shipped defaults from.
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))

# Where user-writable data persists across runs: next to the .exe itself
# when frozen (so it survives between launches), or the project root when
# running from source.
if getattr(sys, "frozen", False):
    USER_DATA_ROOT = Path(sys.executable).resolve().parent
else:
    USER_DATA_ROOT = BUNDLE_ROOT

PROJECT_ROOT = BUNDLE_ROOT  # kept for backwards compatibility with existing imports
DATA_DIR = USER_DATA_ROOT / "data"
TEMPLATES_DIR = USER_DATA_ROOT / "resources" / "templates"
DB_PATH = DATA_DIR / "examcorrector.sqlite3"


def ensure_user_data_seeded() -> None:
    """Copy any bundled default templates into the user-writable templates
    folder the first time the app runs from a given install location, so a
    freshly-unzipped/compiled copy ships with a working default template
    without ever writing into the (ephemeral, when frozen) bundle folder."""
    bundled = BUNDLE_ROOT / "resources" / "templates"
    if not bundled.exists() or bundled == TEMPLATES_DIR:
        return
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    for src in bundled.glob("*.json"):
        dst = TEMPLATES_DIR / src.name
        if not dst.exists():
            shutil.copy2(src, dst)


@dataclass
class RegistrationConfig:
    """Parameters for detecting fiducial markers and computing homography."""
    marker_fill_ratio_min: float = 0.80          # contour_area / bbox_area
    marker_aspect_ratio_range: tuple = (0.6, 1.5)
    marker_area_frac_range: tuple = (0.0003, 0.02)   # fraction of full image area
    dark_threshold: int = 70                      # 0-255, inverse binary threshold (legacy single-threshold fallback)
    max_reprojection_error_px: float = 6.0        # reject homography above this
    min_markers_required: int = 4
    min_geometry_score: float = 45.0               # below this, a 4-marker set is treated as untrustworthy
    min_trusted_confidence: float = 60.0            # below this, a technically-ok registration still gets flagged for review


@dataclass
class QualityConfig:
    min_acceptable_overall: float = 0.35   # below this -> flagged, never auto-rejected
    blur_laplacian_low: float = 60.0        # below -> very blurry
    blur_laplacian_high: float = 600.0      # at/above -> very sharp
    min_short_side_px: int = 900            # informs "resolution" sub-score


@dataclass
class BubbleConfig:
    # Radius is expressed as a fraction of canvas width so it scales with
    # `normalized_canvas_size` instead of being tied to one specific canvas.
    expected_radius_frac: float = 0.009     # ~18px on a 2000px-wide canvas
    radius_tolerance: float = 0.33
    hough_min_dist_factor: float = 1.5      # * expected_radius_px
    hough_param1: int = 80
    hough_param2: int = 18

    # Ring/annulus geometry for local-background-relative darkness (spec
    # sections 7-9): the ring samples the paper immediately around a bubble
    # so a mark is judged against ITS OWN local lighting, not a fixed
    # page-wide paper/ink constant -- this is what keeps a shadow from
    # making an empty bubble look partially filled.
    inner_radius_factor: float = 0.68        # interior circle, 60-75% of r
    ring_inner_factor: float = 1.03          # ring starts just past the printed edge
    ring_outer_factor: float = 1.22          # kept tight so dense grids (Student ID) don't bleed into neighbors
    full_mark_local_contrast: float = 115.0  # ring_mean - inner_mean expected for a fully-inked mark

    def expected_radius_px(self, canvas_width: int) -> int:
        return max(3, round(self.expected_radius_frac * canvas_width))


@dataclass
class ConfidenceConfig:
    """Tunable weights/cutoffs for the confidence engine. See omr/analysis.py."""
    min_margin_for_high_confidence: float = 0.35   # winner - runner-up (0-1 darkness scale)
    min_fill_for_mark: float = 0.22                # below this a bubble is "not marked" at all
    ambiguous_margin: float = 0.12                 # margin below this -> LOW_CONFIDENCE
    multi_mark_min_fill: float = 0.22              # a 2nd/3rd bubble above this fill counts as marked
    multi_mark_margin_ceiling: float = 0.15        # if top-2 fills are this close -> MULTIPLE_MARK
    low_separability_std: float = 0.06             # if all options' fills have low std -> low confidence
    high_confidence_floor: float = 0.90             # displayed confidence for a clean single mark
    low_confidence_ceiling: float = 0.60
    erasure_interior_std_threshold: float = 42.0    # interior_std above this, under the mark floor -> possible erasure


@dataclass
class GradingDefaults:
    correct_score: float = 1.0
    wrong_score: float = 0.0
    blank_score: float = 0.0
    multiple_mark_score: float = 0.0
    multiple_mark_policy: str = "wrong"   # "wrong" | "invalid" | "manual_review"


@dataclass
class AppConfig:
    registration: RegistrationConfig = field(default_factory=RegistrationConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    bubble: BubbleConfig = field(default_factory=BubbleConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    grading_defaults: GradingDefaults = field(default_factory=GradingDefaults)
    language: str = "fa"          # "en" | "fa" | "ar"
    theme: str = "system"         # "light" | "dark" | "gray" | "system"
    normalized_canvas_size: tuple = (2000, 2828)   # (width, height) px, ~A4 ratio


DEFAULT_CONFIG = AppConfig()
