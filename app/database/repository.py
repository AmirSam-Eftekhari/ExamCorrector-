"""
Repository layer -- the only place that writes raw SQL. UI and business
logic depend on this module's typed functions, never on sqlite3 directly
(spec section 4: "the UI must never directly implement low-level logic").
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from app.core.models import (
    AnswerResult, AnswerStatus, Exam, ReviewStatus,
    ScoringRule, Student, Submission, SubmissionStatus,
)


# ---------------------------------------------------------------- Exam ----
def create_exam(conn: sqlite3.Connection, exam: Exam) -> int:
    cur = conn.execute(
        """INSERT INTO exam (name, description, subject, question_count, option_count,
                              student_id_length, template_id, scoring_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (exam.name, exam.description, exam.subject, exam.question_count, exam.option_count,
         exam.student_id_length, exam.template_id, json.dumps(asdict(exam.scoring))),
    )
    conn.commit()
    return cur.lastrowid


def get_exam(conn: sqlite3.Connection, exam_id: int) -> Exam | None:
    row = conn.execute("SELECT * FROM exam WHERE id = ?", (exam_id,)).fetchone()
    if row is None:
        return None
    return Exam(
        id=row["id"], name=row["name"], description=row["description"], subject=row["subject"],
        question_count=row["question_count"], option_count=row["option_count"],
        student_id_length=row["student_id_length"], template_id=row["template_id"],
        scoring=ScoringRule(**json.loads(row["scoring_json"])),
    )


def list_exams(conn: sqlite3.Connection) -> list[Exam]:
    rows = conn.execute("SELECT id FROM exam ORDER BY created_at DESC").fetchall()
    return [get_exam(conn, r["id"]) for r in rows]


def list_exams_using_template(conn: sqlite3.Connection, template_id: str) -> list[Exam]:
    rows = conn.execute("SELECT id FROM exam WHERE template_id = ?", (template_id,)).fetchall()
    return [get_exam(conn, r["id"]) for r in rows]


def delete_exam(conn: sqlite3.Connection, exam_id: int) -> None:
    conn.execute("DELETE FROM exam WHERE id = ?", (exam_id,))
    conn.commit()


def count_submissions(conn: sqlite3.Connection, exam_id: int) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM submission WHERE exam_id = ?", (exam_id,)).fetchone()
    return row["n"]


# ----------------------------------------------------------- AnswerKey ----
def set_answer_key(conn: sqlite3.Connection, exam_id: int, entries: dict[int, str]) -> None:
    conn.executemany(
        """INSERT INTO answer_key (exam_id, question_number, correct_answer)
           VALUES (?, ?, ?)
           ON CONFLICT(exam_id, question_number) DO UPDATE SET correct_answer = excluded.correct_answer""",
        [(exam_id, q, ans) for q, ans in entries.items()],
    )
    conn.commit()


def get_answer_key(conn: sqlite3.Connection, exam_id: int) -> dict[int, str]:
    rows = conn.execute(
        "SELECT question_number, correct_answer FROM answer_key WHERE exam_id = ? ORDER BY question_number",
        (exam_id,),
    ).fetchall()
    return {r["question_number"]: r["correct_answer"] for r in rows}


