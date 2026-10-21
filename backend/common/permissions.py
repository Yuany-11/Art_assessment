"""DRF 权限类。"""
from rest_framework.permissions import BasePermission


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
