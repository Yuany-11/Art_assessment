"""JWT 鉴权。

与模块一（后端 B）约定：
- Access Token 使用 HS256，载荷包含 user_id、role、token_version、jti、token_type。
- 每次请求重新读取数据库角色与 token_version，不信任 Token 中的角色。
- 黑名单/登出由模块一写入缓存键 ``jwt:blacklist:<jti>``，本模块复用同一约定。
"""
from datetime import datetime, timezone as dt_timezone

import jwt
from django.conf import settings
from django.core.cache import cache
from rest_framework import authentication, exceptions

from common.enums import AccountStatus


def issue_access_token(user, ttl=None):
    now = datetime.now(dt_timezone.utc)
    ttl = ttl or settings.JWT_ACCESS_TTL
    payload = {
        "user_id": user.pk,
        "role": user.role,
        "token_version": user.token_version,
        "token_type": "access",
        "jti": __import__("uuid").uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


class JWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Authorization 头格式错误")
        token = parts[1]
        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("登录已过期")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("无效的登录凭证")

        if payload.get("token_type") != "access":
            raise exceptions.AuthenticationFailed("Token 类型错误")
        jti = payload.get("jti")
        if jti and cache.get(f"jwt:blacklist:{jti}"):
            raise exceptions.AuthenticationFailed("登录已失效")

        from accounts.models import User

        try:
            user = User.objects.select_related(
                "school", "current_class", "current_class__school"
            ).get(pk=payload.get("user_id"))
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("账号不存在")

        if user.status != AccountStatus.ACTIVE:
            raise exceptions.AuthenticationFailed("账号已被禁用")
        if payload.get("token_version") != user.token_version:
            raise exceptions.AuthenticationFailed("登录已失效，请重新登录")

        return (user, payload)

    def authenticate_header(self, request):
        return self.keyword
