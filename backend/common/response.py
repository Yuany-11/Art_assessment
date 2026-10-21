"""统一响应结构 {code, message, data}。"""
from rest_framework.response import Response


def success(data=None, message: str = "success") -> Response:
    return Response({"code": 200, "message": message, "data": data})
