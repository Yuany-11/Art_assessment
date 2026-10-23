from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("创建时间", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("更新时间", default=timezone.now)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteModel(TimeStampedModel):
    deleted_at = models.DateTimeField("删除时间", null=True, blank=True, db_index=True)

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])


class AuditLog(models.Model):
    """业务审计日志：补录、重新判分、撤回、证书生成等。

    模块二的操作日志表由后端 B 维护；此处只记录测评模块的审计事件，
    后续可通过事件同步到统一日志中心。
    """

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_logs",
    )
    operator_name = models.CharField(max_length=64, blank=True, default="")
    role = models.CharField(max_length=32, blank=True, default="")
    action = models.CharField(max_length=64, db_index=True)
    resource_type = models.CharField(max_length=32)
    resource_id = models.BigIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    detail = models.JSONField(default=dict, blank=True)
    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=256, blank=True, default="")
    result = models.CharField(max_length=16, default="success")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["resource_type", "resource_id"])]
