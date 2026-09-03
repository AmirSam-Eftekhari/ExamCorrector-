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

import os
import shutil

import cv2
import numpy as np
import pytesseract

from app.templates.schema import TextField


# Common install locations for the tesseract binary itself, checked as a
# fallback when it isn't found on PATH. This matters most on Windows: the
# UB-Mannheim installer doesn't always surface (or default-check) an
# "Add to PATH" option depending on the build/version, and a user who
# doesn't know to fix that manually is left with a correctly-installed
# Tesseract that this app still can't find. Checking these paths directly
# means installing Tesseract "just works" for the overwhelming majority of
# users without them ever having to touch system PATH settings at all.
_COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",  # Apple Silicon Homebrew
    "/usr/bin/tesseract",
]


def _autodetect_tesseract_cmd() -> None:
    """If tesseract isn't already resolvable via PATH, look for it at the
    handful of locations it's actually installed to in practice and point
    pytesseract straight at the binary. No-op (and safe to call repeatedly)
    once a working path has been found."""
    if shutil.which(pytesseract.pytesseract.tesseract_cmd or "tesseract"):
        return
    for candidate in _COMMON_TESSERACT_PATHS:
        if os.path.isfile(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            return


_autodetect_tesseract_cmd()


@lru_cache(maxsize=1)
def tesseract_is_available() -> bool:
    """Whether the Tesseract OCR *engine binary* can actually be invoked at
    all on this machine -- distinct from available_tesseract_langs(), which
    only reports which language packs are installed *given that it runs*.
    pytesseract is just a thin wrapper around shelling out to a separate
    `tesseract` executable that has to be installed independently (it is
    NOT bundled with the Python package), and on a machine where that
    binary is missing or not on PATH, every OCR call raises
    TesseractNotFoundError. Cached (process-lifetime) like the langs check,
    since this also shells out."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


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
    status: str                # "READ" | "EMPTY" | "UNREADABLE" | "ENGINE_UNAVAILABLE"


def _trim_to_content(crop: np.ndarray) -> np.ndarray:
    """Crop tightly to the actual ink within the field box, rather than
    handing tesseract the full (often mostly-blank) designated box as-is.
    A Name field's box has to be wide enough for a long name, but a short
    name only fills part of that width -- confirmed directly as the root
    cause of a real failure: a field that read at 90% confidence here came
    back with *zero* recognized words (not just low-confidence, nothing at
    all) on another machine, and the one thing that field has that a
    narrower one (like Class, which read fine on the same machine) doesn't
    is a lot of blank paper sharing the crop with the text. Tesseract's own
    line segmentation is supposed to handle that, but isn't equally robust
    across engine builds/trained-data versions -- trimming to content
    ourselves removes the dependency on that step working at all."""
    ink_mask = crop < 180
    rows = np.any(ink_mask, axis=1)
    cols = np.any(ink_mask, axis=0)
    if not rows.any() or not cols.any():
        return crop
    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    pad = 6
    y0, x0 = max(0, y0 - pad), max(0, x0 - pad)
    y1, x1 = min(crop.shape[0], y1 + pad + 1), min(crop.shape[1], x1 + pad + 1)
    return crop[y0:y1, x0:x1]


def _preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    """Standard OCR preprocessing -- tesseract is meaningfully more reliable
    on a clean, well-sized, bordered black-on-white image than on a raw
    grayscale crop straight off the (possibly unevenly lit) warped canvas.
    Confirmed directly: the same crop went from "wn smith" (garbled, ~20%
    confidence) to a clean, fully correct read after this preprocessing."""
    crop = _trim_to_content(crop)
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

    # Check the OCR *engine* itself before trying to use it -- a missing or
    # not-on-PATH tesseract binary (a separate system install pytesseract
    # only shells out to, never bundled with it) must not be reported the
    # same way as genuinely illegible handwriting. Confirmed directly: a
    # real user's machine returned identical CV/quality diagnostics to ours
    # on the same file (same lighting/contrast scores, same bubble and
    # Student-ID reads, since those never touch tesseract) but every
    # OCR-dependent field silently came back "unreadable" -- a broken local
    # Tesseract install, indistinguishable from bad handwriting until this
    # check was added.
    if not tesseract_is_available():
        return TextFieldResult(name=field.name, text=None, confidence=0.0, status="ENGINE_UNAVAILABLE")

    ocr_input = _preprocess_for_ocr(crop)

    # Try a couple of segmentation strategies rather than committing to one.
    # PSM 7 (single text line) is the right assumption for a name/class
    # line in general, but a weaker/older Tesseract build (different
    # trained-data quality is common across installs -- confirmed
    # indirectly: the exact same crop that reads at 90% confidence here
    # came back fully unreadable on a real user's machine even after
    # confirming their Tesseract engine itself was working, since a
    # simpler adjacent field on the same sheet read correctly) can
    # mis-segment or under-recognize under PSM 7 specifically. PSM 8
    # (single word) is a cheap second attempt that handles that case
    # differently and sometimes succeeds where PSM 7 finds nothing.
    best_words, best_confs = [], []
    for psm in (7, 8):
        try:
            data = pytesseract.image_to_data(
                ocr_input, lang=lang, config=f"--psm {psm} --oem 3", output_type=pytesseract.Output.DICT
            )
        except pytesseract.pytesseract.TesseractNotFoundError:
            return TextFieldResult(name=field.name, text=None, confidence=0.0, status="ENGINE_UNAVAILABLE")
        except Exception:
            continue

        words, confs = [], []
        for text, conf in zip(data.get("text", []), data.get("conf", [])):
            text = text.strip()
            try:
                conf_f = float(conf)
            except (TypeError, ValueError):
                conf_f = -1.0
            if not text or conf_f < 0:
                continue
            # Tesseract sometimes segments a stray mark (a fragment of a
            # nearby printed line/label bleeding in at the crop edge) as
            # its own "word" -- confirmed directly: a real name crop that
            # read perfectly otherwise still carried a leading ";", ",",
            # or "_" as a separate low-value token. A real name/class/date
            # field's actual content is never a bare punctuation mark on
            # its own, so drop tokens with no alphanumeric character in
            # them rather than let them corrupt an otherwise-correct
            # reading.
            if not any(ch.isalnum() for ch in text):
                continue
            words.append(text)
            confs.append(conf_f)

        if words and (not best_words or sum(confs) / len(confs) > sum(best_confs) / len(best_confs)):
            best_words, best_confs = words, confs

    words, confs = best_words, best_confs

    if not words:
        return TextFieldResult(name=field.name, text=None, confidence=0.0, status="UNREADABLE")

    joined = " ".join(words)
    avg_conf = round(sum(confs) / len(confs), 1)

    # Tesseract will confidently emit noise (stray pixels, a border sliver)
    # as a 1-2 character "word" with low confidence. Rather than surface that
    # as if it were a real reading, report it honestly as unreadable --
    # matching the rest of this system's "never pretend uncertain is certain"
    # rule (spec section 2).
    min_confidence = 35.0
    if avg_conf < min_confidence or len(joined) < 2:
        return TextFieldResult(name=field.name, text=None, confidence=avg_conf, status="UNREADABLE")

    return TextFieldResult(name=field.name, text=joined, confidence=avg_conf, status="READ")


def read_all_text_fields(gray: np.ndarray, fields: list[TextField], canvas_size: tuple, lang: str = "auto") -> list[TextFieldResult]:
    return [read_text_field(gray, f, canvas_size, lang=lang) for f in fields]
