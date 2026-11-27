from collections import Counter
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.qbank.models import Chapter, Course, Question
from common.enums import QuestionStatus, QuestionType, Role, Subject


class AllocateTests(SimpleTestCase):
    def test_allocate_sums_to_total_and_stays_even(self):
        from apps.exams.management.commands.rebalance_question_grades import (
            _allocate,
        )

        result = _allocate(10, {1: 1, 2: 1, 3: 1})
        self.assertEqual(sum(result.values()), 10)
        self.assertLessEqual(max(result.values()) - min(result.values()), 1)

    def test_allocate_respects_weights(self):
        from apps.exams.management.commands.rebalance_question_grades import (
            _allocate,
        )

        result = _allocate(20, {1: 1, 2: 3})
        self.assertEqual(sum(result.values()), 20)
        self.assertEqual(result[2], 15)


class RebalanceCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="qb_admin",
            password="Pass@123456",
            role=Role.QUESTION_ADMIN,
            real_name="题库管理员",
        )
        cls.courses = {}
        for grade in range(1, 10):
            course = Course.objects.create(
                name=f"{grade}年级音乐",
                subject=Subject.MUSIC,
                grade=grade,
            )
            chapter = Chapter.objects.create(course=course, name="乐理基础")
            cls.courses[grade] = (course, chapter)

        course, chapter = cls.courses[7]
        for index in range(30):
            Question.objects.create(
                subject=Subject.MUSIC,
                grade=7,
                course=course,
                chapter=chapter,
                type=QuestionType.SINGLE_CHOICE,
                difficulty=2,
                stem=f"七年级测试题 {index}",
                score=Decimal("2"),
                answer={"value": "A"},
                status=QuestionStatus.APPROVED,
                creator=cls.admin,
            )

    def _run(self):
        call_command(
            "rebalance_question_grades",
            subject=Subject.MUSIC,
            target_per_grade=18,
            stdout=StringIO(),
        )

    def test_rebalance_spreads_questions_by_grade_and_difficulty(self):
        from apps.exams.management.commands.rebalance_question_grades import (
            GRADE_DIFFICULTY,
        )

        self._run()
        questions = Question.objects.all()
        counts = Counter(questions.values_list("grade", flat=True))
        self.assertEqual(sum(counts.values()), 30)
        self.assertEqual(counts[7], 9)
        for grade in (1, 2, 3, 4, 5, 6, 8, 9):
            self.assertGreaterEqual(counts[grade], 2, f"{grade}年级没有分到题")

        for question in questions.select_related("course", "chapter"):
            self.assertEqual(question.difficulty, GRADE_DIFFICULTY[question.grade])
            self.assertEqual(question.course.grade, question.grade)
            self.assertIsNotNone(question.chapter)
            self.assertEqual(question.chapter.course_id, question.course_id)
            self.assertEqual(question.subject, Subject.MUSIC)

    def test_rebalance_is_idempotent(self):
        self._run()
        before = Counter(Question.objects.values_list("grade", flat=True))
        self._run()
        after = Counter(Question.objects.values_list("grade", flat=True))
        self.assertEqual(before, after)
