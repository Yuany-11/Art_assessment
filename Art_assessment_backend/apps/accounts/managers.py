"""用户管理器。"""
from django.contrib.auth.models import BaseUserManager

from common.enums import Role


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username: str, password: str | None, **extra):
        if not username:
            raise ValueError("登录账号不能为空")
        user = self.model(username=username, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(username, password, **extra)

    def create_superuser(self, username: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.PROVINCE_ADMIN)
        extra.setdefault("real_name", username or "管理员")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("status", "active")
        return self._create_user(username, password, **extra)
