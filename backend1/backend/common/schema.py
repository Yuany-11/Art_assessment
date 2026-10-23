"""drf-spectacular 扩展：让 Swagger 显示 Bearer JWT 鉴权。"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "common.authentication.JWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "在 Authorization 头中传 `Bearer <access_token>`",
        }
