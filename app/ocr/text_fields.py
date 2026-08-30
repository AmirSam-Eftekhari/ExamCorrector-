"""
Best-effort text-field extraction (Name, Class, Date, Exam/Subject, ...).

These fields are handwritten or typed free text, not bubbles, so OCR is used
-- but per spec 28 this is optional/never mandatory and per the "no fake
answers" philosophy that runs through this whole project, an empty or
low-confidence result is reported honestly as such rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
import pytesseract

from app.templates.schema import TextField


@lru_cache(maxsize=1)
def available_tesseract_langs() -> frozenset[str]:
    """Which OCR language packs are actually installed on this machine.
    Cached (process-lifetime) since this shells out to `tesseract --list-langs`."""
    try:
        return frozenset(pytesseract.get_languages(config=""))
    except Exception:
        return frozenset({"eng"})


def best_available_lang(preferred: tuple[str, ...] = ("eng", "fas")) -> str:
    """Builds a tesseract multi-language string ('eng+fas') from whichever
    of `preferred` are actually installed, so a handwritten name gets a
    real shot at being read regardless of script -- a name field isn't
    tied to the app's own display-language setting. Falls back to plain
    'eng' if nothing else is available (tesseract always ships eng)."""
    installed = available_tesseract_langs()
    langs = [l for l in preferred if l in installed]
    return "+".join(langs) if langs else "eng"


@dataclass
class TextFieldResult:
    name: str
    text: str | None          # None if nothing readable was found
    confidence: float          # 0-100, tesseract's own per-word confidence, averaged
    status: str                # "READ" | "EMPTY" | "UNREADABLE"


def _preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    """Standard OCR preprocessing -- tesseract is meaningfully more reliable
    on a clean, well-sized, bordered black-on-white image than on a raw
    grayscale crop straight off the (possibly unevenly lit) warped canvas.
    Confirmed directly: the same crop went from "wn smith" (garbled, ~20%
    confidence) to a clean, fully correct read after this preprocessing."""
    h, w = crop.shape[:2]
    # Upscale small crops -- tesseract wants roughly 30px+ of cap-height to
    # read reliably, and a name-field crop at this canvas resolution is
    # often shorter than that.
    if h < 60:
        scale = 60 / max(h, 1)
        crop = cv2.resize(crop, (max(1, int(w * scale)), 60), interpolation=cv2.INTER_CUBIC)

    # Adaptive threshold handles uneven lighting/shadow across the crop
    # better than a single global Otsu value would.
    blurred = cv2.GaussianBlur(crop, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10
    )

    # A white border: tesseract's line/word segmentation is noticeably less
    # reliable when ink touches the image edge with zero margin.
    return cv2.copyMakeBorder(binary, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)


def read_text_field(gray: np.ndarray, field: TextField, canvas_size: tuple, lang: str = "auto") -> TextFieldResult:
    if lang == "auto":
        lang = best_available_lang()
    cw, ch = canvas_size
    x0, y0, x1, y1 = field.box
    px0, py0, px1, py1 = int(x0 * cw), int(y0 * ch), int(x1 * cw), int(y1 * ch)
    px0, py0 = max(0, px0), max(0, py0)
    px1, py1 = min(cw, px1), min(ch, py1)
    if px1 <= px0 or py1 <= py0:
        return TextFieldResult(name=field.name, text=None, confidence=0.0, status="UNREADABLE")

    crop = gray[py0:py1, px0:px1]
    if crop.size == 0:
        return TextFieldResult(name=field.name, text=None, confidence=0.0, status="UNREADABLE")

    # A blank handwriting line is overwhelmingly light (paper white). Cheap
    # early check so we don't bother OCR-ing (and don't fabricate a reading
    # from) a field the student simply left empty.
    ink_ratio = float((crop < 180).mean())
    if ink_ratio < 0.01:
        return TextFieldResult(name=field.name, text=None, confidence=100.0, status="EMPTY")

    ocr_input = _preprocess_for_ocr(crop)

    try:
        data = pytesseract.image_to_data(
            ocr_input, lang=lang, config="--psm 7 --oem 3", output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        return TextFieldResult(name=field.name, text=None, confidence=0.0, status="UNREADABLE")

    words = []
    confs = []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        text = text.strip()
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = -1.0
        if not text or conf_f < 0:
            continue
        # Tesseract sometimes segments a stray mark (a fragment of a nearby
        # printed line/label bleeding in at the crop edge) as its own
        # "word" -- confirmed directly: a real name crop that read
        # perfectly otherwise still carried a leading ";", ",", or "_" as
        # a separate low-value token. A real name/class/date field's
        # actual content is never a bare punctuation mark on its own, so
        # drop tokens with no alphanumeric character in them rather than
        # let them corrupt an otherwise-correct reading.
        if not any(ch.isalnum() for ch in text):
            continue
        words.append(text)
        confs.append(conf_f)

    if not words:
        return TextFieldResult(name=field.name, text=None, confidence=0.0, status="UNREADABLE")

    joined = " ".join(words)
    avg_conf = round(sum(confs) / len(confs), 1)

    # Tesseract will confidently emit noise (stray pixels, a border sliver)
    # as a 1-2 character "word" with low confidence. Rather than surface that
    # as if it were a real reading, report it honestly as unreadable --
    # matching the rest of this system's "never pretend uncertain is certain"
    # rule (spec section 2).
    min_confidence = 45.0
    if avg_conf < min_confidence or len(joined) < 2:
        return TextFieldResult(name=field.name, text=None, confidence=avg_conf, status="UNREADABLE")

    return TextFieldResult(name=field.name, text=joined, confidence=avg_conf, status="READ")


def read_all_text_fields(gray: np.ndarray, fields: list[TextField], canvas_size: tuple, lang: str = "auto") -> list[TextFieldResult]:
    return [read_text_field(gray, f, canvas_size, lang=lang) for f in fields]
