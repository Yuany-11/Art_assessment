import logging

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    """业务异常，统一转换为 {code,message,data}。"""

    def __init__(self, code, message, errors=None):
        self.code = code
        self.message = message
        self.errors = errors
        super().__init__(message)

    @property
    def status_code(self):
        return self.code if 400 <= self.code <= 599 else 400


def _flatten_field_errors(detail):
    """把 DRF 嵌套错误压平为 {field: message}。"""
    errors = {}
    if isinstance(detail, dict):
        for field, messages in detail.items():
            if isinstance(messages, dict):
                errors[field] = _first_message(messages)
            elif isinstance(messages, list):
                errors[field] = _first_message(messages)
            else:
                errors[field] = str(messages)
    elif isinstance(detail, list):
        errors["nonFieldErrors"] = _first_message(detail)
    else:
        errors["nonFieldErrors"] = str(detail)
    return errors


def _first_message(value):
    if isinstance(value, dict):
        for item in value.values():
            return _first_message(item)
    if isinstance(value, (list, tuple)):
        for item in value:
            return _first_message(item)
    return str(value)


def unified_exception_handler(exc, context):
    if isinstance(exc, BusinessError):
        data = {"errors": exc.errors} if exc.errors else None
        return Response(
            {"code": exc.code, "message": exc.message, "data": data},
            status=exc.status_code,
        )

    if isinstance(exc, ValidationError):
        errors = _flatten_field_errors(exc.detail)
        return Response(
            {
                "code": 400,
                "message": "请求参数校验失败",
                "data": {"errors": errors},
            },
            status=400,
        )

    if isinstance(exc, Http404):
        return Response({"code": 404, "message": "资源不存在", "data": None}, status=404)

    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data
        if isinstance(detail, dict):
            message = detail.get("detail") or _first_message(detail)
        elif isinstance(detail, list):
            message = _first_message(detail)
        else:
            message = str(detail)
        response.data = {
            "code": response.status_code,
            "message": str(message),
            "data": None,
        }
        return response

    logger.exception("unhandled error: %s", exc)
    return None


class Conflict(BusinessError):
    def __init__(self, message, errors=None):
        super().__init__(409, message, errors)


class NotFound(BusinessError):
    def __init__(self, message="资源不存在"):
        super().__init__(404, message)


class Forbidden(BusinessError):
    def __init__(self, message="无权限访问"):
        super().__init__(403, message)


class BadRequest(BusinessError):
    def __init__(self, message="请求参数错误", errors=None):
        super().__init__(400, message, errors)


class Unprocessable(BusinessError):
    def __init__(self, message, errors=None):
        super().__init__(422, message, errors)


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "服务暂不可用"
    default_code = "service_unavailable"
