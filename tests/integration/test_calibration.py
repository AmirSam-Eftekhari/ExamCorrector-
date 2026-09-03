import unittest
from pathlib import Path

import cv2
import numpy as np

from app.templates.calibrate import calibrate_template_from_image
from app.templates.schema import Template
from app.cv.page_detect import detect_markers
from app.cv.registration import register
from app.core.config import DEFAULT_CONFIG

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

    def test_measured_radius_is_not_the_old_hardcoded_constant(self):
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
        # The original bug: calibration wrote the fixed expected-radius
        # search-window constant (0.009 -- see BubbleConfig.expected_radius_frac)
        # straight into the template instead of the Hough-detected circles'
        # own measured radius, so every sheet calibrated to the exact same
        # 0.009 regardless of its actual bubble size. Assert neither sheet's
        # measured radius equals that old constant -- a more direct
        # regression check than comparing the two sheets to each other,
        # since two independently-designed sheets can coincidentally end up
        # with similar (but still genuinely *measured*, not hardcoded)
        # bubble proportions.
        OLD_HARDCODED_CONSTANT = 0.009
        self.assertNotAlmostEqual(r_en, OLD_HARDCODED_CONSTANT, places=3)
        self.assertNotAlmostEqual(r_fa, OLD_HARDCODED_CONSTANT, places=3)
        # Sanity bound: neither should collapse to something implausible.
        self.assertGreater(r_en, 0.003)
        self.assertGreater(r_fa, 0.003)

    def _assert_student_id_geometry_matches_reality(self, image_path, template_path):
        img = cv2.imread(str(image_path))
        template = Template.load(str(template_path))
        canvas_size = template.canvas_size
        marker_result = detect_markers(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), DEFAULT_CONFIG.registration)
        reg = register(img, marker_result, canvas_size, cfg=DEFAULT_CONFIG.registration)
        warped_gray = cv2.cvtColor(reg.warped, cv2.COLOR_BGR2GRAY)

        sid = template.student_id
        box_x0, box_y0, box_x1, box_y1 = sid.box
        rx0, ry0 = int(box_x0 * canvas_size[0]), int(box_y0 * canvas_size[1])
        rx1, ry1 = int(box_x1 * canvas_size[0]), int(box_y1 * canvas_size[1])
        roi = warped_gray[ry0:ry1, rx0:rx1]
        circles = cv2.HoughCircles(roi, cv2.HOUGH_GRADIENT, dp=1, minDist=15,
                                    param1=60, param2=15, minRadius=6, maxRadius=10)
        self.assertIsNotNone(circles, f"no circles detected in the Student ID region ({template_path.name})")
        detected = circles[0][:, :2] + np.array([rx0, ry0])

        checked = 0
        for col in (0, sid.n_digits // 2, sid.n_digits - 1):
            for digit in (0, 5, 9):
                cx, cy = sid.bubble_center(col, digit, canvas_size)
                nearest = np.linalg.norm(detected - np.array([cx, cy]), axis=1).min()
                self.assertLess(
                    nearest, sid.bubble_radius * canvas_size[0] * 1.3,
                    f"[{template_path.name}] col={col} digit={digit}: bubble_center() is "
                    f"{nearest:.1f}px from the nearest independently-detected circle -- "
                    f"template geometry doesn't match the actual rendered sheet"
                )
                checked += 1
        self.assertEqual(checked, 9)

    def test_student_id_geometry_matches_independently_detected_circles(self):
        """A hand-measured (not auto-calibrated) region like either default
        template's student_id is never validated by the calibrator, so
        nothing else catches it if the stored numbers are simply wrong --
        confirmed the hard way, twice: the English template's geometry read
        100% confidence on every synthetic test ID while still being off by
        ~15 canvas-px on a real printed sheet, and the Persian template's
        (never previously ground-truth-checked at all) was off by as much
        as ~500px on 14 of 15 spot-checked positions. Every synthetic test
        before this one placed its marks using template.student_id.bubble_
        center() and then read them back with the same function, which
        trivially "passes" even when the stored geometry doesn't correspond
        to where the sheet was actually rendered -- self-consistent, but
        never checked against reality. This test breaks that circularity:
        it detects the bubble circles directly via Hough (independent of
        the template's own claimed positions) and asserts bubble_center()
        lands inside a real detected circle, for both shipped templates."""
        templates_dir = FIXTURE.parent.parent.parent / "resources" / "templates"
        self._assert_student_id_geometry_matches_reality(FIXTURE, templates_dir / "default_100q_4opt.json")
        if FIXTURE_FA.exists():
            self._assert_student_id_geometry_matches_reality(FIXTURE_FA, templates_dir / "default_100q_4opt_fa.json")


if __name__ == "__main__":
    unittest.main()
