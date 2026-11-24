"""同一班级的完整业务闭环：组卷 → 审核 → 发布 → 作答 → 评分 → 证书 → 学情报告。"""
from datetime import timedelta

from django.utils import timezone

from apps.exams.models import Certificate, Score
from apps.exams.tests.base import ApiTestBase
from common.enums import ShowAnswerMode


class SameClassFlowTests(ApiTestBase):
    def test_full_flow_in_one_class(self):
        teacher_client = self.api(self.teacher)
        now = timezone.now()
        paper_payload = {
            "title": "七年级音乐单元测评",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 45,
            "status": "ready",
            "questions": [
                {"questionId": self.questions[key].id, "order": index,
                 "sectionName": "客观题", "score": self.questions[key].score}
                for index, key in enumerate(
                    ("single", "multiple", "true_false", "fill", "short"), start=1
                )
            ],
        }
        created = teacher_client.post("/api/v1/papers/manual", paper_payload, format="json")
        self.assertEqual(created.status_code, 200, created.content.decode())
        paper = created.json()["data"]

        submitted = teacher_client.post(
            f"/api/v1/papers/{paper['id']}/submit-review",
            {"version": paper["version"], "comment": "请审核"},
            format="json",
        )
        self.assertEqual(submitted.status_code, 200, submitted.content.decode())
        self.assertEqual(submitted.json()["data"]["reviewStatus"], "pending")

        admin_client = self.api(self.question_admin)
        reviewed = admin_client.post(
            f"/api/v1/papers/{paper['id']}/review",
            {"action": "approve", "comment": "内容无误", "version": paper["version"]},
            format="json",
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.content.decode())
        self.assertEqual(reviewed.json()["data"]["reviewStatus"], "approved")

        end_time = now + timedelta(days=1)
        published = teacher_client.post("/api/v1/assessments", {
            "paperId": paper["id"],
            "title": "七年级音乐单元测评（正式）",
            "targetType": "class",
            "targetIds": [self.classroom.id],
            "startTime": now.isoformat(),
            "endTime": end_time.isoformat(),
            "attemptLimit": 1,
            "showAnswerMode": ShowAnswerMode.AFTER_SUBMIT,
        }, format="json")
        self.assertEqual(published.status_code, 200, published.content.decode())
        assessment = published.json()["data"]
        self.assertEqual(assessment["publisherName"], self.teacher.real_name)

        student_client = self.api(self.student)
        listed = student_client.get("/api/v1/assessments", {"pageSize": 100})
        self.assertEqual(listed.status_code, 200, listed.content.decode())
        rows = [row for row in listed.json()["data"]["list"] if row["id"] == assessment["id"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["publisherName"], self.teacher.real_name)
        self.assertTrue(rows[0]["endTime"])

        started = student_client.post(
            f"/api/v1/assessments/{assessment['id']}/attempts",
            {"deviceType": "web"}, format="json",
        )
        self.assertEqual(started.status_code, 200, started.content.decode())
        attempt_id = started.json()["data"]["attemptId"]
        submitted = student_client.post(
            f"/api/v1/attempts/{attempt_id}/submit",
            {
                "submitType": "manual",
                "finalAnswers": [
                    {"questionId": self.questions["single"].id, "answer": {"value": "A"}},
                    {"questionId": self.questions["multiple"].id, "answer": {"values": ["A", "C"]}},
                    {"questionId": self.questions["true_false"].id, "answer": {"value": True}},
                    {"questionId": self.questions["fill"].id, "answer": {"values": ["2", "两"]}},
                    {"questionId": self.questions["short"].id, "answer": {"fileId": 1}},
                ],
            },
            format="json",
        )
        self.assertEqual(submitted.status_code, 200, submitted.content.decode())
        self.assertEqual(submitted.json()["data"]["gradingStatus"], "grading")

        review = student_client.get(f"/api/v1/attempts/{attempt_id}/review")
        self.assertEqual(review.status_code, 200, review.content.decode())
        review_data = review.json()["data"]
        self.assertTrue(review_data["answerVisible"])
        self.assertFalse(review_data["scoreReleased"])
        self.assertTrue(all(item["correctAnswer"] for item in review_data["questions"]))

        tasks = teacher_client.get("/api/v1/grading/tasks", {"pageSize": 100})
        self.assertEqual(tasks.status_code, 200, tasks.content.decode())
        task = next(row for row in tasks.json()["data"]["list"] if row["attemptId"] == attempt_id)

        finalized = teacher_client.patch(
            f"/api/v1/grading/attempts/{attempt_id}/scores",
            {
                "items": [{
                    "questionId": self.questions["short"].id,
                    "score": self.questions["short"].score,
                    "comment": "完成度高",
                }],
                "finalize": True,
                "version": task.get("version", 0),
            },
            format="json",
        )
        self.assertEqual(finalized.status_code, 200, finalized.content.decode())

        score = Score.objects.get(attempt_id=attempt_id)
        self.assertEqual(score.total_score, 60)
        self.assertEqual(score.status, "graded")

        scores = student_client.get("/api/v1/scores/me", {"pageSize": 100})
        self.assertEqual(scores.status_code, 200, scores.content.decode())
        self.assertTrue(any(row["attemptId"] == attempt_id for row in scores.json()["data"]["list"]))

        certificates = student_client.get("/api/v1/certificates", {"pageSize": 100})
        self.assertEqual(certificates.status_code, 200, certificates.content.decode())
        self.assertTrue(
            Certificate.objects.filter(assessment_id=assessment["id"], student=self.student).exists()
        )

        report = student_client.get(f"/api/v1/students/{self.student.id}/learning-report")
        self.assertEqual(report.status_code, 200, report.content.decode())

    def test_teacher_only_sees_own_class_information(self):
        other_client = self.api(self.other_teacher)
        accounts = other_client.get("/api/v1/accounts", {"role": "student", "pageSize": 100})
        self.assertEqual(accounts.status_code, 200, accounts.content.decode())
        names = {row["username"] for row in accounts.json()["data"]["list"]}
        self.assertEqual(names, {"outsider"})

        classes = other_client.get("/api/v1/classes", {"pageSize": 100})
        self.assertEqual(classes.status_code, 200, classes.content.decode())
        class_ids = {row["id"] for row in classes.json()["data"]["list"]}
        self.assertEqual(class_ids, {self.classroom2.id})
        self.assertTrue(all(row["myIdentity"] for row in classes.json()["data"]["list"]))

        denied = other_client.get(f"/api/v1/accounts/{self.student.id}")
        self.assertEqual(denied.status_code, 403)
