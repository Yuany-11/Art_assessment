"""音乐作品 AI 建议分：0–100 参考分折算到题目满分，且不写成绩。"""
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.exams.services.ai_scoring import build_suggestion
from common.enums import QuestionType


def _row(max_score=20.0, score=None):
    return SimpleNamespace(question_id=101, max_score=max_score, score=score)


def _tags(raw=85.0, status="completed", **extra):
    data = {
        "status": status,
        "referenceScore": raw,
        "referenceGrade": "良好",
        "genreConfidence": 0.6,
        "emotionConfidence": 0.5,
        "modeConfidence": 0.55,
        "disclaimer": "仅供教学参考",
    }
    data.update(extra)
    return data


SNAPSHOT = {"type": QuestionType.AUDIO_UPLOAD}


class AiSuggestionConversionTests(SimpleTestCase):
    def test_reference_score_converted_to_question_max_score(self):
        suggestion = build_suggestion(_row(max_score=20.0), SNAPSHOT, _tags(85.0))
        self.assertEqual(suggestion["suggestedScore"], 17.0)
        self.assertEqual(suggestion["maxScore"], 20.0)
        self.assertEqual(suggestion["rawScore"], 85.0)

    def test_decimal_max_score_rounds_to_two_places(self):
        suggestion = build_suggestion(_row(max_score=16.65), SNAPSHOT, _tags(83.9))
        self.assertEqual(suggestion["suggestedScore"], 13.97)

    def test_score_is_clipped_to_max_score(self):
        suggestion = build_suggestion(_row(max_score=10.0), SNAPSHOT, _tags(140.0))
        self.assertEqual(suggestion["suggestedScore"], 10.0)

    def test_negative_reference_is_clipped_to_zero(self):
        suggestion = build_suggestion(_row(max_score=10.0), SNAPSHOT, _tags(-5.0))
        self.assertEqual(suggestion["suggestedScore"], 0.0)

    def test_pending_analysis_has_no_score(self):
        suggestion = build_suggestion(
            _row(), SNAPSHOT, _tags(raw=None, status="pending")
        )
        self.assertIsNone(suggestion["suggestedScore"])
        self.assertEqual(suggestion["status"], "pending")
        self.assertTrue(suggestion["needsReview"])

    def test_missing_file_is_reported(self):
        suggestion = build_suggestion(_row(), SNAPSHOT, None)
        self.assertEqual(suggestion["status"], "missing")
        self.assertIsNone(suggestion["suggestedScore"])

    def test_non_audio_question_has_no_suggestion(self):
        suggestion = build_suggestion(
            _row(), {"type": QuestionType.IMAGE_UPLOAD}, _tags()
        )
        self.assertIsNone(suggestion)

    @override_settings(AI_SCORE_CONFIDENCE_THRESHOLD=0.9)
    def test_low_confidence_flags_manual_review_without_lowering_score(self):
        suggestion = build_suggestion(_row(max_score=20.0), SNAPSHOT, _tags(80.0))
        self.assertTrue(suggestion["needsReview"])
        # 置信度只影响复核提示，不影响折算后的建议分。
        self.assertEqual(suggestion["suggestedScore"], 16.0)

    @override_settings(AI_SCORE_CONFIDENCE_THRESHOLD=0.4)
    def test_high_confidence_does_not_flag_review(self):
        suggestion = build_suggestion(_row(max_score=20.0), SNAPSHOT, _tags(80.0))
        self.assertFalse(suggestion["needsReview"])

    def test_suggestion_does_not_write_teacher_score(self):
        row = _row(max_score=20.0, score=15.0)
        build_suggestion(row, SNAPSHOT, _tags(90.0))
        self.assertEqual(row.score, 15.0)
