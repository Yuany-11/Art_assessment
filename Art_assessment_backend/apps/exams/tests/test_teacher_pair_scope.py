"""每个班每科只能由一位老师任教：教学权限必须按（班级, 学科）精确匹配。"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.classes.models import Class, ClassTeacher
from apps.exams.models import Assessment, Score
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.certificate import certificate_eligible
from apps.exams.services.grading import list_tasks
from apps.exams.services.paper import create_manual_paper
from apps.exams.tests.base import ApiTestBase
from common.enums import (
    GradingStatus,
    PaperType,
    ScopeType,
    Subject,
)
from common.exceptions import Forbidden, Unprocessable


class TeacherPairPermissionTests(ApiTestBase):
    def _publish_payload(self, paper, target_ids, title="测评"):
        now = timezone.now()
        return {
            "paperId": paper.id,
            "title": title,
            "targetType": ScopeType.CLASS,
            "targetIds": target_ids,
            "startTime": now - timedelta(minutes=1),
            "endTime": now + timedelta(days=1),
            "attemptLimit": 1,
            "showAnswerMode": "after_end",
            "allowLateSubmit": False,
        }

    def _paper_payload(self, classroom, grade=7):
        return {
            "title": "权限校验试卷",
            "subject": Subject.MUSIC,
            "paperType": PaperType.FORMAL,
            "grade": grade,
            "scopeType": ScopeType.CLASS,
            "scopeId": classroom.id,
            "duration": 45,
            "status": "ready",
            "questions": [
                {
                    "questionId": self.questions["single"].id,
                    "order": 1,
                    "sectionName": "客观题",
                    "score": 10,
                }
            ],
        }

    def test_head_teacher_without_subject_assignment_cannot_create_paper(self):
        headed = Class.objects.create(
            school=self.school,
            name="七年级（4）班",
            grade=7,
            class_code="T-7-4",
            head_teacher=self.teacher,
        )
        with self.assertRaises(Forbidden):
            create_manual_paper(self.teacher, self._paper_payload(headed))

    def test_cannot_publish_to_class_not_taught(self):
        paper = self.make_paper()
        with self.assertRaises(Forbidden):
            publish_assessment(
                self.teacher,
                self._publish_payload(paper, [self.classroom2.id], "越权发布"),
            )

    def test_class_subject_teacher_is_unique_per_class(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClassTeacher.objects.create(
                    class_obj=self.classroom,
                    teacher=self.other_teacher,
                    subject=Subject.MUSIC,
                )

    def test_paper_grade_must_match_class_grade(self):
        grade8 = Class.objects.create(
            school=self.school,
            name="八年级（1）班",
            grade=8,
            class_code="T-8-1",
        )
        ClassTeacher.objects.create(
            class_obj=grade8, teacher=self.teacher, subject=Subject.MUSIC
        )
        with self.assertRaises(Unprocessable):
            create_manual_paper(self.teacher, self._paper_payload(grade8, grade=7))

    def test_publish_rejects_paper_grade_target_grade_mismatch(self):
        paper = self.make_paper()
        grade8 = Class.objects.create(
            school=self.school,
            name="八年级（2）班",
            grade=8,
            class_code="T-8-2",
        )
        ClassTeacher.objects.create(
            class_obj=grade8, teacher=self.teacher, subject=Subject.MUSIC
        )
        with self.assertRaises(Unprocessable):
            publish_assessment(
                self.teacher,
                self._publish_payload(paper, [grade8.id], "跨年级发布"),
            )

    def test_grading_tasks_are_limited_to_own_class_and_subject(self):
        self.make_assessment()
        self.assertEqual(list_tasks(self.teacher, {}).count(), 0)
        self.assertEqual(list_tasks(self.other_teacher, {}).count(), 0)

    def test_practice_assessment_never_issues_certificate(self):
        assessment = Assessment(paper_type=PaperType.PRACTICE, publisher=self.teacher)
        score = Score(
            status=GradingStatus.GRADED, max_score=100, total_score=95
        )
        score.assessment = assessment
        self.assertFalse(certificate_eligible(score))

        formal = Assessment(paper_type=PaperType.FORMAL, publisher=self.teacher)
        score.assessment = formal
        self.assertTrue(certificate_eligible(score))
