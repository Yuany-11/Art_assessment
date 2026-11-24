"""账号列表项与组织创建结果的数据组装。"""
from django.core.cache import cache

from common.constants import TEMPORARY_PASSWORD_CACHE_PREFIX
from common.enums import Role

from .profile import format_datetime


def build_account_item(user) -> dict:
    teacher = getattr(user, "teacher_profile", None)
    student = getattr(user, "student_profile", None)
    classroom = student.classroom if student else None
    org = user.org
    teaching_classes = []
    if teacher is not None:
        from apps.classes.models import Class, ClassTeacher

        rows = ClassTeacher.objects.filter(
            teacher=user, class_obj__deleted_at__isnull=True
        ).select_related("class_obj")
        for row in rows:
            teaching_classes.append({
                "id": row.class_obj_id,
                "classCode": row.class_obj.class_code,
                "name": row.class_obj.name,
                "subject": row.subject,
                "role": "head" if row.class_obj.head_teacher_id == user.id else "subject",
            })
        head_ids = set(Class.objects.filter(
            head_teacher=user, deleted_at__isnull=True
        ).values_list("id", flat=True))
        seen = {item["id"] for item in teaching_classes}
        for classroom in Class.objects.filter(
            id__in=head_ids - seen, deleted_at__isnull=True
        ):
            teaching_classes.append({
                "id": classroom.id,
                "classCode": classroom.class_code,
                "name": classroom.name,
                "subject": teacher.subject,
                "role": "head",
            })
    return {
        "id": user.id,
        "username": user.username,
        "realName": user.real_name,
        "role": user.role,
        "roleName": Role(user.role).label,
        "orgId": org.id if org else None,
        "orgName": org.name if org else None,
        "phone": user.phone,
        "email": user.email,
        "subject": teacher.subject if teacher else None,
        "title": teacher.title if teacher else None,
        "studentNo": student.student_no if student else None,
        "grade": student.grade if student else None,
        "classId": classroom.id if classroom else None,
        "className": classroom.name if classroom else None,
        "teachingClasses": teaching_classes,
        "status": user.status,
        "hasTemporaryPassword": bool(
            cache.get(f"{TEMPORARY_PASSWORD_CACHE_PREFIX}{user.id}")
        ),
        "createdAt": format_datetime(user.created_at),
    }


def build_student_item(user) -> dict:
    student = getattr(user, "student_profile", None)
    classroom = student.classroom if student else None
    return {
        "id": user.id,
        "username": user.username,
        "studentNo": student.student_no if student else None,
        "realName": user.real_name,
        "gender": user.gender,
        "grade": student.grade if student else None,
        "classId": classroom.id if classroom else None,
        "className": classroom.name if classroom else None,
        "status": user.status,
        "joinedAt": format_datetime(user.created_at),
    }


def build_org_create_result(org, admin, initial_password=None) -> dict:
    return {
        "orgId": org.id,
        "orgName": org.name,
        "adminAccount": build_account_item(admin),
        "initialPassword": initial_password,
    }
