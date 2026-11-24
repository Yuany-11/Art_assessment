from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from common.enums import AttemptStatus, PaperStatus, ScopeType, Subject
from apps.classes.models import Class, ClassTeacher
from apps.exams.models import Assessment, Attempt, Paper, PaperQuestion, Score
from apps.exams.tests.base import ApiTestBase
from apps.qbank.models import Course, Question


class GradeQuestionBankTests(SimpleTestCase):
    def test_every_grade_has_enough_questions_and_own_difficulty(self):
        from apps.exams.management.commands.seed_grade_question_bank import (
            GRADE_DIFFICULTY,
            build_specs,
        )

        for grade in range(1, 10):
            for subject in (Subject.MUSIC, Subject.ART):
                specs = build_specs(grade, subject)
                self.assertGreaterEqual(len(specs["single_choice"]), 30)
                self.assertGreaterEqual(len(specs["multiple_choice"]), 12)
                self.assertNotIn("short_answer", specs)
                practice_type = (
                    "audio_upload" if subject == Subject.MUSIC else "image_upload"
                )
                self.assertGreaterEqual(len(specs[practice_type]), 3)
                stems = [
                    spec["stem"]
                    for items in specs.values() for spec in items
                ]
                self.assertEqual(len(stems), len(set(stems)))
                for spec in (item for items in specs.values() for item in items):
                    self.assertEqual(spec["difficulty"], GRADE_DIFFICULTY[grade])


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

    def test_auto_paper_can_draw_from_selected_grades(self):
        """教师可在任教班级的试卷里跨年级抽题，试卷年级仍保持班级年级。"""
        course8 = Course.objects.create(
            name="八年级音乐", subject=Subject.MUSIC, grade=8
        )
        question8 = Question.objects.create(
            subject=Subject.MUSIC,
            grade=8,
            type="single_choice",
            stem="八年级跨年级抽题测试",
            answer={"value": "A"},
            score=10,
            scoring_mode="auto",
            status="approved",
            creator=self.teacher,
            course=course8,
        )
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "跨年级自动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "grades": [8],
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "rules": [{"type": "single_choice", "count": 1}],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["grade"], 7)
        self.assertEqual(
            [item["questionId"] for item in data["questions"]], [question8.id]
        )

    def test_auto_paper_all_grades_use_whole_subject_bank(self):
        """全选年级（grades 为空）时不限制年级，整库可抽。"""
        course8 = Course.objects.create(
            name="八年级音乐", subject=Subject.MUSIC, grade=8
        )
        Question.objects.create(
            subject=Subject.MUSIC,
            grade=8,
            type="single_choice",
            stem="整库抽题测试",
            answer={"value": "A"},
            score=10,
            scoring_mode="auto",
            status="approved",
            creator=self.teacher,
            course=course8,
        )
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "全年级自动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 7,
            "grades": [],
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "rules": [{"type": "single_choice", "count": 3}],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())

    def test_auto_paper_rejects_when_grade_bank_missing(self):
        """题库按年级分册：本年级题目不足时明确提示，不跨年级凑题。"""
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "三年级自动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 3,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "rules": [
                {"type": "single_choice", "count": 2, "scorePerQuestion": 5},
                {"type": "multiple_choice", "count": 1, "scorePerQuestion": 10},
            ],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 409, response.content.decode())
        self.assertIn("shortage", response.json()["data"]["errors"])

    def test_auto_paper_uses_grade_bank_and_selected_difficulty(self):
        """题库按年级分册，组卷只抽取本年级题目；难度按发布时选择筛选。"""
        from io import StringIO

        from django.core.management import call_command

        call_command(
            "seed_grade_question_bank",
            grades="3",
            subject="music",
            single=10,
            multi=5,
            short=2,
            practice=1,
            stdout=StringIO(),
        )
        classroom3 = Class.objects.create(
            school=self.school, name="三年级（1）班", grade=3, class_code="T-3-1"
        )
        ClassTeacher.objects.create(
            teacher=self.teacher, class_obj=classroom3, subject=Subject.MUSIC
        )
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "三年级分层卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 3,
            "scopeType": "class",
            "scopeId": classroom3.id,
            "duration": 30,
            "rules": [
                {"type": "single_choice", "count": 6, "difficulty": 2},
                {"type": "multiple_choice", "count": 3, "difficulty": 2},
                {"type": "audio_upload", "count": 1},
            ],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        paper_id = response.json()["data"]["id"]
        question_ids = list(
            PaperQuestion.objects.filter(paper_id=paper_id)
            .values_list("question_id", flat=True)
        )
        self.assertEqual(len(question_ids), 10)
        questions = Question.objects.filter(id__in=question_ids)
        self.assertEqual(questions.count(), 10)
        self.assertEqual(set(questions.values_list("grade", flat=True)), {3})
        objective = questions.exclude(type="audio_upload")
        self.assertEqual(set(objective.values_list("difficulty", flat=True)), {2})

    def test_manual_paper_rejects_cross_grade_question(self):
        """手动组卷同样校验年级，避免混入其他年级题目。"""
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/manual", {
            "title": "三年级手动卷",
            "subject": "music",
            "paperType": "formal",
            "grade": 3,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "status": "ready",
            "questions": [
                {"questionId": self.questions["single"].id, "order": 1, "score": 10},
            ],
        }, format="json")
        self.assertEqual(response.status_code, 422, response.content.decode())
        self.assertIn("年级", response.json()["message"])

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

    def test_practice_random_creates_fixed_composition(self):
        client = self.api(self.student)
        response = client.post("/api/v1/papers/practice/random", {
            "subject": "music",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["status"], "in_progress")
        self.assertEqual(len(data["questions"]), 10)
        attempt = Attempt.objects.get(pk=data["attemptId"])
        self.assertEqual(attempt.student, self.student)
        types = [q["type"] for q in attempt.questions_snapshot]
        self.assertEqual(types.count("single_choice"), 6)
        self.assertEqual(types.count("multiple_choice"), 3)
        self.assertEqual(types.count("true_false"), 1)
        # 随机练习只出客观题，实践作品题（需上传并人工评分）不再抽取。
        self.assertNotIn("audio_upload", types)
        self.assertNotIn("image_upload", types)
        self.assertNotIn("short_answer", types)
        # 随机练习固定 100 分，10 道题各 10 分，且同一套题不出现重复题干。
        self.assertEqual(attempt.assessment.max_score, 100)
        self.assertEqual(
            [q["score"] for q in attempt.questions_snapshot], [10] * 10
        )
        self.assertEqual(len({q["stem"] for q in attempt.questions_snapshot}), 10)

        # 练习卷即时反馈，实践作品题不进入教师评分任务。
        submitted = client.post(
            f"/api/v1/attempts/{attempt.id}/submit",
            {"submitType": "manual", "finalAnswers": []},
            format="json",
        )
        self.assertEqual(submitted.status_code, 200, submitted.content.decode())
        result = submitted.json()["data"]
        self.assertTrue(result["scoreReleased"])
        self.assertEqual(Score.objects.filter(attempt=attempt).count(), 1)
        self.assertTrue(Score.objects.get(attempt=attempt).level)

    def test_practice_rejects_when_grade_bank_missing(self):
        """随机练习只抽取本年级题目，本年级题库不足时提示教师补充题目。"""
        from apps.qbank.models import Chapter, Question

        chapter = Chapter.objects.create(course=self.course, name="乐理基础")
        Question.objects.filter(
            pk__in=[question.id for question in self.questions.values()]
        ).update(chapter=chapter)

        from apps.accounts.models import StudentProfile, User

        StudentProfile.objects.filter(user=self.student).update(grade=3)
        self.student = User.objects.get(pk=self.student.pk)
        client = self.api(self.student)
        response = client.post("/api/v1/papers/practice/random", {
            "subject": "music",
            "chapterId": chapter.id,
        }, format="json")
        self.assertEqual(response.status_code, 409, response.content.decode())
        self.assertIn("单选题不足", response.json()["message"])


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

    def test_teacher_cannot_publish_to_unassigned_class(self):
        paper = self.make_paper()
        client = self.api(self.teacher)
        now = timezone.now()
        response = client.post("/api/v1/assessments", {
            "paperId": paper.id,
            "title": "越权发布到未任教班级",
            "targetType": "class",
            "targetIds": [self.classroom2.id],
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(days=1)).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("无权在该范围", response.json()["message"])

    def test_published_paper_can_be_published_again(self):
        paper = self.make_paper()
        client = self.api(self.teacher)
        now = timezone.now()
        payload = {
            "paperId": paper.id,
            "title": "首次发布",
            "targetType": "class",
            "targetIds": [self.classroom.id],
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(days=1)).isoformat(),
        }
        first = client.post("/api/v1/assessments", payload, format="json")
        self.assertEqual(first.status_code, 200, first.content.decode())

        payload["title"] = "再次发布同一张试卷"
        second = client.post("/api/v1/assessments", payload, format="json")
        self.assertEqual(second.status_code, 200, second.content.decode())
        self.assertNotEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        paper.refresh_from_db()
        self.assertEqual(paper.status, PaperStatus.PUBLISHED)

    def test_publish_records_selected_difficulty(self):
        paper = self.make_paper()
        client = self.api(self.teacher)
        now = timezone.now()
        response = client.post("/api/v1/assessments", {
            "paperId": paper.id,
            "title": "难度测评",
            "targetType": "class",
            "targetIds": [self.classroom.id],
            "startTime": now.isoformat(),
            "endTime": (now + timedelta(days=1)).isoformat(),
            "difficulty": 3,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["difficulty"], 3)
        self.assertEqual(data["difficultyLabel"], "较难")
        self.assertEqual(Assessment.objects.get(pk=data["id"]).difficulty, 3)

    def test_teacher_cannot_create_other_subject_paper(self):
        """音乐老师不能创建美术试卷。"""
        client = self.api(self.teacher)
        response = client.post("/api/v1/papers/auto", {
            "title": "越权美术卷",
            "subject": "art",
            "paperType": "formal",
            "grade": 7,
            "scopeType": "class",
            "scopeId": self.classroom.id,
            "duration": 30,
            "rules": [{"type": "single_choice", "count": 1}],
            "status": "ready",
        }, format="json")
        self.assertEqual(response.status_code, 403, response.content.decode())

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
