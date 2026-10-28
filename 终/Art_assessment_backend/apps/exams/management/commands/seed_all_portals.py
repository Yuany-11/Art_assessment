"""为所有学生 / 教师账号补齐各功能模块的演示数据（可重复执行）。

在 seed_rich_demo 基础上，为两个班级的音樂、美术四个教学组合补齐：
- 手工组卷 + 自动组卷（含审核通过 / 待审核状态）
- 历史测评、随堂检测、进行中的综合测评
- 已评分成绩、待评分任务、证书
- 每名学生两个学科的学情报告、错题、课外作品
- 班级待审核申请

用法：
    python manage.py seed_all_portals
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.classes.models import Class, ClassTeacher, JoinRequest
from apps.exams.management.commands.seed_rich_demo import Command as RichSeedCommand
from apps.exams.models import Assessment, Certificate, Paper
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.certificate import generate_certificates
from apps.exams.services.paper import create_auto_paper, create_manual_paper
from apps.exams.services.paper_review import review_paper, submit_review
from apps.files.models import FileObject
from apps.files.services import save_upload
from apps.organizations.models import Organization
from apps.qbank.models import Course, Question
from common.enums import (
    FileCategory,
    JoinRequestStatus,
    JoinRequestType,
    PaperStatus,
    PaperType,
    QuestionStatus,
    QuestionType,
    Role,
    ScopeType,
    ShowAnswerMode,
    Subject,
)

MUSIC = Subject.MUSIC
ART = Subject.ART

SUBJECT_CN = {MUSIC: "音乐", ART: "美术"}

SECTION_NAMES = {
    QuestionType.SINGLE_CHOICE: "选择题",
    QuestionType.MULTIPLE_CHOICE: "多选题",
    QuestionType.TRUE_FALSE: "判断题",
    QuestionType.FILL_BLANK: "填空题",
    QuestionType.SHORT_ANSWER: "简答题",
}

MANUAL_RULES = [
    (QuestionType.SINGLE_CHOICE, 5),
    (QuestionType.MULTIPLE_CHOICE, 2),
    (QuestionType.TRUE_FALSE, 2),
    (QuestionType.FILL_BLANK, 2),
    (QuestionType.SHORT_ANSWER, 1),
]
AUTO_RULES = [
    {"type": QuestionType.SINGLE_CHOICE, "count": 6},
    {"type": QuestionType.MULTIPLE_CHOICE, "count": 2},
    {"type": QuestionType.TRUE_FALSE, "count": 2},
    {"type": QuestionType.FILL_BLANK, "count": 2},
    {"type": QuestionType.SHORT_ANSWER, "count": 1},
]


class Command(BaseCommand):
    help = "为所有学生与教师账号生成覆盖各功能页面的演示数据"

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        self.rich = RichSeedCommand()
        self.rich.stdout = self.stdout

        school = Organization.objects.filter(code="S001", deleted_at__isnull=True).first()
        school2 = Organization.objects.filter(
            code="DEMO-SCHOOL", deleted_at__isnull=True
        ).first()
        class1 = Class.objects.filter(school=school, class_code="DEMO-7-1").first()
        class2 = Class.objects.filter(
            school=school2, class_code="DEMO-ACC-7-1"
        ).first()
        if not class1 or not class2:
            raise CommandError("未找到演示班级，请先执行 seed_demo / seed_demo_accounts")

        users = {u.username: u for u in User.objects.filter(
            username__in=[
                "teacher", "teacher_music", "teacher_art", "student", "student2",
                "student_001", "student_002", "question_admin", "school_admin",
            ]
        )}
        missing = [
            name for name in (
                "teacher", "teacher_music", "teacher_art", "student", "student2",
                "student_001", "student_002", "question_admin", "school_admin",
            ) if name not in users
        ]
        if missing:
            raise CommandError(f"缺少演示账号：{', '.join(missing)}")

        teacher = users["teacher"]
        teacher_music = users["teacher_music"]
        teacher_art = users["teacher_art"]
        admin = users["question_admin"]
        student = users["student"]
        student2 = users["student2"]
        student_a = users["student_001"]
        student_b = users["student_002"]

        # teacher_art 同时承担七年级（1）班美术课
        ClassTeacher.objects.get_or_create(
            teacher=teacher_art, class_obj=class1, defaults={"subject": ART}
        )

        music_course = Course.objects.filter(
            name="七年级音乐（人教版）", grade=7
        ).first()
        art_course = Course.objects.filter(
            name="七年级美术（人美版）", grade=7
        ).first()
        if not music_course or not art_course:
            raise CommandError("未找到分类课程，请先执行 seed_rich_demo")

        self._ensure_course_chapters()

        combos = [
            (class1, MUSIC, teacher, music_course, [student, student2], True),
            (class1, ART, teacher_art, art_course, [student, student2], True),
            (class2, MUSIC, teacher_music, music_course, [student_a, student_b], False),
            (class2, ART, teacher_art, art_course, [student_a, student_b], False),
        ]

        stats = {"paper": 0, "assessment": 0, "attempt": 0, "certificate": 0}
        for classroom, subject, subject_teacher, course, students, can_review in combos:
            result = self._seed_combo(
                classroom, subject, subject_teacher, course, students,
                admin, can_review, now,
            )
            for key, value in result.items():
                stats[key] += value

        # 所有学生两个学科的学情报告
        report_count = 0
        for student_obj in (student, student2, student_a, student_b):
            for subject in (MUSIC, ART):
                if self.rich._learning_report(student_obj, subject):
                    report_count += 1

        # 所有学生的音乐 / 美术课外作品
        artwork_count = self._seed_artworks(
            [student, student2, student_a, student_b]
        )

        # 班级申请（教师端班级管理中的申请面板）
        self._seed_join_requests(class1, class2, student2, student_b)

        self.stdout.write(self.style.SUCCESS("全端口演示数据初始化完成"))
        self.stdout.write(
            f"新增试卷 {stats['paper']} 张、测评 {stats['assessment']} 场、"
            f"答卷 {stats['attempt']} 份、证书 {stats['certificate']} 张"
        )
        self.stdout.write(
            f"学情报告 {report_count} 份、课外作品 {artwork_count} 件；"
            "每名学生均有音乐与美术两个学科的成绩、错题与报告"
        )

    # ------------------------------------------------------------------
    def _seed_combo(
        self, classroom, subject, teacher, course, students,
        admin, can_review, now,
    ):
        subject_cn = SUBJECT_CN[subject]
        prefix = f"[全端]{classroom.class_code}·{subject_cn}"
        stats = {"paper": 0, "assessment": 0, "attempt": 0, "certificate": 0}

        manual = self._manual_paper(
            teacher, classroom, course, subject, f"{prefix}·手工组卷", stats
        )
        self._approve(teacher, manual, admin)

        auto_a1 = self._auto_paper(
            teacher, classroom, course, subject, f"{prefix}·自动组卷（阶段一）", stats
        )
        self._approve(teacher, auto_a1, admin)
        auto_a2 = self._auto_paper(
            teacher, classroom, course, subject, f"{prefix}·自动组卷（阶段二）", stats
        )
        self._approve(teacher, auto_a2, admin)
        auto_c = self._auto_paper(
            teacher, classroom, course, subject, f"{prefix}·自动组卷（随堂检测）", stats
        )
        self._approve(teacher, auto_c, admin)

        # 班级 1 额外保留一张待审核试卷，供管理员在试卷审核页操作
        if can_review:
            pending = self._auto_paper(
                teacher, classroom, course, subject, f"{prefix}·待审核试卷", stats
            )
            if pending.review_status == "none":
                submit_review(teacher, pending, pending.version, "演示待审核试卷")

        practice = self._practice_paper(
            teacher, classroom, course, subject, f"{prefix}·实践作品上传体验", stats
        )
        self._approve(teacher, practice, admin)

        a1 = self._assessment(
            teacher, classroom, f"{prefix}·阶段测评（一）", auto_a1,
            now - timedelta(days=50), now - timedelta(days=40), 1, stats,
        )
        a2 = self._assessment(
            teacher, classroom, f"{prefix}·阶段测评（二）", manual,
            now - timedelta(days=15), now - timedelta(days=5), 1, stats,
        )
        c = self._assessment(
            teacher, classroom, f"{prefix}·随堂检测", auto_c,
            now - timedelta(days=3), now - timedelta(days=2), 1, stats,
        )
        self._assessment(
            teacher, classroom, f"{prefix}·综合测评", auto_a2,
            now - timedelta(hours=1), now + timedelta(days=14), 3, stats,
        )
        self._assessment(
            teacher, classroom, f"{prefix}·实践作品上传体验", practice,
            now - timedelta(hours=1), now + timedelta(days=14), 3, stats,
        )

        # 已经评分的两场正式测评
        for assessment, student, wrong_every, rate in (
            (a1, students[0], 3, 0.72),
            (a1, students[1], 5, 0.8),
            (a2, students[0], 7, 0.88),
            (a2, students[1], 4, 0.82),
        ):
            if self.rich._seed_attempt(
                teacher, assessment, student, wrong_every=wrong_every,
                subjective_rate=rate,
            ):
                stats["attempt"] += 1

        # 留一份待评分答卷给教师评分页
        if self.rich._seed_attempt(
            teacher, c, students[1], wrong_every=2, subjective_rate=0.7,
            finalize=False,
        ):
            stats["attempt"] += 1

        # 证书管理页数据
        existing = Certificate.objects.filter(assessment=a2).count()
        try:
            generate_certificates(teacher, {
                "assessmentId": a2.id,
                "subject": subject,
            })
        except Exception as exc:
            self.stderr.write(f"证书生成失败（{prefix}）：{exc}")
        stats["certificate"] += Certificate.objects.filter(assessment=a2).count() - existing
        return stats

    def _manual_paper(self, teacher, classroom, course, subject, title, stats):
        existing = Paper.objects.filter(
            creator=teacher, title=title, deleted_at__isnull=True
        ).first()
        if existing:
            return existing
        questions = list(
            Question.objects.filter(
                subject=subject, grade=7, course=course,
                status=QuestionStatus.APPROVED, deleted_at__isnull=True,
            )
        )
        by_type = {}
        for question in questions:
            by_type.setdefault(question.type, []).append(question)
        configs = []
        order = 0
        for question_type, count in MANUAL_RULES:
            pool = by_type.get(question_type, [])
            if len(pool) < count:
                raise CommandError(
                    f"{title}：{question_type} 题不足，需要 {count} 道，现有 {len(pool)} 道"
                )
            for question in pool[:count]:
                order += 1
                configs.append({
                    "questionId": question.id,
                    "order": order,
                    "sectionName": SECTION_NAMES.get(question_type, ""),
                    "score": float(question.score),
                })
        paper = create_manual_paper(teacher, {
            "title": title,
            "subject": subject,
            "paperType": PaperType.FORMAL,
            "grade": 7,
            "scopeType": ScopeType.CLASS,
            "scopeId": classroom.id,
            "duration": 45,
            "instructions": "教师手工组卷演示试卷。",
            "status": PaperStatus.DRAFT,
            "questions": configs,
        })
        stats["paper"] += 1
        return paper

    def _auto_paper(self, teacher, classroom, course, subject, title, stats):
        existing = Paper.objects.filter(
            creator=teacher, title=title, deleted_at__isnull=True
        ).first()
        if existing:
            return existing
        paper = create_auto_paper(teacher, {
            "title": title,
            "subject": subject,
            "paperType": PaperType.FORMAL,
            "grade": 7,
            "scopeType": ScopeType.CLASS,
            "scopeId": classroom.id,
            "duration": 45,
            "courseIds": [course.id],
            "rules": [dict(rule) for rule in AUTO_RULES],
            "status": PaperStatus.READY,
            "instructions": "自动组卷演示试卷。",
        })
        stats["paper"] += 1
        return paper

    def _practice_paper(self, teacher, classroom, course, subject, title, stats):
        existing = Paper.objects.filter(
            creator=teacher, title=title, deleted_at__isnull=True
        ).first()
        if existing:
            return existing
        practice_type = (
            QuestionType.IMAGE_UPLOAD
            if subject == ART else QuestionType.AUDIO_UPLOAD
        )
        paper = create_auto_paper(teacher, {
            "title": title,
            "subject": subject,
            "paperType": PaperType.PRACTICE,
            "grade": 7,
            "scopeType": ScopeType.CLASS,
            "scopeId": classroom.id,
            "duration": 30,
            "courseIds": [course.id],
            "rules": [
                {"type": QuestionType.SINGLE_CHOICE, "count": 2},
                {"type": QuestionType.SHORT_ANSWER, "count": 1},
                {"type": practice_type, "count": 1},
            ],
            "status": PaperStatus.READY,
            "instructions": "实践作品上传体验：客观题、简答题与实践作品题合计 100 分。",
        })
        stats["paper"] += 1
        return paper

    def _approve(self, teacher, paper, reviewer):
        if paper.review_status == "approved":
            return
        if paper.review_status != "pending":
            if paper.status == PaperStatus.PUBLISHED:
                return
            submit_review(teacher, paper, paper.version, "演示数据自动提交审核")
        paper.refresh_from_db()
        if reviewer and reviewer.id != teacher.id:
            review_paper(
                reviewer, paper, "approve", "演示数据自动审核通过", paper.version
            )

    def _assessment(
        self, teacher, classroom, title, paper, start, end, attempt_limit, stats,
    ):
        existing = Assessment.objects.filter(title=title, publisher=teacher).first()
        if existing:
            return existing
        assessment = publish_assessment(teacher, {
            "paperId": paper.id,
            "title": title,
            "targetType": ScopeType.CLASS,
            "targetIds": [classroom.id],
            "startTime": start,
            "endTime": end,
            "attemptLimit": attempt_limit,
            "showAnswerMode": ShowAnswerMode.AFTER_END,
            "allowLateSubmit": False,
            "instructions": "教学演示测评，请按课堂要求作答。",
        })
        stats["assessment"] += 1
        return assessment

    # ------------------------------------------------------------------
    def _ensure_course_chapters(self):
        """为没有章节的旧课程补建章节，保证学生「趣味课堂」可展开。"""
        from apps.qbank.models import Chapter

        for course in Course.objects.filter(deleted_at__isnull=True):
            if Chapter.objects.filter(
                course=course, deleted_at__isnull=True
            ).exists():
                continue
            questions = Question.objects.filter(
                course=course, deleted_at__isnull=True
            )
            if not questions.exists():
                continue
            chapter = Chapter.objects.create(
                course=course,
                name="综合练习",
                description="本课程基础知识与技能练习。",
                sort_order=1,
            )
            questions.filter(chapter__isnull=True).update(chapter=chapter)

    def _seed_artworks(self, students):
        created = 0
        music_specs = [
            ("歌唱练习-《小星星》.png", 101),
            ("节奏创编-四拍节奏.png", 112),
        ]
        for index, student in enumerate(students):
            for offset, (name, seed) in enumerate(music_specs):
                created += self._owned_artwork(
                    student, MUSIC, name, seed + index * 10 + offset
                )
            if student.username == "student2":
                for offset, (name, seed) in enumerate((
                    ("课外美术-静物写生.png", 131),
                    ("课外美术-图案设计.png", 142),
                )):
                    created += self._owned_artwork(student, ART, name, seed + offset)
        return created

    def _owned_artwork(self, student, subject, name, seed):
        if FileObject.objects.filter(
            category=FileCategory.STUDENT_WORK,
            uploader=student,
            original_name=name,
            deleted_at__isnull=True,
        ).exists():
            return 0
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile(
            name, self.rich._artwork_png(seed), content_type="image/png"
        )
        save_upload(uploaded, FileCategory.STUDENT_WORK, student, subject=subject)
        return 1

    def _seed_join_requests(self, class1, class2, requester1, requester2):
        for classroom, requester, target in (
            (class1, requester1, class2),
            (class2, requester2, class1),
        ):
            JoinRequest.objects.get_or_create(
                class_obj=classroom,
                requester=requester,
                type=JoinRequestType.CHANGE,
                defaults={
                    "requester_role": Role.STUDENT,
                    "target_class": target,
                    "status": JoinRequestStatus.PENDING,
                    "reason": "演示数据：申请转入目标班级",
                },
            )
