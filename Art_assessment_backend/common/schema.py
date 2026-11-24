"""OpenAPI 响应包装与认证 scheme。"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers


def api_response(name: str, data_serializer):
    """生成 {code, message, data} 的响应 Schema。"""
    return inline_serializer(
        name=name,
        fields={
            "code": serializers.IntegerField(),
            "message": serializers.CharField(),
            "data": data_serializer,
        },
    )


def paged_response(name: str, item_serializer):
    """生成 {total, pages, list} 分页响应 Schema。"""
    page = inline_serializer(
        name=f"{name}Page",
        fields={
            "total": serializers.IntegerField(),
            "pages": serializers.IntegerField(),
            "list": item_serializer,
        },
    )
    return api_response(name, page)


class BearerJWTScheme(OpenApiAuthenticationExtension):
    target_class = "common.jwt.JWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}

