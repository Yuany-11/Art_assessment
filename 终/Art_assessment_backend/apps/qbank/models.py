"""题库：课程、章节、试题、选项、资源与操作日志。"""
from django.db import models

from common.enums import (
    CourseStatus,
    OperationResult,
    QuestionStatus,
    QuestionType,
    ResourceType,
    ScoringMode,
    Subject,
)
from common.models import BaseModel


class Course(BaseModel):
    name = models.CharField("课程名称", max_length=128, db_comment="课程名称")
    subject = models.CharField(
        "学科", max_length=16, choices=Subject.choices, db_comment="学科：music/art"
    )
    grade = models.PositiveSmallIntegerField(
        "适用年级", db_comment="适用年级（1~12）"
    )
    description = models.CharField(
        "课程简介", max_length=500, null=True, blank=True, db_comment="课程简介"
    )
    sort_order = models.IntegerField("排序值", default=0, db_comment="排序值")
    status = models.CharField(
        "状态",
        max_length=16,
        choices=CourseStatus.choices,
        default=CourseStatus.ACTIVE,
        db_comment="状态：active/disabled",
    )

    class Meta:
        db_table = "courses"
        db_table_comment = "课程表"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.name


class Chapter(BaseModel):
    course = models.ForeignKey(
        Course,
        verbose_name="所属课程",
        on_delete=models.CASCADE,
        related_name="chapters",
        db_comment="所属课程 ID",
    )
    name = models.CharField("章节名称", max_length=128, db_comment="章节名称")
    description = models.CharField(
        "章节简介", max_length=500, null=True, blank=True, db_comment="章节简介"
    )
    content = models.TextField(
        "知识讲解", null=True, blank=True, db_comment="章节知识讲解正文"
    )
    sort_order = models.IntegerField("排序值", default=0, db_comment="课程内排序值")

    class Meta:
        db_table = "chapters"
        db_table_comment = "课程章节表"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.name


class Question(BaseModel):
    subject = models.CharField(
        "学科",
        max_length=16,
        choices=Subject.choices,
        db_index=True,
        db_comment="学科：music/art",
    )
    grade = models.PositiveSmallIntegerField(
        "年级", db_index=True, db_comment="年级（1~12）"
    )
    course = models.ForeignKey(
        Course,
        verbose_name="所属课程",
        on_delete=models.PROTECT,
        related_name="questions",
        db_comment="所属课程 ID",
    )
    chapter = models.ForeignKey(
        Chapter,
        verbose_name="所属章节",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="questions",
        db_comment="所属章节 ID",
    )
    type = models.CharField(
        "题型",
        max_length=32,
        choices=QuestionType.choices,
        db_index=True,
        db_comment="题型：single_choice/multiple_choice/true_false/fill_blank/short_answer/listening/image_upload/audio_upload",
    )
    difficulty = models.PositiveSmallIntegerField(
        "难度", default=1, db_comment="难度（1~5，1 最简单）"
    )
    stem = models.TextField("题干", db_comment="题干内容")
    score = models.DecimalField(
        "默认分值", max_digits=6, decimal_places=2, db_comment="默认分值"
    )
    answer = models.JSONField("标准答案", db_comment="标准答案 JSON")
    analysis = models.TextField(
        "答案解析", null=True, blank=True, db_comment="答案解析"
    )
    rubric = models.TextField(
        "评分标准", null=True, blank=True, db_comment="人工/AI 评分标准"
    )
    scoring_mode = models.CharField(
        "评分方式",
        max_length=16,
        choices=ScoringMode.choices,
        default=ScoringMode.AUTO,
        db_comment="评分方式：auto/manual/ai",
    )
    status = models.CharField(
        "状态",
        max_length=16,
        choices=QuestionStatus.choices,
        default=QuestionStatus.DRAFT,
        db_comment="状态：draft/pending/approved/rejected/offline",
    )
    creator = models.ForeignKey(
        "accounts.User",
        verbose_name="创建人",
        on_delete=models.PROTECT,
        related_name="created_questions",
        db_comment="创建人用户 ID",
    )
    reviewer = models.ForeignKey(
        "accounts.User",
        verbose_name="审核人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_questions",
        db_comment="审核人用户 ID",
    )
    review_comment = models.CharField(
        "审核意见", max_length=500, null=True, blank=True, db_comment="审核意见"
    )
    reviewed_at = models.DateTimeField(
        "审核时间", null=True, blank=True, db_comment="审核时间"
    )

    class Meta:
        db_table = "questions"
        db_table_comment = "试题表"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["subject", "grade", "status"]),
        ]

    def __str__(self) -> str:
        return f"Q{self.id} {self.stem[:20]}"


class QuestionOption(BaseModel):
    question = models.ForeignKey(
        Question,
        verbose_name="试题",
        on_delete=models.CASCADE,
        related_name="options",
        db_comment="试题 ID",
    )
    key = models.CharField(
        "选项标识", max_length=8, db_comment="选项标识，如 A/B/C/D"
    )
    text = models.CharField("选项文本", max_length=1000, db_comment="选项文本")
    media_url = models.CharField(
        "媒体地址", max_length=500, null=True, blank=True,
        db_comment="选项图片/音频 URL",
    )
    sort_order = models.IntegerField("排序值", default=0, db_comment="选项排序值")

    class Meta:
        db_table = "question_options"
        db_table_comment = "试题选项表"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["question", "key"], name="uniq_question_option_key")
        ]


class QuestionResource(BaseModel):
    question = models.ForeignKey(
        Question,
        verbose_name="试题",
        on_delete=models.CASCADE,
        related_name="resources",
        db_comment="试题 ID",
    )
    file = models.ForeignKey(
        "files.FileObject",
        verbose_name="文件",
        on_delete=models.PROTECT,
        related_name="question_resources",
        db_comment="文件 ID",
    )
    type = models.CharField(
        "资源类型",
        max_length=16,
        choices=ResourceType.choices,
        db_comment="资源类型：image/audio",
    )
    sort_order = models.IntegerField("排序值", default=0, db_comment="资源排序值")

    class Meta:
        db_table = "question_resources"
        db_table_comment = "试题资源关联表"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["question", "file"], name="uniq_question_resource")
        ]


class OperationLog(BaseModel):
    operator = models.ForeignKey(
        "accounts.User",
        verbose_name="操作人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="operation_logs",
        db_comment="操作人用户 ID",
    )
    operator_role = models.CharField(
        "操作人角色", max_length=32, db_comment="操作人角色"
    )
    action = models.CharField(
        "操作类型", max_length=64, db_index=True, db_comment="操作类型，如 question.review"
    )
    resource_type = models.CharField(
        "资源类型", max_length=32, db_index=True, db_comment="资源类型，如 question"
    )
    resource_id = models.BigIntegerField(
        "资源 ID", null=True, blank=True, db_comment="被操作资源 ID"
    )
    description = models.CharField(
        "操作说明", max_length=500, db_comment="操作说明"
    )
    ip = models.CharField(
        "客户端 IP", max_length=64, null=True, blank=True, db_comment="客户端 IP"
    )
    user_agent = models.CharField(
        "客户端标识", max_length=255, null=True, blank=True, db_comment="客户端 User-Agent"
    )
    result = models.CharField(
        "结果",
        max_length=16,
        choices=OperationResult.choices,
        default=OperationResult.SUCCESS,
        db_comment="操作结果：success/failed",
    )

    class Meta:
        db_table = "operation_logs"
        db_table_comment = "操作日志表"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.action
