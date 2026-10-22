"""班级、科任教师关系与入班申请。"""
from django.db import models

from common.enums import ClassStatus, JoinRequestStatus, JoinRequestType, Subject
from common.models import BaseModel


class Class(BaseModel):
    name = models.CharField("班级名称", max_length=128)
    class_code = models.CharField("班级号", max_length=32, unique=True)
    grade = models.PositiveSmallIntegerField("年级")
    school = models.ForeignKey(
        "organizations.Organization",
        verbose_name="所属学校",
        on_delete=models.PROTECT,
        related_name="classes",
    )
    head_teacher = models.ForeignKey(
        "accounts.User",
        verbose_name="班主任",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_classes",
    )
    description = models.CharField("班级简介", max_length=500, null=True, blank=True)
    status = models.CharField(
        "状态", max_length=16, choices=ClassStatus.choices, default=ClassStatus.ACTIVE
    )
    created_by = models.ForeignKey(
        "accounts.User",
        verbose_name="创建人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_classes",
    )

    class Meta:
        db_table = "classes"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.name}({self.class_code})"


class ClassTeacher(BaseModel):
    class_obj = models.ForeignKey(
        Class, verbose_name="班级", on_delete=models.CASCADE, related_name="subject_teachers"
    )
    teacher = models.ForeignKey(
        "accounts.User",
        verbose_name="教师",
        on_delete=models.CASCADE,
        related_name="teaching_classes",
    )
    subject = models.CharField("任教学科", max_length=16, choices=Subject.choices)

    class Meta:
        db_table = "class_teachers"
        constraints = [
            models.UniqueConstraint(
                fields=["class_obj", "teacher"], name="uniq_class_teacher"
            )
        ]


class JoinRequest(BaseModel):
    class_obj = models.ForeignKey(
        Class, verbose_name="申请班级", on_delete=models.CASCADE, related_name="join_requests"
    )
    requester = models.ForeignKey(
        "accounts.User",
        verbose_name="申请人",
        on_delete=models.CASCADE,
        related_name="join_requests",
    )
    requester_role = models.CharField("申请人角色", max_length=16)
    type = models.CharField("申请类型", max_length=16, choices=JoinRequestType.choices)
    target_class = models.ForeignKey(
        Class,
        verbose_name="目标班级",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="target_join_requests",
    )
    subject = models.CharField(
        "任教学科", max_length=16, choices=Subject.choices, null=True, blank=True
    )
    status = models.CharField(
        "状态", max_length=16, choices=JoinRequestStatus.choices, default=JoinRequestStatus.PENDING
    )
    reason = models.CharField("申请理由", max_length=200, null=True, blank=True)
    reviewer = models.ForeignKey(
        "accounts.User",
        verbose_name="审核人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_join_requests",
    )
    review_comment = models.CharField("审核意见", max_length=200, null=True, blank=True)
    reviewed_at = models.DateTimeField("审核时间", null=True, blank=True)
    source_approved = models.BooleanField("原班级已通过", default=False)
    target_approved = models.BooleanField("目标班级已通过", default=False)

    class Meta:
        db_table = "join_requests"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["class_obj", "status"]),
            models.Index(fields=["target_class", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.type}-{self.requester_id}-{self.status}"
