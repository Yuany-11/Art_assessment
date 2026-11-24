"""客观题判分规则：多选题部分给分、错选零分、音频选择判断题自动判分。"""
from django.test import SimpleTestCase

from apps.exams.services.attempt import grade_objective
from common.enums import QuestionType


class MultiSelectScoringTests(SimpleTestCase):
    def setUp(self):
        self.question = {
            "type": QuestionType.MULTIPLE_CHOICE,
            "scoringMode": "auto",
            "score": 10,
            "answer": {"values": ["A", "C"]},
            "partialCredit": True,
        }

    def test_exact_match_gets_full_score(self):
        score, correct, graded = grade_objective(
            self.question, {"values": ["C", "A"]}
        )
        self.assertEqual(score, 10)
        self.assertTrue(correct)
        self.assertTrue(graded)

    def test_subset_gets_partial_score(self):
        score, correct, graded = grade_objective(self.question, {"values": ["A"]})
        self.assertEqual(score, 5)
        self.assertFalse(correct)
        self.assertTrue(graded)

    def test_extra_wrong_option_gets_zero(self):
        score, correct, graded = grade_objective(
            self.question, {"values": ["A", "B"]}
        )
        self.assertEqual(score, 0)
        self.assertFalse(correct)
        self.assertTrue(graded)

    def test_unanswered_gets_zero(self):
        score, correct, graded = grade_objective(self.question, {"values": []})
        self.assertEqual(score, 0)
        self.assertFalse(correct)
        self.assertTrue(graded)

    def test_partial_credit_can_be_disabled(self):
        question = {**self.question, "partialCredit": False}
        score, correct, graded = grade_objective(question, {"values": ["A"]})
        self.assertEqual(score, 0)
        self.assertFalse(correct)
        self.assertTrue(graded)


class AudioChoiceJudgeScoringTests(SimpleTestCase):
    def test_audio_choice_judge_is_objective(self):
        question = {
            "type": QuestionType.AUDIO_CHOICE_JUDGE,
            "scoringMode": "auto",
            "score": 5,
            "answer": {"value": "B"},
        }
        score, correct, graded = grade_objective(question, {"value": "b"})
        self.assertEqual(score, 5)
        self.assertTrue(correct)
        self.assertTrue(graded)
