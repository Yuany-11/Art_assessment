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
        db_comment="上传人用户 ID",
    )
    category = models.CharField(
        "文件分类",
        max_length=32,
        choices=FileCategory.choices,
        db_comment="文件分类：avatar/question_image/question_audio/student_work/certificate/import/other",
    )
    original_name = models.CharField(
        "原始文件名", max_length=255, db_comment="原始文件名"
    )
    object_key = models.CharField(
        "对象 Key", max_length=500, unique=True, db_comment="存储对象 Key（唯一）"
    )
    mime_type = models.CharField(
        "MIME 类型", max_length=100, db_comment="文件 MIME 类型"
    )
    size = models.BigIntegerField("文件大小", db_comment="文件大小（字节）")
    storage_backend = models.CharField(
        "存储后端", max_length=16, default="local", db_comment="存储后端：local/minio"
    )
    biz_id = models.BigIntegerField(
        "关联业务 ID", null=True, blank=True, db_comment="关联业务 ID，如试题 ID、测评 ID"
    )

    class Meta:
        db_table = "files"
        db_table_comment = "文件对象表"
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.original_name

    @property
    def url(self) -> str:
        if self.storage_backend == "minio":
            from .minio import presigned_url

            return presigned_url(self.object_key)
        return f"{settings.MEDIA_URL}{self.object_key}"
