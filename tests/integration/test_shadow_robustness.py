import unittest
from pathlib import Path

import cv2

from app.core.config import DEFAULT_CONFIG
from app.core.models import AnswerStatus
from app.omr.pipeline import process_submission
from app.templates.schema import Template

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "resources" / "templates" / "default_100q_4opt.json"


class TestShadowRobustness(unittest.TestCase):
    """A page-wide brightness gradient (uneven lighting/shadow) must not
    produce false-positive marks, and a genuine mark drawn INSIDE the
    shadowed region must still be read correctly. This is what the
    ring/local-background-relative bubble analysis (as opposed to fixed
    global paper/ink constants) and morphological-opening-based marker
    detection are specifically for."""

    @classmethod
    def setUpClass(cls):
        cls.template = Template.load(TEMPLATE_PATH)

    def test_blank_sheet_under_shadow_gradient_has_no_false_positives(self):
        path = FIXTURES / "sample_sheet_shadow_test.png"
        if not path.exists():
            self.skipTest("shadow fixture not generated in this environment")
        img = cv2.imread(str(path))
        result = process_submission(img, self.template, cfg=DEFAULT_CONFIG)
        self.assertTrue(result.diagnostics.registration_ok)
        statuses = {a.status for a in result.answers}
        self.assertEqual(statuses, {AnswerStatus.BLANK})
        for a in result.answers:
            self.assertGreaterEqual(a.confidence, 70.0)

    def test_marks_inside_shadowed_region_are_still_detected(self):
        path = FIXTURES / "sample_sheet_shadow_with_marks.png"
        if not path.exists():
            self.skipTest("shadow+marks fixture not generated in this environment")
        img = cv2.imread(str(path))
        result = process_submission(img, self.template, cfg=DEFAULT_CONFIG)
        self.assertTrue(result.diagnostics.registration_ok)
        by_q = {a.question_number: a for a in result.answers}
        for q, expected in [(80, "C"), (95, "A")]:
            a = by_q[q]
            self.assertEqual(a.detected_answer, expected)
            self.assertEqual(a.status, AnswerStatus.HIGH_CONFIDENCE)
        blanks = sum(1 for a in result.answers if a.status == AnswerStatus.BLANK)
        self.assertEqual(blanks, 98)


if __name__ == "__main__":
    unittest.main()
