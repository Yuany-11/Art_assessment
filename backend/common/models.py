"""公共抽象模型。"""
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """统一时间字段与逻辑删除。"""

    created_at = models.DateTimeField(
        "创建时间", auto_now_add=True, db_index=True, db_comment="创建时间"
    )
    updated_at = models.DateTimeField(
        "更新时间", auto_now=True, db_comment="最后更新时间"
    )
    deleted_at = models.DateTimeField(
        "删除时间",
        null=True,
        blank=True,
        db_index=True,
        db_comment="逻辑删除时间，NULL 表示未删除",
    )

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])
