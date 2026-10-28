from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

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
    ShowAnswerMode,
    SchoolType,
    Subject,
)
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.paper import create_manual_paper
from apps.qbank.models import Course, Question, QuestionOption


class ApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.province = Organization.objects.create(
            level=OrganizationLevel.PROVINCE, name="测试省", code="T"
        )
        cls.city = Organization.objects.create(
            level=OrganizationLevel.CITY, name="测试市", code="C", parent=cls.province
        )
        cls.district = Organization.objects.create(
            level=OrganizationLevel.DISTRICT, name="测试区", code="D", parent=cls.city
        )
        cls.school = Organization.objects.create(
            level=OrganizationLevel.SCHOOL,
            name="测试中学",
            code="S",
            parent=cls.district,
            school_type=SchoolType.MIDDLE,
        )
        cls.classroom = Class.objects.create(
            school=cls.school, name="七年级（1）班", grade=7, class_code="T-7-1"
        )
        cls.classroom2 = Class.objects.create(
            school=cls.school, name="七年级（2）班", grade=7, class_code="T-7-2"
        )

        def user(username, role, name, org=None, **extra):
            return User.objects.create_user(
                username=username, password="Pass@123456", role=role,
                real_name=name, org=org, **extra,
            )

        cls.teacher = user("teacher", Role.TEACHER, "张老师", org=cls.school)
        TeacherProfile.objects.create(
            user=cls.teacher, teacher_no="T001", subject=Subject.MUSIC
        )
        cls.other_teacher = user("teacher2", Role.TEACHER, "李老师", org=cls.school)
        TeacherProfile.objects.create(
            user=cls.other_teacher, teacher_no="T002", subject=Subject.MUSIC
        )
        cls.school_admin = user(
            "school_admin", Role.SCHOOL_ADMIN, "校管理员", org=cls.school
        )
        cls.district_admin = user(
            "district_admin", Role.DISTRICT_ADMIN, "区管理员", org=cls.district
        )
        cls.city_admin = user("city_admin", Role.CITY_ADMIN, "市管理员", org=cls.city)
        cls.province_admin = user(
            "province_admin", Role.PROVINCE_ADMIN, "省管理员", org=cls.province
        )
        cls.question_admin = user(
            "question_admin", Role.QUESTION_ADMIN, "题库管理员"
        )

        def student(username, name, classroom, student_no):
            obj = user(username, Role.STUDENT, name, org=cls.school)
            StudentProfile.objects.create(
                user=obj, classroom=classroom, grade=7, student_no=student_no
            )
            return obj

        cls.student = student("student", "王小明", cls.classroom, "S001")
        cls.student2 = student("student2", "李小红", cls.classroom, "S002")
        cls.student3 = student("student3", "赵小刚", cls.classroom, "S003")
        cls.outsider = student("outsider", "外部学生", cls.classroom2, "S004")

        ClassTeacher.objects.create(
            teacher=cls.teacher, class_obj=cls.classroom, subject=Subject.MUSIC
        )
        ClassTeacher.objects.create(
            teacher=cls.other_teacher, class_obj=cls.classroom2, subject=Subject.MUSIC
        )

        cls.course = Course.objects.create(
            name="测试课程", subject=Subject.MUSIC, grade=7
        )
        cls.questions = cls._create_questions()

    @classmethod
    def _create_questions(cls):
        def make(qtype, stem, answer, score=10, mode=ScoringMode.AUTO, options=None):
            question = Question.objects.create(
                subject=Subject.MUSIC, grade=7, type=qtype, stem=stem,
                answer=answer, score=score, scoring_mode=mode,
                status="approved", creator=cls.teacher, course=cls.course,
                analysis="测试解析", rubric="测试评分细则",
            )
            for index, (key, text) in enumerate(options or []):
                QuestionOption.objects.create(
                    question=question, key=key, text=text, sort_order=index
                )
            return question

        return {
            "single": make(
                QuestionType.SINGLE_CHOICE, "单选题", {"value": "A"},
                options=[("A", "选项A"), ("B", "选项B")],
            ),
            "multiple": make(
                QuestionType.MULTIPLE_CHOICE, "多选题", {"values": ["A", "C"]},
                options=[("A", "A"), ("B", "B"), ("C", "C")],
            ),
            "true_false": make(
                QuestionType.TRUE_FALSE, "判断题", {"value": True}
            ),
            "fill": make(
                QuestionType.FILL_BLANK, "填空题", {"values": ["2", "两"]}
            ),
            "short": make(
                QuestionType.SHORT_ANSWER, "简答题", {"reference": "参考答案"},
                score=20, mode=ScoringMode.MANUAL,
            ),
            "extra1": make(
                QuestionType.SINGLE_CHOICE, "备用单选题1", {"value": "A"},
                options=[("A", "A"), ("B", "B")],
            ),
            "extra2": make(
                QuestionType.SINGLE_CHOICE, "备用单选题2", {"value": "B"},
                options=[("A", "A"), ("B", "B")],
            ),
            "extra3": make(
                QuestionType.SINGLE_CHOICE, "备用单选题3", {"value": "A"},
                options=[("A", "A"), ("B", "B")],
            ),
            "extra4": make(
                QuestionType.SINGLE_CHOICE, "备用单选题4", {"value": "A"},
                options=[("A", "A"), ("B", "B")],
            ),
            "extra5": make(
                QuestionType.SINGLE_CHOICE, "备用单选题5", {"value": "A"},
                options=[("A", "A"), ("B", "B")],
            ),
            "multiple2": make(
                QuestionType.MULTIPLE_CHOICE, "备用多选题2", {"values": ["A", "B"]},
                options=[("A", "A"), ("B", "B"), ("C", "C")],
            ),
            "multiple3": make(
                QuestionType.MULTIPLE_CHOICE, "备用多选题3", {"values": ["B", "C"]},
                options=[("A", "A"), ("B", "B"), ("C", "C")],
            ),
            "audio": make(
                QuestionType.AUDIO_UPLOAD, "实践题（音频上传）", {"fileId": 1},
                mode=ScoringMode.MANUAL,
            ),
        }

    # ------------------------------------------------------------------
    # 构造辅助
    # ------------------------------------------------------------------
    def api(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_paper(self, *, teacher=None, subject=Subject.MUSIC, grade=7,
                   status=PaperStatus.READY, with_subjective=True, title="测试试卷",
                   scope_id=None, paper_type=PaperType.FORMAL):
        teacher = teacher or self.teacher
        keys = ["single", "multiple", "true_false", "fill"]
        if with_subjective:
            keys.append("short")
        payload = {
            "title": title,
            "subject": subject,
            "paperType": paper_type,
            "grade": grade,
            "scopeType": ScopeType.CLASS,
            "scopeId": scope_id or self.classroom.id,
            "duration": 45,
            "status": status,
            "questions": [
                {
                    "questionId": self.questions[key].id,
                    "order": index,
                    "sectionName": "客观题" if key != "short" else "主观题",
                    "score": self.questions[key].score,
                }
                for index, key in enumerate(keys, start=1)
            ],
        }
        return create_manual_paper(teacher, payload)

    def make_assessment(self, *, paper=None, teacher=None,
                        target_type=ScopeType.CLASS, target_ids=None,
                        start_offset=timedelta(minutes=-1),
                        end_offset=timedelta(days=1), title="测试测评", **overrides):
        teacher = teacher or self.teacher
        paper = paper or self.make_paper(teacher=teacher)
        now = timezone.now()
        payload = {
            "paperId": paper.id,
            "title": title,
            "targetType": target_type,
            "targetIds": target_ids or [self.classroom.id],
            "startTime": now + start_offset,
            "endTime": now + end_offset,
            "attemptLimit": 1,
            "showAnswerMode": ShowAnswerMode.AFTER_END,
            "allowLateSubmit": False,
        }
        payload.update(overrides)
        return publish_assessment(teacher, payload)

    def start_attempt(self, student=None, assessment=None):
        student = student or self.student
        assessment = assessment or getattr(self, "assessment", None) or self.make_assessment()
        client = self.api(student)
        response = client.post(
            f"/api/v1/assessments/{assessment.id}/attempts",
            {"deviceType": "web"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        return response.json()["data"]["attemptId"]

    def submit_all_correct(self, attempt_id, student=None):
        student = student or self.student
        client = self.api(student)
        q = self.questions
        response = client.post(
            f"/api/v1/attempts/{attempt_id}/submit",
            {
                "submitType": "manual",
                "finalAnswers": [
                    {"questionId": q["single"].id, "answer": {"value": "A"}},
                    {"questionId": q["multiple"].id, "answer": {"values": ["C", "A"]}},
                    {"questionId": q["true_false"].id, "answer": {"value": True}},
                    {"questionId": q["fill"].id, "answer": {"values": ["2", "两"]}},
                    {"questionId": q["short"].id, "answer": {"text": "回答内容"}},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        return response.json()["data"]
