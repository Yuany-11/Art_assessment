from rest_framework.response import Response


def ok(data=None, message="success", status=200):
    """统一成功响应 {code,message,data}。"""
    return Response({"code": status, "message": message, "data": data}, status=status)


def deleted(**extra):
    payload = {"deleted": True}
    payload.update(extra)
    return ok(payload)
