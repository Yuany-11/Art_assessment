"""严格 Serializer：拒绝请求体中的未声明字段。"""
from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            unknown = set(data.keys()) - set(self.fields.keys())
            if unknown:
                raise serializers.ValidationError(
                    {field: "不允许的字段" for field in sorted(unknown)}
                )
        return super().to_internal_value(data)
