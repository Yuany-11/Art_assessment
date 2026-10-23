import logging
import uuid

from django.http import JsonResponse

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-Id"] = request.request_id
        return response


class UnhandledExceptionMiddleware:
    """兜底 500，保证不返回 Django 调试页或纯文本。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = getattr(request, "request_id", None) or uuid.uuid4().hex
        try:
            return self.get_response(request)
        except Exception:
            logger.exception("unhandled error request_id=%s", request.request_id)
            return JsonResponse(
                {
                    "code": 500,
                    "message": "服务器内部错误",
                    "data": {"requestId": request.request_id},
                },
                status=500,
            )
