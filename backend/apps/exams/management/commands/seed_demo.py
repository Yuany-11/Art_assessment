"""初始化演示数据，便于前端/联调直接调用模块三接口。

用法：
    python manage.py seed_demo
    python manage.py seed_demo --reset
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import StudentProfile, TeacherProfile, User
from apps.classes.models import Class, ClassTeacher
from apps.organizations.models import Organization
from common.enums import (
    OrganizationLevel,
    PaperStatus,
    PaperType,
    QuestionType,
    Role,
    ScoringMode,
    ScopeType,
    SchoolType,
    ShowAnswerMode,
    Subject,
)
from common.jwt import issue_access_token
from apps.qbank.models import Course, Question, QuestionOption
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.paper import create_manual_paper


class Command(BaseCommand):
    help = "创建演示组织、账号、题库、试卷与测评"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="先清空演示账号与数据")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            User.objects.filter(username__in=[
                "province_admin", "city_admin", "district_admin", "school_admin",
                "teacher", "student", "student2", "question_admin",
            ]).delete()
            Question.objects.filter(stem__startswith="[演示]").delete()
            Organization.objects.filter(name="演示省").delete()

        province, _ = Organization.objects.get_or_create(
            level=OrganizationLevel.PROVINCE, name="演示省",
            defaults={"code": "P00"},
        )
        city, _ = Organization.objects.get_or_create(
            level=OrganizationLevel.CITY, parent=province, name="演示市",
            defaults={"code": "C00"},
        )
        district, _ = Organization.objects.get_or_create(
            level=OrganizationLevel.DISTRICT, parent=city, name="演示区",
            defaults={"code": "D00"},
        )
        school, _ = Organization.objects.get_or_create(
            level=OrganizationLevel.SCHOOL, parent=district, name="演示中学",
            defaults={"code": "S001", "school_type": SchoolType.MIDDLE},
        )
        classroom, _ = Class.objects.get_or_create(
            school=school, class_code="DEMO-7-1",
            defaults={"name": "七年级（1）班", "grade": 7},
        )

        users = {}

        def make_user(username, role, real_name, **extra):
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User.objects.create_user(
                    username=username, password="Demo@123456", role=role,
                    real_name=real_name, **extra,
                )
            else:
                for key, value in extra.items():
                    setattr(user, key, value)
                user.role = role
                user.real_name = real_name
                user.save()
            users[username] = user
            return user

        make_user("province_admin", Role.PROVINCE_ADMIN, "省级管理员", org=province)
        make_user("city_admin", Role.CITY_ADMIN, "市级管理员", org=city)
        make_user("district_admin", Role.DISTRICT_ADMIN, "区县管理员", org=district)
        make_user("school_admin", Role.SCHOOL_ADMIN, "学校管理员", org=school)
        teacher = make_user("teacher", Role.TEACHER, "演示教师", org=school)
        TeacherProfile.objects.get_or_create(
            user=teacher, defaults={"teacher_no": "T20260001", "subject": Subject.MUSIC}
        )
        ClassTeacher.objects.get_or_create(
            teacher=teacher, class_obj=classroom, defaults={"subject": Subject.MUSIC}
        )

        def make_student(username, real_name, student_no):
            obj = make_user(username, Role.STUDENT, real_name, org=school)
            StudentProfile.objects.update_or_create(
                user=obj,
                defaults={
                    "classroom": classroom,
                    "grade": 7,
                    "student_no": student_no,
                },
            )
            return obj

        make_student("student", "王小明", "S20261001")
        make_student("student2", "李小红", "S20261002")
        make_user("question_admin", Role.QUESTION_ADMIN, "题库管理员")

        course, _ = Course.objects.get_or_create(
            name="[演示] 七年级音乐", subject=Subject.MUSIC, grade=7,
            defaults={"description": "演示课程"},
        )
        questions = self._questions(teacher, course)
        paper = self._paper(teacher, classroom, questions)
        assessment = self._assessment(teacher, classroom, paper)

        self.stdout.write(self.style.SUCCESS("演示数据初始化完成"))
        self.stdout.write(f"测评 ID：{assessment.id}，试卷 ID：{paper.id}，班级 ID：{classroom.id}")
        self.stdout.write("账号密码均为 Demo@123456")
        for username in ("teacher", "student", "student2", "school_admin"):
            token = issue_access_token(users[username])
            self.stdout.write(f"{username}: Bearer {token}")

    def _questions(self, creator, course):
        specs = [
            {
                "type": QuestionType.SINGLE_CHOICE, "stem": "[演示] 下列哪个是四分音符？",
                "score": 10, "answer": {"value": "A"}, "scoring_mode": ScoringMode.AUTO,
                "options": [{"key": "A", "text": "♩"}, {"key": "B", "text": "♪"},
                            {"key": "C", "text": "𝅗𝅥"}, {"key": "D", "text": "𝅘𝅥𝅮"}],
            },
            {
                "type": QuestionType.MULTIPLE_CHOICE, "stem": "[演示] 下列属于弦乐器的有？",
                "score": 10, "answer": {"values": ["A", "C"]}, "scoring_mode": ScoringMode.AUTO,
                "options": [{"key": "A", "text": "小提琴"}, {"key": "B", "text": "长笛"},
                            {"key": "C", "text": "大提琴"}, {"key": "D", "text": "小号"}],
            },
            {
                "type": QuestionType.TRUE_FALSE, "stem": "[演示] 五线谱有五条线。",
                "score": 10, "answer": {"value": True}, "scoring_mode": ScoringMode.AUTO,
            },
            {
                "type": QuestionType.FILL_BLANK, "stem": "[演示] 2/4 拍每小节有 ___ 拍。",
                "score": 10, "answer": {"values": ["2", "两"]}, "scoring_mode": ScoringMode.AUTO,
            },
            {
                "type": QuestionType.SHORT_ANSWER, "stem": "[演示] 简述音乐节奏与节拍的区别。",
                "score": 20, "answer": {"reference": "节奏是音的长短组合，节拍是强弱规律。"},
                "rubric": "答出区别得 12 分，举例得当得 8 分。",
                "scoring_mode": ScoringMode.MANUAL,
            },
        ]
        rows = []
        for spec in specs:
            options = spec.pop("options", [])
            question, _ = Question.objects.get_or_create(
                stem=spec["stem"],
                defaults={
                    **spec,
                    "subject": Subject.MUSIC,
                    "grade": 7,
                    "difficulty": 2,
                    "creator": creator,
                    "course": course,
                    "analysis": "演示解析",
                    "status": "approved",
                },
            )
            for index, option in enumerate(options):
                QuestionOption.objects.get_or_create(
                    question=question, key=option["key"],
                    defaults={"text": option["text"], "sort_order": index},
                )
            rows.append(question)
        return rows

    def _paper(self, teacher, classroom, questions):
        existing = teacher.created_papers.filter(title="[演示] 七年级音乐测评卷").first()
        if existing:
            return existing
        payload = {
            "title": "[演示] 七年级音乐测评卷",
            "subject": Subject.MUSIC,
            "paperType": PaperType.FORMAL,
            "grade": 7,
            "scopeType": ScopeType.CLASS,
            "scopeId": classroom.id,
            "duration": 45,
            "instructions": "演示试卷，请按题目要求作答。",
            "status": PaperStatus.READY,
            "questions": [
                {
                    "questionId": q.id, "order": index,
                    "sectionName": "客观题" if index <= 4 else "主观题",
                    "score": q.score,
                }
                for index, q in enumerate(questions, start=1)
            ],
        }
        return create_manual_paper(teacher, payload)

    def _assessment(self, teacher, classroom, paper):
        existing = teacher.published_assessments.filter(title="[演示] 七年级音乐正式测评").first()
        if existing:
            return existing
        now = timezone.now()
        payload = {
            "paperId": paper.id,
            "title": "[演示] 七年级音乐正式测评",
            "targetType": ScopeType.CLASS,
            "targetIds": [classroom.id],
            "startTime": now - timedelta(minutes=5),
            "endTime": now + timedelta(days=7),
            "attemptLimit": 1,
            "showAnswerMode": ShowAnswerMode.AFTER_END,
            "allowLateSubmit": True,
        }
        return publish_assessment(teacher, payload)
