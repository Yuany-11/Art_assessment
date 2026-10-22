from common.models import AuditLog


def log_action(
    user, action, resource_type, resource_id=None, description="",
    detail=None, request=None, result="success",
):
    ip = ""
    user_agent = ""
    if request is not None:
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:256]
    return AuditLog.objects.create(
        operator=user,
        operator_name=getattr(user, "real_name", "") or "",
        role=getattr(user, "role", "") or "",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        detail=detail or {},
        ip=ip,
        user_agent=user_agent,
        result=result,
    )
