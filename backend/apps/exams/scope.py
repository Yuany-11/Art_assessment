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
            # 科任老师只能看到本人任教班级该学科的试卷，班主任身份不扩权。
            return (
                Q(scope_type=ScopeType.CLASS)
                & self.teacher_pair_q("scope_id", "subject")
            ) | Q(creator=self.user, subject__in=self.teacher_subjects)
        return Q(pk__in=[])

    def ensure_paper_scope(self, scope_type, scope_id, subject=None):
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
            if ok and subject is not None:
                ok = self.teaches_subject_in_class(scope_id, subject)
        else:
            ok = False
        if not ok:
            raise Forbidden("无权在该范围创建或发布试卷")

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

    @cached_property
    def teaching_pairs(self) -> set[tuple[int, str]]:
        """教师实际任教的（班级, 学科）组合。

        班主任身份只用于班级管理，不等于在本班任教某学科；组卷、发布测评、
        评分、成绩、证书等教学操作必须命中这里的具体组合。
        """
        if not self.is_teacher:
            return set()
        from apps.classes.models import ClassTeacher

        return set(
            ClassTeacher.objects.filter(
                teacher=self.user,
                deleted_at__isnull=True,
                class_obj__deleted_at__isnull=True,
            ).values_list("class_obj_id", "subject")
        )

    def subject_teacher_class_ids(self, subject=None):
        return {
            class_id
            for class_id, item_subject in self.teaching_pairs
            if subject is None or item_subject == subject
        }

    def teaching_subjects_for_class(self, class_id) -> set[str]:
        return {
            subject
            for item_class_id, subject in self.teaching_pairs
            if item_class_id == class_id
        }

    def teaches_subject_in_class(self, class_id, subject) -> bool:
        return (class_id, subject) in self.teaching_pairs

    def ensure_teacher_pair(self, class_id, subject):
        """教师必须在该班担任该学科的老师，班主任身份不能替代任课关系。"""
        if self.is_teacher and not self.teaches_subject_in_class(class_id, subject):
            raise Forbidden("只能操作本人任教班级该学科的数据")

    def teacher_pair_q(self, class_field: str, subject_field: str) -> Q:
        """构造 (班级字段, 学科字段) 的 OR 条件，供列表查询收敛数据。"""
        condition = Q(pk__in=[])
        for class_id, subject in self.teaching_pairs:
            condition |= Q(**{class_field: class_id, subject_field: subject})
        return condition

    @cached_property
    def teacher_subjects(self) -> set[str]:
        """教师可教学的学科集合：任课关系 + 教师档案任教学科。

        班主任也可以是科任老师；其权限仍由任教学科决定，不会因班主任身份
        获得另一门学科的组卷/测评权限。
        """
        if not self.is_teacher:
            return set()
        from apps.classes.models import ClassTeacher

        subjects = set(
            ClassTeacher.objects.filter(
                teacher=self.user,
                deleted_at__isnull=True,
                class_obj__deleted_at__isnull=True,
            ).values_list("subject", flat=True)
        )
        profile = getattr(self.user, "teacher_profile", None)
        if profile is not None and profile.subject:
            subjects.add(profile.subject)
        return subjects

    def ensure_subject(self, subject):
        if self.is_teacher and subject not in self.teacher_subjects:
            raise Forbidden("只能操作本人任教学科的内容")
