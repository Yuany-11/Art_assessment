"""开发环境配置。"""
import os

from .base import *  # noqa: F401,F403

DEBUG = True

# 本地联调可不安装 MySQL，在 .env 中设置 DB_ENGINE=sqlite 即可使用 SQLite。
if os.getenv("DB_ENGINE", "mysql").strip().lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
