"""
Student roster CSV import/export.

Import format: student_id,name,group[,notes] -- header required, extra
columns ignored, missing optional columns default to empty.
"""
from __future__ import annotations

import csv
import io

from app.core.models import Student


class RosterImportError(ValueError):
    pass


def parse_roster_csv(text: str) -> tuple[list[Student], list[str]]:
    """Returns (students, warnings). Never raises on a single bad row --
    skips it and records why, so one malformed line doesn't block the rest
    of the roster (same fault-tolerance principle as batch sheet processing)."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise RosterImportError("CSV file appears to be empty.")

    normalized_fields = {f.strip().lower(): f for f in reader.fieldnames}
    if "student_id" not in normalized_fields:
        raise RosterImportError(
            "CSV must have a 'student_id' column. Found columns: " + ", ".join(reader.fieldnames)
        )

    id_col = normalized_fields["student_id"]
    name_col = normalized_fields.get("name")
    group_col = normalized_fields.get("group") or normalized_fields.get("class_group") or normalized_fields.get("class")
    notes_col = normalized_fields.get("notes")

    students: list[Student] = []
    warnings: list[str] = []
    seen_ids = set()
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        sid = (row.get(id_col) or "").strip()
        if not sid:
            warnings.append(f"Row {i}: missing student_id -- skipped.")
            continue
        if sid in seen_ids:
            warnings.append(f"Row {i}: duplicate student_id '{sid}' -- later row overwrites earlier one.")
        seen_ids.add(sid)
        students.append(Student(
            student_id=sid,
            name=(row.get(name_col) or "").strip() if name_col else "",
            group=(row.get(group_col) or "").strip() if group_col else "",
            notes=(row.get(notes_col) or "").strip() if notes_col else "",
        ))

    return students, warnings


def export_roster_csv(students: list[Student]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_id", "name", "group", "notes"])
    for s in students:
        writer.writerow([s.student_id, s.name, s.group, s.notes])
    return buf.getvalue()
