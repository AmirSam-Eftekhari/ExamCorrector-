#!/usr/bin/env python3
"""
Auto-calibrate a Template from a clean sample answer sheet.

Usage:
    python scripts/calibrate_template.py <image_path> [--name "My Template"] [--out path.json]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from app.templates.calibrate import calibrate_template_from_image


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", help="Path to a clean/blank sample answer sheet image")
    ap.add_argument("--name", default="Untitled Template")
    ap.add_argument("--out", default=None, help="Where to save the template JSON")
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"Could not read image: {args.image}", file=sys.stderr)
        return 1

    template, report = calibrate_template_from_image(img, name=args.name)
    print(f"Registration: {report.registration_method} "
          f"(reprojection error {report.reprojection_error_px:.2f}px)")
    print(f"Blocks found: {report.blocks_found}   Questions found: {report.questions_found}")
    print(f"Student ID detected: {report.student_id_detected}")
    print(f"Text fields found: {report.text_fields_found}")
    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  - {w}")

    if not report.ok or template is None:
        print("\nCalibration FAILED.", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else Path("resources/templates") / f"{args.name.lower().replace(' ', '_')}.json"
    template.save(out_path)
    print(f"\nTemplate saved to: {out_path}")
    print("Review it (especially the student_id region) in the template editor before grading real submissions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
