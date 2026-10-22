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
    name = models.CharField("课程名称", max_length=128)
    subject = models.CharField("学科", max_length=16, choices=Subject.choices)
    grade = models.PositiveSmallIntegerField("适用年级")
    description = models.CharField("课程简介", max_length=500, null=True, blank=True)
    sort_order = models.IntegerField("排序值", default=0)
    status = models.CharField(
        "状态", max_length=16, choices=CourseStatus.choices, default=CourseStatus.ACTIVE
    )

    class Meta:
        db_table = "courses"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.name


class Chapter(BaseModel):
    course = models.ForeignKey(
        Course, verbose_name="所属课程", on_delete=models.CASCADE, related_name="chapters"
    )
    name = models.CharField("章节名称", max_length=128)
    description = models.CharField("章节简介", max_length=500, null=True, blank=True)
    sort_order = models.IntegerField("排序值", default=0)

    class Meta:
        db_table = "chapters"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.name


class Question(BaseModel):
    subject = models.CharField("学科", max_length=16, choices=Subject.choices, db_index=True)
    grade = models.PositiveSmallIntegerField("年级", db_index=True)
    course = models.ForeignKey(
        Course, verbose_name="所属课程", on_delete=models.PROTECT, related_name="questions"
    )
    chapter = models.ForeignKey(
        Chapter,
        verbose_name="所属章节",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="questions",
    )
    type = models.CharField("题型", max_length=32, choices=QuestionType.choices, db_index=True)
    difficulty = models.PositiveSmallIntegerField("难度", default=1)
    stem = models.TextField("题干")
    score = models.DecimalField("默认分值", max_digits=6, decimal_places=2)
    answer = models.JSONField("标准答案")
    analysis = models.TextField("答案解析", null=True, blank=True)
    scoring_mode = models.CharField(
        "评分方式", max_length=16, choices=ScoringMode.choices, default=ScoringMode.AUTO
    )
    status = models.CharField(
        "状态", max_length=16, choices=QuestionStatus.choices, default=QuestionStatus.DRAFT
    )
    creator = models.ForeignKey(
        "accounts.User",
        verbose_name="创建人",
        on_delete=models.PROTECT,
        related_name="created_questions",
    )
    reviewer = models.ForeignKey(
        "accounts.User",
        verbose_name="审核人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_questions",
    )
    review_comment = models.CharField("审核意见", max_length=500, null=True, blank=True)
    reviewed_at = models.DateTimeField("审核时间", null=True, blank=True)

    class Meta:
        db_table = "questions"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["subject", "grade", "status"]),
        ]

    def __str__(self) -> str:
        return f"Q{self.id} {self.stem[:20]}"


class QuestionOption(BaseModel):
    question = models.ForeignKey(
        Question, verbose_name="试题", on_delete=models.CASCADE, related_name="options"
    )
    key = models.CharField("选项标识", max_length=8)
    text = models.CharField("选项文本", max_length=1000)
    media_url = models.CharField("媒体地址", max_length=500, null=True, blank=True)
    sort_order = models.IntegerField("排序值", default=0)

    class Meta:
        db_table = "question_options"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["question", "key"], name="uniq_question_option_key")
        ]


class QuestionResource(BaseModel):
    question = models.ForeignKey(
        Question, verbose_name="试题", on_delete=models.CASCADE, related_name="resources"
    )
    file = models.ForeignKey(
        "files.FileObject",
        verbose_name="文件",
        on_delete=models.PROTECT,
        related_name="question_resources",
    )
    type = models.CharField("资源类型", max_length=16, choices=ResourceType.choices)
    sort_order = models.IntegerField("排序值", default=0)

    class Meta:
        db_table = "question_resources"
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
    )
    operator_role = models.CharField("操作人角色", max_length=32)
    action = models.CharField("操作类型", max_length=64, db_index=True)
    resource_type = models.CharField("资源类型", max_length=32, db_index=True)
    resource_id = models.BigIntegerField("资源 ID", null=True, blank=True)
    description = models.CharField("操作说明", max_length=500)
    ip = models.CharField("客户端 IP", max_length=64, null=True, blank=True)
    user_agent = models.CharField("客户端标识", max_length=255, null=True, blank=True)
    result = models.CharField(
        "结果", max_length=16, choices=OperationResult.choices, default=OperationResult.SUCCESS
    )

    class Meta:
        db_table = "operation_logs"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.action
