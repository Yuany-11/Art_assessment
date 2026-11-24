"""证书文件存取：MinIO 私有桶，测试/本地环境回退 MEDIA_ROOT。"""
from django.conf import settings
from django.core.files.storage import default_storage

from apps.files.models import FileObject
from apps.files.services import save_generated
from common.enums import FileCategory


def save_certificate(certificate_no: str, content: bytes, uploader=None) -> str:
    """保存证书 PDF，返回对象 Key。"""
    file_obj = save_generated(
        f"{certificate_no}.pdf", content, FileCategory.CERTIFICATE, uploader
    )
    return file_obj.object_key


def read_certificate(file_key: str) -> bytes | None:
    """按对象 Key 读取证书内容。"""
    if not file_key:
        return None
    file_obj = FileObject.objects.filter(object_key=file_key).first()
    if file_obj is None or file_obj.storage_backend == "local":
        try:
            with default_storage.open(file_key, "rb") as handle:
                return handle.read()
        except FileNotFoundError:
            return None

    from apps.files import minio

    try:
        response = minio.get_client().get_object(
            Bucket=settings.MINIO_BUCKET, Key=file_key
        )
        return response["Body"].read()
    except Exception:
        return None
