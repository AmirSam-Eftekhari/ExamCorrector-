"""
CSV export. Kept dependency-free (stdlib csv + io) since pandas/openpyxl
aren't needed for a flat results table -- they stay reserved for a real
XLSX export later (spec section 37).
"""
from __future__ import annotations

import csv
import io
import sqlite3

from app.database import repository as repo


def export_results_csv(conn: sqlite3.Connection, exam_id: int) -> str:
    submissions = repo.list_submissions(conn, exam_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "submission_id", "student_id", "student_name", "source_file", "status",
        "quality_score", "score", "percentage", "timestamp",
    ])
    for s in submissions:
        writer.writerow([
            s.id, s.student_id_detected or "", s.student_name_detected or "", s.source_file,
            s.status.value, s.quality_score, s.score if s.score is not None else "",
            s.percentage if s.percentage is not None else "", s.timestamp,
        ])
    return buf.getvalue()


def export_answer_details_csv(conn: sqlite3.Connection, exam_id: int) -> str:
    rows = repo.get_all_answer_results_for_exam(conn, exam_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["submission_id", "question_number", "detected_answer", "final_answer",
                      "correct_answer", "confidence", "status"])
    for r in rows:
        writer.writerow([
            r["submission_id"], r["question_number"], r["detected_answer"] or "",
            r["final_answer"] or "", r["correct_answer"] or "", r["confidence"], r["status"],
        ])
    return buf.getvalue()
