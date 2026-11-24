"""账号字段校验：手机号、登录账号与学籍号。"""
import re

from rest_framework import serializers

CN_MOBILE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{4,32}$")
# 学籍号格式：全系统唯一来源，前后端/导入/登录提示共用。
# 兼容学校现有 S 开头学号和未来的 18 位数字学号。
STUDENT_NO_MIN_LENGTH = 6
STUDENT_NO_MAX_LENGTH = 20
STUDENT_NO_PATTERN = re.compile(r"^[A-Za-z0-9]{6,20}$")
USERNAME_REQUIREMENT = "登录账号需为 4~32 位字母、数字或下划线"
STUDENT_NO_REQUIREMENT = "学籍号需为 6~20 位字母或数字"


def validate_mobile(value, label: str = "手机号", allow_blank: bool = False):
    """校验并返回标准化手机号；None 原样返回，allow_blank 时空白视作未填写。"""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        if allow_blank:
            return None
        raise serializers.ValidationError(f"请填写{label}")
    if not CN_MOBILE_PATTERN.match(value):
        raise serializers.ValidationError(f"{label}需为 11 位数字，且以 1 开头")
    return value


def is_valid_mobile(value) -> bool:
    return bool(value) and bool(CN_MOBILE_PATTERN.match(str(value).strip()))


def validate_username(value: str) -> str:
    value = (value or "").strip()
    if not USERNAME_PATTERN.match(value):
        raise serializers.ValidationError(USERNAME_REQUIREMENT)
    return value


def validate_student_no(value: str) -> str:
    value = (value or "").strip()
    if not STUDENT_NO_PATTERN.match(value):
        raise serializers.ValidationError(STUDENT_NO_REQUIREMENT)
    return value


def is_valid_username(value) -> bool:
    return bool(USERNAME_PATTERN.match(str(value or "").strip()))


def is_valid_student_no(value) -> bool:
    return bool(STUDENT_NO_PATTERN.match(str(value or "").strip()))
