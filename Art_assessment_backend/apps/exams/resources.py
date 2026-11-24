"""试题资源读取：统一走 FileObject（MinIO/本地）。"""
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage

from apps.files.models import FileObject

MAX_RESOURCE_BYTES = 50 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-一-鿿]+")


def safe_filename(name, fallback="file"):
    name = os.path.basename(name or "").strip() or fallback
    name = _SAFE_NAME.sub("_", name)
    return name[:120]


def build_resource_rows(question) -> list[dict]:
    """试题快照中的资源列表。"""
    rows = []
    for resource in question.resources.select_related("file").all():
        file_obj = resource.file
        rows.append(
            {
                "type": resource.type,
                "url": file_obj.url,
                "name": file_obj.original_name,
                "fileId": file_obj.id,
            }
        )
    return rows


def _file_id(resource):
    if isinstance(resource, dict):
        return resource.get("fileId") or resource.get("file_id")
    return getattr(resource, "file_id", None)


def _local_path(resource):
    if isinstance(resource, dict):
        return resource.get("localPath") or resource.get("local_path") or ""
    return getattr(resource, "local_path", "") or ""


def read_resource(resource) -> bytes | None:
    """读取试题资源字节；仅允许 FileObject 或 MEDIA_ROOT 内本地文件。"""
    file_id = _file_id(resource)
    if file_id:
        file_obj = FileObject.objects.filter(pk=file_id).first()
        if file_obj is not None:
            if file_obj.storage_backend == "minio":
                from apps.files import minio

                try:
                    response = minio.get_client().get_object(
                        Bucket=settings.MINIO_BUCKET, Key=file_obj.object_key
                    )
                    return response["Body"].read()
                except Exception:
                    return None
            try:
                if default_storage.exists(file_obj.object_key):
                    if default_storage.size(file_obj.object_key) > MAX_RESOURCE_BYTES:
                        return None
                    with default_storage.open(file_obj.object_key, "rb") as handle:
                        return handle.read()
            except Exception:
                return None

    local_path = _local_path(resource)
    if local_path:
        path = Path(local_path)
        if not path.is_absolute():
            path = Path(settings.MEDIA_ROOT) / local_path
        try:
            path = path.resolve()
            media_root = Path(settings.MEDIA_ROOT).resolve()
            if path.is_relative_to(media_root) and path.is_file():
                if path.stat().st_size <= MAX_RESOURCE_BYTES:
                    return path.read_bytes()
        except (OSError, ValueError):
            return None
    return None
