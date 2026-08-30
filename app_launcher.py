#!/usr/bin/env python3
"""
ExamCorrector -- standalone launcher.

This is the entry point meant to be compiled into a single-file executable
(see build_exe.bat / build_exe.sh). It's a plain interactive console menu
with no GUI dependency, so it can be built and run today -- unlike the
PySide6 desktop shell in app/ui/, which needs PySide6 installed to even
import (see README "Known limitations").

Double-clicking the compiled .exe opens a console window and runs main()
below; nothing here requires typing commands or flags.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# When compiled by PyInstaller, sys._MEIPASS points at the bundled files.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(BASE_DIR))

from app.core.config import TEMPLATES_DIR as DEFAULT_TEMPLATES_DIR, ensure_user_data_seeded  # noqa: E402


def _pause_before_exit(code: int = 0):
    print()
    try:
        input("Press Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass
    raise SystemExit(code)


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip().strip('"')
    return val or (default or "")


def _ask_existing_path(prompt: str, default: str | None = None) -> Path:
    while True:
        raw = _ask(prompt, default)
        p = Path(raw)
        if p.exists():
            return p
        print(f"  Can't find: {p}  -- try again (or Ctrl+C to cancel).")


def _list_templates() -> list[Path]:
    if not DEFAULT_TEMPLATES_DIR.exists():
        return []
    return sorted(DEFAULT_TEMPLATES_DIR.glob("*.json"))


def action_calibrate():
    import cv2
    from app.templates.calibrate import calibrate_template_from_image

    print("\n--- Calibrate a template from a clean/blank sample sheet ---")
    img_path = _ask_existing_path("Path to the clean sample sheet image")
    name = _ask("Template name", default=img_path.stem)

    img = cv2.imread(str(img_path))
    if img is None:
        print("  Could not read that image (unsupported format?).")
        return

    template, report = calibrate_template_from_image(img, name=name)
    print(f"\nRegistration: {report.registration_method} "
          f"(reprojection error {report.reprojection_error_px:.2f}px)")
    print(f"Blocks found: {report.blocks_found}   Questions found: {report.questions_found}")
    print(f"Student ID detected: {report.student_id_detected}")
    print(f"Text fields found: {report.text_fields_found}")
    for w in report.warnings:
        print(f"  WARNING: {w}")

    if not report.ok or template is None:
        print("\nCalibration failed -- see warnings above.")
        return

    DEFAULT_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DEFAULT_TEMPLATES_DIR / f"{name.lower().replace(' ', '_')}.json"
    template.save(out_path)
    print(f"\nSaved: {out_path}")


def action_process_sheet():
    import cv2
    from app.core.config import DEFAULT_CONFIG
    from app.core.models import ScoringRule
    from app.diagnostics.report import format_diagnostic_summary
    from app.grading.engine import grade_submission
    from app.omr.pipeline import process_submission
    from app.templates.schema import Template

    print("\n--- Process a filled-in answer sheet ---")

    templates = _list_templates()
    if templates:
        print("Available templates:")
        for i, t in enumerate(templates, 1):
            print(f"  {i}. {t.name}")
        choice = _ask("Pick a number, or enter a path to a different template.json", default="1")
        if choice.isdigit() and 1 <= int(choice) <= len(templates):
            template_path = templates[int(choice) - 1]
        else:
            template_path = Path(choice)
            while not template_path.exists():
                print(f"  Can't find: {template_path}")
                template_path = Path(_ask("Path to template.json"))
    else:
        template_path = _ask_existing_path("Path to template.json (none found in resources/templates)")

    img_path = _ask_existing_path("Path to the filled-in sheet image")
    template = Template.load(template_path)
    img = cv2.imread(str(img_path))
    if img is None:
        print("  Could not read that image (unsupported format?).")
        return

    result = process_submission(img, template, cfg=DEFAULT_CONFIG)
    print("\n" + "=" * 60)
    print(format_diagnostic_summary(result))
    print("=" * 60)

    key_path_raw = _ask("Path to an answer-key JSON to grade against (blank to skip)", default="")
    if key_path_raw:
        key_path = Path(key_path_raw)
        if key_path.exists():
            key = {int(k): v for k, v in json.loads(key_path.read_text()).items()}
            grade = grade_submission(result.answers, key, ScoringRule())
            print(f"\nGRADE: {grade.total_score}/{grade.max_score} ({grade.percentage}%)")
            print(f"Correct: {grade.correct}  Wrong: {grade.wrong}  Blank: {grade.blank}  "
                  f"Multiple/Invalid: {grade.multiple_or_invalid}")
        else:
            print(f"  Can't find: {key_path} -- skipping grading.")

    save = _ask("Save full result as JSON? (y/n)", default="n").lower().startswith("y")
    if save:
        out_path = img_path.with_suffix(".result.json")
        payload = {
            "status": result.status.value,
            "answers": [
                {"question_number": a.question_number, "detected_answer": a.detected_answer,
                 "confidence": a.confidence, "status": a.status.value}
                for a in result.answers
            ],
            "student_id": result.student_id.partial_id if result.student_id else None,
            "text_fields": [{"name": t.name, "text": t.text, "status": t.status} for t in result.text_fields],
        }
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"Saved: {out_path}")


def main():
    print("=" * 60)
    print("  ExamCorrector -- offline OMR & exam assessment")
    print("=" * 60)
    print("This console tool covers template calibration and single-sheet")
    print("processing/grading. (The full desktop UI is a separate, still")
    print("in-progress phase -- see README.)")
    ensure_user_data_seeded()

    while True:
        print("\nWhat would you like to do?")
        print("  1) Calibrate a template from a clean sample sheet")
        print("  2) Process a filled-in sheet (and optionally grade it)")
        print("  3) Exit")
        choice = _ask("Choice", default="3")
        try:
            if choice == "1":
                action_calibrate()
            elif choice == "2":
                action_process_sheet()
            else:
                break
        except KeyboardInterrupt:
            print("\nCancelled.")
        except Exception:
            print("\nSomething went wrong:")
            traceback.print_exc()

    _pause_before_exit()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        _pause_before_exit(1)
