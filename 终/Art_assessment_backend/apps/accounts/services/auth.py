"""认证与账号资料业务逻辑。"""
from django.db.models import Q
from django.utils import timezone

from common.enums import AccountStatus
from common.exceptions import BusinessError
from common.jwt import (
    TokenError,
    blacklist_token,
    consume_refresh,
    decode_token,
    get_active_user,
    is_blacklisted,
    issue_pair,
)

from ..models import User


def login(username: str, password: str, role: str | None = None) -> dict:
    user = (
        User.objects.filter(deleted_at__isnull=True)
        .select_related("org")
        .filter(Q(username=username) | Q(student_profile__student_no=username))
        .first()
    )
    if user is None or not user.check_password(password):
        raise BusinessError(401, "账号或密码错误")
    if user.status != AccountStatus.ACTIVE:
        raise BusinessError(403, "账号已被禁用，请联系管理员")
    if role and user.role != role:
        raise BusinessError(403, "账号角色与登录入口不匹配")

    tokens = issue_pair(user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login", "updated_at"])
    return {**tokens, "user": user}


def refresh(refresh_token: str) -> dict:
    try:
        payload = decode_token(refresh_token, "refresh")
    except TokenError as exc:
        raise BusinessError(401, str(exc)) from exc

    if is_blacklisted(payload["jti"]):
        raise BusinessError(401, "刷新令牌已失效，请重新登录")

    user = get_active_user(payload)
    if user is None:
        raise BusinessError(401, "账号不存在或已删除")
    if user.status != AccountStatus.ACTIVE:
        raise BusinessError(403, "账号已被禁用，请联系管理员")
    if user.token_version != payload.get("token_version"):
        raise BusinessError(401, "登录状态已变更，请重新登录")

    try:
        consume_refresh(payload)
    except TokenError as exc:
        raise BusinessError(401, str(exc)) from exc

    return issue_pair(user)


def logout(access_payload: dict, refresh_token: str | None = None) -> dict:
    blacklist_token(access_payload)
    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token, "refresh")
        except TokenError:
            refresh_payload = None
        if refresh_payload:
            blacklist_token(refresh_payload)
    return {"loggedOut": True}


def update_profile(user, data: dict):
    field_map = {
        "realName": "real_name",
        "gender": "gender",
        "phone": "phone",
        "email": "email",
        "avatarUrl": "avatar_url",
    }
    changed = []
    for api_field, model_field in field_map.items():
        if api_field in data:
            setattr(user, model_field, data[api_field])
            changed.append(model_field)
    if changed:
        user.save(update_fields=[*changed, "updated_at"])
    return user


def change_password(user, old_password: str, new_password: str) -> dict:
    if not user.check_password(old_password):
        raise BusinessError(400, "旧密码不正确")
    user.set_password(new_password)
    user.token_version += 1
    user.save(update_fields=["password", "token_version", "updated_at"])
    return {"changed": True, "reloginRequired": True}
