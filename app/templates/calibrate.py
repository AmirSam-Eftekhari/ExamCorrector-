"""
Template calibration: given a clean example answer sheet image, attempt to
auto-detect page/markers, the answer-block grid, the student-ID grid, and
text fields (Name/Class/Date/...), producing a Template.

This mirrors what the "+ New Template" UI workflow will drive (spec 11) --
the algorithm here is the same one that would back the visual template
editor's auto-fill step. It is deliberately generic (geometry + gap
analysis), not hard-coded to any one sheet layout.

Anything this function isn't confident about is marked with
`needs_confirmation=True` / flagged in the returned CalibrationReport rather
than silently guessed -- a human is expected to review it in the template
editor before it's used for real grading.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract

from app.core.config import AppConfig, DEFAULT_CONFIG
from app.cv.page_detect import detect_markers
from app.cv.registration import register
from app.cv.bubble_grid import detect_circles, cluster_rows, cluster_1d, split_row_into_blocks
from app.templates.schema import Template, AnswerBlock, StudentIdRegion, TextField, RegistrationSpec


@dataclass
class CalibrationReport:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    registration_method: str = ""
    reprojection_error_px: float = 0.0
    blocks_found: int = 0
    questions_found: int = 0
    student_id_detected: bool = False
    text_fields_found: int = 0


def _clean_label(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^[^A-Za-z]+", "", raw)          # drop stray OCR junk before first letter
    raw = re.sub(r"[^A-Za-z0-9 /]+$", "", raw)      # drop trailing junk
    raw = raw.strip().rstrip(":.").strip()
    return raw or "field"


def calibrate_template_from_image(
    image_bgr: np.ndarray,
    name: str,
    cfg: AppConfig = DEFAULT_CONFIG,
) -> tuple[Template | None, CalibrationReport]:
    report = CalibrationReport(ok=False)
    gray_full = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    marker_result = detect_markers(gray_full, cfg.registration)
    reg_result = register(image_bgr, marker_result, cfg.normalized_canvas_size, cfg=cfg.registration)
    report.registration_method = reg_result.method
    report.reprojection_error_px = reg_result.reprojection_error_px

    if not reg_result.ok:
        report.warnings.append(f"Registration failed: {reg_result.reason}")
        return None, report

    warped = reg_result.warped
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    cw, ch = cfg.normalized_canvas_size

    # ---- 1. Detect the main answer-bubble grid ----
    r = cfg.bubble.expected_radius_px(cw)
    circles = detect_circles(
        gray,
        min_radius=int(r * (1 - cfg.bubble.radius_tolerance)),
        max_radius=int(r * (1 + cfg.bubble.radius_tolerance)),
        min_dist=int(r * cfg.bubble.hough_min_dist_factor),
        param1=cfg.bubble.hough_param1,
        param2=cfg.bubble.hough_param2,
    )
    rows = cluster_rows(circles, y_tol=r * 0.6)
    if not rows:
        report.warnings.append("No bubble grid detected at all.")
        return None, report

    # A "grid row" is one whose total bubble count is close to the modal count
    # across all rows -- tolerant to an occasional stray/missed detection,
    # unlike requiring an exact per-block signature match.
    from collections import Counter
    counts = [len(row) for row in rows]
    modal_count, _ = Counter(counts).most_common(1)[0]
    grid_row_idx = [i for i, n in enumerate(counts) if abs(n - modal_count) <= max(2, round(modal_count * 0.15))]
    grid_rows = [rows[i] for i in grid_row_idx]
    if len(grid_rows) < 3:
        report.warnings.append("Could not find enough consistent grid rows.")
        return None, report

    # Column positions are stable across rows, so cluster ALL x-values from all
    # grid rows together -- real columns get one cluster per row (~len(grid_rows)
    # members), stray/spurious circles form tiny clusters we can discard.
    all_x = np.concatenate([row[:, 0] for row in grid_rows])
    x_clusters = cluster_1d(all_x.tolist(), tol=r * 0.7)
    min_support = max(2, round(0.7 * len(grid_rows)))
    real_cols = sorted(
        float(np.mean([all_x[i] for i in idxs])) for idxs in x_clusters if len(idxs) >= min_support
    )
    if len(real_cols) < 2:
        report.warnings.append("Could not resolve stable column positions for the answer grid.")
        return None, report

    # Split the resolved columns into blocks by gap, same idea as split_row_into_blocks.
    diffs = np.diff(real_cols)
    median_gap = float(np.median(diffs))
    split_at = [i for i, d in enumerate(diffs) if d > 2.5 * median_gap]
    col_blocks: list[list[float]] = []
    start = 0
    for s in split_at:
        col_blocks.append(real_cols[start:s + 1])
        start = s + 1
    col_blocks.append(real_cols[start:])

    option_counts = [len(b) for b in col_blocks]
    option_count, _ = Counter(option_counts).most_common(1)[0]
    if any(n != option_count for n in option_counts):
        report.warnings.append(
            f"Detected blocks with uneven option counts {option_counts}; "
            f"using the modal option count ({option_count}) -- review in the template editor."
        )
    option_labels = [chr(ord("A") + i) for i in range(option_count)]

    row_ys = sorted(float(row[:, 1].mean()) for row in grid_rows)
    row_pitch = float(np.mean(np.diff(row_ys))) if len(row_ys) > 1 else 0.0

    # Use the ACTUAL measured radius of the detected circles (Hough returns
    # one per circle in column 2), not the fixed expected-radius constant --
    # that constant is only a search-window center, and reusing it verbatim
    # as the final calibrated value silently mis-sizes the ring/interior
    # sampling geometry for any sheet whose bubbles differ from the original
    # tuning sheet's proportions (found via a real Persian-template test:
    # expected 0.009 frac gave 23.8px on a sheet whose true bubbles measured
    # ~13.5px, corrupting the ring-relative darkness signal for every bubble).
    measured_radii = np.concatenate([row[:, 2] for row in grid_rows])
    measured_r = float(np.median(measured_radii))

    answer_blocks: list[AnswerBlock] = []
    q_counter = 1
    for order_idx, block_cols in enumerate(col_blocks):
        col_pitch = float(np.mean(np.diff(block_cols))) if len(block_cols) > 1 else 0.0
        q_start = q_counter
        q_end = q_counter + len(row_ys) - 1
        q_counter = q_end + 1
        answer_blocks.append(AnswerBlock(
            block_id=f"block_{order_idx + 1}",
            question_start=q_start,
            question_end=q_end,
            option_labels=option_labels[:len(block_cols)] if len(block_cols) != option_count else option_labels,
            row_start_y=row_ys[0] / ch,
            row_pitch_y=row_pitch / ch if row_pitch else 0.0,
            col_start_x=block_cols[0] / cw,
            col_pitch_x=col_pitch / cw if col_pitch else 0.0,
            bubble_radius=measured_r / cw,
        ))

    report.blocks_found = len(answer_blocks)
    report.questions_found = q_counter - 1
    if len(row_ys) < 2:
        report.warnings.append("Fewer than 2 consistent rows found; geometry may be unreliable.")

    top_of_grid = row_ys[0]

    # ---- 2. Detect text fields (Name/Class/Date/...) above the answer grid.
    # These give a reliable "bottom of the info panel" marker (their own
    # underlines), which we then use to bound the ID-grid search below --
    # much tighter than searching the whole header, which is full of title
    # text that a generic circle detector can false-positive on.
    text_fields = _calibrate_text_fields(gray, cw, ch, search_bottom_px=top_of_grid)
    report.text_fields_found = len(text_fields)
    if text_fields:
        fields_bottom_px = max(f.line_box[3] for f in text_fields) * ch
        id_search_top = fields_bottom_px + 0.01 * ch
    else:
        report.warnings.append("No text fields (Name/Class/Date/...) auto-detected; add them manually if present.")
        id_search_top = 0.0

    # ---- 3. Detect the student-ID grid (smaller bubbles), searched only
    # between the text fields and the answer grid. ----
    student_id = _calibrate_student_id(gray, cw, ch, id_search_top, top_of_grid, r, cfg)
    report.student_id_detected = student_id.present
    if student_id.present and student_id.needs_confirmation:
        report.warnings.append(
            "Student-ID grid geometry was auto-estimated and may not exactly match the "
            "physical bubble layout -- confirm/adjust it in the template editor before grading."
        )

    template = Template(
        name=name,
        description="Auto-calibrated from a clean sample sheet. Review before production use.",
        canvas_size=cfg.normalized_canvas_size,
        registration=RegistrationSpec(strategy=reg_result.method, marker_margin_frac=0.03),
        blocks=answer_blocks,
        student_id=student_id,
        text_fields=text_fields,
    )
    report.ok = True
    return template, report


def _calibrate_student_id(gray, cw, ch, search_top_px, search_bottom_px, big_r, cfg) -> StudentIdRegion:
    search_top_px, search_bottom_px = int(max(0, search_top_px)), int(search_bottom_px)
    search = gray[search_top_px:search_bottom_px, :]
    small_r = max(3, int(big_r * 0.55))
    circles = detect_circles(
        search,
        min_radius=max(3, int(small_r * 0.6)),
        max_radius=int(small_r * 1.4),
        min_dist=int(small_r * 1.6),
        param1=60, param2=13,
    )
    if len(circles) < 20:
        return StudentIdRegion(present=False)
    circles = circles.copy()
    circles[:, 1] += search_top_px  # back to full-canvas y coordinates

    all_rows = cluster_rows(circles, y_tol=small_r * 1.2)
    if not all_rows:
        return StudentIdRegion(present=False)
    # A real ID sub-row lights up many bubbles at once (one per digit column).
    # Isolated text glyphs (titles, captions, box borders) look circular to
    # Hough too, but never in that quantity -- keep only rows close to the
    # densest ones found, instead of a fixed absolute count.
    max_count = max(len(row) for row in all_rows)
    rows = [row for row in all_rows if len(row) >= max(10, 0.5 * max_count)]
    if not rows:
        return StudentIdRegion(present=False)

    all_x = np.concatenate([row[:, 0] for row in rows])
    all_y = np.concatenate([row[:, 1] for row in rows])
    x0, x1 = float(all_x.min() - small_r * 2), float(all_x.max() + small_r * 2)
    y0, y1 = float(all_y.min() - small_r * 2), float(all_y.max() + small_r * 2)

    # Same fix as the main answer grid: use the actually-measured circle
    # radius from Hough's own output, not the fixed search-window estimate.
    measured_radii = np.concatenate([row[:, 2] for row in rows])
    measured_small_r = float(np.median(measured_radii))

    row_ys = sorted(float(row[:, 1].mean()) for row in rows)
    row_pitch = float(np.mean(np.diff(row_ys))) if len(row_ys) > 1 else small_r * 3.0

    # Estimate the number of digit *columns* the same way the answer grid does:
    # cluster x-values across all sub-rows and keep clusters with broad support,
    # rather than trusting a single row's gap-split (which is noise-sensitive).
    from collections import Counter as _Counter
    x_clusters = cluster_1d(all_x.tolist(), tol=small_r * 1.3)
    min_support = max(2, round(0.6 * len(rows)))
    col_centers = sorted(
        float(np.mean([all_x[i] for i in idxs])) for idxs in x_clusters if len(idxs) >= min_support
    )
    if len(col_centers) < 2:
        # Fall back to a single row's gap split if global clustering was too strict.
        col_blocks = split_row_into_blocks(rows[0], gap_factor=1.8)
        col_centers = [float(b[:, 0].mean()) for b in col_blocks]
    n_digits = max(1, len(col_centers))
    col_pitch = float(np.mean(np.diff(col_centers))) if len(col_centers) > 1 else 0.0
    bubbles_per_row = max(1, round(len(rows[0]) / max(1, n_digits)))

    # The dense ID grid (small, sometimes touching bubbles, mixed with printed
    # digit labels) is the hardest region to auto-parse precisely. We trust the
    # *bounding box* (it comes from many detections and is robust) but if the
    # fine-grained column/row count looks implausible for a real ID grid, fall
    # back to a conventional 8-digit / 2-sub-row layout scaled to that box
    # rather than emitting a nonsensical value -- either way this region is
    # marked needs_confirmation and must be checked in the template editor.
    plausible = 2 <= n_digits <= 12 and 1 <= len(row_ys) <= 3 and 2 <= bubbles_per_row <= 10
    if not plausible:
        n_digits = 8
        col_pitch = (x1 - x0 - small_r * 4) / n_digits
        col_start = x0 + small_r * 2
        bubbles_per_row = 5
        row_start = y0 + small_r * 2
        row_pitch = (y1 - y0 - small_r * 4) / 2
        return StudentIdRegion(
            present=True,
            n_digits=n_digits,
            digits_per_column=10,
            rows_per_column=2,
            box=(x0 / cw, y0 / ch, x1 / cw, y1 / ch),
            col_start_x=col_start / cw,
            col_pitch_x=col_pitch / cw,
            row_start_y=row_start / ch,
            row_pitch_y=row_pitch / ch,
            bubbles_per_row=bubbles_per_row,
            bubble_radius=measured_small_r / cw,
            needs_confirmation=True,
        )

    return StudentIdRegion(
        present=True,
        n_digits=n_digits,
        digits_per_column=10,
        rows_per_column=len(row_ys),
        box=(x0 / cw, y0 / ch, x1 / cw, y1 / ch),
        col_start_x=col_centers[0] / cw if col_centers else 0.0,
        col_pitch_x=col_pitch / cw,
        row_start_y=row_ys[0] / ch,
        row_pitch_y=row_pitch / ch,
        bubbles_per_row=bubbles_per_row,
        bubble_radius=measured_small_r / cw,
        needs_confirmation=True,
    )


def _calibrate_text_fields(gray, cw, ch, search_bottom_px: float) -> list[TextField]:
    top = gray[0:int(search_bottom_px), :]
    _, th = cv2.threshold(top, 150, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(cw * 0.03), 1))
    lines = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Ignore anything in the bottom slice of the searched band: real
    # Name/Class/Date-style fields sit well above the answer grid, so lines
    # hugging the grid's top edge are almost always block-header rules
    # ("QUESTIONS 1-25" underlines etc.), not info-panel fields.
    y_cutoff = 0.88 * search_bottom_px

    fields = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if h > 8 or w < cw * 0.05 or w > cw * 0.55 or y > y_cutoff:
            continue  # too tall (a box border), wrong length, or too close to the grid
        label_x0 = max(0, x - int(cw * 0.09))
        label_crop = gray[max(0, y - 24):y + 6, label_x0:x]
        try:
            raw_label = pytesseract.image_to_string(label_crop, config="--psm 7").strip()
        except Exception:
            raw_label = ""
        label = _clean_label(raw_label) if raw_label else f"field_{len(fields) + 1}"
        # The OCR crop needs real room on every side, not just found from the
        # detected line's own bounding box verbatim:
        # - vertical: a 34px-tall band (the original 30px-above/4px-below
        #   margins) clips through the middle of handwritten or even typed
        #   characters, since ascenders/full letter height commonly need
        #   40-60px+ to OCR reliably at this canvas resolution.
        # - horizontal: using the line's exact x-span with no margin clips
        #   the first character whenever real writing starts even slightly
        #   before the printed line (very common). Empirically tuned via a
        #   direct sweep against a real "John Smith" OCR test: 0px margin
        #   read "wn smith", 30px still clipped to "ohn Smith", 60px read
        #   perfectly, and anything past ~75px started pulling in the
        #   printed field label itself ("Name:") and corrupting the read --
        #   3% of canvas width (60px at this canvas size) is the sweet spot.
        # - the bottom edge is pulled back above the line's own stroke
        #   (rather than a fixed +8px past its top) so the ruled line itself
        #   isn't included in what gets OCR'd, which was visibly confusing
        #   tesseract's line segmentation.
        x_margin_left = int(cw * 0.03)
        x_margin_right = int(cw * 0.015)
        value_box = (
            max(0, x - x_margin_left) / cw,
            max(0, y - 55) / ch,
            min(cw, x + w + x_margin_right) / cw,
            max(0, y - 2) / ch,
        )
        line_box = (x / cw, y / ch, (x + w) / cw, (y + h) / ch)
        fields.append(TextField(name=label, box=value_box, line_box=line_box))
    return fields
