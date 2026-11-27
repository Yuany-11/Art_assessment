"""为演示班级补齐教师发布的正式测评与练习测评。

学生端原先只有音乐正式测评和少量学生自主随机练习，美术练习测评及
两个学科的教师练习测评缺失。本命令按班级现有任课关系，为每个班级的
音乐、美术各生成一张正式卷和一张练习卷，提交题库管理员审核后由任课
教师发布到本班，保证学生端“正式测评 / 练习测评”都有可演示数据。

命令幂等：已存在的试卷、测评不会重复创建；重复执行只补缺失项。
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.classes.models import Class, ClassTeacher
from apps.exams.models import Assessment, Paper
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.paper import create_auto_paper
from apps.exams.services.paper_review import review_paper, submit_review
from apps.qbank.models import Course
from common.enums import (
    ClassStatus,
    PaperStatus,
    PaperType,
    QuestionType,
    Role,
    ShowAnswerMode,
    ScopeType,
    Subject,
)

MUSIC = Subject.MUSIC
ART = Subject.ART
SUBJECT_LABEL = {MUSIC: "音乐", ART: "美术"}
FALLBACK_TEACHER = {MUSIC: "teacher_music", ART: "teacher_art"}


class Command(BaseCommand):
    help = "为每个演示班级补齐音乐/美术正式测评与练习测评"

    def add_arguments(self, parser):
        parser.add_argument("--class-code", help="只处理指定班级号")

    @transaction.atomic
    def handle(self, *args, **options):
        admin = (
            User.objects.filter(role=Role.QUESTION_ADMIN, deleted_at__isnull=True)
            .order_by("id")
            .first()
        )
        if admin is None:
            raise CommandError("未找到题库管理员账号，请先执行 seed_demo_accounts")

        classes = Class.objects.filter(
            deleted_at__isnull=True, status=ClassStatus.ACTIVE
        ).select_related("school").order_by("id")
        if options.get("class_code"):
            classes = classes.filter(class_code=options["class_code"])
        if not classes.exists():
            raise CommandError("未找到可用的演示班级")

        now = timezone.now()
        paper_count = 0
        assessment_count = 0
        for classroom in classes:
            for subject in (MUSIC, ART):
                teacher = self._teacher_for(classroom, subject)
                if teacher is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"跳过 {classroom.name} {SUBJECT_LABEL[subject]}：没有任课教师"
                        )
                    )
                    continue
                course = (
                    Course.objects.filter(
                        subject=subject,
                        grade=classroom.grade,
                        deleted_at__isnull=True,
                    )
                    .order_by("id")
                    .first()
                )
                if course is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"跳过 {classroom.name} {SUBJECT_LABEL[subject]}："
                            f"{classroom.grade} 年级课程不存在"
                        )
                    )
                    continue
                for paper_type, label, duration, attempt_limit in (
                    (PaperType.FORMAL, "阶段测评", 45, 1),
                    (PaperType.PRACTICE, "练习测评", 30, 3),
                ):
                    title = f"{classroom.name}·{SUBJECT_LABEL[subject]}{label}"
                    paper = self._paper(
                        teacher, classroom, course, subject, paper_type, title, duration
                    )
                    if paper is None:
                        continue
                    paper_count += 1
                    self._approve(teacher, paper, admin)
                    if paper.status == PaperStatus.PUBLISHED:
                        if Assessment.objects.filter(
                            title=title, publisher=teacher, deleted_at__isnull=True
                        ).exists():
                            continue
                        self.stdout.write(
                            self.style.WARNING(
                                f"跳过 {title}：试卷已发布但没有对应测评，请手动复制试卷"
                            )
                        )
                        continue
                    if Assessment.objects.filter(
                        title=title, publisher=teacher, deleted_at__isnull=True
                    ).exists():
                        continue
                    publish_assessment(
                        teacher,
                        {
                            "paperId": paper.id,
                            "title": title,
                            "targetType": ScopeType.CLASS,
                            "targetIds": [classroom.id],
                            "startTime": now - timedelta(days=1),
                            "endTime": now + timedelta(days=60),
                            "attemptLimit": attempt_limit,
                            "showAnswerMode": ShowAnswerMode.AFTER_END,
                            "allowLateSubmit": False,
                            "instructions": (
                                f"{classroom.name}{SUBJECT_LABEL[subject]}{label}，"
                                "请在规定时间内完成。"
                            ),
                        },
                    )
                    assessment_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"班级测评已补齐：检查 {paper_count} 张试卷，新增 {assessment_count} 场测评"
            )
        )

    def _teacher_for(self, classroom: Class, subject: str):
        relation = (
            ClassTeacher.objects.filter(
                class_obj=classroom, subject=subject, teacher__deleted_at__isnull=True
            )
            .select_related("teacher")
            .first()
        )
        if relation is not None:
            return relation.teacher
        fallback = User.objects.filter(
            username=FALLBACK_TEACHER[subject],
            role=Role.TEACHER,
            deleted_at__isnull=True,
        ).first()
        if fallback is None:
            return None
        ClassTeacher.objects.create(
            class_obj=classroom, teacher=fallback, subject=subject
        )
        return fallback

    def _paper(
        self, teacher, classroom, course, subject, paper_type, title, duration
    ):
        existing = Paper.objects.filter(
            creator=teacher, title=title, deleted_at__isnull=True
        ).first()
        if existing is not None:
            return existing
        practical_type = (
            QuestionType.AUDIO_UPLOAD if subject == MUSIC else QuestionType.IMAGE_UPLOAD
        )
        return create_auto_paper(
            teacher,
            {
                "title": title,
                "subject": subject,
                "paperType": paper_type,
                "grade": classroom.grade,
                "scopeType": ScopeType.CLASS,
                "scopeId": classroom.id,
                "duration": duration,
                "courseIds": [course.id],
                "rules": [
                    {"type": QuestionType.SINGLE_CHOICE, "count": 6},
                    {"type": QuestionType.MULTIPLE_CHOICE, "count": 3},
                    {"type": practical_type, "count": 1},
                ],
                "status": PaperStatus.READY,
                "instructions": "客观题与实践作品题合计 100 分。",
            },
        )

    def _approve(self, teacher, paper: Paper, reviewer: User):
        if paper.review_status == "approved":
            return
        if paper.review_status != "pending":
            submit_review(teacher, paper, paper.version, "演示测评自动提交审核")
            paper.refresh_from_db()
        if reviewer.id != teacher.id:
            review_paper(
                reviewer, paper, "approve", "演示测评自动审核通过", paper.version
            )
            paper.refresh_from_db()
