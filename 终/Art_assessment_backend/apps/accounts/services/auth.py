"""认证与账号资料业务逻辑。"""
import secrets

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from common.enums import AccountStatus, Role
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

from ..models import StudentProfile, User


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


REGISTER_CODE_TTL = 300
REGISTER_CODE_COOLDOWN = 60
REGISTER_CODE_MAX_ATTEMPTS = 5


def _code_key(email: str) -> str:
    return f"register:code:{email}"


def _cooldown_key(email: str) -> str:
    return f"register:code:cooldown:{email}"


def _attempts_key(email: str) -> str:
    return f"register:code:attempts:{email}"


def _email_in_use(email: str) -> bool:
    return (
        User.objects.filter(deleted_at__isnull=True)
        .filter(Q(username__iexact=email) | Q(email__iexact=email))
        .exists()
    )


def send_register_code(email: str) -> dict:
    """发送学生注册邮箱验证码（6 位数字，5 分钟内有效）。"""
    email = email.strip().lower()
    if _email_in_use(email):
        raise BusinessError(409, "该邮箱已被注册")
    if cache.get(_cooldown_key(email)):
        raise BusinessError(429, "验证码发送过于频繁，请稍后再试")

    code = f"{secrets.randbelow(10 ** 6):06d}"
    cache.set(_code_key(email), code, REGISTER_CODE_TTL)
    cache.delete(_attempts_key(email))
    try:
        send_mail(
            subject="【艺术素质测评系统】注册验证码",
            message=(
                f"您的注册验证码是 {code}，{REGISTER_CODE_TTL // 60} 分钟内有效。"
                "如非本人操作，请忽略本邮件。"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as exc:
        cache.delete(_code_key(email))
        raise BusinessError(500, "验证码发送失败，请稍后重试") from exc

    cache.set(_cooldown_key(email), True, REGISTER_CODE_COOLDOWN)
    return {"sent": True, "expiresIn": REGISTER_CODE_TTL}


def register_student(data: dict) -> dict:
    """校验邮箱验证码并创建学生账号（邮箱即登录账号）。"""
    email = data["email"].strip().lower()
    if _email_in_use(email):
        raise BusinessError(409, "该邮箱已被注册")

    stored = cache.get(_code_key(email))
    if not stored:
        raise BusinessError(400, "验证码已过期，请重新获取")
    attempts = cache.get(_attempts_key(email)) or 0
    if attempts >= REGISTER_CODE_MAX_ATTEMPTS:
        cache.delete(_code_key(email))
        raise BusinessError(429, "验证码错误次数过多，请重新获取")
    if not secrets.compare_digest(str(stored), str(data["code"])):
        cache.set(_attempts_key(email), attempts + 1, REGISTER_CODE_TTL)
        raise BusinessError(400, "验证码不正确")

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                password=data["password"],
                real_name=data["nickname"].strip(),
                role=Role.STUDENT,
                email=email,
                status=AccountStatus.ACTIVE,
            )
            StudentProfile.objects.create(user=user)
    except IntegrityError as exc:
        raise BusinessError(409, "该邮箱已被注册") from exc

    cache.delete(_code_key(email))
    cache.delete(_attempts_key(email))
    return {"registered": True}
