from common.enums import Role
from common.exceptions import Forbidden

ADMIN_ROLES = {
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
}
TEACHER_AND_ADMIN = {Role.TEACHER, *ADMIN_ROLES}
ALL_VIEW_ROLES = {Role.STUDENT, *TEACHER_AND_ADMIN}


def ensure_role(user, *roles):
    allowed = set()
    for role in roles:
        allowed.add(role)
    if user.role not in allowed:
        raise Forbidden("当前角色无权访问该资源")


def ensure_teacher_or_admin(user):
    ensure_role(user, *TEACHER_AND_ADMIN)


def ensure_student(user):
    ensure_role(user, Role.STUDENT)
