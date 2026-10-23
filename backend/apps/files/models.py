"""文件对象与本地存储。"""
from django.conf import settings
from django.db import models

from common.enums import FileCategory
from common.models import BaseModel


class FileObject(BaseModel):
    uploader = models.ForeignKey(
        "accounts.User",
        verbose_name="上传人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_files",
    )
    category = models.CharField("文件分类", max_length=32, choices=FileCategory.choices)
    original_name = models.CharField("原始文件名", max_length=255)
    object_key = models.CharField("对象 Key", max_length=500, unique=True)
    mime_type = models.CharField("MIME 类型", max_length=100)
    size = models.BigIntegerField("文件大小")
    storage_backend = models.CharField("存储后端", max_length=16, default="local")
    biz_id = models.BigIntegerField("关联业务 ID", null=True, blank=True)

    class Meta:
        db_table = "files"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.original_name

    @property
    def url(self) -> str:
        if self.storage_backend == "minio":
            from .minio import presigned_url

            return presigned_url(self.object_key)
        return f"{settings.MEDIA_URL}{self.object_key}"
