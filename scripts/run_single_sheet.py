#!/usr/bin/env python3
"""
Process one answer-sheet image end to end and print a diagnostic report.

Usage:
    python scripts/run_single_sheet.py <image_path> --template resources/templates/x.json \
        [--answer-key key.json] [--save-db] [--exam-id N] [--json-out result.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from app.core.config import DEFAULT_CONFIG, DB_PATH
from app.core.models import ScoringRule, Submission, SubmissionStatus
from app.database.db import connect, init_db
from app.database import repository as repo
from app.diagnostics.report import format_diagnostic_summary, explain_answer
from app.grading.engine import grade_submission
from app.omr.pipeline import process_submission
from app.templates.schema import Template


def _answer_result_to_dict(a) -> dict:
    return {
        "question_number": a.question_number,
        "detected_answer": a.detected_answer,
        "confidence": a.confidence,
        "status": a.status.value,
        "explanation": a.explanation,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("--template", required=True)
    ap.add_argument("--answer-key", default=None, help="JSON file: {\"1\": \"A\", \"2\": \"C\", ...}")
    ap.add_argument("--save-db", action="store_true")
    ap.add_argument("--exam-id", type=int, default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--explain", type=int, default=None, help="Print full explanation for one question number")
    args = ap.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        print(f"Could not read image: {args.image}", file=sys.stderr)
        return 1

    template = Template.load(Path(args.template))
    result = process_submission(img, template, cfg=DEFAULT_CONFIG)

    print("=" * 70)
    print(f"Submission: {args.image}")
    print(f"Status: {result.status.value}")
    print("=" * 70)
    print(format_diagnostic_summary(result))

    grade = None
    if args.answer_key:
        key_raw = json.loads(Path(args.answer_key).read_text())
        key = {int(k): v for k, v in key_raw.items()}
        grade = grade_submission(result.answers, key, ScoringRule())
        print("\n" + "-" * 70)
        print(f"GRADE: {grade.total_score}/{grade.max_score} ({grade.percentage}%)")
        print(f"Correct: {grade.correct}  Wrong: {grade.wrong}  Blank: {grade.blank}  "
              f"Multiple/Invalid: {grade.multiple_or_invalid}  Pending review: {grade.unscored_pending_review}")

    if args.explain is not None:
        a = next((a for a in result.answers if a.question_number == args.explain), None)
        if a:
            print("\n" + "-" * 70)
            print(explain_answer(a))

    if args.save_db:
        if args.exam_id is None:
            print("\n--save-db requires --exam-id", file=sys.stderr)
            return 1
        conn = connect(DB_PATH)
        init_db(conn)
        sub_id = repo.create_submission(conn, Submission(
            exam_id=args.exam_id, source_file=str(args.image), status=result.status,
            quality_score=result.diagnostics.quality.overall if result.diagnostics.quality else 0.0,
            score=grade.total_score if grade else None,
            percentage=grade.percentage if grade else None,
        ))
        repo.save_answer_results(conn, sub_id, result.answers)
        print(f"\nSaved to database as submission id {sub_id}")
        conn.close()

    if args.json_out:
        payload = {
            "status": result.status.value,
            "answers": [_answer_result_to_dict(a) for a in result.answers],
            "student_id": {
                "student_id": result.student_id.student_id if result.student_id else None,
                "partial_id": result.student_id.partial_id if result.student_id else None,
                "confidence": result.student_id.overall_confidence if result.student_id else None,
                "needs_review": result.student_id.needs_review if result.student_id else None,
            } if result.student_id else None,
            "text_fields": [{"name": t.name, "text": t.text, "confidence": t.confidence, "status": t.status}
                             for t in result.text_fields],
            "grade": grade.__dict__ if grade else None,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nJSON written to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
