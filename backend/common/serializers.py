"""严格 Serializer：拒绝请求体中的未声明字段。"""
from rest_framework import serializers

from common.passwords import PASSWORD_REQUIREMENT, is_strong_password


class StrongPasswordField(serializers.CharField):
    """统一密码字段：8~32 位且同时包含字母和数字。"""

    def __init__(self, **kwargs):
        kwargs.setdefault("min_length", 8)
        kwargs.setdefault("max_length", 32)
        kwargs.setdefault("trim_whitespace", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value and not is_strong_password(value):
            raise serializers.ValidationError(PASSWORD_REQUIREMENT)
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
