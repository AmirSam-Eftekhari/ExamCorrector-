"""
Template schema (spec section 10 & 62).

A template describes the LOGICAL structure of an answer sheet in the
registered/normalized coordinate space (fractions of the canvas, not raw
photo pixels) so the same template works for any photo of that sheet once
registration has run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

TEMPLATE_SCHEMA_VERSION = 1


@dataclass
class AnswerBlock:
    """A rectangular group of questions, e.g. 'Questions 1-25'."""
    block_id: str
    question_start: int
    question_end: int
    option_labels: list[str]              # ["A","B","C","D"]
    row_start_y: float                    # fraction of canvas height, first row center
    row_pitch_y: float                    # fraction of canvas height, between row centers
    col_start_x: float                    # fraction of canvas width, first option center
    col_pitch_x: float                    # fraction of canvas width, between option centers
    bubble_radius: float                  # fraction of canvas width (radius)

    @property
    def question_count(self) -> int:
        return self.question_end - self.question_start + 1

    def bubble_center(self, question_number: int, option_index: int, canvas_size: tuple) -> tuple:
        row = question_number - self.question_start
        cw, ch = canvas_size
        x = (self.col_start_x + option_index * self.col_pitch_x) * cw
        y = (self.row_start_y + row * self.row_pitch_y) * ch
        return (x, y)


@dataclass
class StudentIdRegion:
    present: bool = False
    n_digits: int = 8
    digits_per_column: int = 10
    rows_per_column: int = 2               # bubbles stacked in N sub-rows per digit column
    box: tuple = (0.0, 0.0, 0.0, 0.0)      # (x0,y0,x1,y1) fractions of canvas
    col_start_x: float = 0.0
    col_pitch_x: float = 0.0
    row_start_y: float = 0.0
    row_pitch_y: float = 0.0
    bubbles_per_row: int = 5
    bubble_radius: float = 0.0
    needs_confirmation: bool = True        # auto-detected ID layouts should be human-confirmed

    def bubble_center(self, digit_col: int, digit_value: int, canvas_size: tuple) -> tuple:
        sub_row = digit_value // self.bubbles_per_row
        sub_col = digit_value % self.bubbles_per_row
        cw, ch = canvas_size
        x = (self.col_start_x + digit_col * self.col_pitch_x + sub_col * self.bubble_radius * 2.6) * cw
        y = (self.row_start_y + sub_row * self.row_pitch_y) * ch
        return (x, y)


@dataclass
class TextField:
    """A free-text / handwritten field (Name, Class, Date, ...), best-effort OCR only."""
    name: str
    box: tuple            # (x0,y0,x1,y1) fractions of canvas -- the area to OCR (above the line)
    line_box: tuple        # (x0,y0,x1,y1) fractions of canvas -- the underline itself


@dataclass
class RegistrationSpec:
    strategy: str = "fiducial_markers"     # "fiducial_markers" | "page_contour"
    marker_margin_frac: float = 0.03


@dataclass
class Template:
    name: str
    description: str = ""
    template_version: int = TEMPLATE_SCHEMA_VERSION
    version: int = 1                        # user-facing template revision (spec 45)
    canvas_size: tuple = (2000, 2828)
    registration: RegistrationSpec = field(default_factory=RegistrationSpec)
    blocks: list[AnswerBlock] = field(default_factory=list)
    student_id: StudentIdRegion = field(default_factory=StudentIdRegion)
    text_fields: list[TextField] = field(default_factory=list)

    @property
    def question_count(self) -> int:
        return sum(b.question_count for b in self.blocks)

    def block_for_question(self, question_number: int) -> Optional[AnswerBlock]:
        for b in self.blocks:
            if b.question_start <= question_number <= b.question_end:
                return b
        return None

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> "Template":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Template.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> "Template":
        errors = validate_template_dict(data)
        if errors:
            raise TemplateValidationError(errors)
        blocks = [AnswerBlock(**b) for b in data.get("blocks", [])]
        sid = StudentIdRegion(**data["student_id"]) if data.get("student_id") else StudentIdRegion()
        fields_ = [TextField(**f) for f in data.get("text_fields", [])]
        reg = RegistrationSpec(**data["registration"]) if data.get("registration") else RegistrationSpec()
        return Template(
            name=data["name"],
            description=data.get("description", ""),
            template_version=data.get("template_version", TEMPLATE_SCHEMA_VERSION),
            version=data.get("version", 1),
            canvas_size=tuple(data.get("canvas_size", (2000, 2828))),
            registration=reg,
            blocks=blocks,
            student_id=sid,
            text_fields=fields_,
        )


class TemplateValidationError(ValueError):
    pass


def validate_template_dict(data: dict) -> list[str]:
    """Never let a corrupt template crash the app (spec section 63)."""
    errors = []
    if "name" not in data or not data["name"]:
        errors.append("Missing required field: name")
    if "template_version" in data and data["template_version"] > TEMPLATE_SCHEMA_VERSION:
        errors.append(
            f"Template schema version {data['template_version']} is newer than "
            f"supported version {TEMPLATE_SCHEMA_VERSION}."
        )
    blocks = data.get("blocks", [])
    if not blocks:
        errors.append("Template has no answer blocks defined.")
    seen_questions = set()
    for b in blocks:
        required = {"block_id", "question_start", "question_end", "option_labels",
                    "row_start_y", "row_pitch_y", "col_start_x", "col_pitch_x", "bubble_radius"}
        missing = required - set(b.keys())
        if missing:
            errors.append(f"Block {b.get('block_id', '?')} missing fields: {missing}")
            continue
        if b["question_end"] < b["question_start"]:
            errors.append(f"Block {b['block_id']}: question_end < question_start")
        qs = set(range(b["question_start"], b["question_end"] + 1))
        overlap = qs & seen_questions
        if overlap:
            errors.append(f"Block {b['block_id']}: question numbers overlap another block: {sorted(overlap)[:5]}")
        seen_questions |= qs
        if not (1 <= len(b["option_labels"]) <= 10):
            errors.append(f"Block {b['block_id']}: option_labels count out of sane range")
    return errors
