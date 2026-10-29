"""严格 Serializer：拒绝请求体中的未声明字段。"""
import re

from rest_framework import serializers

CN_PHONE_PATTERN = re.compile(r"^\d{11}$")
CN_PHONE_MESSAGE = "手机号需为 11 位数字"


def is_cn_phone(value) -> bool:
    """手机号是否为 11 位数字。"""
    return bool(value) and bool(CN_PHONE_PATTERN.fullmatch(str(value).strip()))


def validate_cn_phone(value: str) -> str:
    """序列化器用：校验并返回去除首尾空白的手机号。"""
    value = (value or "").strip()
    if not CN_PHONE_PATTERN.fullmatch(value):
        raise serializers.ValidationError(CN_PHONE_MESSAGE)
    return value


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data.keys()) - set(self.fields.keys())
            if unknown:
                raise serializers.ValidationError(
                    {field: "不允许的字段" for field in sorted(unknown)}
                )
        return super().to_internal_value(data)
