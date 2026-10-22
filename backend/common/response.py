"""统一响应结构 {code, message, data}。"""
from rest_framework.response import Response


def success(data=None, message: str = "success") -> Response:
    return Response({"code": 200, "message": message, "data": data})


def ok(data=None, message: str = "success", status: int = 200) -> Response:
    return Response({"code": status, "message": message, "data": data}, status=status)


def deleted(**extra) -> Response:
    payload = {"deleted": True}
    payload.update(extra)
    return ok(payload)
