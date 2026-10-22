"""通知写入与读取服务。"""
from django.utils import timezone

from common.exceptions import NotFound

from .models import Notification


def notify(user, ntype: str, title: str, content: str = "", link: str = "", payload=None):
    """写入一条站内通知；用户为空时忽略。"""
    if user is None or not getattr(user, "pk", None):
        return None
    return Notification.objects.create(
        user=user,
        type=ntype,
        title=title[:128],
        content=content or "",
        link=(link or "")[:255],
        payload=payload or {},
    )


def list_for_user(user, *, unread_only: bool = False, ntype: str | None = None):
    qs = Notification.objects.filter(user=user, deleted_at__isnull=True)
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    if ntype:
        qs = qs.filter(type=ntype)
    return qs.order_by("-created_at", "-id")


def unread_count(user) -> int:
    return Notification.objects.filter(
        user=user, read_at__isnull=True, deleted_at__isnull=True
    ).count()


def mark_read(user, notification_id: int) -> Notification:
    notification = Notification.objects.filter(
        pk=notification_id, user=user, deleted_at__isnull=True
    ).first()
    if notification is None:
        raise NotFound("通知不存在")
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])
    return notification


def mark_all_read(user):
    now = timezone.now()
    updated = Notification.objects.filter(
        user=user, read_at__isnull=True, deleted_at__isnull=True
    ).update(read_at=now, updated_at=now)
    return updated, now
