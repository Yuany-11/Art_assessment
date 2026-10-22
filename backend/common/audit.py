"""统一操作审计：写入 OperationLog。"""
from common.request_context import get_current_request


def log_action(
    user,
    action,
    resource_type,
    resource_id=None,
    description="",
    detail=None,
    request=None,
    result="success",
) -> None:
    """测评模块审计入口，统一落到 OperationLog。"""
    if detail:
        import json

        extra = json.dumps(detail, ensure_ascii=False, default=str)
        description = f"{description} {extra}".strip()
    log_operation(
        user, action, resource_type, resource_id, description, result, request
    )


def log_operation(
    actor,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    description: str = "",
    result: str = "success",
    request=None,
) -> None:
    """记录操作日志；请求上下文缺失时仍落库，IP/UA 为空。"""
    from apps.qbank.models import OperationLog

    current = request or get_current_request()
    OperationLog.objects.create(
        operator=actor if getattr(actor, "pk", None) else None,
        operator_role=getattr(actor, "role", "") or "",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=(description or "")[:500],
        ip=current.META.get("REMOTE_ADDR") if current else None,
        user_agent=((current.META.get("HTTP_USER_AGENT") or "")[:255] if current else None),
        result=result,
    )
