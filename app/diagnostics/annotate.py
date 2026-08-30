"""
Renders the confidence-engine's decisions back onto the registered page
image as a color-coded overlay -- this is what makes a result "explainable"
at a glance instead of just a table of letters (spec section 46).

Color key:
    green   -- HIGH_CONFIDENCE marked bubble
    amber   -- LOW_CONFIDENCE / AMBIGUOUS marked bubble
    red     -- every bubble involved in a MULTIPLE_MARK call
    gray    -- BLANK (a small dot at the question number, nothing on the bubbles)
"""
from __future__ import annotations

import cv2
import numpy as np

from app.core.models import AnswerResult, AnswerStatus
from app.templates.schema import Template

COLORS = {
    AnswerStatus.HIGH_CONFIDENCE: (46, 163, 63),      # green (BGR)
    AnswerStatus.LOW_CONFIDENCE: (13, 158, 235),       # amber
    AnswerStatus.AMBIGUOUS: (13, 158, 235),
    AnswerStatus.MULTIPLE_MARK: (39, 39, 214),          # red
    AnswerStatus.UNREADABLE: (128, 128, 128),
    AnswerStatus.BLANK: (170, 170, 170),
}


def annotate_result_image(
    warped_bgr: np.ndarray,
    template: Template,
    answers: list[AnswerResult],
) -> np.ndarray:
    out = warped_bgr.copy()
    cw, ch = template.canvas_size
    by_q = {a.question_number: a for a in answers}

    for block in template.blocks:
        for q in range(block.question_start, block.question_end + 1):
            a = by_q.get(q)
            if a is None:
                continue
            color = COLORS.get(a.status, (170, 170, 170))
            radius_px = int(block.bubble_radius * cw)

            if a.status == AnswerStatus.MULTIPLE_MARK:
                # highlight every option that contributed to the multi-mark call
                candidates = (a.explanation or {}).get("candidates", [])
                marked_options = {c["option"] for c in candidates if c["fill_ratio"] >= 0.22}
                for opt_idx, opt_label in enumerate(block.option_labels):
                    if opt_label in marked_options:
                        cx, cy = block.bubble_center(q, opt_idx, template.canvas_size)
                        cv2.circle(out, (int(cx), int(cy)), int(radius_px * 1.35), color, 3, cv2.LINE_AA)
            elif a.status != AnswerStatus.BLANK and a.detected_answer:
                opt_idx = block.option_labels.index(a.detected_answer) if a.detected_answer in block.option_labels else None
                if opt_idx is not None:
                    cx, cy = block.bubble_center(q, opt_idx, template.canvas_size)
                    cv2.circle(out, (int(cx), int(cy)), int(radius_px * 1.35), color, 3, cv2.LINE_AA)

            # small status dot beside the question number, for every question
            # (including BLANK) so scanning the page tells the whole story
            label_x = (block.col_start_x - block.bubble_radius * 3.6) * cw
            label_y = block.row_start_y * ch + (q - block.question_start) * block.row_pitch_y * ch
            cv2.circle(out, (int(label_x), int(label_y)), max(3, int(radius_px * 0.35)), color, -1, cv2.LINE_AA)

    return out


def encode_png_base64(img_bgr: np.ndarray, max_width: int | None = 1400) -> str:
    import base64
    if max_width and img_bgr.shape[1] > max_width:
        scale = max_width / img_bgr.shape[1]
        img_bgr = cv2.resize(img_bgr, (max_width, int(img_bgr.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise ValueError("Could not encode image")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def crop_question_base64(warped_bgr: np.ndarray, template: Template, question_number: int, pad_factor: float = 3.0) -> str:
    block = template.block_for_question(question_number)
    if block is None:
        return ""
    cw, ch = template.canvas_size
    radius_px = block.bubble_radius * cw
    row_idx = question_number - block.question_start
    y = (block.row_start_y + row_idx * block.row_pitch_y) * ch
    x0 = (block.col_start_x - pad_factor * block.bubble_radius) * cw
    x1 = (block.col_start_x + (len(block.option_labels) - 1) * block.col_pitch_x + pad_factor * block.bubble_radius) * cw
    y0, y1 = y - radius_px * pad_factor, y + radius_px * pad_factor

    h, w = warped_bgr.shape[:2]
    x0, x1 = max(0, int(x0)), min(w, int(x1))
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    if x1 <= x0 or y1 <= y0:
        return ""
    crop = warped_bgr[y0:y1, x0:x1]
    return encode_png_base64(crop, max_width=600)
