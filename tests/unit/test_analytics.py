import tempfile
import unittest
from pathlib import Path

from app.analytics.engine import compute_exam_stats, compute_question_stats
from app.database.db import connect, init_db
from app.database import repository as repo
from app.core.models import AnswerResult, AnswerStatus, Exam, Submission, SubmissionStatus


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.sqlite3"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.exam_id = repo.create_exam(self.conn, Exam(name="E", question_count=3, option_count=4))
        repo.set_answer_key(self.conn, self.exam_id, {1: "A", 2: "B", 3: "C"})

    def tearDown(self):
        self.conn.close()
        self._tmpdir.cleanup()

    def _add_submission(self, percentage, answers):
        sub_id = repo.create_submission(self.conn, Submission(
            exam_id=self.exam_id, source_file=f"s{percentage}.png",
            status=SubmissionStatus.COMPLETED, score=percentage / 100 * 3, percentage=percentage,
        ))
        repo.save_answer_results(self.conn, sub_id, answers)
        return sub_id

    def test_exam_stats_empty(self):
        stats = compute_exam_stats(self.conn, self.exam_id)
        self.assertEqual(stats.n_submissions, 0)
        self.assertIsNone(stats.average)

    def test_exam_stats_basic(self):
        self._add_submission(100.0, [
            AnswerResult(1, 1, "A", 95, AnswerStatus.HIGH_CONFIDENCE),
            AnswerResult(1, 2, "B", 95, AnswerStatus.HIGH_CONFIDENCE),
            AnswerResult(1, 3, "C", 95, AnswerStatus.HIGH_CONFIDENCE),
        ])
        self._add_submission(0.0, [
            AnswerResult(1, 1, "D", 90, AnswerStatus.HIGH_CONFIDENCE),
            AnswerResult(1, 2, "D", 90, AnswerStatus.HIGH_CONFIDENCE),
            AnswerResult(1, 3, "D", 90, AnswerStatus.HIGH_CONFIDENCE),
        ])
        stats = compute_exam_stats(self.conn, self.exam_id)
        self.assertEqual(stats.n_submissions, 2)
        self.assertEqual(stats.average, 50.0)
        self.assertEqual(stats.minimum, 0.0)
        self.assertEqual(stats.maximum, 100.0)
        total_bucketed = sum(n for _, n in stats.distribution)
        self.assertEqual(total_bucketed, 2)

    def test_question_stats_correct_wrong_blank_multiple(self):
        self._add_submission(100.0, [
            AnswerResult(1, 1, "A", 95, AnswerStatus.HIGH_CONFIDENCE),   # correct
            AnswerResult(1, 2, "A", 95, AnswerStatus.HIGH_CONFIDENCE),   # wrong (key is B)
            AnswerResult(1, 3, None, 80, AnswerStatus.BLANK),            # blank
        ])
        self._add_submission(0.0, [
            AnswerResult(2, 1, None, 90, AnswerStatus.MULTIPLE_MARK),    # multiple
            AnswerResult(2, 2, "B", 90, AnswerStatus.HIGH_CONFIDENCE),   # correct
            AnswerResult(2, 3, "C", 90, AnswerStatus.HIGH_CONFIDENCE),   # correct
        ])
        stats = {s.question_number: s for s in compute_question_stats(self.conn, self.exam_id)}
        self.assertEqual(stats[1].correct_pct, 50.0)   # 1/2 correct
        self.assertEqual(stats[1].multiple_pct, 50.0)  # 1/2 multiple
        self.assertEqual(stats[2].correct_pct, 50.0)   # 1/2 correct, 1/2 wrong
        self.assertEqual(stats[2].wrong_pct, 50.0)
        self.assertEqual(stats[3].correct_pct, 50.0)   # 1/2 correct, 1/2 blank
        self.assertEqual(stats[3].blank_pct, 50.0)

    def test_human_correction_reflected_in_question_stats(self):
        sub_id = self._add_submission(0.0, [
            AnswerResult(1, 1, None, 90, AnswerStatus.MULTIPLE_MARK),
            AnswerResult(1, 2, "B", 90, AnswerStatus.HIGH_CONFIDENCE),
            AnswerResult(1, 3, "C", 90, AnswerStatus.HIGH_CONFIDENCE),
        ])
        repo.apply_review_correction(self.conn, sub_id, 1, "A")
        stats = {s.question_number: s for s in compute_question_stats(self.conn, self.exam_id)}
        self.assertEqual(stats[1].correct_pct, 100.0)
        self.assertEqual(stats[1].multiple_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
