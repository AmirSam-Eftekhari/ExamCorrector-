import tempfile
import unittest
from pathlib import Path

from app.database.db import connect, init_db
from app.database import repository as repo
from app.core.models import AnswerResult, AnswerStatus, Exam, ScoringRule, Submission, SubmissionStatus
from app.export.pdf_export import generate_exam_report_pdf


class TestPdfExport(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.sqlite3"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.exam = Exam(name="PDF Test Exam", subject="Biology", question_count=2, option_count=4)
        self.exam.id = repo.create_exam(self.conn, self.exam)
        repo.set_answer_key(self.conn, self.exam.id, {1: "A", 2: "B"})

    def tearDown(self):
        self.conn.close()
        self._tmpdir.cleanup()

    def test_produces_a_valid_pdf_with_no_submissions(self):
        data = generate_exam_report_pdf(self.conn, self.exam)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 500)

    def test_produces_a_valid_pdf_with_real_data(self):
        sub_id = repo.create_submission(self.conn, Submission(
            exam_id=self.exam.id, source_file="s1.png", student_id_detected="2002",
            student_name_detected="Test Learner", status=SubmissionStatus.COMPLETED,
            score=1.0, percentage=50.0))
        repo.save_answer_results(self.conn, sub_id, [
            AnswerResult(sub_id, 1, "A", 92.0, AnswerStatus.HIGH_CONFIDENCE),
            AnswerResult(sub_id, 2, "C", 88.0, AnswerStatus.HIGH_CONFIDENCE),
        ])
        data = generate_exam_report_pdf(self.conn, self.exam)
        self.assertTrue(data.startswith(b"%PDF"))

        # Actually parse the PDF (content streams are compressed, so a raw
        # byte search won't find real text) and confirm the student's own
        # data made it into the rendered report, not a static template.
        from pypdf import PdfReader
        import io as _io
        reader = PdfReader(_io.BytesIO(data))
        full_text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Test Learner", full_text)
        self.assertIn("2002", full_text)
        self.assertIn("PDF Test Exam", full_text)


if __name__ == "__main__":
    unittest.main()
