"""班级、科任教师关系与入班申请。"""
from django.db import models

from common.enums import ClassStatus, JoinRequestStatus, JoinRequestType, Subject
from common.models import BaseModel


class Class(BaseModel):
    name = models.CharField("班级名称", max_length=128, db_comment="班级名称")
    class_code = models.CharField(
        "班级号", max_length=32, unique=True, db_comment="班级号（全局唯一）"
    )
    grade = models.PositiveSmallIntegerField("年级", db_comment="年级（1~12）")
    school = models.ForeignKey(
        "organizations.Organization",
        verbose_name="所属学校",
        on_delete=models.PROTECT,
        related_name="classes",
        db_comment="所属学校 ID",
    )
    head_teacher = models.ForeignKey(
        "accounts.User",
        verbose_name="班主任",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_classes",
        db_comment="班主任用户 ID",
    )
    description = models.CharField(
        "班级简介", max_length=500, null=True, blank=True, db_comment="班级简介"
    )
    status = models.CharField(
        "状态",
        max_length=16,
        choices=ClassStatus.choices,
        default=ClassStatus.ACTIVE,
        db_comment="状态：active/archived",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        verbose_name="创建人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_classes",
        db_comment="创建人用户 ID",
    )

    class Meta:
        db_table = "classes"
        db_table_comment = "班级表"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.name}({self.class_code})"


class ClassTeacher(BaseModel):
    class_obj = models.ForeignKey(
        Class,
        verbose_name="班级",
        on_delete=models.CASCADE,
        related_name="subject_teachers",
        db_comment="班级 ID",
    )
    teacher = models.ForeignKey(
        "accounts.User",
        verbose_name="教师",
        on_delete=models.CASCADE,
        related_name="teaching_classes",
        db_comment="教师用户 ID",
    )
    subject = models.CharField(
        "任教学科",
        max_length=16,
        choices=Subject.choices,
        db_comment="任教学科：music/art",
    )

    class Meta:
        db_table = "class_teachers"
        db_table_comment = "班级科任教师关系表"
        constraints = [
            models.UniqueConstraint(
                fields=["class_obj", "teacher"], name="uniq_class_teacher"
            )
        ]


class JoinRequest(BaseModel):
    class_obj = models.ForeignKey(
        Class,
        verbose_name="申请班级",
        on_delete=models.CASCADE,
        related_name="join_requests",
        db_comment="申请班级 ID",
    )
    requester = models.ForeignKey(
        "accounts.User",
        verbose_name="申请人",
        on_delete=models.CASCADE,
        related_name="join_requests",
        db_comment="申请人用户 ID",
    )
    requester_role = models.CharField(
        "申请人角色", max_length=16, db_comment="申请人角色"
    )
    type = models.CharField(
        "申请类型",
        max_length=16,
        choices=JoinRequestType.choices,
        db_comment="申请类型：join/change/leave",
    )
    target_class = models.ForeignKey(
        Class,
        verbose_name="目标班级",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="target_join_requests",
        db_comment="转班目标班级 ID",
    )
    subject = models.CharField(
        "任教学科",
        max_length=16,
        choices=Subject.choices,
        null=True,
        blank=True,
        db_comment="教师申请时的任教学科",
    )
    status = models.CharField(
        "状态",
        max_length=16,
        choices=JoinRequestStatus.choices,
        default=JoinRequestStatus.PENDING,
        db_comment="状态：pending/approved/rejected/cancelled",
    )
    reason = models.CharField(
        "申请理由", max_length=200, null=True, blank=True, db_comment="申请理由"
    )
    reviewer = models.ForeignKey(
        "accounts.User",
        verbose_name="审核人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_join_requests",
        db_comment="审核人用户 ID",
    )
    review_comment = models.CharField(
        "审核意见", max_length=200, null=True, blank=True, db_comment="审核意见"
    )
    reviewed_at = models.DateTimeField(
        "审核时间", null=True, blank=True, db_comment="审核时间"
    )
    source_approved = models.BooleanField(
        "原班级已通过", default=False, db_comment="转班申请原班级是否已通过"
    )
    target_approved = models.BooleanField(
        "目标班级已通过", default=False, db_comment="转班申请目标班级是否已通过"
    )

    class Meta:
        db_table = "join_requests"
        db_table_comment = "入班/退班/转班申请表"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["class_obj", "status"]),
            models.Index(fields=["target_class", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.type}-{self.requester_id}-{self.status}"
