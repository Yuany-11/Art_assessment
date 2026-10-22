"""账号、教师/学生扩展资料与角色菜单。"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from common.enums import AccountStatus, Gender, Role
from common.models import BaseModel

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    username = models.CharField("登录账号", max_length=64, unique=True)
    real_name = models.CharField("真实姓名", max_length=64)
    role = models.CharField("角色", max_length=32, choices=Role.choices, db_index=True)
    org = models.ForeignKey(
        "organizations.Organization",
        verbose_name="所属组织",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )
    phone = models.CharField("手机号", max_length=32, null=True, blank=True)
    email = models.EmailField("邮箱", null=True, blank=True)
    gender = models.CharField(
        "性别", max_length=16, choices=Gender.choices, default=Gender.UNKNOWN
    )
    avatar_url = models.URLField("头像地址", max_length=500, null=True, blank=True)
    status = models.CharField(
        "账号状态", max_length=16, choices=AccountStatus.choices, default=AccountStatus.ACTIVE
    )
    token_version = models.PositiveIntegerField("令牌版本", default=0)
    must_change_password = models.BooleanField("下次登录需改密", default=False)
    is_staff = models.BooleanField("可登录后台", default=False)
    is_active = models.BooleanField("账号有效", default=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.real_name}({self.username})"

    def get_full_name(self) -> str:
        return self.real_name

    def get_short_name(self) -> str:
        return self.real_name


class TeacherProfile(BaseModel):
    user = models.OneToOneField(
        User, primary_key=True, on_delete=models.CASCADE, related_name="teacher_profile"
    )
    teacher_no = models.CharField("教师工号", max_length=32, unique=True, null=True, blank=True)
    subject = models.CharField("任教学科", max_length=16, null=True, blank=True)
    title = models.CharField("职称", max_length=64, null=True, blank=True)

    class Meta:
        db_table = "teacher_profiles"

    def __str__(self) -> str:
        return f"教师资料 {self.user_id}"


class StudentProfile(BaseModel):
    user = models.OneToOneField(
        User, primary_key=True, on_delete=models.CASCADE, related_name="student_profile"
    )
    student_no = models.CharField("学籍号", max_length=32, unique=True, null=True, blank=True)
    grade = models.PositiveSmallIntegerField("年级", null=True, blank=True)
    guardian_phone = models.CharField("监护人手机号", max_length=32, null=True, blank=True)
    classroom = models.ForeignKey(
        "classes.Class",
        verbose_name="所在班级",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="students",
    )

    class Meta:
        db_table = "student_profiles"

    def __str__(self) -> str:
        return f"学生资料 {self.user_id}"


class ImportTask(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    task_id = models.CharField("任务 ID", max_length=64, unique=True)
    task_type = models.CharField("任务类型", max_length=32, default="teacher_import")
    status = models.CharField(
        "状态", max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    requested_by = models.ForeignKey(
        User,
        verbose_name="发起人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_tasks",
    )
    total = models.PositiveIntegerField("总行数", default=0)
    success_count = models.PositiveIntegerField("成功条数", default=0)
    fail_count = models.PositiveIntegerField("失败条数", default=0)
    errors = models.JSONField("失败明细", default=list)
    file_key = models.CharField("导入文件 Key", max_length=500, null=True, blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        db_table = "import_tasks"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.task_id


class MenuItem(BaseModel):
    code = models.CharField("菜单编码", max_length=64, unique=True)
    role = models.CharField("角色", max_length=32, choices=Role.choices, db_index=True)
    parent_code = models.CharField("父菜单编码", max_length=64, null=True, blank=True)
    name = models.CharField("菜单名称", max_length=64)
    path = models.CharField("前端路由", max_length=255)
    icon = models.CharField("图标", max_length=64, null=True, blank=True)
    sort_order = models.IntegerField("排序值", default=0)
    permission = models.CharField("权限码", max_length=64, null=True, blank=True)

    class Meta:
        db_table = "menu_items"
        ordering = ["role", "sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.role}:{self.name}"
