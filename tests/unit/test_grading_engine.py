import unittest

from app.core.models import AnswerResult, AnswerStatus, ScoringRule
from app.grading.engine import grade_submission


def _mk(q, ans, status=AnswerStatus.HIGH_CONFIDENCE, conf=90.0):
    return AnswerResult(submission_id=1, question_number=q, detected_answer=ans, confidence=conf, status=status)


class TestGradingEngine(unittest.TestCase):
    def test_basic_correct_wrong_blank_multiple(self):
        answers = [
            _mk(1, "A"),
            _mk(2, "B"),
            _mk(3, None, AnswerStatus.BLANK),
            _mk(4, None, AnswerStatus.MULTIPLE_MARK),
            _mk(5, "C"),
        ]
        key = {1: "A", 2: "A", 3: "A", 4: "A", 5: "C"}
        rule = ScoringRule(correct=1.0, wrong=-0.25, blank=0.0, multiple_mark_policy="wrong")
        grade = grade_submission(answers, key, rule)
        self.assertEqual(grade.correct, 2)
        self.assertEqual(grade.wrong, 1)
        self.assertEqual(grade.blank, 1)
        self.assertEqual(grade.multiple_or_invalid, 1)
        self.assertAlmostEqual(grade.total_score, 1.0 - 0.25 + 0.0 - 0.25 + 1.0)

    def test_is_deterministic(self):
        answers = [_mk(i, "A") for i in range(1, 21)]
        key = {i: "A" for i in range(1, 21)}
        rule = ScoringRule()
        g1 = grade_submission(answers, key, rule)
        g2 = grade_submission(answers, key, rule)
        self.assertEqual(g1.total_score, g2.total_score)
        self.assertEqual(g1.per_question, g2.per_question)

    def test_multiple_mark_manual_review_policy_withholds_score(self):
        answers = [_mk(1, None, AnswerStatus.MULTIPLE_MARK)]
        key = {1: "A"}
        rule = ScoringRule(multiple_mark_policy="manual_review")
        grade = grade_submission(answers, key, rule)
        self.assertEqual(grade.unscored_pending_review, 1)
        self.assertEqual(grade.total_score, 0.0)

    def test_human_correction_overrides_automated_status(self):
        a = _mk(1, None, AnswerStatus.MULTIPLE_MARK)
        a.final_answer = "A"
        key = {1: "A"}
        grade = grade_submission([a], key, ScoringRule(correct=1.0))
        self.assertEqual(grade.correct, 1)
        self.assertEqual(grade.total_score, 1.0)

    def test_multi_correct_answer_key_any_of(self):
        answers = [_mk(1, "B")]
        key = {1: "A,B"}
        grade = grade_submission(answers, key, ScoringRule(correct=1.0))
        self.assertEqual(grade.correct, 1)

    def test_question_missing_from_key_is_skipped_not_fabricated(self):
        answers = [_mk(1, "A"), _mk(2, "B")]
        key = {1: "A"}  # question 2 has no key entry
        grade = grade_submission(answers, key, ScoringRule(correct=1.0))
        self.assertEqual(grade.max_score, 1.0)
        self.assertEqual(len(grade.per_question), 1)


if __name__ == "__main__":
    unittest.main()
