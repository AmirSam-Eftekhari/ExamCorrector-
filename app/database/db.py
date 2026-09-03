"""
SQLite schema. Uses the stdlib sqlite3 module directly (a thin repository
layer, see repository.py) rather than an ORM, so this runs with zero extra
dependencies -- SQLAlchemy can be dropped in later behind the same
repository interface without touching callers.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS exam (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    question_count INTEGER NOT NULL,
    option_count INTEGER NOT NULL,
    student_id_length INTEGER DEFAULT 8,
    template_id TEXT,
    scoring_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS student (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT '',
    class_group TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS answer_key (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL REFERENCES exam(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    correct_answer TEXT NOT NULL,
    scoring_override_json TEXT,
    UNIQUE(exam_id, question_number)
);

CREATE TABLE IF NOT EXISTS submission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL REFERENCES exam(id) ON DELETE CASCADE,
    student_id TEXT,
    student_name TEXT,
    student_id_corrected TEXT,
    student_name_corrected TEXT,
    student_id_confidence REAL DEFAULT 0,
    source_file TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    quality_score REAL DEFAULT 0,
    score REAL,
    percentage REAL,
    failure_reason TEXT,
    stored_image_path TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS answer_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    detected_answer TEXT,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    raw_scores_json TEXT,
    review_status TEXT DEFAULT 'NOT_NEEDED',
    final_answer TEXT,
    explanation_json TEXT,
    UNIQUE(submission_id, question_number)
);

CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER REFERENCES submission(id) ON DELETE CASCADE,
    level TEXT NOT NULL DEFAULT 'INFO',
    message TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_answer_result_submission ON answer_result(submission_id);
CREATE INDEX IF NOT EXISTS idx_submission_exam ON submission(exam_id);
CREATE INDEX IF NOT EXISTS idx_answer_key_exam ON answer_key(exam_id);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

CURRENT_SCHEMA_VERSION = 5


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Idempotent: safe to call on every app start (spec section 64, migrations)."""
    conn.executescript(SCHEMA)
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_meta(key, value) VALUES ('version', ?)", (str(CURRENT_SCHEMA_VERSION),))
        conn.commit()
    else:
        stored_version = int(row["value"])
        if stored_version < CURRENT_SCHEMA_VERSION:
            _migrate(conn, stored_version, CURRENT_SCHEMA_VERSION)


def _migrate(conn: sqlite3.Connection, from_version: int, to_version: int) -> None:
    """Versioned ALTER TABLE steps -- never drops/recreates user data."""
    if from_version < 2:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(submission)")}
        if "student_name" not in existing:
            conn.execute("ALTER TABLE submission ADD COLUMN student_name TEXT")
        if "student_id_confidence" not in existing:
            conn.execute("ALTER TABLE submission ADD COLUMN student_id_confidence REAL DEFAULT 0")
        if "failure_reason" not in existing:
            conn.execute("ALTER TABLE submission ADD COLUMN failure_reason TEXT")
    if from_version < 3:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(submission)")}
        if "stored_image_path" not in existing:
            conn.execute("ALTER TABLE submission ADD COLUMN stored_image_path TEXT")
    if from_version < 4:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(student)")}
        if "notes" not in existing:
            conn.execute("ALTER TABLE student ADD COLUMN notes TEXT DEFAULT ''")
    if from_version < 5:
        # Manual correction for a misread Student ID / Name -- kept as
        # separate columns rather than overwriting student_id/student_name
        # directly, matching the same detected-vs-corrected pattern already
        # used for question answers (review_status/final_answer): the
        # original OCR/bubble reading stays visible for audit even after a
        # human fixes it.
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(submission)")}
        if "student_id_corrected" not in existing:
            conn.execute("ALTER TABLE submission ADD COLUMN student_id_corrected TEXT")
        if "student_name_corrected" not in existing:
            conn.execute("ALTER TABLE submission ADD COLUMN student_name_corrected TEXT")
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'version'", (str(to_version),))
    conn.commit()
