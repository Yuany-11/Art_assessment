"""DRF 权限类与角色校验。"""
from rest_framework.permissions import BasePermission

from common.enums import Role

ADMIN_ROLES = {
    Role.SCHOOL_ADMIN,
    Role.DISTRICT_ADMIN,
    Role.CITY_ADMIN,
    Role.PROVINCE_ADMIN,
}
TEACHER_AND_ADMIN = {Role.TEACHER, *ADMIN_ROLES}
ALL_VIEW_ROLES = {Role.STUDENT, *TEACHER_AND_ADMIN}


def ensure_role(user, *roles):
    from common.exceptions import Forbidden

    if user.role not in set(roles):
        raise Forbidden("当前角色无权访问该资源")


class IsAuthenticatedActive(BasePermission):
    """必须已登录且账号为 active。"""

    message = "登录已失效，请重新登录"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.status == "active"
            and user.deleted_at is None
        )


def roles_required(*roles: str):
    """生成“仅指定角色可访问”的权限类。"""

    class _RolePermission(BasePermission):
        message = "当前角色无权访问该资源"

        def has_permission(self, request, view):
            user = getattr(request, "user", None)
            return bool(
                user
                and user.is_authenticated
                and user.status == "active"
                and user.role in roles
            )

    return _RolePermission
