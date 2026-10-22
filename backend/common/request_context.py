"""请求上下文：把 request_id 透传到日志。"""
import contextvars
import logging

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_current_request: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "current_request", default=None
)


def set_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


def set_current_request(request):
    return _current_request.set(request)


def reset_current_request(token) -> None:
    _current_request.reset(token)


def get_current_request():
    return _current_request.get()


class RequestIdFilter(logging.Filter):
    """给每条日志记录注入 request_id。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
