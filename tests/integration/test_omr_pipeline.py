import unittest
from pathlib import Path

import cv2

from app.core.models import AnswerStatus, SubmissionStatus
from app.omr.pipeline import process_submission
from app.templates.schema import Template

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "resources" / "templates" / "default_100q_4opt.json"


class TestOmrPipelineOnBlankSheet(unittest.TestCase):
    """A completely unmarked sheet must never produce a false-positive answer."""

    @classmethod
    def setUpClass(cls):
        cls.template = Template.load(TEMPLATE_PATH)
        img = cv2.imread(str(FIXTURES / "sample_sheet_blank.png"))
        cls.result = process_submission(img, cls.template)

    def test_registration_succeeds(self):
        self.assertTrue(self.result.diagnostics.registration_ok)

    def test_all_100_questions_are_blank(self):
        self.assertEqual(len(self.result.answers), 100)
        for a in self.result.answers:
            self.assertEqual(a.status, AnswerStatus.BLANK)
            self.assertIsNone(a.detected_answer)

    def test_blank_confidence_is_reasonably_high_and_not_flagged(self):
        # A clean, unambiguous blank shouldn't need a human to double check it.
        for a in self.result.answers:
            self.assertGreaterEqual(a.confidence, 55.0)


class TestOmrPipelineOnMarkedSheet(unittest.TestCase):
    """Fixture has known synthetic marks; verify each is classified correctly.
    See scripts used to generate: single marks (Q1,Q5,Q100), a genuine blank
    (Q2), and two options marked with comparable strength (Q3)."""

    @classmethod
    def setUpClass(cls):
        cls.template = Template.load(TEMPLATE_PATH)
        img = cv2.imread(str(FIXTURES / "sample_sheet_synthetic_marked.png"))
        cls.result = process_submission(img, cls.template)
        cls.by_q = {a.question_number: a for a in cls.result.answers}

    def test_clear_single_marks_are_high_confidence_and_correct(self):
        for q, expected in [(1, "B"), (5, "D"), (100, "A")]:
            a = self.by_q[q]
            self.assertEqual(a.detected_answer, expected)
            self.assertEqual(a.status, AnswerStatus.HIGH_CONFIDENCE)
            self.assertGreaterEqual(a.confidence, 80.0)

    def test_untouched_question_is_blank(self):
        a = self.by_q[2]
        self.assertEqual(a.status, AnswerStatus.BLANK)
        self.assertIsNone(a.detected_answer)

    def test_two_marked_options_yield_multiple_mark_not_a_guess(self):
        a = self.by_q[3]
        self.assertEqual(a.status, AnswerStatus.MULTIPLE_MARK)
        self.assertIsNone(a.detected_answer)

    def test_marked_questions_do_not_bleed_into_neighbours(self):
        # Q1 was marked; Q2's own bubbles must still read as untouched.
        self.assertIsNone(self.by_q[2].detected_answer)
        # unrelated block/question far away from any mark stays blank too
        self.assertEqual(self.by_q[50].status, AnswerStatus.BLANK)

    def test_name_field_extracted_when_present(self):
        name_field = next((t for t in self.result.text_fields if t.name == "Name"), None)
        self.assertIsNotNone(name_field)
        self.assertEqual(name_field.status, "READ")
        # Regression test for a real bug: the calibrated OCR crop used to be
        # only ~22-34px tall with zero horizontal margin, which reliably
        # clipped the first character(s) of a real name ("John Smith" came
        # back as "wn smith") and sometimes returned nothing readable at
        # all. Now checks the exact text, not just "something non-None".
        self.assertEqual(name_field.text, "Amirsam Eftekharinia")

    def test_untouched_text_fields_reported_as_unreadable_not_fabricated(self):
        date_field = next((t for t in self.result.text_fields if t.name == "Date"), None)
        self.assertIsNotNone(date_field)
        self.assertIn(date_field.status, ("UNREADABLE", "EMPTY"))
        self.assertIsNone(date_field.text)


class TestOmrPipelineLowConfidenceAndShadow(unittest.TestCase):
    """Fixture has a very faint mark (Q7) and a uniformly-shadowed row (Q8)."""

    @classmethod
    def setUpClass(cls):
        cls.template = Template.load(TEMPLATE_PATH)
        img = cv2.imread(str(FIXTURES / "sample_sheet_lowconf_test.png"))
        cls.result = process_submission(img, cls.template)
        cls.by_q = {a.question_number: a for a in cls.result.answers}

    def test_shadowed_row_is_not_silently_guessed_as_high_confidence(self):
        a = self.by_q[8]
        self.assertIn(a.status, (AnswerStatus.LOW_CONFIDENCE, AnswerStatus.MULTIPLE_MARK, AnswerStatus.AMBIGUOUS))
        self.assertLess(a.confidence, 70.0)


if __name__ == "__main__":
    unittest.main()
