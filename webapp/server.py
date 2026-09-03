#!/usr/bin/env python3
"""
ExamCorrector -- local web UI.

Run with:  python webapp/server.py
Then open: http://127.0.0.1:5050

This is a genuinely functional GUI on top of the already-tested engine in
app/ -- not a mockup. It intentionally does NOT talk to the network (no
CDNs, no external calls): consistent with the project's offline-first
requirement, all CSS/JS is served from webapp/static/.

State is kept in a simple in-memory dict (SESSIONS). That's the right
amount of complexity for a local, single-user desktop-replacement tool --
see spec section 73, "no overengineering without value". Restarting the
server clears in-progress (unsaved) results; anything explicitly graded
against a real Exam is persisted to SQLite via app/database as usual.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import sys
import uuid
import webbrowser
from pathlib import Path
from threading import Timer

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(BASE_DIR))

import cv2
import numpy as np
from flask import Flask, Response, g, redirect, render_template, request, url_for, flash

from app.analytics.engine import compute_exam_stats, compute_question_stats
from app.core.config import DEFAULT_CONFIG, DB_PATH, DATA_DIR, TEMPLATES_DIR, ensure_user_data_seeded
from app.core.models import (
    AnswerStatus, Exam, ScoringRule, Student, Submission, SubmissionStatus,
)
from app.cv.page_detect import detect_markers
from app.cv.registration import register
from app.database.db import connect, init_db
from app.database import repository as repo
from app.database.roster_import import parse_roster_csv, export_roster_csv, RosterImportError
from app.diagnostics.annotate import annotate_result_image, encode_png_base64, crop_question_base64
from app.diagnostics.report import format_diagnostic_summary
from app.export.csv_export import export_results_csv, export_answer_details_csv
from app.export.xlsx_export import export_exam_workbook
from app.export.pdf_export import generate_exam_report_pdf
from app.grading.engine import grade_submission
from app.localization.strings import tr, is_rtl
from app.omr.pipeline import process_submission
from app.ocr.text_fields import available_tesseract_langs, tesseract_is_available
from app.templates.calibrate import calibrate_template_from_image
from app.templates.schema import Template
from webapp.icons import icon
from webapp.upload_utils import load_pages_from_upload, UploadReadError, PDF_RENDER_DPI

LANG = DEFAULT_CONFIG.language  # "fa" by default -- overridden at startup from saved settings, and by Settings page changes
THEME = DEFAULT_CONFIG.theme     # "system" | "light" | "dark"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "webapp" / "templates"),
    static_folder=str(BASE_DIR / "webapp" / "static"),
)
app.secret_key = "examcorrector-local-dev"  # local single-user tool; not internet-facing

SESSIONS: dict[str, dict] = {}
UPLOADS_DIR = DATA_DIR / "uploads"


def _reload_warped_image(stored_image_path: str | None, template: Template):
    """Re-open a persisted sheet image and re-register it, so pages that
    load a submission from the database (rather than the in-memory
    process-just-now session) can still render the color overlay / crops.
    Cheap: registration only, not the full OMR pass -- the answer statuses
    used for coloring come from the database, corrections included."""
    if not stored_image_path:
        return None
    p = Path(stored_image_path)
    if not p.exists():
        return None
    try:
        img = cv2.imread(str(p))
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        marker_result = detect_markers(gray, DEFAULT_CONFIG.registration)
        reg_result = register(img, marker_result, template.canvas_size, cfg=DEFAULT_CONFIG.registration)
        return reg_result.warped if reg_result.ok else None
    except Exception:
        return None


@app.context_processor
def inject_i18n():
    return {"tr": lambda k: tr(k, LANG), "lang": LANG, "rtl": is_rtl(LANG), "theme": THEME, "icon": icon}


def flash_msg(category: str, message: str) -> None:
    flash(message, category)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _t(fa: str, en: str) -> str:
    return fa if LANG == "fa" else en


def _upload_error_message(exc: "UploadReadError") -> str:
    code = str(exc)
    messages = {
        "empty_file": _t("فایل خالی است.", "The file is empty."),
        "pdf_unsupported": _t(
            "پشتیبانی از PDF روی این سیستم فعال نیست (poppler نصب نیست).",
            "PDF support isn't available on this system (poppler isn't installed).",
        ),
        "pdf_unreadable": _t("فایل PDF قابل خواندن نبود یا خراب است.", "The PDF couldn't be read or is corrupted."),
        "pdf_no_pages": _t("این PDF هیچ صفحه‌ای ندارد.", "This PDF has no pages."),
        "image_unreadable": _t("فایل تصویر خوانده نشد.", "Could not read this image file."),
    }
    return messages.get(code, _t("فایل خوانده نشد.", "Could not read this file."))


def _list_templates() -> list[Template]:
    out = []
    if not TEMPLATES_DIR.exists():
        return out
    for p in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            t = Template.load(p)
            t._path = p  # type: ignore[attr-defined]
            out.append(t)
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ Dashboard
@app.route("/")
def dashboard():
    templates = _list_templates()
    recent = list(SESSIONS.items())[-5:][::-1]
    return render_template("dashboard.html", templates=templates, recent=recent)


# ------------------------------------------------------------------ Templates
@app.route("/templates")
def templates_page():
    templates = _list_templates()
    return render_template("templates_list.html", templates=templates)


@app.route("/templates/calibrate", methods=["POST"])
def templates_calibrate():
    file = request.files.get("sheet_image")
    name = (request.form.get("name") or "").strip()
    if not file or not file.filename:
        flash_msg("error", "یک تصویر پاسخ‌برگ خالی انتخاب کنید." if LANG == "fa" else "Choose a clean sheet image.")
        return redirect(url_for("templates_page"))

    try:
        pages = load_pages_from_upload(file.filename, file.read())
    except UploadReadError as exc:
        flash_msg("error", _upload_error_message(exc))
        return redirect(url_for("templates_page"))

    if len(pages) > 1:
        flash_msg("warning", _t(
            f"این PDF {len(pages)} صفحه دارد؛ فقط صفحه‌ی اول برای کالیبراسیون استفاده شد.",
            f"This PDF has {len(pages)} pages; only the first was used for calibration.",
        ))
    img = pages[0].image_bgr

    name = name or Path(file.filename).stem
    template, report = calibrate_template_from_image(img, name=name)

    if not report.ok or template is None:
        flash_msg("error", f"کالیبراسیون شکست خورد: {'; '.join(report.warnings)}" if LANG == "fa"
               else f"Calibration failed: {'; '.join(report.warnings)}")
        return redirect(url_for("templates_page"))

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TEMPLATES_DIR / f"{name.lower().replace(' ', '_')}.json"
    template.save(out_path)

    msg = (f"قالب «{name}» ساخته شد: {report.questions_found} سوال در {report.blocks_found} بلوک."
           if LANG == "fa" else
           f"Template \"{name}\" created: {report.questions_found} questions in {report.blocks_found} blocks.")
    flash_msg("success", msg)
    for w in report.warnings:
        flash_msg("warning", w)
    return redirect(url_for("templates_page"))


@app.route("/templates/<path:filename>/student-id", methods=["GET", "POST"])
def template_student_id_editor(filename: str):
    path = TEMPLATES_DIR / filename
    if not path.exists():
        flash_msg("error", _t("قالب یافت نشد.", "Template not found."))
        return redirect(url_for("templates_page"))
    template = Template.load(path)

    if request.method == "POST":
        try:
            sid = template.student_id
            sid.present = True
            sid.n_digits = int(request.form.get("n_digits", sid.n_digits))
            sid.digits_per_column = int(request.form.get("digits_per_column", sid.digits_per_column))
            sid.rows_per_column = int(request.form.get("rows_per_column", sid.rows_per_column))
            sid.bubbles_per_row = int(request.form.get("bubbles_per_row", sid.bubbles_per_row))
            sid.col_start_x = float(request.form.get("col_start_x_pct", sid.col_start_x * 100)) / 100.0
            sid.col_pitch_x = float(request.form.get("col_pitch_x_pct", sid.col_pitch_x * 100)) / 100.0
            sid.row_start_y = float(request.form.get("row_start_y_pct", sid.row_start_y * 100)) / 100.0
            sid.row_pitch_y = float(request.form.get("row_pitch_y_pct", sid.row_pitch_y * 100)) / 100.0
            sid.bubble_radius = float(request.form.get("bubble_radius_pct", sid.bubble_radius * 100)) / 100.0
            sid.needs_confirmation = False  # a human just explicitly confirmed/edited this geometry
        except (TypeError, ValueError):
            flash_msg("error", _t("مقادیر واردشده معتبر نیستند.", "The values entered aren't valid numbers."))
            return redirect(url_for("template_student_id_editor", filename=filename))

        template.version += 1  # template versioning (spec 20/45): record that this geometry changed
        template.save(path)
        flash_msg("success", _t("ناحیه‌ی شناسه‌ی دانش‌آموز ذخیره شد.", "Student ID region saved."))
        return redirect(url_for("templates_page"))

    return render_template("template_student_id_editor.html", template=template, filename=filename,
                            exams_using_it=repo.list_exams_using_template(get_db(), filename))


# ------------------------------------------------------------------ Exams
@app.route("/exams")
def exams_list():
    conn = get_db()
    exams = repo.list_exams(conn)
    counts = {e.id: repo.count_submissions(conn, e.id) for e in exams}
    key_counts = {e.id: len(repo.get_answer_key(conn, e.id)) for e in exams}
    return render_template("exams_list.html", exams=exams, counts=counts, key_counts=key_counts)


@app.route("/exams/new", methods=["GET", "POST"])
def exam_new():
    templates = _list_templates()
    if request.method == "GET":
        return render_template("exam_new.html", templates=templates)

    conn = get_db()
    name = (request.form.get("name") or "").strip()
    template_file = request.form.get("template_file")
    if not name or not template_file:
        flash_msg("error", _t("نام آزمون و قالب را وارد کنید.", "Enter an exam name and pick a template."))
        return redirect(url_for("exam_new"))

    template = Template.load(TEMPLATES_DIR / template_file)
    try:
        correct = float(request.form.get("correct") or 1)
        wrong = float(request.form.get("wrong") or 0)
        blank = float(request.form.get("blank") or 0)
    except ValueError:
        correct, wrong, blank = 1.0, 0.0, 0.0
    multi_policy = request.form.get("multiple_mark_policy", "wrong")

    exam = Exam(
        name=name,
        subject=(request.form.get("subject") or "").strip(),
        description=(request.form.get("description") or "").strip(),
        question_count=template.question_count,
        option_count=len(template.blocks[0].option_labels) if template.blocks else 4,
        template_id=template_file,
        scoring=ScoringRule(correct=correct, wrong=wrong, blank=blank, multiple_mark_policy=multi_policy),
    )
    exam_id = repo.create_exam(conn, exam)
    flash_msg("success", _t(f"آزمون «{name}» ساخته شد. حالا کلید پاسخ را وارد کن.",
                             f'Exam "{name}" created. Now set the answer key.'))
    return redirect(url_for("exam_key", exam_id=exam_id))


@app.route("/exams/<int:exam_id>")
def exam_detail(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        flash_msg("error", _t("آزمون یافت نشد.", "Exam not found."))
        return redirect(url_for("exams_list"))
    key = repo.get_answer_key(conn, exam_id)
    submissions = repo.list_submissions(conn, exam_id)
    template = None
    if exam.template_id:
        try:
            template = Template.load(TEMPLATES_DIR / exam.template_id)
        except Exception:
            template = None
    return render_template("exam_detail.html", exam=exam, key=key, submissions=submissions, template=template)


@app.route("/exams/<int:exam_id>/delete", methods=["POST"])
def exam_delete(exam_id: int):
    conn = get_db()
    repo.delete_exam(conn, exam_id)
    flash_msg("success", _t("آزمون حذف شد.", "Exam deleted."))
    return redirect(url_for("exams_list"))


# ------------------------------------------------------------------ Answer key editor
@app.route("/exams/<int:exam_id>/key", methods=["GET", "POST"])
def exam_key(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        return redirect(url_for("exams_list"))

    if request.method == "POST":
        entries = {}
        for k, v in request.form.items():
            if k.startswith("q_") and v:
                entries[int(k[2:])] = v
        repo.set_answer_key(conn, exam_id, entries)
        flash_msg("success", _t("کلید پاسخ ذخیره شد.", "Answer key saved."))
        return redirect(url_for("exam_detail", exam_id=exam_id))

    key = repo.get_answer_key(conn, exam_id)
    template = Template.load(TEMPLATES_DIR / exam.template_id) if exam.template_id else None
    option_labels = template.blocks[0].option_labels if template and template.blocks else ["A", "B", "C", "D"]
    question_count = template.question_count if template else exam.question_count
    return render_template("exam_key.html", exam=exam, key=key, option_labels=option_labels,
                            question_count=question_count)


# ------------------------------------------------------------------ Batch processing
@app.route("/exams/<int:exam_id>/batch", methods=["GET", "POST"])
def exam_batch(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        return redirect(url_for("exams_list"))

    if request.method == "GET":
        return render_template("exam_batch.html", exam=exam)

    if not exam.template_id:
        flash_msg("error", _t("این آزمون قالبی ندارد.", "This exam has no template."))
        return redirect(url_for("exam_detail", exam_id=exam_id))

    template = Template.load(TEMPLATES_DIR / exam.template_id)
    key = repo.get_answer_key(conn, exam_id)
    files = request.files.getlist("sheet_images")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    summary = {"completed": 0, "needs_review": 0, "failed": 0}
    for f in files:
        if not f or not f.filename:
            continue
        raw_bytes = f.read()
        try:
            pages = load_pages_from_upload(f.filename, raw_bytes)
        except UploadReadError as exc:
            repo.create_submission(conn, Submission(
                exam_id=exam_id, source_file=f.filename, status=SubmissionStatus.FAILED,
                failure_reason=_upload_error_message(exc),
            ))
            summary["failed"] += 1
            continue

        for page in pages:
            img = page.image_bgr
            result = process_submission(img, template, cfg=DEFAULT_CONFIG)
            grade = grade_submission(result.answers, key, exam.scoring) if key else None
            name_field = next((t for t in result.text_fields if t.name.lower() in ("name", "اسم") and t.text), None)

            # Roster cross-check (spec: "never fabricate a student" -- this only
            # ever fills in a name when the *detected* ID matches a known
            # roster entry; an unmatched ID is left exactly as detected, not
            # guessed at).
            detected_id = result.student_id.student_id if result.student_id else None
            roster_name = None
            if detected_id:
                roster_student = repo.get_student(conn, detected_id)
                if roster_student:
                    roster_name = roster_student.name

            sub = Submission(
                exam_id=exam_id, source_file=page.name,
                student_id_detected=detected_id,
                student_id_confidence=result.student_id.overall_confidence if result.student_id else 0.0,
                student_name_detected=roster_name or (name_field.text if name_field else None),
                quality_score=result.diagnostics.quality.overall if result.diagnostics.quality else 0.0,
                status=result.status,
                score=grade.total_score if grade else None,
                percentage=grade.percentage if grade else None,
                failure_reason=result.failure_reason,
            )
            sub_id = repo.create_submission(conn, sub)
            repo.save_answer_results(conn, sub_id, result.answers)

            # Persist the original image so results/review can be revisited
            # later (batch runs happen once; students get reviewed over days,
            # not seconds). Always store as a plain image -- a PDF page has
            # already been rendered to a raster page by this point, so there
            # is no PDF left to keep; re-encoding keeps every stored
            # submission image in the same simple format regardless of what
            # was originally uploaded.
            ok, encoded = cv2.imencode(".png", img)
            image_path = UPLOADS_DIR / f"{sub_id}.png"
            if ok:
                image_path.write_bytes(encoded.tobytes())
                repo.set_stored_image_path(conn, sub_id, str(image_path))

            if result.status == SubmissionStatus.COMPLETED:
                summary["completed"] += 1
            elif result.status == SubmissionStatus.FAILED:
                summary["failed"] += 1
        else:
            summary["needs_review"] += 1

    flash_msg("success", _t(
        f"{summary['completed']} تکمیل، {summary['needs_review']} نیاز به بازبینی، {summary['failed']} ناموفق.",
        f"{summary['completed']} completed, {summary['needs_review']} need review, {summary['failed']} failed."))
    return redirect(url_for("exam_results", exam_id=exam_id))


# ------------------------------------------------------------------ Results (persistent, DB-backed)
@app.route("/exams/<int:exam_id>/results")
def exam_results(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        return redirect(url_for("exams_list"))
    submissions = repo.list_submissions(conn, exam_id)
    return render_template("exam_results.html", exam=exam, submissions=submissions)


@app.route("/exams/<int:exam_id>/results/<int:submission_id>")
def submission_detail(exam_id: int, submission_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    sub = repo.get_submission(conn, submission_id)
    if not exam or not sub:
        return redirect(url_for("exams_list"))

    answers = repo.get_answer_results(conn, submission_id)
    key = repo.get_answer_key(conn, exam_id)
    grade = grade_submission(answers, key, exam.scoring) if key else None
    flagged = [a for a in answers if a.confidence < 60 or a.status.value in
               ("LOW_CONFIDENCE", "MULTIPLE_MARK", "AMBIGUOUS", "UNREADABLE")]

    template = Template.load(TEMPLATES_DIR / exam.template_id) if exam.template_id else None
    annotated_b64 = None
    if template:
        warped = _reload_warped_image(sub.stored_image_path, template)
        if warped is not None:
            annotated_b64 = encode_png_base64(annotate_result_image(warped, template, answers))

    return render_template("submission_detail.html", exam=exam, sub=sub, answers=answers,
                            grade=grade, flagged=flagged, annotated_b64=annotated_b64)


@app.route("/exams/<int:exam_id>/results/<int:submission_id>/edit-identity", methods=["POST"])
def submission_edit_identity(exam_id: int, submission_id: int):
    conn = get_db()
    sub = repo.get_submission(conn, submission_id)
    if not sub or sub.exam_id != exam_id:
        return redirect(url_for("exams_list"))

    new_id = (request.form.get("student_id") or "").strip()
    new_name = (request.form.get("student_name") or "").strip()
    repo.apply_identity_correction(conn, submission_id, new_id, new_name)
    flash_msg("success", _t("شناسه/نام دانش‌آموز به‌روزرسانی شد.", "Student ID/name updated."))
    return redirect(url_for("submission_detail", exam_id=exam_id, submission_id=submission_id))


@app.route("/exams/<int:exam_id>/results/<int:submission_id>/edit-answers")
def submission_edit_all(exam_id: int, submission_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    sub = repo.get_submission(conn, submission_id)
    if not exam or not sub:
        return redirect(url_for("exams_list"))

    answers = repo.get_answer_results(conn, submission_id)
    answers_by_q = {a.question_number: a for a in answers}
    flagged_qnums = {a.question_number for a in answers if a.confidence < 60 or a.status.value in
                      ("LOW_CONFIDENCE", "MULTIPLE_MARK", "AMBIGUOUS", "UNREADABLE")}

    template = Template.load(TEMPLATES_DIR / exam.template_id) if exam.template_id else None
    return render_template("submission_edit_all.html", exam=exam, sub=sub, template=template,
                            answers_by_q=answers_by_q, flagged_qnums=flagged_qnums)


@app.route("/exams/<int:exam_id>/results/<int:submission_id>/review")
def submission_review(exam_id: int, submission_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    sub = repo.get_submission(conn, submission_id)
    if not exam or not sub:
        return redirect(url_for("exams_list"))

    answers = repo.get_answer_results(conn, submission_id)
    flagged = [a for a in answers if a.confidence < 60 or a.status.value in
               ("LOW_CONFIDENCE", "MULTIPLE_MARK", "AMBIGUOUS", "UNREADABLE")]

    template = Template.load(TEMPLATES_DIR / exam.template_id) if exam.template_id else None
    crops = {}
    if template:
        warped = _reload_warped_image(sub.stored_image_path, template)
        if warped is not None:
            for a in flagged:
                crops[a.question_number] = crop_question_base64(warped, template, a.question_number)

    return render_template("submission_review.html", exam=exam, sub=sub, flagged=flagged,
                            template=template, crops=crops)


@app.route("/exams/<int:exam_id>/results/<int:submission_id>/review/apply", methods=["POST"])
def submission_review_apply(exam_id: int, submission_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    # "Edit all answers" submits every question's current value every time
    # (not just the ones actually changed), so only apply a correction --
    # and only mark review_status='CORRECTED' -- where the value genuinely
    # differs from what's already stored; otherwise every submission
    # touched via that page would misleadingly show as 100% human-reviewed.
    existing = {a.question_number: a for a in repo.get_answer_results(conn, submission_id)}
    for k, v in request.form.items():
        if k.startswith("q_"):
            qnum = int(k[2:])
            new_val = v or None
            current = existing.get(qnum)
            if current is None:
                continue
            current_val = current.final_answer if current.final_answer else current.detected_answer
            if new_val != current_val:
                repo.apply_review_correction(conn, submission_id, qnum, new_val)

    answers = repo.get_answer_results(conn, submission_id)
    key = repo.get_answer_key(conn, exam_id)
    if key and exam:
        grade = grade_submission(answers, key, exam.scoring)
        repo.update_submission_status(conn, submission_id, SubmissionStatus.COMPLETED,
                                       score=grade.total_score, percentage=grade.percentage)

    flash_msg("success", _t("تصحیح‌ها ذخیره شد.", "Corrections saved."))
    return redirect(url_for("submission_detail", exam_id=exam_id, submission_id=submission_id))


# ------------------------------------------------------------------ Students
@app.route("/students")
def students_list():
    conn = get_db()
    students = repo.list_students(conn)
    return render_template("students_list.html", students=students)


@app.route("/students/import", methods=["POST"])
def students_import():
    conn = get_db()
    file = request.files.get("roster_csv")
    if not file or not file.filename:
        flash_msg("error", _t("یک فایل CSV انتخاب کن.", "Choose a CSV file."))
        return redirect(url_for("students_list"))
    try:
        text = file.read().decode("utf-8-sig")
        students, warnings = parse_roster_csv(text)
    except RosterImportError as exc:
        flash_msg("error", str(exc))
        return redirect(url_for("students_list"))
    except UnicodeDecodeError:
        flash_msg("error", _t("فایل CSV قابل خواندن نبود (encoding).", "Could not read the CSV file (encoding)."))
        return redirect(url_for("students_list"))

    if not students:
        flash_msg("error", _t("هیچ دانش‌آموزی در فایل پیدا نشد.", "No students found in the file."))
        return redirect(url_for("students_list"))

    repo.bulk_upsert_students(conn, students)
    flash_msg("success", _t(f"{len(students)} دانش‌آموز وارد شد.", f"{len(students)} students imported."))
    for w in warnings[:10]:
        flash_msg("warning", w)
    return redirect(url_for("students_list"))


@app.route("/students/<student_id>/delete", methods=["POST"])
def student_delete(student_id: str):
    conn = get_db()
    repo.delete_student(conn, student_id)
    flash_msg("success", _t("دانش‌آموز حذف شد.", "Student deleted."))
    return redirect(url_for("students_list"))


@app.route("/students/export.csv")
def students_export():
    conn = get_db()
    students = repo.list_students(conn)
    csv_text = export_roster_csv(students)
    return Response(csv_text, mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=students.csv"})


# ------------------------------------------------------------------ Analytics & export
@app.route("/exams/<int:exam_id>/analytics")
def exam_analytics(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        return redirect(url_for("exams_list"))
    stats = compute_exam_stats(conn, exam_id)
    q_stats = compute_question_stats(conn, exam_id)
    max_bucket = max([n for _, n in stats.distribution], default=0) if stats.distribution else 0
    return render_template("exam_analytics.html", exam=exam, stats=stats, q_stats=q_stats, max_bucket=max_bucket)


@app.route("/exams/<int:exam_id>/export/results.csv")
def export_results_route(exam_id: int):
    conn = get_db()
    csv_text = export_results_csv(conn, exam_id)
    return Response(csv_text, mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename=exam_{exam_id}_results.csv"})


@app.route("/exams/<int:exam_id>/export/answers.csv")
def export_answers_route(exam_id: int):
    conn = get_db()
    csv_text = export_answer_details_csv(conn, exam_id)
    return Response(csv_text, mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename=exam_{exam_id}_answers.csv"})


@app.route("/exams/<int:exam_id>/export/report.xlsx")
def export_xlsx_route(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        return redirect(url_for("exams_list"))
    data = export_exam_workbook(conn, exam)
    safe_name = "".join(c if c.isalnum() else "_" for c in exam.name)[:40] or f"exam_{exam_id}"
    return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     headers={"Content-Disposition": f"attachment; filename={safe_name}.xlsx"})


@app.route("/exams/<int:exam_id>/export/report.pdf")
def export_pdf_route(exam_id: int):
    conn = get_db()
    exam = repo.get_exam(conn, exam_id)
    if not exam:
        return redirect(url_for("exams_list"))
    data = generate_exam_report_pdf(conn, exam)
    safe_name = "".join(c if c.isalnum() else "_" for c in exam.name)[:40] or f"exam_{exam_id}"
    return Response(data, mimetype="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename={safe_name}.pdf"})


# ------------------------------------------------------------------ Process
@app.route("/process")
def process_form():
    templates = _list_templates()
    return render_template("process_form.html", templates=templates)


@app.route("/process", methods=["POST"])
def process_submit():
    template_file = request.form.get("template_file")
    sheet = request.files.get("sheet_image")
    key_file = request.files.get("answer_key")

    if not template_file or not sheet or not sheet.filename:
        flash_msg("error", "قالب و تصویر پاسخ‌برگ را انتخاب کنید." if LANG == "fa" else "Pick a template and a sheet image.")
        return redirect(url_for("process_form"))

    template = Template.load(TEMPLATES_DIR / template_file)
    try:
        pages = load_pages_from_upload(sheet.filename, sheet.read())
    except UploadReadError as exc:
        flash_msg("error", _upload_error_message(exc))
        return redirect(url_for("process_form"))

    if len(pages) > 1:
        flash_msg("warning", _t(
            f"این PDF {len(pages)} صفحه دارد؛ فقط صفحه‌ی اول پردازش شد. برای پردازش همه‌ی صفحات از «پردازش دسته‌ای» در یک آزمون استفاده کن.",
            f"This PDF has {len(pages)} pages; only the first was processed. Use an exam's Batch Process to handle every page.",
        ))
    img = pages[0].image_bgr

    result = process_submission(img, template, cfg=DEFAULT_CONFIG)

    answer_key = None
    if key_file and key_file.filename:
        try:
            raw = json.loads(key_file.read().decode("utf-8"))
            answer_key = {int(k): v for k, v in raw.items()}
        except Exception:
            flash_msg("warning", "فایل کلید پاسخ خوانده نشد؛ بدون نمره‌دهی ادامه داده شد."
                   if LANG == "fa" else "Could not parse the answer key; continuing without grading.")

    token = uuid.uuid4().hex[:12]
    SESSIONS[token] = {
        "template": template,
        "result": result,
        "answer_key": answer_key,
        "sheet_name": sheet.filename,
    }
    return redirect(url_for("process_result", token=token))


@app.route("/process/result/<token>")
def process_result(token: str):
    session = SESSIONS.get(token)
    if not session:
        flash_msg("error", "این نتیجه دیگر در دسترس نیست (سرور را ری‌استارت کردید؟)."
               if LANG == "fa" else "That result is no longer available (server restarted?).")
        return redirect(url_for("process_form"))

    result = session["result"]
    template = session["template"]

    annotated_b64 = None
    if result.warped_image is not None:
        annotated = annotate_result_image(result.warped_image, template, result.answers)
        annotated_b64 = encode_png_base64(annotated)

    grade = None
    if session["answer_key"] and result.status.value != "FAILED":
        grade = grade_submission(result.answers, session["answer_key"], ScoringRule())

    flagged = [a for a in result.answers if a.confidence < 60 or a.status.value in
               ("LOW_CONFIDENCE", "MULTIPLE_MARK", "AMBIGUOUS", "UNREADABLE")]

    return render_template(
        "process_result.html",
        token=token, result=result, template=template, grade=grade,
        annotated_b64=annotated_b64, flagged=flagged,
        diagnostic_text=format_diagnostic_summary(result),
        sheet_name=session["sheet_name"],
    )


# ------------------------------------------------------------------ Review
@app.route("/review/<token>")
def review(token: str):
    session = SESSIONS.get(token)
    if not session:
        flash_msg("error", "این نتیجه دیگر در دسترس نیست." if LANG == "fa" else "That result is no longer available.")
        return redirect(url_for("process_form"))

    result = session["result"]
    template = session["template"]
    flagged = [a for a in result.answers if a.confidence < 60 or a.status.value in
               ("LOW_CONFIDENCE", "MULTIPLE_MARK", "AMBIGUOUS", "UNREADABLE")]

    crops = {}
    if result.warped_image is not None:
        for a in flagged:
            crops[a.question_number] = crop_question_base64(result.warped_image, template, a.question_number)

    return render_template("review.html", token=token, flagged=flagged, template=template,
                            crops=crops, result=result)


@app.route("/review/<token>/apply", methods=["POST"])
def review_apply(token: str):
    session = SESSIONS.get(token)
    if not session:
        return redirect(url_for("process_form"))

    result = session["result"]
    by_q = {a.question_number: a for a in result.answers}
    for key, value in request.form.items():
        if not key.startswith("q_"):
            continue
        q_num = int(key[2:])
        if q_num in by_q:
            by_q[q_num].final_answer = value if value else None
            by_q[q_num].review_status = by_q[q_num].review_status.__class__("CORRECTED")

    flash_msg("success", "تصحیح‌ها ذخیره شد." if LANG == "fa" else "Corrections saved.")
    return redirect(url_for("process_result", token=token))


# ------------------------------------------------------------------ Settings
@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    global LANG, THEME
    conn = get_db()
    if request.method == "POST":
        new_lang = request.form.get("language", LANG)
        new_theme = request.form.get("theme", THEME)
        repo.set_setting(conn, "language", new_lang)
        repo.set_setting(conn, "theme", new_theme)
        LANG, THEME = new_lang, new_theme
        flash_msg("success", _t("تنظیمات ذخیره شد.", "Settings saved."))
        return redirect(url_for("settings_page"))

    return render_template("settings.html", current_theme=THEME, current_lang=LANG,
                            ocr_langs=sorted(available_tesseract_langs() - {"osd"}),
                            ocr_engine_available=tesseract_is_available())


def _open_browser():
    webbrowser.open("http://127.0.0.1:5050")


def main():
    global LANG, THEME
    ensure_user_data_seeded()
    connect(DB_PATH)
    conn = connect(DB_PATH)
    init_db(conn)
    LANG = repo.get_setting(conn, "language", LANG)
    THEME = repo.get_setting(conn, "theme", THEME)
    conn.close()
    Timer(0.8, _open_browser).start()
    app.run(host="127.0.0.1", port=5050, debug=False)


if __name__ == "__main__":
    main()
