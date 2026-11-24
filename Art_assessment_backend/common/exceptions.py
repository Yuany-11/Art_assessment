"""统一异常处理：所有异常输出 {code, message, data}。"""
import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework.exceptions import (
    APIException,
    PermissionDenied as DRFPermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    """业务异常，由 Service 层抛出。"""

    def __init__(self, status_code: int, message: str, data=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.data = data


class BadRequest(BusinessError):
    def __init__(self, message: str = "请求参数错误", data=None, **extra):
        super().__init__(400, message, data if data is not None else (extra or None))


class Forbidden(BusinessError):
    def __init__(self, message: str = "无权访问", data=None, **extra):
        super().__init__(403, message, data if data is not None else (extra or None))


class NotFound(BusinessError):
    def __init__(self, message: str = "资源不存在", data=None, **extra):
        super().__init__(404, message, data if data is not None else (extra or None))


class Conflict(BusinessError):
    def __init__(self, message: str = "资源状态冲突", data=None, **extra):
        super().__init__(409, message, data if data is not None else (extra or None))


class Unprocessable(BusinessError):
    def __init__(self, message: str = "业务规则不满足", data=None, **extra):
        super().__init__(422, message, data if data is not None else (extra or None))


def _first_message(detail) -> str:
    if isinstance(detail, dict):
        for value in detail.values():
            return _first_message(value)
        return "请求处理失败"
    if isinstance(detail, (list, tuple)):
        if not detail:
            return "请求处理失败"
        return _first_message(detail[0])
    return str(detail)


def _field_errors(detail) -> dict:
    errors: dict[str, str] = {}
    if isinstance(detail, dict):
        for field, messages in detail.items():
            if isinstance(messages, (list, tuple)):
                errors[field] = str(messages[0]) if messages else "参数错误"
            elif isinstance(messages, dict):
                errors[field] = _first_message(messages)
            else:
                errors[field] = str(messages)
    else:
        errors["nonFieldErrors"] = _first_message(detail)
    return errors


def unified_exception_handler(exc, context):
    """DRF 全局异常处理器。"""
    if isinstance(exc, BusinessError):
        return Response(
            {"code": exc.status_code, "message": exc.message, "data": exc.data},
            status=exc.status_code,
        )

    if isinstance(exc, ValidationError):
        return Response(
            {
                "code": 400,
                "message": "请求参数校验失败",
                "data": {"errors": _field_errors(exc.detail)},
            },
            status=400,
        )

    if isinstance(exc, Http404):
        return Response({"code": 404, "message": "资源不存在", "data": None}, status=404)

    if isinstance(exc, (PermissionDenied, DRFPermissionDenied)):
        return Response({"code": 403, "message": "无权访问该资源", "data": None}, status=403)

    if isinstance(exc, APIException):
        response = exception_handler(exc, context)
        if response is not None:
            detail = (
                response.data.get("detail", "请求处理失败")
                if isinstance(response.data, dict)
                else _first_message(response.data)
            )
            return Response(
                {"code": response.status_code, "message": str(detail), "data": None},
                status=response.status_code,
            )

    logger.exception("unhandled exception", exc_info=exc)
    return None
