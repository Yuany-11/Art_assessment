import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from common.enums import ShowAnswerMode
from exams.models import Score
from exams.tests.base import ApiTestBase


class ScoreApiTests(ApiTestBase):
    def setUp(self):
        self.assessment = self.make_assessment(showAnswerMode=ShowAnswerMode.AFTER_END)
        self.attempt_id = self.start_attempt()
        self.submit_all_correct(self.attempt_id)
        self.teacher_client = self.api(self.teacher)
        self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 18}],
             "finalize": True, "version": 0},
            format="json",
        )
        self.score = Score.objects.get(attempt_id=self.attempt_id)

    def test_my_scores(self):
        response = self.api(self.student).get("/api/v1/scores/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)
        self.assertEqual(response.json()["data"]["list"][0]["totalScore"], 58)

    def test_student_cannot_use_score_list(self):
        response = self.api(self.student).get("/api/v1/scores")
        self.assertEqual(response.status_code, 403)

    def test_question_admin_cannot_access_scores(self):
        client = self.api(self.question_admin)
        self.assertEqual(client.get("/api/v1/scores").status_code, 403)
        self.assertEqual(client.get(f"/api/v1/scores/{self.score.id}").status_code, 403)
        response = client.get("/api/v1/scores/statistics?dimension=class&targetId=1")
        self.assertEqual(response.status_code, 403)

    def test_score_detail_answer_hidden_until_end(self):
        client = self.api(self.student)
        response = client.get(f"/api/v1/scores/{self.score.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertFalse(data["answerVisible"])
        self.assertTrue(all(item["correctAnswer"] is None for item in data["answerDetails"]))
        self.assertTrue(all(item["analysis"] is None for item in data["answerDetails"]))

        self.assessment.end_time = timezone.now() - timedelta(minutes=1)
        self.assessment.save(update_fields=["end_time"])
        data = client.get(f"/api/v1/scores/{self.score.id}").json()["data"]
        self.assertTrue(data["answerVisible"])
        self.assertIsNotNone(data["answerDetails"][0]["correctAnswer"])

    def test_answer_visible_after_submit_mode(self):
        assessment = self.make_assessment(showAnswerMode=ShowAnswerMode.AFTER_SUBMIT)
        attempt_id = self.start_attempt(student=self.student2, assessment=assessment)
        self.submit_all_correct(attempt_id, student=self.student2)
        score = Score.objects.get(attempt_id=attempt_id)
        data = self.api(self.student2).get(
            f"/api/v1/scores/{score.id}"
        ).json()["data"]
        self.assertTrue(data["answerVisible"])

    def test_never_show_answer_even_after_end(self):
        assessment = self.make_assessment(showAnswerMode=ShowAnswerMode.NEVER)
        attempt_id = self.start_attempt(student=self.student2, assessment=assessment)
        self.submit_all_correct(attempt_id, student=self.student2)
        assessment.end_time = timezone.now() - timedelta(minutes=1)
        assessment.save(update_fields=["end_time"])
        score = Score.objects.get(attempt_id=attempt_id)
        data = self.api(self.student2).get(
            f"/api/v1/scores/{score.id}"
        ).json()["data"]
        self.assertFalse(data["answerVisible"])

    def test_student_cannot_read_other_score(self):
        response = self.api(self.student2).get(f"/api/v1/scores/{self.score.id}")
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_list_scores_in_scope(self):
        response = self.teacher_client.get("/api/v1/scores")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)
        response = self.teacher_client.get(
            f"/api/v1/scores?classId={self.classroom2.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_manual_score_duplicate_then_overwrite(self):
        payload = {
            "studentId": self.student.id,
            "assessmentId": self.assessment.id,
            "subject": "music",
            "scoreItems": [{"name": "演唱", "score": 40, "maxScore": 60}],
            "reason": "线下成绩补录",
        }
        response = self.teacher_client.post(
            "/api/v1/scores/manual", payload, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("overwrite", response.json()["message"])

        payload["overwrite"] = True
        response = self.teacher_client.post(
            "/api/v1/scores/manual", payload, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()["data"]["totalScore"], 40)
        self.assertEqual(response.json()["data"]["source"], "manual")

        response = self.teacher_client.post("/api/v1/scores/manual", {
            "studentId": self.student.id,
            "assessmentId": self.assessment.id,
            "subject": "music",
            "scoreItems": [{"name": "演唱", "score": 40, "maxScore": 60}],
            "totalScore": 41,
            "reason": "合计不一致",
        }, format="json")
        self.assertEqual(response.status_code, 422)

    def test_manual_score_requires_student_in_target(self):
        response = self.teacher_client.post("/api/v1/scores/manual", {
            "studentId": self.outsider.id,
            "assessmentId": self.assessment.id,
            "subject": "music",
            "scoreItems": [{"name": "演唱", "score": 10, "maxScore": 20}],
            "reason": "越权补录",
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_import_partial_success(self):
        csv_content = (
            "学籍号,姓名,客观题得分,主观题得分,AI得分,总分,备注\n"
            "S002,李小红,20,20,0,40,正常\n"
            "S003,错误姓名,10,10,0,20,姓名不符\n"
            "S999,不存在,10,10,0,20,缺考\n"
        ).encode("utf-8-sig")
        upload = SimpleUploadedFile(
            "scores.csv", csv_content, content_type="text/csv"
        )
        response = self.teacher_client.post(
            "/api/v1/scores/import",
            {"file": upload, "assessmentId": self.assessment.id, "subject": "music"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["successCount"], 1)
        self.assertEqual(data["failCount"], 2)
        self.assertTrue(Score.objects.filter(
            assessment=self.assessment, student=self.student2
        ).exists())

    def test_import_rejects_bad_header(self):
        upload = SimpleUploadedFile(
            "bad.csv", "学号,姓名\nS002,李小红\n".encode("utf-8"),
            content_type="text/csv",
        )
        response = self.teacher_client.post(
            "/api/v1/scores/import",
            {"file": upload, "assessmentId": self.assessment.id, "subject": "music"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


class StatisticsApiTests(ApiTestBase):
    def setUp(self):
        self.assessment = self.make_assessment()
        for student, total in (
            (self.student, 55), (self.student2, 55), (self.student3, 30)
        ):
            response = self.api(self.teacher).post("/api/v1/scores/manual", {
                "studentId": student.id,
                "assessmentId": self.assessment.id,
                "subject": "music",
                "scoreItems": [{"name": "总分", "score": total, "maxScore": 60}],
                "reason": "统计测试",
            }, format="json")
            self.assertEqual(response.status_code, 200, response.content.decode())

    def test_overview_counts_manual_scores_as_participants(self):
        response = self.api(self.teacher).get(
            f"/api/v1/scores/statistics?dimension=assessment"
            f"&assessmentId={self.assessment.id}"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["studentCount"], 3)
        self.assertEqual(data["participantCount"], 3)
        self.assertEqual(data["submittedCount"], 3)
        self.assertAlmostEqual(data["avgScore"], 46.67, places=2)
        self.assertEqual(data["highestScore"], 55)
        self.assertEqual(data["lowestScore"], 30)

    def test_class_ranking_with_ties(self):
        response = self.api(self.teacher).get(
            "/api/v1/scores/statistics/list?groupBy=class"
            f"&assessmentId={self.assessment.id}"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        rows = response.json()["data"]["list"]
        class_row = next(row for row in rows if row["targetId"] == self.classroom.id)
        self.assertEqual(class_row["rank"], 1)

        scores = list(Score.objects.filter(assessment=self.assessment).order_by("id"))
        ranks = {s.student_id: s.class_rank for s in scores}
        self.assertEqual(ranks[self.student.id], 1)
        self.assertEqual(ranks[self.student2.id], 1)
        self.assertEqual(ranks[self.student3.id], 3)

    def test_teacher_cannot_group_by_school(self):
        response = self.api(self.teacher).get(
            "/api/v1/scores/statistics/list?groupBy=school"
        )
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_view_statistics(self):
        response = self.api(self.student).get(
            f"/api/v1/scores/statistics?dimension=assessment"
            f"&assessmentId={self.assessment.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_export_xlsx(self):
        response = self.api(self.school_admin).get(
            f"/api/v1/scores/statistics/export?dimension=assessment"
            f"&assessmentId={self.assessment.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))

    def test_student_export_forbidden(self):
        response = self.api(self.student).get(
            f"/api/v1/scores/statistics/export?dimension=student"
            f"&targetId={self.student.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_province_overview(self):
        response = self.api(self.province_admin).get(
            f"/api/v1/scores/statistics?dimension=province"
            f"&targetId={self.province.id}"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()["data"]["participantCount"], 3)

    def test_dimension_scope_enforced(self):
        other_province = __import__(
            "accounts.models", fromlist=["Province"]
        ).Province.objects.create(name="其他省")
        response = self.api(self.district_admin).get(
            f"/api/v1/scores/statistics?dimension=province"
            f"&targetId={other_province.id}"
        )
        self.assertEqual(response.status_code, 403)
