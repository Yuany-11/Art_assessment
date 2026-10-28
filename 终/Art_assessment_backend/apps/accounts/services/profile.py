"""用户资料组装：把 User + profile + 组织链输出为 UserProfile 契约。"""
from django.utils import timezone

from common.enums import OrganizationLevel, Role

from ..permissions_map import permissions_for


def org_chain(org) -> dict:
    """按层级收集组织链，缺失层级不出现。"""
    chain: dict[str, object] = {}
    current = org
    while current is not None:
        chain[current.level] = current
        current = current.parent
    return chain


def format_datetime(dt):
    return timezone.localtime(dt).isoformat() if dt else None


def _iso(dt):
    return format_datetime(dt)


def build_user_profile(user) -> dict:
    chain = org_chain(user.org) if user.org else {}
    school = chain.get(OrganizationLevel.SCHOOL)
    district = chain.get(OrganizationLevel.DISTRICT)
    city = chain.get(OrganizationLevel.CITY)
    province = chain.get(OrganizationLevel.PROVINCE)

    teacher_profile = getattr(user, "teacher_profile", None)
    student_profile = getattr(user, "student_profile", None)

    return {
        "id": user.id,
        "username": user.username,
        "realName": user.real_name,
        "role": user.role,
        "roleName": Role(user.role).label,
        "permissions": permissions_for(user.role),
        "avatarUrl": user.avatar_url,
        "gender": user.gender,
        "phone": user.phone,
        "email": user.email,
        "studentNo": student_profile.student_no if student_profile else None,
        "teacherNo": teacher_profile.teacher_no if teacher_profile else None,
        "subject": teacher_profile.subject if teacher_profile else None,
        "title": teacher_profile.title if teacher_profile else None,
        "schoolId": school.id if school else None,
        "schoolName": school.name if school else None,
        "districtId": district.id if district else None,
        "districtName": district.name if district else None,
        "cityId": city.id if city else None,
        "cityName": city.name if city else None,
        "provinceId": province.id if province else None,
        "provinceName": province.name if province else None,
        "grade": student_profile.grade if student_profile else None,
        "classId": student_profile.classroom_id if student_profile else None,
        "className": student_profile.classroom.name if student_profile and student_profile.classroom else None,
        "status": user.status,
        "lastLoginAt": _iso(user.last_login),
        "createdAt": _iso(user.created_at),
    }
