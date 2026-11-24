"""P4 测评主链路支撑：解析测评发布目标的学生名单。"""
from common.enums import OrganizationLevel, Role
from common.exceptions import BusinessError
from common.scope import descendant_org_ids

from apps.accounts.models import User
from apps.organizations.models import Organization

from .models import Class

TARGET_TYPES = {"class", "school", "district", "city", "province"}


def _class_students(class_ids: list[int], grades: list[int] | None):
    queryset = User.objects.filter(
        role=Role.STUDENT,
        deleted_at__isnull=True,
        student_profile__classroom_id__in=class_ids,
        student_profile__deleted_at__isnull=True,
    )
    if grades:
        queryset = queryset.filter(student_profile__grade__in=grades)
    return queryset


def _org_students(org_ids: list[int], grades: list[int] | None):
    queryset = User.objects.filter(
        role=Role.STUDENT,
        deleted_at__isnull=True,
        org_id__in=org_ids,
        student_profile__deleted_at__isnull=True,
    )
    if grades:
        queryset = queryset.filter(student_profile__grade__in=grades)
    return queryset


def resolve_target_students(
    target_type: str,
    target_ids: list[int],
    target_grades: list[int] | None = None,
) -> list[User]:
    """按发布范围返回应参与学生，供测评发布生成名单与参与率统计使用。"""
    if target_type not in TARGET_TYPES:
        raise BusinessError(400, "targetType 不合法")
    if not target_ids:
        return []

    if target_type == "class":
        valid_classes = list(
            Class.objects.filter(
                pk__in=target_ids, deleted_at__isnull=True
            ).values_list("id", flat=True)
        )
        if len(valid_classes) != len(set(target_ids)):
            raise BusinessError(400, "班级不存在或已归档")
        queryset = _class_students(valid_classes, target_grades)
    else:
        level_map = {
            "school": OrganizationLevel.SCHOOL,
            "district": OrganizationLevel.DISTRICT,
            "city": OrganizationLevel.CITY,
            "province": OrganizationLevel.PROVINCE,
        }
        orgs = list(
            Organization.objects.filter(
                pk__in=target_ids,
                level=level_map[target_type],
                deleted_at__isnull=True,
            )
        )
        if len(orgs) != len(set(target_ids)):
            raise BusinessError(400, "组织不存在或层级不匹配")

        org_ids: list[int] = []
        for org in orgs:
            org_ids.extend(descendant_org_ids(org))
        queryset = _org_students(list(set(org_ids)), target_grades)

    return list(
        queryset.select_related("org", "student_profile__classroom").order_by(
            "student_profile__classroom_id", "student_profile__student_no", "id"
        )
    )


def build_student_ref(user: User) -> dict:
    """学生名单快照，供测评参与名单与统计落库。"""
    profile = getattr(user, "student_profile", None)
    classroom = profile.classroom if profile else None
    return {
        "studentId": user.id,
        "studentNo": profile.student_no if profile else None,
        "realName": user.real_name,
        "grade": profile.grade if profile else None,
        "classId": classroom.id if classroom else None,
        "className": classroom.name if classroom else None,
        "schoolId": user.org_id,
        "schoolName": user.org.name if user.org else None,
    }
