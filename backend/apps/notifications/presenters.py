"""通知响应字段组装。"""
from common.utils import iso


def notification_item(notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "content": notification.content,
        "link": notification.link or "",
        "read": notification.read_at is not None,
        "createdAt": iso(notification.created_at),
    }
