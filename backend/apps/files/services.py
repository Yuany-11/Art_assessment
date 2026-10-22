"""文件上传校验与本地/MinIO 存储。"""
import uuid

from django.conf import settings
from django.core.files.storage import default_storage

from common.audit import log_operation
from common.enums import FileCategory, Role
from common.exceptions import BusinessError

from . import minio as minio_storage
from .models import FileObject

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a"}
IMPORT_EXTS = {".csv", ".xlsx"}

CATEGORY_RULES: dict[str, tuple[set[str], int]] = {
    FileCategory.AVATAR: (IMAGE_EXTS, 10),
    FileCategory.QUESTION_IMAGE: (IMAGE_EXTS, 10),
    FileCategory.STUDENT_WORK: (IMAGE_EXTS, 10),
    FileCategory.QUESTION_AUDIO: (AUDIO_EXTS, 50),
    FileCategory.CERTIFICATE: ({".pdf"}, 20),
    FileCategory.IMPORT: (IMPORT_EXTS, 10),
    FileCategory.OTHER: (IMAGE_EXTS | AUDIO_EXTS | IMPORT_EXTS | {".pdf"}, 20),
}

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _header(uploaded, size: int = 16) -> bytes:
    uploaded.seek(0)
    header = uploaded.read(size)
    uploaded.seek(0)
    return header


def _check_magic(ext: str, header: bytes) -> bool:
    if ext in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if ext == ".mp3":
        return header[:3] == b"ID3" or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)
    if ext == ".wav":
        return header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if ext == ".m4a":
        return header[4:8] == b"ftyp"
    if ext == ".pdf":
        return header.startswith(b"%PDF")
    if ext == ".xlsx":
        return header.startswith(b"PK\x03\x04")
    if ext == ".csv":
        return True
    return False


def validate_upload(uploaded, category: str) -> str:
    if category not in CATEGORY_RULES:
        raise BusinessError(400, "文件分类不合法")

    name = uploaded.name or ""
    if "." not in name:
        raise BusinessError(400, "文件缺少扩展名")
    ext = "." + name.rsplit(".", 1)[-1].lower()

    allowed_exts, max_mb = CATEGORY_RULES[category]
    if ext not in allowed_exts:
        raise BusinessError(400, f"该分类不支持 {ext} 文件")
    if uploaded.size > max_mb * 1024 * 1024:
        raise BusinessError(400, f"文件大小不能超过 {max_mb} MB")
    if not _check_magic(ext, _header(uploaded)):
        raise BusinessError(400, "文件内容与扩展名不匹配")
    return ext


def save_upload(uploaded, category: str, uploader, biz_id: int | None = None) -> FileObject:
    ext = validate_upload(uploaded, category)
    object_key = f"{category}/{uuid.uuid4().hex}{ext}"
    mime_type = MIME_MAP.get(ext, "application/octet-stream")

    if settings.FILE_STORAGE == "minio":
        try:
            minio_storage.upload_object(uploaded, object_key, mime_type)
        except Exception as exc:
            raise BusinessError(500, "文件存储服务不可用") from exc
        saved_key = object_key
        backend = "minio"
    else:
        saved_key = default_storage.save(object_key, uploaded)
        backend = "local"

    file_obj = FileObject.objects.create(
        uploader=uploader,
        category=category,
        original_name=uploaded.name,
        object_key=saved_key,
        mime_type=mime_type,
        size=uploaded.size,
        storage_backend=backend,
        biz_id=biz_id,
    )
    log_operation(
        uploader,
        "file.upload",
        "resource" if category in {FileCategory.QUESTION_IMAGE, FileCategory.QUESTION_AUDIO} else "system",
        file_obj.id,
        f"上传文件 {uploaded.name}（{category}）",
    )
    return file_obj


def delete_file(actor, file: FileObject) -> dict:
    from apps.qbank.models import QuestionResource

    if actor.role not in {
        Role.STUDENT,
        Role.TEACHER,
        Role.SCHOOL_ADMIN,
        Role.DISTRICT_ADMIN,
        Role.CITY_ADMIN,
        Role.PROVINCE_ADMIN,
        Role.QUESTION_ADMIN,
    }:
        raise BusinessError(403, "无权删除该文件")
    if file.uploader_id not in {None, actor.id} and actor.role not in {
        Role.SCHOOL_ADMIN,
        Role.DISTRICT_ADMIN,
        Role.CITY_ADMIN,
        Role.PROVINCE_ADMIN,
        Role.QUESTION_ADMIN,
    }:
        raise BusinessError(403, "无权删除该文件")

    if QuestionResource.objects.filter(file=file, deleted_at__isnull=True).exists():
        raise BusinessError(409, "文件已被试题引用，无法删除")

    try:
        if file.storage_backend == "minio":
            minio_storage.delete_object(file.object_key)
        else:
            default_storage.delete(file.object_key)
    except Exception:
        pass
    file.delete()
    log_operation(
        actor,
        "file.delete",
        "resource" if file.category in {FileCategory.QUESTION_IMAGE, FileCategory.QUESTION_AUDIO} else "system",
        file.id,
        f"删除文件 {file.original_name}",
    )
    return {"deleted": True, "fileId": file.id}
