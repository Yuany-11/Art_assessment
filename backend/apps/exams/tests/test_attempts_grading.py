from datetime import timedelta

from django.utils import timezone

from common.enums import AttemptStatus, GradingStatus, SubmitType
from apps.exams.models import Attempt, GradingLog, Score
from apps.exams.services.attempt import auto_submit_expired
from apps.exams.tests.base import ApiTestBase


class AttemptApiTests(ApiTestBase):
    def setUp(self):
        self.assessment = self.make_assessment()

    def test_answer_payload_does_not_leak_answer_or_analysis(self):
        attempt_id = self.start_attempt()
        client = self.api(self.student)
        response = client.get(f"/api/v1/attempts/{attempt_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        for question in data["questions"]:
            self.assertNotIn("answer", question)
            self.assertNotIn("analysis", question)
            self.assertNotIn("rubric", question)
        raw = response.content.decode()
        self.assertNotIn("测试解析", raw)

    def test_save_answers_and_invalid_question(self):
        attempt_id = self.start_attempt()
        client = self.api(self.student)
        ok = client.patch(f"/api/v1/attempts/{attempt_id}/answers", {
            "answers": [{"questionId": self.questions["single"].id,
                         "answer": {"value": "A"}}]
        }, format="json")
        self.assertEqual(ok.status_code, 200, ok.content.decode())
        self.assertEqual(ok.json()["data"]["savedCount"], 1)

        invalid = client.patch(f"/api/v1/attempts/{attempt_id}/answers", {
            "answers": [{"questionId": 999999, "answer": {"value": "A"}}]
        }, format="json")
        self.assertEqual(invalid.status_code, 400)

    def test_submit_grades_objective_and_is_idempotent(self):
        attempt_id = self.start_attempt()
        first = self.submit_all_correct(attempt_id)
        self.assertEqual(first["objectiveScore"], 40)
        self.assertEqual(first["totalScore"], 40)
        self.assertEqual(first["gradingStatus"], GradingStatus.GRADING)
        self.assertEqual(first["status"], AttemptStatus.SUBMITTED)

        client = self.api(self.student)
        second = client.post(
            f"/api/v1/attempts/{attempt_id}/submit", {}, format="json"
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["data"]["submittedAt"], first["submittedAt"])
        self.assertEqual(Score.objects.filter(attempt_id=attempt_id).count(), 1)

    def test_attempt_limit_enforced(self):
        attempt_id = self.start_attempt()
        self.submit_all_correct(attempt_id)
        client = self.api(self.student)
        response = client.post(
            f"/api/v1/assessments/{self.assessment.id}/attempts", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("作答次数", response.json()["message"])

    def test_other_student_cannot_access_attempt(self):
        attempt_id = self.start_attempt()
        other = self.api(self.student2)
        response = other.get(f"/api/v1/attempts/{attempt_id}")
        self.assertEqual(response.status_code, 403)
        response = other.patch(f"/api/v1/attempts/{attempt_id}/answers", {
            "answers": [{"questionId": self.questions["single"].id,
                         "answer": {"value": "A"}}]
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_use_student_attempt_endpoint(self):
        attempt_id = self.start_attempt()
        response = self.api(self.teacher).get(f"/api/v1/attempts/{attempt_id}")
        self.assertEqual(response.status_code, 403)

    def test_expired_attempt_auto_submits_on_read(self):
        attempt_id = self.start_attempt()
        attempt = Attempt.objects.get(pk=attempt_id)
        attempt.deadline = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["deadline"])

        response = self.api(self.student).get(f"/api/v1/attempts/{attempt_id}")
        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.SUBMITTED)
        self.assertTrue(attempt.auto_submitted)
        self.assertEqual(attempt.submit_type, SubmitType.AUTO)

    def test_manual_submit_after_deadline_rejected_without_late_submit(self):
        attempt_id = self.start_attempt()
        attempt = Attempt.objects.get(pk=attempt_id)
        attempt.deadline = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["deadline"])

        response = self.api(self.student).post(
            f"/api/v1/attempts/{attempt_id}/submit", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.IN_PROGRESS)

    def test_late_submit_within_grace_allowed(self):
        assessment = self.make_assessment(allowLateSubmit=True)
        attempt_id = self.start_attempt(assessment=assessment)
        attempt = Attempt.objects.get(pk=attempt_id)
        attempt.deadline = timezone.now() - timedelta(minutes=1)
        attempt.save(update_fields=["deadline"])

        response = self.api(self.student).post(
            f"/api/v1/attempts/{attempt_id}/submit", {}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())

    def test_auto_submit_expired_command_service(self):
        attempt_id = self.start_attempt()
        Attempt.objects.filter(pk=attempt_id).update(
            deadline=timezone.now() - timedelta(seconds=1)
        )
        count = auto_submit_expired()
        self.assertGreaterEqual(count, 1)
        self.assertEqual(
            Attempt.objects.get(pk=attempt_id).status, AttemptStatus.SUBMITTED
        )


class GradingApiTests(ApiTestBase):
    def setUp(self):
        self.assessment = self.make_assessment()
        self.attempt_id = self.start_attempt()
        self.submit_all_correct(self.attempt_id)
        self.teacher_client = self.api(self.teacher)

    def test_task_list_and_detail(self):
        response = self.teacher_client.get("/api/v1/grading/tasks")
        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["list"][0]
        self.assertEqual(item["attemptId"], self.attempt_id)
        self.assertEqual(item["pendingCount"], 1)

        detail = self.teacher_client.get(
            f"/api/v1/grading/attempts/{self.attempt_id}"
        )
        self.assertEqual(detail.status_code, 200)
        data = detail.json()["data"]
        self.assertFalse(data["canFinalize"])
        self.assertEqual(data["questions"][0]["questionId"], self.questions["short"].id)

        attempt = Attempt.objects.get(pk=self.attempt_id)
        self.assertEqual(attempt.questions_snapshot[4]["stem"], "简答题")
        self.assertNotIn("finalAnswers", data)

    def test_grade_then_finalize(self):
        response = self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id,
                        "score": 18, "comment": "答得不错"}],
             "finalize": True, "reason": "人工终评", "version": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["status"], AttemptStatus.GRADED)
        self.assertEqual(data["subjectiveScore"], 18)
        self.assertEqual(data["totalScore"], 58)
        self.assertTrue(GradingLog.objects.filter(
            attempt_id=self.attempt_id, action="finalize"
        ).exists())
        score = Score.objects.get(attempt_id=self.attempt_id)
        self.assertEqual(score.total_score, 58)
        self.assertEqual(score.level, "excellent")
        self.assertEqual(score.class_rank, 1)

    def test_finalize_requires_all_subjective_scored(self):
        response = self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [], "finalize": True}, format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["single"].id, "score": 10}],
             "finalize": True}, format="json",
        )
        self.assertEqual(response.status_code, 422)

    def test_version_conflict(self):
        first = self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 10}],
             "version": 0}, format="json",
        )
        self.assertEqual(first.status_code, 200, first.content.decode())
        stale = self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 12}],
             "version": 0}, format="json",
        )
        self.assertEqual(stale.status_code, 409)

    def test_score_cannot_exceed_max(self):
        response = self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 21}]},
            format="json",
        )
        self.assertEqual(response.status_code, 422)

    def test_other_teacher_cannot_grade(self):
        other = self.api(self.other_teacher)
        response = other.get(f"/api/v1/grading/attempts/{self.attempt_id}")
        self.assertEqual(response.status_code, 403)

    def test_regrade_after_grading(self):
        self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 20}],
             "finalize": True, "version": 0},
            format="json",
        )
        score = Score.objects.get(attempt_id=self.attempt_id)
        # 篡改客观题分数后重新判分应恢复正确值
        attempt = Attempt.objects.get(pk=self.attempt_id)
        attempt.answers.filter(question_id=self.questions["single"].id).update(score=0)
        attempt.objective_score = 30
        attempt.total_score = 50
        attempt.save()

        response = self.teacher_client.post(
            f"/api/v1/scores/{score.id}/regrade",
            {"reason": "复核成绩"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        score.refresh_from_db()
        self.assertEqual(score.objective_score, 40)
        self.assertEqual(score.total_score, 60)

    def test_admin_can_regrade_in_scope(self):
        self.teacher_client.patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 20}],
             "finalize": True, "version": 0},
            format="json",
        )
        score = Score.objects.get(attempt_id=self.attempt_id)
        response = self.api(self.district_admin).post(
            f"/api/v1/scores/{score.id}/regrade",
            {"reason": "区级复核"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
