"""清空业务演示数据并重新生成一套互相关联的学校数据。

保留：组织、账号、班级、课程/章节（登录和基础结构不重建）。
重建：试题、试卷、测评、答卷、成绩、证书、错题、学情报告、通知、日志、
     入班申请。

默认保留现有题库，只重建试卷/测评/答卷/成绩/证书等业务数据；
确需重建题库时显式加 --reset-questions。

用法：
    python manage.py seed_realistic_reset --yes
    python manage.py seed_realistic_reset --yes --reset-questions
"""
from __future__ import annotations

import io
import random
import time
import wave
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import User
from apps.classes.models import Class, ClassTeacher, JoinRequest
from apps.exams.management.commands.seed_rich_demo import Command as RichSeedCommand
from apps.exams.models import (
    Assessment,
    AssessmentGrade,
    AssessmentTarget,
    Attempt,
    AttemptAnswer,
    Certificate,
    GradingLog,
    ImportTask,
    LearningReport,
    Notification,
    Paper,
    PaperQuestion,
    PaperReviewLog,
    Score,
    WrongQuestion,
)
from apps.exams.services.assessment import publish_assessment
from apps.exams.services.paper import create_manual_paper
from apps.files.models import FileObject
from apps.files.services import save_upload
from apps.organizations.models import Organization
from apps.qbank.models import (
    Chapter,
    Course,
    OperationLog,
    Question,
    QuestionFavorite,
    QuestionOption,
    QuestionResource,
)
from common.enums import (
    FileCategory,
    JoinRequestStatus,
    JoinRequestType,
    PaperReviewStatus,
    PaperStatus,
    PaperType,
    QuestionStatus,
    QuestionType,
    ResourceType,
    Role,
    ScoringMode,
    ScopeType,
    ShowAnswerMode,
    Subject,
)

RNG = random.Random(20261118)
SUBJECT_LABEL = {Subject.MUSIC: "音乐", Subject.ART: "美术"}
GRADE_LABEL = {1: "一年级", 2: "二年级", 3: "三年级", 4: "四年级", 5: "五年级", 6: "六年级", 7: "七年级", 8: "八年级", 9: "九年级"}


