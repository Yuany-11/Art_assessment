"""测评模块数据范围。

模块三的接口统一通过本类收敛数据权限。组织使用单表四级结构
（Organization.level / parent），班级使用 classes.Class。
"""
from functools import cached_property

from django.db.models import Q

from common.enums import AccountStatus, OrganizationLevel, Role, ScopeType
from common.exceptions import Forbidden
from common.scope import descendant_org_ids


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
            Role.SCHOOL_ADMIN,
            Role.DISTRICT_ADMIN,
            Role.CITY_ADMIN,
            Role.PROVINCE_ADMIN,
        }

    # ------------------------------------------------------------------
    # 组织范围
    # ------------------------------------------------------------------
    @cached_property
    def org(self):
        return self.user.org

    @cached_property
    def _descendant_org_ids(self) -> list[int]:
        if self.org is None:
            return []
        return descendant_org_ids(self.org)

    @cached_property
    def school_id(self):
        org = self.org
        if org is not None and org.level == OrganizationLevel.SCHOOL:
            return org.id
        return None

    @cached_property
    def district_id(self):
        org = self.org
        while org is not None:
            if org.level == OrganizationLevel.DISTRICT:
                return org.id
            org = org.parent
        return None

    @cached_property
    def city_id(self):
        org = self.org
        while org is not None:
            if org.level == OrganizationLevel.CITY:
                return org.id
            org = org.parent
        return None

    @cached_property
    def province_id(self):
        org = self.org
        while org is not None:
            if org.level == OrganizationLevel.PROVINCE:
                return org.id
            org = org.parent
        return None

    def _org_ids_at(self, level: str) -> set[int]:
        from apps.organizations.models import Organization

        if self.is_province_admin:
            return set(
                Organization.objects.filter(
                    level=level, deleted_at__isnull=True
                ).values_list("id", flat=True)
            )
        return set(
            Organization.objects.filter(
                id__in=self._descendant_org_ids, level=level, deleted_at__isnull=True
            ).values_list("id", flat=True)
        )

    @cached_property
    def school_ids(self) -> set[int]:
        from apps.classes.models import Class, ClassTeacher

        if self.is_province_admin:
            return self._org_ids_at(OrganizationLevel.SCHOOL)
        if self.is_city_admin or self.is_district_admin:
            return self._org_ids_at(OrganizationLevel.SCHOOL)
        if self.school_id:
            return {self.school_id}
        if self.is_teacher:
            subject_schools = set(
                ClassTeacher.objects.filter(
                    teacher=self.user, class_obj__deleted_at__isnull=True
                ).values_list("class_obj__school_id", flat=True)
            )
            head_schools = set(
                Class.objects.filter(
                    head_teacher=self.user, deleted_at__isnull=True
                ).values_list("school_id", flat=True)
            )
            return subject_schools | head_schools
        return set()

    @cached_property
    def district_ids(self) -> set[int]:
        if self.is_province_admin:
            return self._org_ids_at(OrganizationLevel.DISTRICT)
        if self.is_city_admin:
            return self._org_ids_at(OrganizationLevel.DISTRICT)
        if self.district_id:
            return {self.district_id}
        return set()

    @cached_property
    def city_ids(self) -> set[int]:
        if self.is_province_admin:
            return self._org_ids_at(OrganizationLevel.CITY)
        if self.city_id:
            return {self.city_id}
        return set()

    @cached_property
    def class_ids(self) -> set[int]:
        from apps.classes.models import Class, ClassTeacher

        base = Class.objects.filter(deleted_at__isnull=True)
        if self.is_province_admin:
            return set(base.values_list("id", flat=True))
        if self.is_city_admin or self.is_district_admin:
            return set(
                base.filter(school_id__in=self._descendant_org_ids).values_list(
                    "id", flat=True
                )
            )
        if self.is_school_admin:
            return set(base.filter(school_id=self.school_id).values_list("id", flat=True))
        if self.is_teacher:
            subject_ids = set(
                ClassTeacher.objects.filter(
                    teacher=self.user, class_obj__deleted_at__isnull=True
                ).values_list("class_obj_id", flat=True)
            )
            head_ids = set(
                base.filter(head_teacher=self.user).values_list("id", flat=True)
            )
            return subject_ids | head_ids
        if self.is_student:
            class_id = getattr(
                getattr(self.user, "student_profile", None), "classroom_id", None
            )
            return {class_id} if class_id else set()
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
        from apps.accounts.models import User

        qs = User.objects.filter(role=Role.STUDENT, status=AccountStatus.ACTIVE)
        if self.is_province_admin:
            return qs
        if self.is_city_admin or self.is_district_admin:
            return qs.filter(org_id__in=self.school_ids)
        if self.school_id:
            return qs.filter(org_id=self.school_id)
        if self.class_ids:
            return qs.filter(student_profile__classroom_id__in=self.class_ids)
        return qs.none()

    # ------------------------------------------------------------------
    # 试卷范围
    # ------------------------------------------------------------------
    def paper_q(self):
        if self.is_province_admin:
            return Q()
        if self.is_city_admin:
            return (
                Q(scope_type=ScopeType.CLASS, scope_id__in=self.class_ids)
                | Q(scope_type=ScopeType.SCHOOL, scope_id__in=self.school_ids)
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
        from apps.classes.models import ClassTeacher

        qs = ClassTeacher.objects.filter(teacher=self.user)
        if subject:
            qs = qs.filter(subject=subject)
        return set(qs.values_list("class_obj_id", flat=True))
