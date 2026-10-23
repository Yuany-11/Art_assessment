"""测试环境配置：SQLite + 本地内存缓存，不依赖外部服务。"""
import tempfile

from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "art-assessment-test",
    }
}

MEDIA_ROOT = tempfile.mkdtemp(prefix="art-assessment-test-media-")
FILE_STORAGE = "local"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
