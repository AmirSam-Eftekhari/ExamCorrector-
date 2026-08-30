import unittest
from pathlib import Path

import cv2

from app.templates.calibrate import calibrate_template_from_image

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_sheet_blank.png"
FIXTURE_FA = Path(__file__).resolve().parents[1] / "fixtures" / "sample_sheet_blank_fa.png"


class TestCalibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        img = cv2.imread(str(FIXTURE))
        assert img is not None, f"fixture missing: {FIXTURE}"
        cls.template, cls.report = calibrate_template_from_image(img, name="test-template")

    def test_calibration_succeeds(self):
        self.assertTrue(self.report.ok)
        self.assertIsNotNone(self.template)

    def test_registration_is_exact_on_the_calibration_source(self):
        # Registering the same image the markers were measured from should
        # have ~zero reprojection error.
        self.assertLess(self.report.reprojection_error_px, 1.0)

    def test_finds_all_100_questions_in_4_blocks_of_25(self):
        self.assertEqual(self.template.question_count, 100)
        self.assertEqual(len(self.template.blocks), 4)
        for block in self.template.blocks:
            self.assertEqual(block.question_count, 25)
            self.assertEqual(block.option_labels, ["A", "B", "C", "D"])

    def test_question_numbering_is_contiguous_and_ordered(self):
        expected_ranges = [(1, 25), (26, 50), (51, 75), (76, 100)]
        actual = [(b.question_start, b.question_end) for b in self.template.blocks]
        self.assertEqual(actual, expected_ranges)

    def test_student_id_region_detected_with_plausible_geometry(self):
        sid = self.template.student_id
        self.assertTrue(sid.present)
        self.assertTrue(sid.needs_confirmation)  # must always require human confirmation
        self.assertGreaterEqual(sid.n_digits, 2)
        self.assertLessEqual(sid.n_digits, 12)

    def test_text_fields_detected(self):
        names = {f.name for f in self.template.text_fields}
        # OCR of the printed labels should recover at least these common ones
        self.assertIn("Name", names)
        self.assertIn("Class", names)
        self.assertIn("Date", names)

    def test_template_round_trips_through_json(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.json"
            self.template.save(path)
            from app.templates.schema import Template
            loaded = Template.load(path)
            self.assertEqual(loaded.question_count, self.template.question_count)
            self.assertEqual(len(loaded.blocks), len(self.template.blocks))


class TestCalibrationMeasuresActualBubbleRadius(unittest.TestCase):
    """Regression test for a real bug: calibration used to write the fixed
    expected-radius search-window constant straight into the template
    instead of the Hough-detected circles' own measured radius. That made
    every calibration report the same ~0.009 fraction regardless of the
    sheet's actual bubble size -- harmless for the original sheet (whose
    bubbles happen to be close to that constant) but silently corrupting
    the ring-relative darkness geometry for any sheet with different
    proportions, discovered when a Persian-language sheet with visibly
    smaller bubbles still calibrated to the same fixed radius.
    """

    def test_two_sheets_with_different_bubble_sizes_get_different_radii(self):
        if not FIXTURE_FA.exists():
            self.skipTest("Persian fixture not present in this checkout")
        img_en = cv2.imread(str(FIXTURE))
        img_fa = cv2.imread(str(FIXTURE_FA))
        template_en, report_en = calibrate_template_from_image(img_en, name="en")
        template_fa, report_fa = calibrate_template_from_image(img_fa, name="fa")
        self.assertTrue(report_en.ok)
        self.assertTrue(report_fa.ok)

        r_en = template_en.blocks[0].bubble_radius
        r_fa = template_fa.blocks[0].bubble_radius
        # These two sheets have genuinely different bubble sizes -- a
        # regression to the fixed-constant bug would make r_en == r_fa
        # exactly, every time.
        self.assertNotAlmostEqual(r_en, r_fa, places=3)
        # Sanity bound: neither should collapse to something implausible.
        self.assertGreater(r_en, 0.003)
        self.assertGreater(r_fa, 0.003)


if __name__ == "__main__":
    unittest.main()
