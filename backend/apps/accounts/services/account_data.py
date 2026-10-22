"""账号列表项与组织创建结果的数据组装。"""
from common.enums import Role

from .profile import format_datetime


def build_account_item(user) -> dict:
    teacher = getattr(user, "teacher_profile", None)
    student = getattr(user, "student_profile", None)
    classroom = student.classroom if student else None
    org = user.org
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
        "classId": classroom.id if classroom else None,
        "className": classroom.name if classroom else None,
        "status": user.status,
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


def build_org_create_result(org, admin) -> dict:
    return {
        "orgId": org.id,
        "orgName": org.name,
        "adminAccount": build_account_item(admin),
    }
