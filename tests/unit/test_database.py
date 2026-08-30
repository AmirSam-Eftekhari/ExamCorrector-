import tempfile
import unittest
from pathlib import Path

from app.database.db import connect, init_db
from app.database import repository as repo
from app.core.models import (
    AnswerResult, AnswerStatus, Exam, ScoringRule, Student, Submission, SubmissionStatus,
)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.sqlite3"
        self.conn = connect(self.db_path)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        self._tmpdir.cleanup()

    def test_exam_round_trip(self):
        exam_id = repo.create_exam(self.conn, Exam(
            name="Midterm", subject="Physics", question_count=100, option_count=4,
            scoring=ScoringRule(correct=1, wrong=-0.25),
        ))
        exam = repo.get_exam(self.conn, exam_id)
        self.assertEqual(exam.name, "Midterm")
        self.assertEqual(exam.scoring.wrong, -0.25)

    def test_answer_key_round_trip(self):
        exam_id = repo.create_exam(self.conn, Exam(name="E", question_count=10, option_count=4))
        repo.set_answer_key(self.conn, exam_id, {i: "A" for i in range(1, 11)})
        key = repo.get_answer_key(self.conn, exam_id)
        self.assertEqual(len(key), 10)
        self.assertEqual(key[1], "A")

    def test_answer_key_upsert_overwrites(self):
        exam_id = repo.create_exam(self.conn, Exam(name="E", question_count=1, option_count=4))
        repo.set_answer_key(self.conn, exam_id, {1: "A"})
        repo.set_answer_key(self.conn, exam_id, {1: "B"})
        self.assertEqual(repo.get_answer_key(self.conn, exam_id)[1], "B")

    def test_submission_and_answer_results_round_trip(self):
        exam_id = repo.create_exam(self.conn, Exam(name="E", question_count=5, option_count=4))
        sub_id = repo.create_submission(self.conn, Submission(
            exam_id=exam_id, source_file="sheet1.png", status=SubmissionStatus.QUEUED))
        results = [AnswerResult(submission_id=sub_id, question_number=i, detected_answer="A",
                                 confidence=90.0, status=AnswerStatus.HIGH_CONFIDENCE) for i in range(1, 6)]
        repo.save_answer_results(self.conn, sub_id, results)
        loaded = repo.get_answer_results(self.conn, sub_id)
        self.assertEqual(len(loaded), 5)
        self.assertEqual(loaded[0].detected_answer, "A")

    def test_review_correction_updates_final_answer(self):
        exam_id = repo.create_exam(self.conn, Exam(name="E", question_count=1, option_count=4))
        sub_id = repo.create_submission(self.conn, Submission(
            exam_id=exam_id, source_file="s.png", status=SubmissionStatus.NEEDS_REVIEW))
        repo.save_answer_results(self.conn, sub_id, [
            AnswerResult(submission_id=sub_id, question_number=1, detected_answer=None,
                         confidence=40.0, status=AnswerStatus.MULTIPLE_MARK)
        ])
        repo.apply_review_correction(self.conn, sub_id, 1, "B")
        loaded = repo.get_answer_results(self.conn, sub_id)
        self.assertEqual(loaded[0].final_answer, "B")
        self.assertEqual(loaded[0].review_status.value, "CORRECTED")

    def test_student_upsert(self):
        repo.upsert_student(self.conn, Student(student_id="1001", name="A"))
        repo.upsert_student(self.conn, Student(student_id="1001", name="B"))
        s = repo.get_student(self.conn, "1001")
        self.assertEqual(s.name, "B")  # second upsert overwrote the name

    def test_init_db_is_idempotent(self):
        init_db(self.conn)  # calling twice must not raise or duplicate schema
        init_db(self.conn)


if __name__ == "__main__":
    unittest.main()
