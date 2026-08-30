"""
Loads one or more OMR-ready images from a single uploaded file.

Supports plain image formats (jpg/png/webp/bmp/tiff) directly, and PDF --
each page of a PDF becomes its own image, since the common real-world
workflow is "scan a stack of filled sheets into one combined PDF". No
network access is used; PDF rendering is local via poppler (pdf2image).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

try:
    from pdf2image import convert_from_bytes
    from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError
    _PDF_SUPPORT = True
except ImportError:  # pdf2image or poppler not available in this environment
    _PDF_SUPPORT = False


PDF_RENDER_DPI = 220  # matches typical flatbed-scan resolution well enough
# for marker/bubble detection without producing unreasonably large images.


@dataclass
class LoadedPage:
    name: str            # display name, e.g. "roster.pdf (page 2)" or "sheet1.png"
    image_bgr: np.ndarray


class UploadReadError(ValueError):
    pass


def is_pdf(filename: str, head_bytes: bytes) -> bool:
    if filename and filename.lower().endswith(".pdf"):
        return True
    return head_bytes[:5] == b"%PDF-"


def load_pages_from_upload(filename: str, raw_bytes: bytes) -> list[LoadedPage]:
    """Returns one LoadedPage per page for a PDF, or a single LoadedPage for
    a regular image. Raises UploadReadError with a human-readable message
    on failure -- callers should catch this and flash it, not crash."""
    if not raw_bytes:
        raise UploadReadError("empty_file")

    if is_pdf(filename, raw_bytes[:8]):
        if not _PDF_SUPPORT:
            raise UploadReadError("pdf_unsupported")
        try:
            pages = convert_from_bytes(raw_bytes, dpi=PDF_RENDER_DPI)
        except (PDFPageCountError, PDFSyntaxError, Exception) as exc:
            raise UploadReadError("pdf_unreadable") from exc
        if not pages:
            raise UploadReadError("pdf_no_pages")
        results = []
        for i, pil_page in enumerate(pages, start=1):
            rgb = np.array(pil_page.convert("RGB"))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            label = filename if len(pages) == 1 else f"{filename} (page {i})"
            results.append(LoadedPage(name=label, image_bgr=bgr))
        return results

    data = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise UploadReadError("image_unreadable")
    return [LoadedPage(name=filename, image_bgr=img)]
