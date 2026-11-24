"""JWT 签发、校验、轮换与 Redis 黑名单。"""
import uuid
from datetime import datetime, timezone

import jwt as pyjwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

BLACKLIST_PREFIX = "jwt:blacklist:"
USED_PREFIX = "jwt:used:"


class TokenError(Exception):
    """令牌无效或已失效。"""


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _issue(user, token_type: str, ttl: int):
    now = _now()
    payload = {
        "user_id": user.id,
        "sub": str(user.id),
        "role": user.role,
        "token_version": user.token_version,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl,
    }
    token = pyjwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, payload


def issue_access_token(user, ttl: int | None = None) -> str:
    """签发 Access Token（测试、演示数据使用）。"""
    token, _ = _issue(user, "access", ttl or settings.JWT_ACCESS_TTL)
    return token


def issue_pair(user) -> dict:
    access_token, _ = _issue(user, "access", settings.JWT_ACCESS_TTL)
    refresh_token, _ = _issue(user, "refresh", settings.JWT_REFRESH_TTL)
    return {
        "token": access_token,
        "refreshToken": refresh_token,
        "tokenType": "Bearer",
        "expiresIn": settings.JWT_ACCESS_TTL,
        "refreshExpiresIn": settings.JWT_REFRESH_TTL,
    }


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = pyjwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise TokenError("登录已过期，请重新登录") from exc
    except pyjwt.PyJWTError as exc:
        raise TokenError("无效的登录凭证") from exc

    if payload.get("type") != expected_type or not payload.get("jti"):
        raise TokenError("无效的登录凭证")
    if "user_id" not in payload:
        raise TokenError("无效的登录凭证")
    return payload


def is_blacklisted(jti: str) -> bool:
    return bool(cache.get(BLACKLIST_PREFIX + jti))


def blacklist_token(payload: dict) -> None:
    jti = payload.get("jti")
    if not jti:
        return
    ttl = max(0, int(payload.get("exp", 0)) - _now())
    if ttl:
        cache.set(BLACKLIST_PREFIX + jti, 1, ttl)


def consume_refresh(payload: dict) -> None:
    """刷新令牌一次性使用：原子标记，重复使用即视为失效。"""
    jti = payload["jti"]
    ttl = max(1, int(payload["exp"]) - _now())
    if not cache.add(USED_PREFIX + jti, 1, ttl):
        raise TokenError("刷新令牌已失效，请重新登录")
    blacklist_token(payload)


def get_active_user(payload: dict):
    user_model = get_user_model()
    return user_model.objects.filter(
        pk=payload.get("user_id"), deleted_at__isnull=True
    ).first()


class JWTAuthentication(BaseAuthentication):
    """Bearer JWT 认证，校验黑名单与 token_version。"""

    keyword = "Bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise AuthenticationFailed("无效的认证请求头")

        try:
            payload = decode_token(header[1].decode(), "access")
        except TokenError as exc:
            raise AuthenticationFailed(str(exc)) from exc

        if is_blacklisted(payload["jti"]):
            raise AuthenticationFailed("登录已失效，请重新登录")

        user = get_active_user(payload)
        if user is None:
            raise AuthenticationFailed("账号不存在或已删除")
        if user.status != "active":
            raise AuthenticationFailed("账号已被禁用")
        if user.token_version != payload.get("token_version"):
            raise AuthenticationFailed("登录状态已变更，请重新登录")

        return user, payload

    def authenticate_header(self, request):
        return self.keyword
