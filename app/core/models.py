"""
Domain models. These are plain dataclasses independent of the database layer
and independent of the CV layer -- the grading engine and analytics only ever
see these, never raw pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AnswerStatus(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    BLANK = "BLANK"
    MULTIPLE_MARK = "MULTIPLE_MARK"
    AMBIGUOUS = "AMBIGUOUS"
    UNREADABLE = "UNREADABLE"


class ReviewStatus(str, Enum):
    NOT_NEEDED = "NOT_NEEDED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"


class SubmissionStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


@dataclass
class ScoringRule:
    correct: float = 1.0
    wrong: float = 0.0
    blank: float = 0.0
    multiple_mark_policy: str = "wrong"     # "wrong" | "invalid" | "manual_review"
    multiple_mark_score: float = 0.0


@dataclass
class Exam:
    name: str
    subject: str = ""
    description: str = ""
    question_count: int = 0
    option_count: int = 4
    student_id_length: int = 8
    template_id: Optional[str] = None
    scoring: ScoringRule = field(default_factory=ScoringRule)
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Student:
    student_id: str
    name: str = ""
    group: str = ""
    notes: str = ""
    id: Optional[int] = None


@dataclass
class AnswerKeyEntry:
    exam_id: int
    question_number: int
    correct_answer: str          # "A".."?" or "MULTI:AB" if multiple correct allowed


@dataclass
class BubbleScore:
    option: str
    fill_ratio: float
    mean_intensity: float
    dark_pixel_ratio: float
    edge_density: float
    ring_mean: float = 0.0
    local_darkness: float = 0.0
    adaptive_dark_ratio: float = 0.0
    interior_std: float = 0.0
    preprocessing_vote: float | None = None


@dataclass
class AnswerResult:
    submission_id: Optional[int]
    question_number: int
    detected_answer: Optional[str]        # None if blank/unreadable
    confidence: float                     # 0-100
    status: AnswerStatus
    raw_scores: list[BubbleScore] = field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.NOT_NEEDED
    final_answer: Optional[str] = None    # set once reviewed/confirmed
    explanation: dict = field(default_factory=dict)


@dataclass
class Submission:
    exam_id: int
    source_file: str
    student_id_detected: Optional[str] = None
    student_id_confidence: float = 0.0
    student_name_detected: Optional[str] = None
    quality_score: float = 0.0
    status: SubmissionStatus = SubmissionStatus.QUEUED
    score: Optional[float] = None
    percentage: Optional[float] = None
    failure_reason: str = ""
    stored_image_path: Optional[str] = None
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
