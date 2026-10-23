from unittest.mock import patch

from exams.services import ai, scoring_rules
from exams.tests.base import ApiTestBase


class ScoringRuleLibraryTests(ApiTestBase):
    def test_library_loads_and_weights_are_complete(self):
        data = scoring_rules.list_rules()
        self.assertEqual(data["versions"], {"music": "1.0.0", "art": "1.0.0"})
        subjects = {item["subject"]: item for item in data["subjects"]}
        self.assertEqual(
            {c["key"] for c in subjects["music"]["categories"]},
            {"vocal", "instrumental", "solfege", "theory"},
        )
        self.assertEqual(
            {c["key"] for c in subjects["art"]["categories"]},
            {"sketch", "color", "quick_sketch", "calligraphy", "children"},
        )
        for subject in data["subjects"]:
            self.assertEqual(len(subject["levels"]), 10)
            for category in subject["categories"]:
                total = sum(d["weight"] for d in category["dimensions"])
                self.assertAlmostEqual(total, 1.0, places=6)

    def test_list_endpoint_visible_to_all_roles(self):
        for user in (self.student, self.teacher, self.school_admin):
            response = self.api(user).get("/api/v1/scoring-rules")
            self.assertEqual(response.status_code, 200, response.content.decode())
            self.assertIn("subjects", response.json()["data"])

    def test_list_endpoint_requires_login(self):
        from rest_framework.test import APIClient

        response = APIClient().get("/api/v1/scoring-rules")
        self.assertIn(response.status_code, (401, 403))

    def test_detail_returns_level_profile_and_cutoffs(self):
        response = self.api(self.student).get(
            "/api/v1/scoring-rules/music/vocal?level=5"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["category"], "vocal")
        self.assertEqual(data["levelProfile"]["level"], 5)
        self.assertEqual(data["levelProfile"]["bandCutoffs"]["pass"], 0.60)
        self.assertEqual(len(data["dimensions"]), 5)

    def test_unknown_category_returns_404(self):
        response = self.api(self.student).get(
            "/api/v1/scoring-rules/music/unknown"
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_level_returns_400(self):
        response = self.api(self.student).get(
            "/api/v1/scoring-rules/music/vocal?level=11"
        )
        self.assertEqual(response.status_code, 400)


class ScoringRuleEvaluateTests(ApiTestBase):
    VOCAL_METRICS = {
        "pitchAccuracy": 0.9,
        "rhythmAccuracy": 0.9,
        "timbreQuality": 0.9,
        "dictionClarity": 0.9,
        "expression": 0.9,
    }

    def test_teacher_evaluates_and_gets_band(self):
        response = self.api(self.teacher).post(
            "/api/v1/scoring-rules/evaluate",
            {
                "subject": "music",
                "category": "vocal",
                "level": 5,
                "maxScore": 100,
                "metrics": self.VOCAL_METRICS,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertGreater(data["totalScore"], 0)
        self.assertEqual(data["bandLabel"], "优秀")
        self.assertEqual(data["ruleId"], "music.vocal")
        self.assertEqual(len(data["dimensions"]), 5)
        self.assertFalse(data["needsManualReview"])

    def test_student_cannot_evaluate(self):
        response = self.api(self.student).post(
            "/api/v1/scoring-rules/evaluate",
            {"subject": "music", "category": "vocal", "metrics": self.VOCAL_METRICS},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_required_metric_requires_manual_review(self):
        metrics = dict(self.VOCAL_METRICS)
        metrics.pop("pitchAccuracy")
        response = self.api(self.teacher).post(
            "/api/v1/scoring-rules/evaluate",
            {"subject": "music", "category": "vocal", "metrics": metrics},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertIsNone(data["totalScore"])
        self.assertIsNone(data["band"])
        self.assertTrue(data["needsManualReview"])
        self.assertTrue(any("pitchAccuracy" in item for item in data["warnings"]))

    def test_cap_limits_sketch_total_score(self):
        response = self.api(self.teacher).post(
            "/api/v1/scoring-rules/evaluate",
            {
                "subject": "art",
                "category": "sketch",
                "metrics": {
                    "proportionPerspective": 0.2,
                    "composition": 0.9,
                    "structureForm": 0.9,
                    "valueRelation": 0.9,
                    "technique": 0.9,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["totalScore"], 55.0)
        self.assertEqual(data["capsApplied"][0]["metric"], "proportionPerspective")
        self.assertEqual(data["bandLabel"], "不合格")

    def test_same_metrics_band_differs_by_level(self):
        level_one = scoring_rules.evaluate(
            "music", "vocal", level=1, metrics=self.VOCAL_METRICS
        )
        level_ten = scoring_rules.evaluate(
            "music", "vocal", level=10, metrics=self.VOCAL_METRICS
        )
        self.assertEqual(level_one["band"], "excellent")
        self.assertEqual(level_ten["band"], "good")
        self.assertEqual(level_one["totalScore"], level_ten["totalScore"])

    def test_low_confidence_flags_manual_review(self):
        response = self.api(self.teacher).post(
            "/api/v1/scoring-rules/evaluate",
            {
                "subject": "music",
                "category": "vocal",
                "metrics": self.VOCAL_METRICS,
                "confidence": 0.5,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertTrue(data["needsManualReview"])
        self.assertTrue(any("置信度" in item for item in data["warnings"]))

    def test_metrics_out_of_range_rejected(self):
        metrics = dict(self.VOCAL_METRICS)
        metrics["pitchAccuracy"] = 1.5
        response = self.api(self.teacher).post(
            "/api/v1/scoring-rules/evaluate",
            {"subject": "music", "category": "vocal", "metrics": metrics},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class ScoringRuleModelIntegrationTests(ApiTestBase):
    def test_infer_category_from_stem(self):
        self.assertEqual(scoring_rules.infer_category("music", "演唱《茉莉花》"), "vocal")
        self.assertEqual(scoring_rules.infer_category("art", "毛笔楷书临摹"), "calligraphy")
        self.assertIsNone(scoring_rules.infer_category("art", "完成一幅作品"))

    def test_analyze_answer_sends_rule_set(self):
        question = {
            "type": "audio_upload",
            "stem": "演唱一首歌曲",
            "ruleContext": {"category": "vocal", "level": 5},
        }
        with patch.object(ai, "_post", return_value={"score": 88}) as post:
            ai.analyze_answer(question, {"fileId": 1}, 100, subject="music")
        payload = post.call_args.args[1]
        self.assertEqual(payload["scoringRules"]["category"], "vocal")
        self.assertEqual(payload["scoringRules"]["levelProfile"]["level"], 5)
        self.assertEqual(payload["scoringRules"]["version"], "1.0.0")

    def test_model_metrics_override_raw_score(self):
        question = {
            "type": "art_score",
            "stem": "素描静物",
            "ruleContext": {"category": "sketch", "level": 5},
        }
        result = {
            "score": 95,
            "metrics": {
                "proportionPerspective": 0.2,
                "composition": 0.9,
                "structureForm": 0.9,
                "valueRelation": 0.9,
                "technique": 0.9,
            },
        }
        rule_result, category = ai._evaluate_rules("art", question, result, 100)
        self.assertEqual(category, "sketch")
        self.assertEqual(rule_result["totalScore"], 55.0)
