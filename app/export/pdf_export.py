"""
Offline PDF report generation (spec section 42/43) using reportlab --
no external/online service, matching this project's offline-first rule.
"""
from __future__ import annotations

import io
import sqlite3

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

from app.analytics.engine import compute_exam_stats, compute_question_stats
from app.core.models import Exam
from app.database import repository as repo

_STYLES = getSampleStyleSheet()
_TITLE = ParagraphStyle("ExamTitle", parent=_STYLES["Title"], fontSize=20)
_H2 = ParagraphStyle("H2", parent=_STYLES["Heading2"], spaceBefore=14, spaceAfter=6)
_BODY = _STYLES["BodyText"]

_TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D5DD")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8FA")]),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
])


def generate_exam_report_pdf(conn: sqlite3.Connection, exam: Exam) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                             leftMargin=16 * mm, rightMargin=16 * mm)
    story = []

    story.append(Paragraph(exam.name, _TITLE))
    subtitle = " · ".join(x for x in [exam.subject, f"{exam.question_count} questions"] if x)
    story.append(Paragraph(subtitle, _BODY))
    story.append(Spacer(1, 10))

    stats = compute_exam_stats(conn, exam.id)
    story.append(Paragraph("Summary", _H2))
    if stats.n_scored == 0:
        story.append(Paragraph("No scored submissions yet.", _BODY))
    else:
        summary_rows = [
            ["Submissions", "Average", "Median", "Min", "Max", "Std dev"],
            [str(stats.n_submissions), f"{stats.average}%", f"{stats.median}%",
             f"{stats.minimum}%", f"{stats.maximum}%", str(stats.std_dev)],
        ]
        t = Table(summary_rows, hAlign="LEFT")
        t.setStyle(_TABLE_STYLE)
        story.append(t)

        story.append(Paragraph("Score distribution", _H2))
        dist_rows = [["Range", "Count"]] + [[label, str(count)] for label, count in stats.distribution]
        t2 = Table(dist_rows, hAlign="LEFT", colWidths=[60 * mm, 30 * mm])
        t2.setStyle(_TABLE_STYLE)
        story.append(t2)

    story.append(Paragraph("Student results", _H2))
    submissions = repo.list_submissions(conn, exam.id)
    if not submissions:
        story.append(Paragraph("No submissions processed yet.", _BODY))
    else:
        rows = [["Student ID", "Name", "File", "Score", "Percentage", "Status"]]
        for s in submissions:
            rows.append([
                s.student_id_detected or "—", s.student_name_detected or "—", s.source_file,
                f"{s.score:.2f}" if s.score is not None else "—",
                f"{s.percentage:.1f}%" if s.percentage is not None else "—",
                s.status.value,
            ])
        t3 = Table(rows, hAlign="LEFT", repeatRows=1)
        t3.setStyle(_TABLE_STYLE)
        story.append(t3)

    story.append(PageBreak())
    story.append(Paragraph("Question analysis", _H2))
    q_stats = compute_question_stats(conn, exam.id)
    if not q_stats:
        story.append(Paragraph("No answer data yet.", _BODY))
    else:
        rows = [["Q", "Key", "Correct%", "Wrong%", "Blank%", "Multi%", "Review%"]]
        for qs in q_stats:
            rows.append([
                f"{qs.question_number:03d}", qs.correct_answer or "—",
                f"{qs.correct_pct}", f"{qs.wrong_pct}", f"{qs.blank_pct}",
                f"{qs.multiple_pct}", f"{qs.review_rate_pct}",
            ])
        t4 = Table(rows, hAlign="LEFT", repeatRows=1)
        t4.setStyle(_TABLE_STYLE)
        story.append(t4)

    doc.build(story)
    return buf.getvalue()
