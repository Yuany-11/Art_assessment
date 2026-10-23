"""模块一的最小对接模型。

注意：账号与权限的完整实现由后端 B（柴国继）负责。本文件只保留测评业务
必须依赖的字段与关系，字段命名与 api.md 2.1 对齐；合并代码时应以模块一
的正式实现替换，保持 User/Class/School 的字段命名不变即可。
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from common.enums import AccountStatus, Gender, Role, Subject


class Province(models.Model):
    name = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "org_province"

    def __str__(self):
        return self.name


class City(models.Model):
    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name="cities")
    name = models.CharField(max_length=64)
    code = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "org_city"
        unique_together = [("province", "name")]

    def __str__(self):
        return self.name


class District(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=64)
    code = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        db_table = "org_district"
        unique_together = [("city", "name")]

    def __str__(self):
        return self.name


class School(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="schools")
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(max_length=16, default="active")

    class Meta:
        db_table = "org_school"

    def __str__(self):
        return self.name

    @property
    def city_id(self):
        return self.district.city_id

    @property
    def province_id(self):
        return self.district.city.province_id


class Class(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=64)
    grade = models.PositiveSmallIntegerField()
    class_code = models.CharField(max_length=32, unique=True)
    head_teacher = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="headed_classes",
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=16, default="active")
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_classes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "school_class"
        ordering = ["grade", "name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    role = models.CharField(max_length=32, choices=Role.choices, db_index=True)
    real_name = models.CharField(max_length=64)
    gender = models.CharField(max_length=16, choices=Gender.choices, default=Gender.UNKNOWN)
    phone = models.CharField(max_length=32, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    avatar_url = models.CharField(max_length=512, null=True, blank=True)

    student_no = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    teacher_no = models.CharField(max_length=32, null=True, blank=True)
    title = models.CharField(max_length=64, null=True, blank=True)

    school = models.ForeignKey(
        School, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    current_class = models.ForeignKey(
        Class, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="students", db_column="current_class_id",
    )
    grade = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=AccountStatus.choices, default=AccountStatus.ACTIVE
    )
    token_version = models.PositiveIntegerField(default=0)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "account_user"

    def __str__(self):
        return f"{self.real_name}({self.username})"

    # ---- 组织快捷属性（测评模块大量使用） ----
    # 注：school_id 由 ForeignKey 自动提供，不能再定义同名 property。

    @property
    def district_id(self):
        return self.school.district_id if self.school_id else None

    @property
    def city_id(self):
        return self.school.district.city_id if self.school_id else None

    @property
    def province_id(self):
        return self.school.district.city.province_id if self.school_id else None

    @property
    def class_id(self):
        return self.current_class_id

    @property
    def class_name(self):
        return self.current_class.name if self.current_class_id else None

    @property
    def school_name(self):
        return self.school.name if self.school_id else None

    @property
    def role_name(self):
        return Role(self.role).label if self.role else ""

    def has_role(self, *roles):
        return self.role in roles


class TeacherClass(models.Model):
    """教师任教班级关系。"""

    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="teaching_relations"
    )
    classroom = models.ForeignKey(
        Class, on_delete=models.CASCADE, related_name="teacher_relations"
    )
    subject = models.CharField(max_length=16, choices=Subject.choices, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "teacher_class"
        unique_together = [("teacher", "classroom", "subject")]

    @property
    def class_id(self):
        return self.classroom_id
