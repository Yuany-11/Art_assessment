"""请求 ID 与兜底异常中间件。"""
import logging
import uuid

from django.http import JsonResponse

from common.request_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """生成或透传 X-Request-Id，并写入日志上下文。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response["X-Request-Id"] = request_id
        return response


class UnhandledExceptionMiddleware:
    """兜底未捕获异常，避免暴露堆栈与调试页。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            logger.exception("unhandled error request_id=%s", getattr(request, "request_id", None))
            return JsonResponse(
                {
                    "code": 500,
                    "message": "服务器内部错误",
                    "data": {"requestId": getattr(request, "request_id", None)},
                },
                status=500,
            )