# ---------------------------------------------------------- Submission ----
def create_submission(conn: sqlite3.Connection, sub: Submission) -> int:
    cur = conn.execute(
        """INSERT INTO submission (exam_id, student_id, student_name, student_id_confidence,
                                    source_file, status, quality_score, score, percentage, failure_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sub.exam_id, sub.student_id_detected, sub.student_name_detected, sub.student_id_confidence,
         sub.source_file, sub.status.value, sub.quality_score, sub.score, sub.percentage, sub.failure_reason),
    )
    conn.commit()
    return cur.lastrowid


def update_submission_status(conn: sqlite3.Connection, submission_id: int, status: SubmissionStatus,
                              score: float | None = None, percentage: float | None = None) -> None:
    conn.execute(
        "UPDATE submission SET status = ?, score = COALESCE(?, score), percentage = COALESCE(?, percentage) WHERE id = ?",
        (status.value, score, percentage, submission_id),
    )
    conn.commit()


def get_submission(conn: sqlite3.Connection, submission_id: int) -> Submission | None:
    row = conn.execute("SELECT * FROM submission WHERE id = ?", (submission_id,)).fetchone()
    if row is None:
        return None
    return _submission_from_row(row)


def list_submissions(conn: sqlite3.Connection, exam_id: int) -> list[Submission]:
    rows = conn.execute("SELECT * FROM submission WHERE exam_id = ? ORDER BY timestamp", (exam_id,)).fetchall()
    return [_submission_from_row(r) for r in rows]


def delete_submission(conn: sqlite3.Connection, submission_id: int) -> None:
    conn.execute("DELETE FROM submission WHERE id = ?", (submission_id,))
    conn.commit()


def set_stored_image_path(conn: sqlite3.Connection, submission_id: int, path: str) -> None:
    conn.execute("UPDATE submission SET stored_image_path = ? WHERE id = ?", (path, submission_id))
    conn.commit()


def _submission_from_row(row: sqlite3.Row) -> Submission:
    keys = row.keys()
    return Submission(
        id=row["id"], exam_id=row["exam_id"], source_file=row["source_file"],
        student_id_detected=row["student_id"],
        student_name_detected=row["student_name"] if "student_name" in keys else None,
        student_id_corrected=row["student_id_corrected"] if "student_id_corrected" in keys else None,
        student_name_corrected=row["student_name_corrected"] if "student_name_corrected" in keys else None,
        student_id_confidence=(row["student_id_confidence"] if "student_id_confidence" in keys else 0.0) or 0.0,
        quality_score=row["quality_score"],
        status=SubmissionStatus(row["status"]), score=row["score"], percentage=row["percentage"],
        failure_reason=(row["failure_reason"] if "failure_reason" in keys else "") or "",
        stored_image_path=row["stored_image_path"] if "stored_image_path" in keys else None,
        timestamp=row["timestamp"],
    )


def apply_identity_correction(conn: sqlite3.Connection, submission_id: int,
                               student_id: str | None, student_name: str | None) -> None:
    """Save a human correction for a misread Student ID / Name. Empty
    string means "clear the correction, go back to the detected value" --
    stored as NULL, not '', so student_id_effective correctly falls back."""
    conn.execute(
        "UPDATE submission SET student_id_corrected = ?, student_name_corrected = ? WHERE id = ?",
        (student_id or None, student_name or None, submission_id),
    )
    conn.commit()


# --------------------------------------------------------- AnswerResult ----
def save_answer_results(conn: sqlite3.Connection, submission_id: int, results: list[AnswerResult]) -> None:
    rows = [
        (
            submission_id, r.question_number, r.detected_answer, r.confidence, r.status.value,
            json.dumps([asdict(s) for s in r.raw_scores]), r.review_status.value, r.final_answer,
            json.dumps(r.explanation),
        )
        for r in results
    ]
    conn.executemany(
        """INSERT INTO answer_result (submission_id, question_number, detected_answer, confidence, status,
                                       raw_scores_json, review_status, final_answer, explanation_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(submission_id, question_number) DO UPDATE SET
               detected_answer=excluded.detected_answer, confidence=excluded.confidence,
               status=excluded.status, raw_scores_json=excluded.raw_scores_json,
               review_status=excluded.review_status, final_answer=excluded.final_answer,
               explanation_json=excluded.explanation_json""",
        rows,
    )
    conn.commit()


def get_answer_results(conn: sqlite3.Connection, submission_id: int) -> list[AnswerResult]:
    rows = conn.execute(
        "SELECT * FROM answer_result WHERE submission_id = ? ORDER BY question_number", (submission_id,)
    ).fetchall()
    out = []
    for r in rows:
        out.append(AnswerResult(
            submission_id=r["submission_id"], question_number=r["question_number"],
            detected_answer=r["detected_answer"], confidence=r["confidence"],
            status=AnswerStatus(r["status"]), review_status=ReviewStatus(r["review_status"]),
            final_answer=r["final_answer"],
            explanation=json.loads(r["explanation_json"]) if r["explanation_json"] else {},
        ))
    return out


def apply_review_correction(conn: sqlite3.Connection, submission_id: int, question_number: int, final_answer: str | None) -> None:
    conn.execute(
        "UPDATE answer_result SET final_answer = ?, review_status = 'CORRECTED' WHERE submission_id = ? AND question_number = ?",
        (final_answer, submission_id, question_number),
    )
    conn.commit()


def get_all_answer_results_for_exam(conn: sqlite3.Connection, exam_id: int) -> list[sqlite3.Row]:
    """Every AnswerResult row across every submission of an exam, joined with
    the answer key -- the raw material for question-level analytics."""
    return conn.execute(
        """SELECT ar.submission_id, ar.question_number, ar.detected_answer, ar.final_answer,
                  ar.confidence, ar.status, ak.correct_answer
           FROM answer_result ar
           JOIN submission s ON s.id = ar.submission_id
           LEFT JOIN answer_key ak ON ak.exam_id = s.exam_id AND ak.question_number = ar.question_number
           WHERE s.exam_id = ?
           ORDER BY ar.question_number, ar.submission_id""",
        (exam_id,),
    ).fetchall()


# ------------------------------------------------------------- Student ----
def upsert_student(conn: sqlite3.Connection, student: Student) -> int:
    conn.execute(
        """INSERT INTO student (student_id, name, class_group, notes) VALUES (?, ?, ?, ?)
           ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, class_group=excluded.class_group,
               notes=excluded.notes""",
        (student.student_id, student.name, student.group, student.notes),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM student WHERE student_id = ?", (student.student_id,)).fetchone()
    return row["id"]


def get_student(conn: sqlite3.Connection, student_id: str) -> Student | None:
    row = conn.execute("SELECT * FROM student WHERE student_id = ?", (student_id,)).fetchone()
    if row is None:
        return None
    return _student_from_row(row)


def list_students(conn: sqlite3.Connection) -> list[Student]:
    rows = conn.execute("SELECT * FROM student ORDER BY student_id").fetchall()
    return [_student_from_row(r) for r in rows]


def delete_student(conn: sqlite3.Connection, student_id: str) -> None:
    conn.execute("DELETE FROM student WHERE student_id = ?", (student_id,))
    conn.commit()


def bulk_upsert_students(conn: sqlite3.Connection, students: list[Student]) -> int:
    """Returns the number of rows written. Used by CSV import -- one
    executemany rather than N individual commits."""
    conn.executemany(
        """INSERT INTO student (student_id, name, class_group, notes) VALUES (?, ?, ?, ?)
           ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, class_group=excluded.class_group,
               notes=excluded.notes""",
        [(s.student_id, s.name, s.group, s.notes) for s in students],
    )
    conn.commit()
    return len(students)


def _student_from_row(row: sqlite3.Row) -> Student:
    keys = row.keys()
    return Student(
        id=row["id"], student_id=row["student_id"], name=row["name"], group=row["class_group"],
        notes=row["notes"] if "notes" in keys else "",
    )


# ------------------------------------------------------------- Settings ----
DEFAULT_SETTINGS = {"theme": "system", "language": "fa", "accent": "indigo"}


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, default)


def get_all_settings(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    settings.update({r["key"]: r["value"] for r in rows})
    return settings


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """INSERT INTO app_settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, value),
    )
    conn.commit()
