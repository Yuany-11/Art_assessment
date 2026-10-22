"""统一数据范围（数据权限）计算。

所有测评、成绩、统计、证书接口都必须先经过这里，禁止在视图内各自拼条件。
"""
from functools import cached_property

from django.db.models import Q

from common.enums import AccountStatus, Role, ScopeType
from common.exceptions import Forbidden


class DataScope:
    def __init__(self, user):
        self.user = user
        self.role = user.role

    # ------------------------------------------------------------------
    # 角色
    # ------------------------------------------------------------------
    @property
    def is_student(self):
        return self.role == Role.STUDENT

    @property
    def is_teacher(self):
        return self.role == Role.TEACHER

    @property
    def is_province_admin(self):
        return self.role == Role.PROVINCE_ADMIN

    @property
    def is_school_admin(self):
        return self.role == Role.SCHOOL_ADMIN

    @property
    def is_district_admin(self):
        return self.role == Role.DISTRICT_ADMIN

    @property
    def is_city_admin(self):
        return self.role == Role.CITY_ADMIN

    @property
    def is_admin(self):
        return self.role in {
            Role.SCHOOL_ADMIN, Role.DISTRICT_ADMIN, Role.CITY_ADMIN, Role.PROVINCE_ADMIN
        }

    # ------------------------------------------------------------------
    # 组织范围
    # ------------------------------------------------------------------
    @cached_property
    def school_id(self):
        return self.user.school_id

    @cached_property
    def district_id(self):
        return self.user.school.district_id if self.user.school_id else None

    @cached_property
    def city_id(self):
        return self.user.school.district.city_id if self.user.school_id else None

    @cached_property
    def province_id(self):
        return self.user.school.district.city.province_id if self.user.school_id else None

    @cached_property
    def class_ids(self):
        """可访问的班级 ID 集合。"""
        from accounts.models import Class, TeacherClass

        if self.is_province_admin:
            return set(Class.objects.filter(deleted_at__isnull=True).values_list("id", flat=True))
        if self.is_city_admin:
            return set(
                Class.objects.filter(
                    deleted_at__isnull=True, school__district__city_id=self.city_id
                ).values_list("id", flat=True)
            )
        if self.is_district_admin:
            return set(
                Class.objects.filter(
                    deleted_at__isnull=True, school__district_id=self.district_id
                ).values_list("id", flat=True)
            )
        if self.is_school_admin:
            return set(
                Class.objects.filter(
                    deleted_at__isnull=True, school_id=self.school_id
                ).values_list("id", flat=True)
            )
        if self.is_teacher:
            return set(
                TeacherClass.objects.filter(
                    teacher=self.user, classroom__deleted_at__isnull=True
                ).values_list("classroom_id", flat=True)
            )
        if self.is_student:
            return {self.user.current_class_id} if self.user.current_class_id else set()
        return set()

    @cached_property
    def school_ids(self):
        from accounts.models import School

        qs = School.objects.all()
        if self.is_province_admin:
            return set(qs.values_list("id", flat=True))
        if self.is_city_admin:
            return set(qs.filter(district__city_id=self.city_id).values_list("id", flat=True))
        if self.is_district_admin:
            return set(qs.filter(district_id=self.district_id).values_list("id", flat=True))
        if self.school_id:
            return {self.school_id}
        if self.is_teacher:
            return set(
                self.user.teaching_relations.values_list("classroom__school_id", flat=True)
            )
        return set()

    @cached_property
    def district_ids(self):
        from accounts.models import District

        if self.is_province_admin:
            return set(District.objects.values_list("id", flat=True))
        if self.is_city_admin:
            return set(District.objects.filter(city_id=self.city_id).values_list("id", flat=True))
        if self.district_id:
            return {self.district_id}
        return set()

    @cached_property
    def city_ids(self):
        from accounts.models import City

        if self.is_province_admin:
            return set(City.objects.values_list("id", flat=True))
        if self.city_id:
            return {self.city_id}
        return set()

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def ensure_class(self, class_id):
        if class_id not in self.class_ids:
            raise Forbidden("无权访问该班级数据")

    def ensure_school(self, school_id):
        if school_id not in self.school_ids:
            raise Forbidden("无权访问该学校数据")

    def student_qs(self):
        from accounts.models import User

        qs = User.objects.filter(role=Role.STUDENT, status=AccountStatus.ACTIVE)
        if self.is_province_admin:
            return qs
        if self.is_city_admin:
            return qs.filter(school__district__city_id=self.city_id)
        if self.is_district_admin:
            return qs.filter(school__district_id=self.district_id)
        if self.school_id:
            return qs.filter(school_id=self.school_id)
        if self.class_ids:
            return qs.filter(current_class_id__in=self.class_ids)
        return qs.none()

    # ------------------------------------------------------------------
    # 试卷范围
    # ------------------------------------------------------------------
    def paper_q(self):
        """返回限定试卷数据范围的 Q 对象。"""
        if self.is_province_admin:
            return Q()
        q = Q()
        if self.is_city_admin:
            school_ids = self.school_ids
            class_ids = self.class_ids
            return (
                Q(scope_type=ScopeType.CLASS, scope_id__in=class_ids)
                | Q(scope_type=ScopeType.SCHOOL, scope_id__in=school_ids)
                | Q(scope_type=ScopeType.DISTRICT, scope_id__in=self.district_ids)
                | Q(scope_type=ScopeType.CITY, scope_id__in=self.city_ids)
                | Q(creator=self.user)
            )
        if self.is_district_admin:
            return (
                Q(scope_type=ScopeType.CLASS, scope_id__in=self.class_ids)
                | Q(scope_type=ScopeType.SCHOOL, scope_id__in=self.school_ids)
                | Q(scope_type=ScopeType.DISTRICT, scope_id__in=self.district_ids)
                | Q(creator=self.user)
            )
        if self.is_school_admin:
            return (
                Q(scope_type=ScopeType.CLASS, scope_id__in=self.class_ids)
                | Q(scope_type=ScopeType.SCHOOL, scope_id=self.school_id)
                | Q(creator=self.user)
            )
        if self.is_teacher:
            return (
                Q(scope_type=ScopeType.CLASS, scope_id__in=self.class_ids)
                | Q(creator=self.user)
            )
        return Q(pk__in=[])

    def ensure_paper_scope(self, scope_type, scope_id):
        """校验是否可在指定层级/组织创建试卷。"""
        if self.is_province_admin:
            return
        if self.is_city_admin:
            ok = (
                (scope_type == ScopeType.CLASS and scope_id in self.class_ids)
                or (scope_type == ScopeType.SCHOOL and scope_id in self.school_ids)
                or (scope_type == ScopeType.DISTRICT and scope_id in self.district_ids)
                or (scope_type == ScopeType.CITY and scope_id == self.city_id)
            )
        elif self.is_district_admin:
            ok = (
                (scope_type == ScopeType.CLASS and scope_id in self.class_ids)
                or (scope_type == ScopeType.SCHOOL and scope_id in self.school_ids)
                or (scope_type == ScopeType.DISTRICT and scope_id == self.district_id)
            )
        elif self.is_school_admin:
            ok = (
                (scope_type == ScopeType.CLASS and scope_id in self.class_ids)
                or (scope_type == ScopeType.SCHOOL and scope_id == self.school_id)
            )
        elif self.is_teacher:
            ok = scope_type == ScopeType.CLASS and scope_id in self.class_ids
        else:
            ok = False
        if not ok:
            raise Forbidden("无权在该范围创建试卷")

    @property
    def max_scope_type(self):
        if self.is_province_admin:
            return ScopeType.PROVINCE
        if self.is_city_admin:
            return ScopeType.CITY
        if self.is_district_admin:
            return ScopeType.DISTRICT
        if self.is_school_admin:
            return ScopeType.SCHOOL
        return ScopeType.CLASS

    def subject_teacher_class_ids(self, subject=None):
        from accounts.models import TeacherClass

        qs = TeacherClass.objects.filter(teacher=self.user)
        if subject:
            qs = qs.filter(subject__in=["", subject])
        return set(qs.values_list("classroom_id", flat=True))
