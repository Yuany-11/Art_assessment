"""模块二的最小对接模型。

完整题库 CRUD、审核与资源管理由后端 B（柴国继）实现。测评模块只依赖
Course / Chapter / Question / QuestionOption / QuestionResource 的读取，
合并时保持下列字段命名即可。
"""
from django.conf import settings
from django.db import models

from common.enums import QuestionStatus, QuestionType, ScoringMode, Subject


class Course(models.Model):
    name = models.CharField(max_length=128)
    subject = models.CharField(max_length=16, choices=Subject.choices)
    grade = models.PositiveSmallIntegerField()
    description = models.CharField(max_length=255, null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=16, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "qb_course"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class Chapter(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="chapters")
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=255, null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "qb_chapter"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class Question(models.Model):
    subject = models.CharField(max_length=16, choices=Subject.choices, db_index=True)
    grade = models.PositiveSmallIntegerField(db_index=True)
    course = models.ForeignKey(
        Course, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )
    chapter = models.ForeignKey(
        Chapter, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions"
    )
    type = models.CharField(max_length=32, choices=QuestionType.choices, db_index=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    stem = models.TextField()
    score = models.FloatField(default=5)
    answer = models.JSONField(default=dict, blank=True)
    analysis = models.TextField(null=True, blank=True)
    rubric = models.TextField(null=True, blank=True)
    scoring_mode = models.CharField(
        max_length=16, choices=ScoringMode.choices, default=ScoringMode.AUTO
    )
    status = models.CharField(
        max_length=16, choices=QuestionStatus.choices,
        default=QuestionStatus.APPROVED, db_index=True,
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="created_questions",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_questions",
    )
    review_comment = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "qb_question"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Q{self.pk} {self.stem[:20]}"


class QuestionOption(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )
    key = models.CharField(max_length=8)
    text = models.CharField(max_length=512)
    media_url = models.CharField(max_length=512, null=True, blank=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "qb_question_option"
        ordering = ["sort_order", "id"]
        unique_together = [("question", "key")]


class QuestionResource(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="resources"
    )
    file_id = models.CharField(max_length=64, blank=True, default="")
    type = models.CharField(max_length=16)  # image / audio
    url = models.CharField(max_length=512)
    name = models.CharField(max_length=255, default="")
    mime_type = models.CharField(max_length=128, blank=True, default="")
    size = models.BigIntegerField(default=0)
    local_path = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "qb_question_resource"
        ordering = ["id"]
