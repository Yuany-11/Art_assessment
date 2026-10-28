"""开发环境配置：默认无需 MySQL / Redis / MinIO，克隆后可直接跑起来。

- 数据库：默认 SQLite（backend/db.sqlite3），设置 DB_ENGINE=mysql 切回 MySQL；
- 缓存：默认进程内缓存，设置 CACHE_BACKEND=redis 切回 Redis；
- 文件：默认落盘到 backend/media/，设置 FILE_STORAGE=minio 切回 MinIO。

以上默认值只在没有 `.env` 或 `.env` 未配置对应项时生效，显式配置始终优先。
"""
import os

from .base import *  # noqa: F401,F403

DEBUG = True

if os.getenv("DB_ENGINE", "sqlite").strip().lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

if os.getenv("CACHE_BACKEND", "locmem") != "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "art-assessment",
        }
    }

FILE_STORAGE = os.getenv("FILE_STORAGE", "local")
