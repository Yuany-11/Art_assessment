"""站内通知：只面向接收人本人。"""
from django.db import models

from common.enums import NotificationType
from common.models import BaseModel


class Notification(BaseModel):
    user = models.ForeignKey(
        "accounts.User",
        verbose_name="接收人",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(
        "通知类型", max_length=32, choices=NotificationType.choices, db_index=True
    )
    title = models.CharField("标题", max_length=128)
    content = models.TextField("正文", blank=True, default="")
    link = models.CharField("跳转地址", max_length=255, blank=True, default="")
    payload = models.JSONField("附加数据", default=dict, blank=True)
    read_at = models.DateTimeField("已读时间", null=True, blank=True, db_index=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "read_at"]),
            models.Index(fields=["user", "type"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.type}:{self.title}"