class Command(BaseCommand):
    help = "清空业务演示数据并重建一套互相关联的真实感数据"

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="确认清空并重建")
        parser.add_argument(
            "--reset-questions",
            action="store_true",
            help="同时清空题库并重新生成试题（默认保留现有题库）",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("该命令会清空现有业务数据，请加 --yes 确认")
        started = time.time()
        reset_questions = options["reset_questions"]
        self.stdout.write("1/6 清理旧业务数据...")
        self._clear(reset_questions=reset_questions)
        if reset_questions:
            self.stdout.write("2/6 生成试题...")
            question_count = self._seed_questions()
            self.stdout.write(f"   试题 {question_count} 道")
        else:
            question_count = Question.objects.filter(deleted_at__isnull=True).count()
            self.stdout.write(f"2/6 保留现有题库：{question_count} 道")
        self.stdout.write("3/6 组卷...")
        papers = self._seed_papers()
        self.stdout.write(f"   试卷 {len(papers)} 张")
        self.stdout.write("4/6 发布测评与生成答卷...")
        assessments = self._seed_assessments(papers)
        attempts = self._seed_attempts(assessments)
        self.stdout.write(f"   测评 {len(assessments)} 场，答卷 {attempts} 份")
        self.stdout.write("5/6 证书、报告、待办申请...")
        certificates = self._seed_certificates(assessments)
        reports = self._seed_reports()
        requests = self._seed_join_requests()
        artworks = self._seed_artworks()
        wrong_added = self._seed_wrong_questions()
        self.stdout.write(
            f"   证书 {certificates} 张，学情报告 {reports} 份，入班申请 {requests} 条，"
            f"课外作品 {artworks} 件，补充错题 {wrong_added} 条"
        )
        self.stdout.write("6/6 校验数据...")
        self._verify()
        self.stdout.write(
            self.style.SUCCESS(f"完成，用时 {time.time() - started:.1f}s")
        )

    # ------------------------------------------------------------------
    def _clear(self, reset_questions=False):
        # 先删依赖方，再删被引用方；QuerySet.delete() 为硬删除。
        models = [
            AttemptAnswer,
            Attempt,
            Score,
            Certificate,
            LearningReport,
            WrongQuestion,
            Notification,
            GradingLog,
            PaperReviewLog,
            AssessmentTarget,
            AssessmentGrade,
            Assessment,
            PaperQuestion,
            Paper,
            ImportTask,
        ]
        if reset_questions:
            models += [
                QuestionFavorite,
                QuestionResource,
                FileObject,
                QuestionOption,
                Question,
            ]
        models += [JoinRequest, OperationLog]
        for model in models:
            if model is FileObject:
                # 保留头像；题目资源、学生作品、证书等旧文件记录全部重建。
                model.objects.exclude(category=FileCategory.AVATAR).delete()
            else:
                model.objects.all().delete()
        if not reset_questions:
            # 保留题库时只清理学生作品文件，避免每次执行重复累加作品。
            FileObject.objects.filter(category=FileCategory.STUDENT_WORK).delete()

    def _teacher(self, subject):
        username = "teacher_music" if subject == Subject.MUSIC else "teacher_art"
        return User.objects.get(username=username)

    def _admin(self):
        return User.objects.get(username="question_admin")

    # ------------------------------------------------------------------
    def _question_payload(self, subject, chapter_name, index):
        """返回 (type, stem, options, answer, analysis, score, mode)。"""
        music = subject == Subject.MUSIC
        kind = index % 6
        if kind == 0:
            if music:
                stem = f"聆听与“{chapter_name}”相关的音乐片段，下列哪一项描述最符合该段音乐的节拍特点？（ ）"
                options = [
                    ("A", "节奏自由，没有明显节拍"),
                    ("B", "节拍稳定，强弱规律清晰"),
                    ("C", "只有人声，没有器乐"),
                    ("D", "速度始终不变且没有起伏"),
                ]
                analysis = "该单元重点感知稳定节拍与强弱规律，B 项符合课堂听辨要点。"
            else:
                stem = f"在“{chapter_name}”单元中，下列哪一项属于美术学习的重要内容？（ ）"
                options = [
                    ("A", "只背诵画家生平"),
                    ("B", "观察、想象与造型表现"),
                    ("C", "只抄写课本文字"),
                    ("D", "与画面无关的计算"),
                ]
                analysis = "美术学习强调观察、想象、造型与表达，B 项最全面。"
            return (
                QuestionType.SINGLE_CHOICE, stem, options, {"value": "B"},
                analysis, 5, ScoringMode.AUTO,
            )
        if kind == 1:
            if music:
                stem = f"学习“{chapter_name}”时，节拍与节奏是完全相同的概念。（ ）"
                analysis = "节拍是强弱规律，节奏是音的长短组合，两者不同。"
                answer = {"value": False}
            else:
                stem = f"完成“{chapter_name}”作品时，只需要临摹，不需要观察生活。（ ）"
                analysis = "观察生活是美术创作的重要来源，临摹不能替代观察与想象。"
                answer = {"value": False}
            return (
                QuestionType.TRUE_FALSE, stem, [], answer,
                analysis, 5, ScoringMode.AUTO,
            )
        if kind == 2:
            if music:
                stem = f"音乐中由强弱规律形成的循环单位通常称为____。"
                answer = {"values": ["节拍"]}
                analysis = "节拍是音乐中强弱交替的规律单位。"
            else:
                stem = f"“{chapter_name}”单元中，用来表现物体明暗层次的因素是____。"
                answer = {"values": ["明暗"]}
                analysis = "明暗关系是塑造体积和空间感的重要手段。"
            return (
                QuestionType.FILL_BLANK, stem, [], answer,
                analysis, 5, ScoringMode.AUTO,
            )
        if kind == 3:
            if music:
                stem = f"学习“{chapter_name}”时，下列哪些方式有助于感受音乐？（ ）"
                options = [
                    ("A", "跟随节拍轻轻律动"),
                    ("B", "关注旋律的起伏"),
                    ("C", "只抄写歌词不聆听"),
                    ("D", "分辨乐器音色"),
                ]
                answer = {"values": ["A", "B", "D"]}
                analysis = "律动、旋律起伏和音色分辨都能帮助感受音乐。"
            else:
                stem = f"完成“{chapter_name}”作品时，下列哪些做法有助于提升画面效果？（ ）"
                options = [
                    ("A", "先观察再起稿"),
                    ("B", "注意主体与背景的关系"),
                    ("C", "完全不考虑构图"),
                    ("D", "适当运用色彩对比"),
                ]
                answer = {"values": ["A", "B", "D"]}
                analysis = "观察、构图和色彩对比都能提升画面表现。"
            return (
                QuestionType.MULTIPLE_CHOICE, stem, options, answer,
                analysis, 6, ScoringMode.AUTO,
            )
        if kind == 4:
            if music:
                stem = f"“{chapter_name}”单元中，下列哪一件乐器属于民族管弦乐队常用的拉弦乐器？（ ）"
                options = [("A", "二胡"), ("B", "小号"), ("C", "钢琴"), ("D", "架子鼓")]
                answer = {"value": "A"}
                analysis = "二胡是民族管弦乐队常用的拉弦乐器。"
            else:
                stem = f"在“{chapter_name}”单元中，下列哪种工具最适合表现细腻的线条？（ ）"
                options = [("A", "油画棒"), ("B", "勾线笔"), ("C", "海绵"), ("D", "调色刀")]
                answer = {"value": "B"}
                analysis = "勾线笔更适合表现细腻、连续的线条。"
            return (
                QuestionType.SINGLE_CHOICE, stem, options, answer,
                analysis, 5, ScoringMode.AUTO,
            )
        if music:
            stem = f"“{chapter_name}”学习中，音乐的速度与情绪没有任何关系。（ ）"
            analysis = "速度会明显影响音乐情绪，例如快速常显得活泼，慢速常显得抒情。"
            answer = {"value": False}
        else:
            stem = f"“{chapter_name}”单元中，画面的主体应始终放在正中央，不能有其他安排。（ ）"
            analysis = "主体可以居中，也可以通过三分法、均衡等方式安排。"
            answer = {"value": False}
        return (
            QuestionType.TRUE_FALSE, stem, [], answer,
            analysis, 5, ScoringMode.AUTO,
        )

    def _seed_questions(self):
        admin = self._admin()
        now = timezone.now()
        created = 0
        for course in Course.objects.filter(deleted_at__isnull=True).order_by("grade", "subject"):
            chapters = list(
                Chapter.objects.filter(course=course, deleted_at__isnull=True).order_by("sort_order", "id")
            )
            if not chapters:
                continue
            teacher = self._teacher(course.subject)
            for index in range(20):
                chapter = chapters[index % len(chapters)]
                qtype, stem, options, answer, analysis, score, mode = self._question_payload(
                    course.subject, chapter.name, index
                )
                status = QuestionStatus.APPROVED
                if index == 18:
                    status = QuestionStatus.PENDING
                elif index == 19:
                    status = QuestionStatus.REJECTED
                question = Question.objects.create(
                    subject=course.subject,
                    grade=course.grade,
                    course=course,
                    chapter=chapter,
                    type=qtype,
                    difficulty=(index % 4) + 1,
                    stem=stem,
                    score=score,
                    answer=answer,
                    analysis=analysis,
                    rubric="按课堂评分要点给分，鼓励结合具体作品说明。" if mode == ScoringMode.MANUAL else None,
                    scoring_mode=mode,
                    knowledge_point=chapter.name,
                    status=status,
                    creator=teacher,
                    reviewer=admin if status != QuestionStatus.PENDING else None,
                    reviewed_at=now if status != QuestionStatus.PENDING else None,
                    review_comment=(
                        "内容与教材单元匹配，审核通过。" if status == QuestionStatus.APPROVED
                        else "题干表述不够清晰，请修改后重新提交。" if status == QuestionStatus.REJECTED
                        else None
                    ),
                )
                for sort_order, (key, text) in enumerate(options):
                    QuestionOption.objects.create(
                        question=question, key=key, text=text, sort_order=sort_order
                    )
                created += 1

            # 每门课一道实践作品题，保证教师评分页始终有待评分任务。
            manual_type = QuestionType.IMAGE_UPLOAD if course.subject == Subject.ART else QuestionType.AUDIO_UPLOAD
            manual_stem = (
                f"围绕“{chapters[0].name}”完成一幅美术作品，上传清晰照片并说明创作思路。"
                if course.subject == Subject.ART
                else f"围绕“{chapters[0].name}”演唱或演奏一段作品，上传音频并说明情绪处理。"
            )
            Question.objects.create(
                subject=course.subject,
                grade=course.grade,
                course=course,
                chapter=chapters[0],
                type=manual_type,
                difficulty=3,
                stem=manual_stem,
                score=20,
                answer={"rubric": {"criteria": "主题、表现、完整性各占一定分值"}},
                analysis="按评分要点结合作品完成度给分。",
                rubric="主题明确 5 分；表现与技法 8 分；完整性 7 分。",
                scoring_mode=ScoringMode.MANUAL,
                knowledge_point=chapters[0].name,
                status=QuestionStatus.APPROVED,
                creator=teacher,
                reviewer=admin,
                reviewed_at=now,
                review_comment="实践题评分标准清晰，审核通过。",
            )
            created += 1

        # 图像/音频选择判断题：给七年级美术、音乐各补 2 道，确保题型链路有数据。
        created += self._seed_media_questions()
        return created

    def _seed_media_questions(self):
        admin = self._admin()
        now = timezone.now()
        count = 0
        for subject, qtype, category, ext in (
            (Subject.ART, QuestionType.IMAGE_CHOICE_JUDGE, FileCategory.QUESTION_IMAGE, "png"),
            (Subject.MUSIC, QuestionType.AUDIO_CHOICE_JUDGE, FileCategory.QUESTION_AUDIO, "wav"),
        ):
            course = Course.objects.filter(
                subject=subject, grade=7, deleted_at__isnull=True
            ).first()
            if course is None:
                continue
            chapter = Chapter.objects.filter(course=course, deleted_at__isnull=True).first()
            teacher = self._teacher(subject)
            for index in range(2):
                if qtype == QuestionType.IMAGE_CHOICE_JUDGE:
                    image = Image.new("RGB", (480, 320), "white")
                    draw = ImageDraw.Draw(image)
                    draw.rectangle((40, 50, 220, 270), fill=(230, 120, 90))
                    draw.ellipse((240, 80, 430, 270), fill=(90, 140, 220))
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    content = buffer.getvalue()
                    uploaded = SimpleUploadedFile(
                        f"seed-art-{index}.png", content, content_type="image/png"
                    )
                    stem = "观察题干图片，画面中主要运用了哪种构图方式？（ ）"
                    options = [("A", "对称"), ("B", "均衡"), ("C", "透视"), ("D", "留白")]
                    answer = {"value": "B"}
                else:
                    buffer = io.BytesIO()
                    with wave.open(buffer, "wb") as handle:
                        handle.setnchannels(1)
                        handle.setsampwidth(2)
                        handle.setframerate(22050)
                        frames = bytearray()
                        for i in range(22050):
                            value = int(8000 * (1 if (i // 500) % 2 == 0 else -1))
                            frames += value.to_bytes(2, "little", signed=True)
                        handle.writeframes(bytes(frames))
                    content = buffer.getvalue()
                    uploaded = SimpleUploadedFile(
                        f"seed-music-{index}.wav", content, content_type="audio/wav"
                    )
                    stem = "聆听题干音频，这段声音的节拍特点是（ ）。"
                    options = [("A", "节拍稳定"), ("B", "完全无节拍"), ("C", "只有人声"), ("D", "速度自由")]
                    answer = {"value": "A"}
                file_obj = save_upload(uploaded, category, teacher)
                question = Question.objects.create(
                    subject=subject,
                    grade=7,
                    course=course,
                    chapter=chapter,
                    type=qtype,
                    difficulty=2,
                    stem=stem,
                    score=5,
                    answer=answer,
                    analysis="结合题干媒体内容与课堂知识作答。",
                    scoring_mode=ScoringMode.AUTO,
                    knowledge_point=chapter.name if chapter else "综合",
                    status=QuestionStatus.APPROVED,
                    creator=teacher,
                    reviewer=admin,
                    reviewed_at=now,
                    review_comment="媒体资源清晰，审核通过。",
                )
                for order, (key, text) in enumerate(options):
                    QuestionOption.objects.create(
                        question=question, key=key, text=text, sort_order=order
                    )
                QuestionResource.objects.create(
                    question=question,
                    file=file_obj,
                    type=ResourceType.IMAGE if qtype == QuestionType.IMAGE_CHOICE_JUDGE else ResourceType.AUDIO,
                    sort_order=0,
                )
                count += 1
        return count

    # ------------------------------------------------------------------
    def _seed_papers(self):
        admin = self._admin()
        now = timezone.now()
        papers = []
        classes = list(Class.objects.filter(deleted_at__isnull=True).select_related("school"))
        for classroom in classes:
            for subject in (Subject.MUSIC, Subject.ART):
                course = Course.objects.filter(
                    subject=subject, grade=classroom.grade, deleted_at__isnull=True
                ).first()
                if course is None:
                    continue
                teacher = ClassTeacher.objects.filter(
                    class_obj=classroom, subject=subject, deleted_at__isnull=True
                ).select_related("teacher").first()
                creator = teacher.teacher if teacher else self._teacher(subject)
                approved = list(
                    Question.objects.filter(
                        course=course,
                        subject=subject,
                        grade=classroom.grade,
                        status=QuestionStatus.APPROVED,
                        deleted_at__isnull=True,
                    ).order_by("id")
                )
                manual = [q for q in approved if q.scoring_mode == ScoringMode.MANUAL]
                objective = [q for q in approved if q.scoring_mode != ScoringMode.MANUAL]
                questions = (manual[:1] + objective)[:8]
                if len(questions) < 5:
                    continue
                for paper_type, suffix in (
                    (PaperType.FORMAL, "期末测评卷"),
                    (PaperType.PRACTICE, "单元练习卷"),
                ):
                    title = (
                        f"2026-2027学年第一学期{GRADE_LABEL[classroom.grade]}"
                        f"{SUBJECT_LABEL[subject]}{suffix}（{classroom.name}）"
                    )
                    score = round(100 / len(questions), 2)
                    paper = create_manual_paper(
                        creator,
                        {
                            "title": title,
                            "subject": subject,
                            "paperType": paper_type,
                            "grade": classroom.grade,
                            "scopeType": ScopeType.CLASS,
                            "scopeId": classroom.id,
                            "duration": 45 if paper_type == PaperType.FORMAL else 30,
                            "status": PaperStatus.READY,
                            "instructions": "请按要求独立完成，作品题注意画面完整与主题表达。",
                            "questions": [
                                {
                                    "questionId": question.id,
                                    "order": index,
                                    "score": score,
                                    "sectionName": "试题部分",
                                }
                                for index, question in enumerate(questions, start=1)
                            ],
                        },
                    )
                    Paper.objects.filter(pk=paper.pk).update(
                        review_status=PaperReviewStatus.APPROVED,
                        reviewer=admin,
                        reviewed_at=now,
                        review_comment="题目与课程章节匹配，审核通过。",
                    )
                    papers.append(paper)

        # 没有对应班级的年级也补一套校级试卷，保证组卷列表覆盖 1~9 年级。
        school = Organization.objects.filter(level="school", deleted_at__isnull=True).first()
        school_admin = User.objects.filter(role=Role.SCHOOL_ADMIN, org=school).first()
        existing_grades = {paper.grade for paper in papers}
        if school and school_admin:
            for grade in range(1, 10):
                if grade in existing_grades:
                    continue
                for subject in (Subject.MUSIC, Subject.ART):
                    course = Course.objects.filter(
                        subject=subject, grade=grade, deleted_at__isnull=True
                    ).first()
                    if course is None:
                        continue
                    approved = list(
                        Question.objects.filter(
                            course=course,
                            status=QuestionStatus.APPROVED,
                            deleted_at__isnull=True,
                        ).order_by("id")
                    )
                    manual = [q for q in approved if q.scoring_mode == ScoringMode.MANUAL]
                    objective = [q for q in approved if q.scoring_mode != ScoringMode.MANUAL]
                    questions = (manual[:1] + objective)[:8]
                    if len(questions) < 5:
                        continue
                    title = (
                        f"2026-2027学年第一学期{GRADE_LABEL[grade]}"
                        f"{SUBJECT_LABEL[subject]}期末测评卷（校级）"
                    )
                    paper = create_manual_paper(
                        school_admin,
                        {
                            "title": title,
                            "subject": subject,
                            "paperType": PaperType.FORMAL,
                            "grade": grade,
                            "scopeType": ScopeType.SCHOOL,
                            "scopeId": school.id,
                            "duration": 45,
                            "status": PaperStatus.READY,
                            "instructions": "校级统一测评卷，请按题目要求完成。",
                            "questions": [
                                {
                                    "questionId": question.id,
                                    "order": index,
                                    "score": round(100 / len(questions), 2),
                                    "sectionName": "试题部分",
                                }
                                for index, question in enumerate(questions, start=1)
                            ],
                        },
                    )
                    Paper.objects.filter(pk=paper.pk).update(
                        review_status=PaperReviewStatus.APPROVED,
                        reviewer=admin,
                        reviewed_at=now,
                        review_comment="校级试卷审核通过。",
                    )
                    papers.append(paper)

        # 留 2 张待审核试卷，保证题库管理端的“试卷审核”页面有任务。
        for subject in (Subject.MUSIC, Subject.ART):
            classroom = Class.objects.filter(grade=7, deleted_at__isnull=True).first()
            if classroom is None:
                continue
            course = Course.objects.filter(
                subject=subject, grade=7, deleted_at__isnull=True
            ).first()
            teacher = ClassTeacher.objects.filter(
                class_obj=classroom, subject=subject, deleted_at__isnull=True
            ).select_related("teacher").first()
            creator = teacher.teacher if teacher else self._teacher(subject)
            questions = list(
                Question.objects.filter(
                    course=course, subject=subject, status=QuestionStatus.APPROVED,
                    deleted_at__isnull=True,
                ).order_by("id")[:6]
            ) if course else []
            if len(questions) < 5:
                continue
            paper = create_manual_paper(
                creator,
                {
                    "title": f"2026-2027学年第一学期七年级{SUBJECT_LABEL[subject]}抽检测评卷（待审核）",
                    "subject": subject,
                    "paperType": PaperType.FORMAL,
                    "grade": 7,
                    "scopeType": ScopeType.CLASS,
                    "scopeId": classroom.id,
                    "duration": 45,
                    "status": PaperStatus.READY,
                    "instructions": "抽检测评卷，提交题库管理员审核。",
                    "questions": [
                        {
                            "questionId": question.id,
                            "order": index,
                            "score": round(100 / len(questions), 2),
                            "sectionName": "试题部分",
                        }
                        for index, question in enumerate(questions, start=1)
                    ],
                },
            )
            Paper.objects.filter(pk=paper.pk).update(review_status=PaperReviewStatus.PENDING)
            papers.append(paper)
        return papers

    # ------------------------------------------------------------------
    def _seed_assessments(self, papers):
        now = timezone.now()
        assessments = []
        for paper in papers:
            if paper.scope_type != ScopeType.CLASS:
                continue
            classroom = Class.objects.filter(pk=paper.scope_id, deleted_at__isnull=True).first()
            if classroom is None:
                continue
            creator = paper.creator
            if paper.paper_type == PaperType.FORMAL:
                title = (
                    f"2026-2027学年第一学期{GRADE_LABEL[classroom.grade]}"
                    f"{SUBJECT_LABEL[paper.subject]}期末测评（{classroom.name}）"
                )
                start, end = now - timedelta(days=22), now - timedelta(days=15)
            else:
                title = (
                    f"2026-2027学年第一学期{GRADE_LABEL[classroom.grade]}"
                    f"{SUBJECT_LABEL[paper.subject]}单元练习（{classroom.name}）"
                )
                start, end = now - timedelta(hours=2), now + timedelta(days=7)
            try:
                assessment = publish_assessment(
                    creator,
                    {
                        "paperId": paper.id,
                        "title": title,
                        "targetType": ScopeType.CLASS,
                        "targetIds": [classroom.id],
                        "startTime": start,
                        "endTime": end,
                        "attemptLimit": 2,
                        "showAnswerMode": ShowAnswerMode.AFTER_END,
                        "allowLateSubmit": False,
                        "instructions": "按课堂要求完成；作品题请上传清晰照片或音频。",
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"发布测评失败（{title}）：{exc}")
                continue
            assessments.append(assessment)
        return assessments

    def _seed_attempts(self, assessments):
        helper = RichSeedCommand()
        helper.stdout = self.stdout
        helper.stderr = self.stderr
        now = timezone.now()
        count = 0
        for assessment in assessments:
            if assessment.end_time > now:
                continue
            classroom = Class.objects.filter(pk=assessment.target_ids[0]).first() if assessment.target_ids else None
            if classroom is None:
                continue
            teacher = ClassTeacher.objects.filter(
                class_obj=classroom, subject=assessment.subject, deleted_at__isnull=True
            ).select_related("teacher").first()
            grader = teacher.teacher if teacher else assessment.paper.creator
            students = list(
                User.objects.filter(
                    student_profile__classroom=classroom,
                    student_profile__deleted_at__isnull=True,
                    deleted_at__isnull=True,
                ).order_by("id")[:5]
            )
            for index, student in enumerate(students):
                # 第一位学生给出 90+ 的成绩，保证证书模块有真实可发的数据。
                perfect = index == 0 and assessment.paper_type == PaperType.FORMAL
                try:
                    if helper._seed_attempt(
                        grader,
                        assessment,
                        student,
                        wrong_every=0 if perfect else 3 + (index % 3),
                        subjective_rate=1.0 if perfect else 0.75 + index * 0.05,
                        finalize=index < 3,
                    ):
                        count += 1
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(
                        f"生成答卷失败（{assessment.title}/{student.username}）：{exc}"
                    )
        return count

    # ------------------------------------------------------------------
    def _seed_certificates(self, assessments):
        count = 0
        for assessment in assessments:
            if assessment.paper_type != PaperType.FORMAL:
                continue
            classroom = Class.objects.filter(pk=assessment.target_ids[0]).first() if assessment.target_ids else None
            if classroom is None:
                continue
            teacher = ClassTeacher.objects.filter(
                class_obj=classroom, subject=assessment.subject, deleted_at__isnull=True
            ).select_related("teacher").first()
            grader = teacher.teacher if teacher else assessment.paper.creator
            student_ids = list(
                Score.objects.filter(
                    assessment=assessment, status="graded"
                ).values_list("student_id", flat=True)[:2]
            )
            if not student_ids:
                continue
            try:
                generate = __import__(
                    "apps.exams.services.certificate", fromlist=["generate_certificates"]
                ).generate_certificates
                actors = [assessment.publisher, grader, assessment.paper.creator]
                for actor in actors:
                    if actor is None:
                        continue
                    try:
                        generate(
                            actor,
                            {
                                "assessmentId": assessment.id,
                                "subject": assessment.subject,
                                "studentIds": student_ids,
                            },
                        )
                        break
                    except Exception:
                        continue
                count += Certificate.objects.filter(
                    assessment=assessment, student_id__in=student_ids
                ).count()
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"证书生成失败（{assessment.title}）：{exc}")
        return count

    def _seed_reports(self):
        helper = RichSeedCommand()
        count = 0
        for student in User.objects.filter(role=Role.STUDENT, deleted_at__isnull=True)[:20]:
            for subject in (Subject.MUSIC, Subject.ART):
                try:
                    if helper._learning_report(student, subject):
                        count += 1
                except Exception:
                    continue
        return count

    def _seed_join_requests(self):
        count = 0
        classes = list(Class.objects.filter(deleted_at__isnull=True))
        if len(classes) < 2:
            return 0
        students = list(
            User.objects.filter(role=Role.STUDENT, deleted_at__isnull=True)[:100]
        )
        for student in students:
            if count >= 3:
                break
            profile = getattr(student, "student_profile", None)
            if profile is None or profile.classroom_id is None:
                continue
            target = next(
                (item for item in classes if item.id != profile.classroom_id and item.grade == profile.grade),
                None,
            )
            if target is None:
                continue
            JoinRequest.objects.create(
                class_obj=profile.classroom,
                requester=student,
                requester_role=Role.STUDENT,
                type=JoinRequestType.CHANGE,
                target_class=target,
                status=JoinRequestStatus.PENDING,
                reason="家庭住址调整，希望转入同年级其他班级。",
            )
            count += 1
        return count

    def _seed_wrong_questions(self):
        from apps.exams.models import Attempt
        now = timezone.now()
        added = 0
        demo_names = ["student", "student_001", "student_002", "student2"]
        students = list(
            User.objects.filter(username__in=demo_names, deleted_at__isnull=True)
        )
        students += list(
            User.objects.filter(role=Role.STUDENT, deleted_at__isnull=True)
            .exclude(id__in=[item.id for item in students])[:2]
        )
        for student in students:
            existing = set(
                WrongQuestion.objects.filter(student=student).values_list("question_id", flat=True)
            )
            profile = getattr(student, "student_profile", None)
            grade = profile.grade if profile else None
            questions = list(
                Question.objects.filter(
                    status=QuestionStatus.APPROVED,
                    deleted_at__isnull=True,
                    grade=grade or 7,
                ).exclude(id__in=existing).order_by("id")[:3]
            )
            attempt = Attempt.objects.filter(student=student).order_by("-id").first()
            for question in questions:
                options = list(
                    question.options.filter(deleted_at__isnull=True)
                    .order_by("sort_order", "id")
                    .values("key", "text")
                )
                answer = question.answer or {}
                student_answer = {}
                if question.type in (QuestionType.SINGLE_CHOICE, QuestionType.LISTENING, QuestionType.AUDIO_CHOICE_JUDGE):
                    wrong_keys = [item["key"] for item in options if item["key"] != answer.get("value")]
                    student_answer = {"value": wrong_keys[0] if wrong_keys else "A"}
                elif question.type == QuestionType.TRUE_FALSE:
                    student_answer = {"value": not bool(answer.get("value"))}
                elif question.type == QuestionType.MULTIPLE_CHOICE:
                    student_answer = {"values": list(answer.get("values") or [])[:-1] or ["A"]}
                else:
                    student_answer = {"values": ["未掌握"]}
                WrongQuestion.objects.create(
                    student=student,
                    question_id=question.id,
                    subject=question.subject,
                    type=question.type,
                    stem=question.stem,
                    options=options,
                    resources=[],
                    correct_answer=answer,
                    student_answer=student_answer,
                    analysis=question.analysis,
                    wrong_count=1,
                    last_wrong_at=now,
                    mastery_status="unmastered",
                    source_type="formal",
                    source_assessment_id=attempt.assessment_id if attempt else None,
                    source_assessment_title=attempt.assessment.title if attempt else None,
                )
                added += 1
        return added

    def _seed_artworks(self):
        count = 0
        demo_names = ["student", "student_001", "student_002", "student2"]
        students = list(
            User.objects.filter(username__in=demo_names, deleted_at__isnull=True)
        )
        students += list(
            User.objects.filter(role=Role.STUDENT, deleted_at__isnull=True)
            .exclude(id__in=[item.id for item in students])[:2]
        )
        reviewer = User.objects.filter(username="teacher_art").first()
        for student in students:
            for subject, label, color in (
                (Subject.ART, "课外写生-校园一角", (235, 160, 120)),
                (Subject.ART, "水彩练习-秋日静物", (160, 200, 230)),
            ):
                image = Image.new("RGB", (480, 360), "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((30, 40, 450, 330), outline=color, width=6)
                draw.ellipse((160, 100, 330, 280), fill=color)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                uploaded = SimpleUploadedFile(
                    f"{label}.png", buffer.getvalue(), content_type="image/png"
                )
                file_obj = save_upload(
                    uploaded, FileCategory.STUDENT_WORK, student, subject=subject.value
                )
                file_obj.review_score = 88
                file_obj.review_comment = "构图完整，色彩关系较好，建议加强细节观察。"
                file_obj.reviewed_by = reviewer
                file_obj.reviewed_at = timezone.now()
                file_obj.save(update_fields=["review_score", "review_comment", "reviewed_by", "reviewed_at", "updated_at"])
                count += 1
        return count

    # ------------------------------------------------------------------
    def _verify(self):
        checks = [
            ("用户", User.objects.count()),
            ("课程", Course.objects.count()),
            ("章节", Chapter.objects.count()),
            ("试题", Question.objects.count()),
            ("待审试题", Question.objects.filter(status=QuestionStatus.PENDING).count()),
            ("试卷", Paper.objects.count()),
            ("测评", Assessment.objects.count()),
            ("答卷", Attempt.objects.count()),
            ("成绩", Score.objects.count()),
            ("证书", Certificate.objects.count()),
            ("错题", WrongQuestion.objects.count()),
            ("学情报告", LearningReport.objects.count()),
            ("通知", Notification.objects.count()),
        ]
        for label, value in checks:
            self.stdout.write(f"   {label}: {value}")
            if value == 0:
                self.stderr.write(f"   [警告] {label} 为空")
