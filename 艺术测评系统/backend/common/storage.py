"""本地文件存储与受限资源读取。

生产环境可替换为 MinIO 客户端；本模块只暴露最小接口，方便后续接对象存储。
"""
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from django.conf import settings

MAX_RESOURCE_BYTES = 50 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-一-鿿]+")


def safe_filename(name, fallback="file"):
    name = os.path.basename(name or "").strip() or fallback
    name = _SAFE_NAME.sub("_", name)
    return name[:120]


def certificate_path(certificate_no):
    return Path(settings.CERTIFICATE_ROOT) / f"{certificate_no}.pdf"


def save_certificate(certificate_no, content):
    path = certificate_path(certificate_no)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pdf.tmp")
    tmp.write_bytes(content)
    tmp.replace(path)
    return str(path)


def read_certificate(certificate_no):
    path = certificate_path(certificate_no)
    if not path.exists():
        return None
    return path.read_bytes()


def read_resource(resource):
    """读取试题资源字节；无法读取时返回 None。

    仅允许本地文件或 RESOURCE_ALLOWED_HOSTS 白名单内的 http(s) 地址，
    防止通过资源 URL 进行 SSRF。
    """
    local_path = getattr(resource, "local_path", "") or ""
    if local_path:
        path = Path(local_path)
        if not path.is_absolute():
            path = Path(settings.MEDIA_ROOT) / local_path
        try:
            path = path.resolve()
            media_root = Path(settings.MEDIA_ROOT).resolve()
            books = [media_root, Path(settings.BASE_DIR).resolve()]
            if any(path.is_relative_to(root) for root in books) and path.is_file():
                if path.stat().st_size <= MAX_RESOURCE_BYTES:
                    return path.read_bytes()
        except (OSError, ValueError):
            return None

    url = getattr(resource, "url", "") or ""
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.hostname in set(
        settings.RESOURCE_ALLOWED_HOSTS
    ):
        try:
            with urlopen(url, timeout=10) as response:  # noqa: S310 - 白名单域
                data = response.read(MAX_RESOURCE_BYTES + 1)
            if len(data) <= MAX_RESOURCE_BYTES:
                return data
        except OSError:
            return None
    return None


def public_file_url(file_id):
    """文件访问 URL 由模块一签发 5 分钟签名地址；此处返回稳定内部标识。"""
    return f"/api/v1/files/{file_id}"
