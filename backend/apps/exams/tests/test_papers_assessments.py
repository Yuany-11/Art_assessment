from datetime import timedelta

from django.utils import timezone

from common.enums import AttemptStatus, PaperStatus, ScopeType, Subject
from apps.exams.models import Assessment, Attempt, Paper, PaperQuestion
from apps.exams.tests.base import ApiTestBase


class PaperApiTests(ApiTestBase):
    def test_manual_paper_create_and_detail(self):
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/manual", {
            "title": "手动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 45,
            "status": "ready",
            "questions": [
                {"questionId": self.questions["single"].id, "order": 2, "score": 10},
                {"questionId": self.questions["short"].id, "order": 1, "score": 20},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["totalScore"], 30)
        self.assertEqual(data["questionCount"], 2)
        self.assertEqual([q["questionId"] for q in data["questions"]],
                         [self.questions["short"].id, self.questions["single"].id])

        detail = client.get(f"/api/v1/papers/{data['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["title"], "手动卷")

    def test_manual_paper_rejects_duplicate_questions(self):
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/manual", {
            "title": "重复题",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 45,
            "questions": [
                {"questionId": self.questions["single"].id, "order": 1, "score": 10},
                {"questionId": self.questions["single"].id, "order": 2, "score": 10},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("questions", response.json()["data"]["errors"])

    def test_teacher_cannot_create_paper_for_other_class(self):
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/manual", {
            "title": "越权卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom2.id,
            "duration": 45,
            "questions": [
                {"questionId": self.questions["single"].id, "order": 1, "score": 10},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_auto_paper_shortage_returns_409(self):
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "自动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "rules": [{"type": "single_choice", "count": 99, "scorePerQuestion": 5}],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 409)

    def test_auto_paper_creation(self):
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "自动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "rules": [
                {"type": "single_choice", "count": 2, "scorePerQuestion": 5},
                {"type": "multiple_choice", "count": 1, "scorePerQuestion": 10},
            ],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()["data"]["generateMode"], "auto")
        self.assertEqual(response.json()["data"]["questionCount"], 3)

    def test_draft_update_and_delete(self):
        paper = self.make_paper(status=PaperStatus.DRAFT)
        client = self.api(self.teacher)
        response = client.patch(f"/api/v1/papers/{paper.id}/draft", {
            "title": "暂存标题",
            "questions": [
                {"questionId": self.questions["single"].id, "order": 1, "score": 10},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()["data"]["title"], "暂存标题")
        self.assertEqual(response.json()["data"]["questionCount"], 1)

        deleted = client.delete(f"/api/v1/papers/{paper.id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["data"]["deleted"])
        self.assertFalse(Paper.objects.filter(pk=paper.id, deleted_at__isnull=True).exists())

    def test_published_paper_cannot_be_modified(self):
        paper = self.make_paper()
        self.make_assessment(paper=paper)
        client = self.api(self.teacher)
        response = client.patch(f"/api/v1/papers/{paper.id}", {
            "title": "修改已发布试卷"
        }, format="json")
        self.assertEqual(response.status_code, 409)

    def test_teacher_cannot_access_other_teacher_paper(self):
        paper = self.make_paper(
            teacher=self.other_teacher, scope_id=self.classroom2.id
        )
        client = self.api(self.teacher)
        response = client.get(f"/api/v1/papers/{paper.id}")
        self.assertEqual(response.status_code, 403)

    def test_practice_random_creates_attempt(self):
        client = self.api(self.student)
        response = client.post("/api/v1/papers/practice/random", {
            "subject": "music", "questionCount": 3,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["status"], "in_progress")
        self.assertEqual(len(data["questions"]), 3)
        attempt = Attempt.objects.get(pk=data["attemptId"])
        self.assertEqual(attempt.student, self.student)


class AssessmentApiTests(ApiTestBase):
    def test_publish_and_list_for_student(self):
        assessment = self.make_assessment()
        client = self.api(self.student)
        response = client.get("/api/v1/assessments")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["data"]["list"]]
        self.assertIn(assessment.id, ids)

        outsider = self.api(self.outsider)
        response = outsider.get("/api/v1/assessments")
        ids = [item["id"] for item in response.json()["data"]["list"]]
        self.assertNotIn(assessment.id, ids)

    def test_publish_freezes_question_snapshot(self):
        assessment = self.make_assessment()
        self.questions["single"].stem = "题库已修改"
        self.questions["single"].save()
        client = self.api(self.student)
        attempt_id = self.start_attempt(assessment=assessment)
        attempt = Attempt.objects.get(pk=attempt_id)
        stems = [q["stem"] for q in attempt.questions_snapshot]
        self.assertIn("单选题", stems)
        self.assertNotIn("题库已修改", stems)

    def test_teacher_cannot_publish_to_school(self):
        paper = self.make_paper()
        client = self.api(self.teacher)
        now = timezone.now()
        response = client.post("/api/v1/assessments", {
            "paperId": paper.id,
            "title": "越权发布",
            "targetType": "school",
            "targetIds": [self.school.id],
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(days=1)).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_publish_requires_ready_paper(self):
        paper = self.make_paper(status=PaperStatus.DRAFT)
        client = self.api(self.teacher)
        now = timezone.now()
        response = client.post("/api/v1/assessments", {
            "paperId": paper.id,
            "title": "草稿发布",
            "targetType": "class",
            "targetIds": [self.classroom.id],
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(days=1)).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 409)

    def test_publish_is_idempotent_with_header(self):
        paper = self.make_paper()
        client = self.api(self.teacher)
        now = timezone.now()
        payload = {
            "paperId": paper.id,
            "title": "幂等发布",
            "targetType": "class",
            "targetIds": [self.classroom.id],
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(days=1)).isoformat(),
        }
        first = client.post(
            "/api/v1/assessments", payload, format="json",
            HTTP_IDEMPOTENCY_KEY="publish-once",
        )
        second = client.post(
            "/api/v1/assessments", payload, format="json",
            HTTP_IDEMPOTENCY_KEY="publish-once",
        )
        self.assertEqual(first.status_code, 200, first.content.decode())
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        self.assertEqual(Assessment.objects.filter(title="幂等发布").count(), 1)

    def test_withdraw_auto_submits_in_progress_attempt(self):
        assessment = self.make_assessment()
        attempt_id = self.start_attempt(assessment=assessment)
        client = self.api(self.teacher)
        response = client.post(
            f"/api/v1/assessments/{assessment.id}/withdraw",
            {"reason": "安排冲突"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.assertEqual(response.json()["data"]["status"], "withdrawn")
        attempt = Attempt.objects.get(pk=attempt_id)
        self.assertEqual(attempt.status, AttemptStatus.SUBMITTED)
        self.assertTrue(attempt.auto_submitted)

    def test_withdraw_after_end_conflicts(self):
        assessment = self.make_assessment(
            start_offset=timedelta(days=-2), end_offset=timedelta(days=-1)
        )
        client = self.api(self.teacher)
        response = client.post(
            f"/api/v1/assessments/{assessment.id}/withdraw",
            {"reason": "已结束"}, format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_student_cannot_publish_or_withdraw(self):
        student = self.api(self.student)
        response = student.post("/api/v1/assessments", {}, format="json")
        self.assertEqual(response.status_code, 403)
