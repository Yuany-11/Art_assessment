"""账号、教师/学生扩展资料与角色菜单。"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db import models

from common.enums import AccountStatus, Gender, OrganizationLevel, Role
from common.models import BaseModel

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    username = models.CharField(
        "登录账号", max_length=64, unique=True, db_comment="登录账号（全局唯一）"
    )
    real_name = models.CharField(
        "真实姓名", max_length=64, db_comment="真实姓名"
    )
    role = models.CharField(
        "角色",
        max_length=32,
        choices=Role.choices,
        db_index=True,
        db_comment="角色：student/teacher/school_admin/district_admin/city_admin/province_admin/question_admin",
    )
    org = models.ForeignKey(
        "organizations.Organization",
        verbose_name="所属组织",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
        db_comment="所属组织 ID",
    )
    phone = models.CharField(
        "手机号", max_length=32, null=True, blank=True, db_comment="手机号"
    )
    email = models.EmailField(
        "邮箱", null=True, blank=True, db_comment="电子邮箱"
    )
    gender = models.CharField(
        "性别",
        max_length=16,
        choices=Gender.choices,
        default=Gender.UNKNOWN,
        db_comment="性别：male/female/unknown",
    )
    avatar_url = models.URLField(
        "头像地址", max_length=500, null=True, blank=True, db_comment="头像图片 URL"
    )
    status = models.CharField(
        "账号状态",
        max_length=16,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
        db_comment="账号状态：active/disabled",
    )
    token_version = models.PositiveIntegerField(
        "令牌版本", default=0, db_comment="令牌版本，改密或禁用后自增使旧令牌失效"
    )
    must_change_password = models.BooleanField(
        "下次登录需改密", default=False, db_comment="下次登录是否必须修改密码"
    )
    is_staff = models.BooleanField(
        "可登录后台", default=False, db_comment="是否可登录 Django 管理后台"
    )
    is_active = models.BooleanField(
        "账号有效", default=True, db_comment="账号是否有效"
    )

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "users"
        db_table_comment = "用户账号表（7 种角色）"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.real_name}({self.username})"

    def get_full_name(self) -> str:
        return self.real_name

    def get_short_name(self) -> str:
        return self.real_name

    # ---- 模块三契约兼容属性（只读，不落库） ----
    def _profile(self, attr: str):
        try:
            return getattr(self, attr)
        except ObjectDoesNotExist:
            return None

    def _ancestor_org_id(self, level: str):
        org = self.org
        while org is not None:
            if org.level == level:
                return org.id
            org = org.parent
        return None

    @property
    def school(self):
        org = self.org
        if org is not None and org.level == OrganizationLevel.SCHOOL:
            return org
        return None

    @property
    def school_id(self):
        school = self.school
        return school.id if school else None

    @property
    def school_name(self):
        return self.school.name if self.school_id else None

    @property
    def current_class(self):
        profile = self._profile("student_profile")
        return profile.classroom if profile else None

    @property
    def current_class_id(self):
        classroom = self.current_class
        return classroom.id if classroom else None

    @property
    def class_id(self):
        return self.current_class_id

    @property
    def class_name(self):
        return self.current_class.name if self.current_class_id else None

    @property
    def grade(self):
        profile = self._profile("student_profile")
        return profile.grade if profile else None

    @property
    def student_no(self):
        profile = self._profile("student_profile")
        return profile.student_no if profile else None

    @property
    def teacher_no(self):
        profile = self._profile("teacher_profile")
        return profile.teacher_no if profile else None

    @property
    def district_id(self):
        return self._ancestor_org_id(OrganizationLevel.DISTRICT)

    @property
    def city_id(self):
        return self._ancestor_org_id(OrganizationLevel.CITY)

    @property
    def province_id(self):
        return self._ancestor_org_id(OrganizationLevel.PROVINCE)

    @property
    def role_name(self):
        if not self.role:
            return ""
        return Role(self.role).label

    def has_role(self, *roles) -> bool:
        return self.role in roles


class TeacherProfile(BaseModel):
    user = models.OneToOneField(
        User,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        db_comment="用户 ID（一对一关联 users.id）",
    )
    teacher_no = models.CharField(
        "教师工号",
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        db_comment="教师工号（全局唯一）",
    )
    subject = models.CharField(
        "任教学科", max_length=16, null=True, blank=True,
        db_comment="任教学科：music/art",
    )
    title = models.CharField(
        "职称", max_length=64, null=True, blank=True, db_comment="教师职称"
    )

    class Meta:
        db_table = "teacher_profiles"
        db_table_comment = "教师扩展资料表"

    def __str__(self) -> str:
        return f"教师资料 {self.user_id}"


class StudentProfile(BaseModel):
    user = models.OneToOneField(
        User,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="student_profile",
        db_comment="用户 ID（一对一关联 users.id）",
    )
    student_no = models.CharField(
        "学籍号",
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        db_comment="学籍号（全局唯一）",
    )
    grade = models.PositiveSmallIntegerField(
        "年级", null=True, blank=True, db_comment="年级（1~12）"
    )
    guardian_phone = models.CharField(
        "监护人手机号", max_length=32, null=True, blank=True,
        db_comment="监护人手机号",
    )
    classroom = models.ForeignKey(
        "classes.Class",
        verbose_name="所在班级",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="students",
        db_comment="所在班级 ID",
    )

    class Meta:
        db_table = "student_profiles"
        db_table_comment = "学生扩展资料表"

    def __str__(self) -> str:
        return f"学生资料 {self.user_id}"


class ImportTask(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    task_id = models.CharField(
        "任务 ID", max_length=64, unique=True, db_comment="导入任务 ID（唯一）"
    )
    task_type = models.CharField(
        "任务类型", max_length=32, default="teacher_import",
        db_comment="任务类型，如 teacher_import",
    )
    status = models.CharField(
        "状态",
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_comment="状态：queued/processing/completed/failed",
    )
    requested_by = models.ForeignKey(
        User,
        verbose_name="发起人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_tasks",
        db_comment="发起人用户 ID",
    )
    total = models.PositiveIntegerField("总行数", default=0, db_comment="导入总行数")
    success_count = models.PositiveIntegerField(
        "成功条数", default=0, db_comment="导入成功条数"
    )
    fail_count = models.PositiveIntegerField(
        "失败条数", default=0, db_comment="导入失败条数"
    )
    errors = models.JSONField(
        "失败明细", default=list, db_comment="失败明细 JSON：[{row, username, message}]"
    )
    file_key = models.CharField(
        "导入文件 Key", max_length=500, null=True, blank=True,
        db_comment="导入文件存储 Key",
    )
    finished_at = models.DateTimeField(
        "完成时间", null=True, blank=True, db_comment="任务完成时间"
    )

    class Meta:
        db_table = "import_tasks"
        db_table_comment = "批量导入任务表"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.task_id


class MenuItem(BaseModel):
    code = models.CharField(
        "菜单编码", max_length=64, unique=True, db_comment="菜单编码（唯一）"
    )
    role = models.CharField(
        "角色",
        max_length=32,
        choices=Role.choices,
        db_index=True,
        db_comment="可见角色",
    )
    parent_code = models.CharField(
        "父菜单编码", max_length=64, null=True, blank=True,
        db_comment="父菜单编码，NULL 表示一级菜单",
    )
    name = models.CharField("菜单名称", max_length=64, db_comment="菜单名称")
    path = models.CharField("前端路由", max_length=255, db_comment="前端路由地址")
    icon = models.CharField(
        "图标", max_length=64, null=True, blank=True, db_comment="菜单图标"
    )
    sort_order = models.IntegerField("排序值", default=0, db_comment="同级排序值")
    permission = models.CharField(
        "权限码", max_length=64, null=True, blank=True,
        db_comment="访问该菜单所需权限码",
    )

    class Meta:
        db_table = "menu_items"
        db_table_comment = "角色菜单表"
        ordering = ["role", "sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.role}:{self.name}"
