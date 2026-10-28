from datetime import date, timedelta

from django.utils import timezone

from common.enums import (
    CertificateStatus,
    GradingStatus,
    Level,
    PaperType,
    Subject,
)
from apps.exams.models import Certificate, Score
from apps.exams.tests.base import ApiTestBase


class TotalScoreRuleApiTests(ApiTestBase):
    def setUp(self):
        self.practice = self.make_assessment(
            paper=self.make_paper(
                paper_type=PaperType.PRACTICE, title="平时练习卷一"
            ),
            title="平时练习测评一",
        )
        self.practice2 = self.make_assessment(
            paper=self.make_paper(
                paper_type=PaperType.PRACTICE, title="平时练习卷二"
            ),
            title="平时练习测评二",
        )
        self.formal = self.make_assessment(
            paper=self.make_paper(
                paper_type=PaperType.FORMAL, title="期末测评卷"
            ),
            title="期末测评",
        )

    # ------------------------------------------------------------------
    # 夹具
    # ------------------------------------------------------------------
    def create_rule(self, **overrides):
        payload = {
            "name": "音乐学期总评",
            "subject": Subject.MUSIC,
            "classId": self.classroom.id,
        }
        payload.update(overrides)
        response = self.api(self.teacher).post(
            "/api/v1/total-score-rules", payload, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        return response.json()["data"]

    def add_score(self, student, assessment, total, max_score=100, days_ago=0):
        score = Score.objects.create(
            assessment=assessment,
            subject=assessment.subject,
            student=student,
            student_name=student.real_name,
            student_no=student.student_no or "",
            classroom=self.classroom,
            class_name=self.classroom.name,
            school=self.school,
            school_name=self.school.name,
            grade=7,
            total_score=total,
            max_score=max_score,
            status=GradingStatus.GRADED,
        )
        if days_ago:
            Score.objects.filter(pk=score.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
        return score

    def add_certificate(self, student, assessment, level=Level.EXCELLENT):
        return Certificate.objects.create(
            certificate_no=f"CERT-{student.id}-{assessment.id}",
            student=student,
            student_name=student.real_name,
            assessment=assessment,
            subject=assessment.subject,
            classroom=self.classroom,
            class_name=self.classroom.name,
            school=self.school,
            school_name=self.school.name,
            score=95,
            level=level,
            issue_date=date(2026, 6, 1),
            status=CertificateStatus.READY,
        )

    def results(self, rule_id, **params):
        response = self.api(self.teacher).get(
            f"/api/v1/total-score-rules/{rule_id}/results", params
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        return response.json()["data"]

    def student_row(self, data, student):
        return next(
            row for row in data["students"] if row["studentId"] == student.id
        )

    # ------------------------------------------------------------------
    # 规则配置
    # ------------------------------------------------------------------
    def test_create_rule_uses_defaults(self):
        rule = self.create_rule()
        self.assertEqual(rule["weights"], {
            "usual": 0.4, "formal": 0.4, "certificate": 0.2,
        })
        self.assertEqual(rule["aggregation"]["certificate"], "best")
        self.assertEqual(rule["missingPolicy"], "renormalize")
        self.assertEqual(rule["status"], "draft")
        self.assertEqual(rule["version"], 1)
        self.assertEqual(rule["className"], self.classroom.name)

    def test_weights_must_sum_to_one(self):
        response = self.api(self.teacher).post(
            "/api/v1/total-score-rules",
            {
                "name": "错误权重",
                "subject": Subject.MUSIC,
                "classId": self.classroom.id,
                "usualWeight": 0.5,
                "formalWeight": 0.5,
                "certificateWeight": 0.2,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("权重之和", response.json()["message"])

    def test_only_teaching_class_allowed(self):
        response = self.api(self.teacher).post(
            "/api/v1/total-score-rules",
            {
                "name": "越权规则",
                "subject": Subject.MUSIC,
                "classId": self.classroom2.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_update_bumps_version(self):
        rule = self.create_rule()
        response = self.api(self.teacher).patch(
            f"/api/v1/total-score-rules/{rule['id']}",
            {"usualWeight": 0.5, "formalWeight": 0.3, "certificateWeight": 0.2},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["weights"]["usual"], 0.5)
        self.assertEqual(data["version"], 2)

    def test_other_teacher_cannot_read_rule(self):
        rule = self.create_rule()
        response = self.api(self.other_teacher).get(
            f"/api/v1/total-score-rules/{rule['id']}"
        )
        self.assertEqual(response.status_code, 403)
        listing = self.api(self.other_teacher).get("/api/v1/total-score-rules")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["data"]["total"], 0)

    def test_student_cannot_manage_rules(self):
        response = self.api(self.student).get("/api/v1/total-score-rules")
        self.assertEqual(response.status_code, 403)

    def test_publish_archives_previous_published_rule(self):
        first = self.create_rule(name="第一版")
        response = self.api(self.teacher).post(
            f"/api/v1/total-score-rules/{first['id']}/publish", {}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()["data"]["status"], "published")

        second = self.create_rule(name="第二版")
        response = self.api(self.teacher).post(
            f"/api/v1/total-score-rules/{second['id']}/publish", {}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())

        first_after = self.api(self.teacher).get(
            f"/api/v1/total-score-rules/{first['id']}"
        ).json()["data"]
        self.assertEqual(first_after["status"], "archived")
        self.assertEqual(response.json()["data"]["status"], "published")

    def test_delete_archives_rule(self):
        rule = self.create_rule()
        response = self.api(self.teacher).delete(
            f"/api/v1/total-score-rules/{rule['id']}"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        listing = self.api(self.teacher).get("/api/v1/total-score-rules")
        self.assertEqual(listing.json()["data"]["total"], 0)
        listing = self.api(self.teacher).get(
            "/api/v1/total-score-rules", {"includeArchived": "true"}
        )
        self.assertEqual(listing.json()["data"]["total"], 1)

    # ------------------------------------------------------------------
    # 总评计算
    # ------------------------------------------------------------------
    def test_weighted_total_uses_usual_formal_and_certificate(self):
        rule = self.create_rule()
        self.add_score(self.student, self.practice, 80)
        self.add_score(self.student, self.practice2, 90)
        self.add_score(self.student, self.formal, 70)
        self.add_certificate(self.student, self.formal)

        data = self.results(rule["id"])
        row = self.student_row(data, self.student)
        self.assertEqual(row["totalScore"], 81.0)
        self.assertEqual(row["level"], "good")
        components = {item["key"]: item for item in row["components"]}
        self.assertEqual(components["usual"]["score"], 85.0)
        self.assertEqual(components["formal"]["score"], 70.0)
        self.assertEqual(components["certificate"]["score"], 95.0)
        self.assertEqual(components["usual"]["contribution"], 34.0)
        self.assertEqual(components["certificate"]["contribution"], 19.0)
        self.assertEqual(data["summary"]["studentCount"], 3)
        self.assertEqual(data["summary"]["computedCount"], 1)
        self.assertEqual(data["summary"]["incompleteCount"], 2)

    def test_missing_certificate_renormalizes_by_default(self):
        rule = self.create_rule()
        self.add_score(self.student, self.practice, 80)
        self.add_score(self.student, self.formal, 70)

        row = self.student_row(self.results(rule["id"]), self.student)
        self.assertEqual(row["totalScore"], 75.0)
        components = {item["key"]: item for item in row["components"]}
        self.assertFalse(components["certificate"]["available"])
        self.assertIsNone(components["certificate"]["score"])
        self.assertTrue(any("证书" in item for item in row["warnings"]))

    def test_missing_policy_zero_counts_as_zero(self):
        rule = self.create_rule(missingPolicy="zero")
        self.add_score(self.student, self.practice, 80)
        self.add_score(self.student, self.formal, 70)

        row = self.student_row(self.results(rule["id"]), self.student)
        self.assertEqual(row["totalScore"], 60.0)
        self.assertEqual(row["level"], "pass")

    def test_aggregation_best_and_latest(self):
        best_rule = self.create_rule(name="最高分", usualAggregation="best")
        latest_rule = self.create_rule(name="最近一次", usualAggregation="latest")
        self.add_score(self.student, self.practice, 90, days_ago=2)
        self.add_score(self.student, self.practice2, 60, days_ago=1)
        self.add_score(self.student, self.formal, 70)
        self.add_certificate(self.student, self.formal)

        best = self.student_row(self.results(best_rule["id"]), self.student)
        latest = self.student_row(self.results(latest_rule["id"]), self.student)
        best_components = {item["key"]: item for item in best["components"]}
        latest_components = {item["key"]: item for item in latest["components"]}
        self.assertEqual(best_components["usual"]["score"], 90.0)
        self.assertEqual(latest_components["usual"]["score"], 60.0)

    def test_custom_level_lines(self):
        rule = self.create_rule(excellentLine=95, goodLine=90, passLine=60)
        self.add_score(self.student, self.practice, 80)
        self.add_score(self.student, self.formal, 70)
        self.add_certificate(self.student, self.formal)

        row = self.student_row(self.results(rule["id"]), self.student)
        self.assertEqual(row["totalScore"], 79.0)
        self.assertEqual(row["level"], "pass")

    def test_results_filter_by_student_keyword(self):
        rule = self.create_rule()
        self.add_score(self.student, self.practice, 80)
        self.add_score(self.student, self.formal, 70)
        self.add_certificate(self.student, self.formal)

        data = self.results(rule["id"], studentKeyword="王")
        self.assertEqual(len(data["students"]), 1)
        self.assertEqual(data["students"][0]["studentName"], "王小明")

    def test_certificate_level_scores_are_configurable(self):
        rule = self.create_rule(
            certificateLevelScores={
                "excellent": 100, "good": 80, "pass": 60, "fail": 40,
            }
        )
        self.add_score(self.student, self.practice, 80)
        self.add_score(self.student, self.formal, 70)
        self.add_certificate(self.student, self.formal, level=Level.GOOD)

        row = self.student_row(self.results(rule["id"]), self.student)
        components = {item["key"]: item for item in row["components"]}
        self.assertEqual(components["certificate"]["score"], 80.0)
