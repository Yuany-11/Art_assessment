"""v2.0 站内通知中心。

通知只由服务端事件写入，面向接收人本人；不提供公开创建接口。
"""
from django.db import transaction
from django.utils import timezone

from common.exceptions import NotFound
from exams.models import Notification


def notify(user, *, type, title, content, link=None):
    return Notification.objects.create(
        user=user,
        type=type,
        title=title,
        content=content,
        link=link or None,
    )


def list_notifications(user, params):
    qs = Notification.objects.filter(user=user)
    if _as_bool(params.get("unreadOnly")):
        qs = qs.filter(read=False)
    if params.get("type"):
        qs = qs.filter(type=params["type"])
    return qs.order_by("-created_at", "-id")


def unread_count(user):
    return Notification.objects.filter(user=user, read=False).count()


def mark_read(user, notification_id):
    notification = Notification.objects.filter(
        pk=notification_id, user=user
    ).first()
    if notification is None:
        raise NotFound("通知不存在")
    if not notification.read:
        with transaction.atomic():
            notification.read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["read", "read_at"])
    return notification


def mark_all_read(user):
    now = timezone.now()
    updated = Notification.objects.filter(user=user, read=False).update(
        read=True, read_at=now
    )
    return updated, now


def _as_bool(value):
    return str(value).lower() in ("1", "true", "yes", "on")
