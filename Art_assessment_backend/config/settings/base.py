"""基础配置：所有环境共享，环境差异放在 dev/prod/test。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
PROJECT_ROOT = BASE_DIR.parent  # Art_assessment/

for env_file in (PROJECT_ROOT / ".env", BASE_DIR / ".env"):
    if env_file.exists():
        load_dotenv(env_file, override=False)


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "django_rq",
    "common",
    "apps.organizations",
    "apps.accounts",
    "apps.classes",
    "apps.files",
    "apps.qbank",
    "apps.exams",
]

MIDDLEWARE = [
    "common.middleware.RequestIdMiddleware",
    "common.middleware.UnhandledExceptionMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "art_assessment"),
        "USER": os.getenv("DB_USER", "art"),
        "PASSWORD": os.getenv("DB_PASSWORD", "art_pass"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "3307"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET time_zone = '+08:00'",
        },
    }
}

AUTH_USER_MODEL = "accounts.User"

# 新建账号（学生/教师/各级管理员/批量导入）未指定初始密码时统一使用该值。
DEFAULT_INITIAL_PASSWORD = os.getenv("DEFAULT_INITIAL_PASSWORD", "Art@2026")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

if os.getenv("CACHE_BACKEND", "redis") == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "art-assessment",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        }
    }

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- 文件存储 ----------
FILE_STORAGE = os.getenv("FILE_STORAGE", "minio")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", MINIO_ENDPOINT)
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "art-assessment")
MINIO_USE_SSL = env_bool("MINIO_USE_SSL", False)
MINIO_PRESIGN_EXPIRES = int(os.getenv("MINIO_PRESIGN_EXPIRES", "300"))

# 音频标签模型（arteval-v4）：独立 CPU 推理服务，默认地址 http://127.0.0.1:8100。
# 关闭或服务不可用时，上传、评分和题库功能保持可用，只是不展示音频标签。
AUDIO_TAGGER_ENABLED = env_bool("AUDIO_TAGGER_ENABLED", True)
AUDIO_TAGGER_URL = os.getenv("AUDIO_TAGGER_URL", "http://127.0.0.1:8100").rstrip("/")
AUDIO_TAGGER_TIMEOUT = int(os.getenv("AUDIO_TAGGER_TIMEOUT", "120"))
AUDIO_TAGGER_DISCLAIMER = (
    "音频标签由开源音乐标签模型生成，仅供教学参考；规则参考分不是成绩，"
    "不参与自动判分，最终得分以教师人工评分为准。"
)

# 音乐作品 AI 建议分：把 8100 的 0–100 参考分折算到题目满分后展示给教师。
# 仅作参考，不写入成绩；置信度低于阈值时提示人工复核，但不会因此压分。
AI_SCORE_SUGGESTION_ENABLED = env_bool("AI_SCORE_SUGGESTION_ENABLED", True)
AI_SCORE_CONFIDENCE_THRESHOLD = float(
    os.getenv("AI_SCORE_CONFIDENCE_THRESHOLD", "0.4")
)
AI_SCORE_SOURCE_MAX = float(os.getenv("AI_SCORE_SOURCE_MAX", "100"))

# 美术作品 AI 辅助评分。没有外部模型时使用规则式降级（degraded=true），
# 永远只返回建议分，不写成绩。
ART_SCORER_ENABLED = env_bool("ART_SCORER_ENABLED", True)
ART_SCORER_URL = os.getenv("ART_SCORER_URL", "").rstrip("/")
ART_SCORER_TIMEOUT = int(os.getenv("ART_SCORER_TIMEOUT", "60"))
ART_SCORER_CONFIDENCE_THRESHOLD = float(
    os.getenv("ART_SCORER_CONFIDENCE_THRESHOLD", "0.6")
)

# 美术出题模型（Model B，Qwen2.5-3B-Instruct + QLoRA）：独立 GPU 服务，
# 默认关闭；只用于生成待审草稿，不参与组卷和判分。
# QGEN_PROVIDER=model_b 调用本地 8002；QGEN_PROVIDER=api 调用兼容 OpenAI 的云接口。
QGEN_ENABLED = env_bool("QGEN_ENABLED", False)
QGEN_PROVIDER = os.getenv("QGEN_PROVIDER", "model_b").strip().lower()
QGEN_URL = os.getenv("QGEN_URL", "http://127.0.0.1:8002").rstrip("/")
QGEN_TIMEOUT = int(os.getenv("QGEN_TIMEOUT", "90"))
QGEN_TOKEN = os.getenv("QGEN_TOKEN", "")
QGEN_API_BASE = os.getenv("QGEN_API_BASE", "").rstrip("/")
QGEN_API_KEY = os.getenv("QGEN_API_KEY", "")
QGEN_API_MODEL = os.getenv("QGEN_API_MODEL", "")
QGEN_API_TIMEOUT = int(os.getenv("QGEN_API_TIMEOUT", "60"))
QGEN_API_TEMPERATURE = float(os.getenv("QGEN_API_TEMPERATURE", "0.7"))
QGEN_ALLOWED_TYPES = ["single_choice", "true_false"]
# 图题：默认请求模型优先生成带配图的题（无同题型素材时服务会自动退回文字题）。
QGEN_WITH_IMAGE = env_bool("QGEN_WITH_IMAGE", True)
# 模型服务返回的配图 URL 前缀；后端只从该前缀/QGEN_URL 下载图片，避免任意 URL 拉取。
QGEN_RESOURCE_URL_BASE = os.getenv("QGEN_RESOURCE_URL_BASE", "/resources").rstrip("/")
QGEN_RESOURCE_TIMEOUT = int(os.getenv("QGEN_RESOURCE_TIMEOUT", "30"))
QGEN_RESOURCE_MAX_BYTES = int(
    os.getenv("QGEN_RESOURCE_MAX_BYTES", str(10 * 1024 * 1024))
)
QGEN_BANK_PATH = os.getenv("QGEN_BANK_PATH", "")
QGEN_UNIT_MAP_PATH = os.getenv("QGEN_UNIT_MAP_PATH", "")
QGEN_NEAR_DUPLICATE = float(os.getenv("QGEN_NEAR_DUPLICATE", "0.9"))

# ---------- 测评模块 ----------
LATE_SUBMIT_GRACE_MINUTES = int(os.getenv("LATE_SUBMIT_GRACE_MINUTES", "10"))
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))
SCORE_IMPORT_ASYNC_THRESHOLD = int(os.getenv("SCORE_IMPORT_ASYNC_THRESHOLD", "500"))
SCORE_IMPORT_MAX_BYTES = int(os.getenv("SCORE_IMPORT_MAX_BYTES", str(10 * 1024 * 1024)))
RESOURCE_ALLOWED_HOSTS = [
    h for h in os.getenv("RESOURCE_ALLOWED_HOSTS", "").split(",") if h
]
CERTIFICATE_ROOT = MEDIA_ROOT / "certificates"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["common.jwt.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["common.permissions.IsAuthenticatedActive"],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "PAGE_SIZE": 10,
    "EXCEPTION_HANDLER": "common.exceptions.unified_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "艺术素质测评系统 API",
    "VERSION": "2.0.0",
    "DESCRIPTION": "艺术素质测评系统后端接口文档（后端 B：模块一、模块二、模块三）",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "AccountStatusEnum": "common.enums.AccountStatus",
        "ClassStatusEnum": "common.enums.ClassStatus",
        "CourseStatusEnum": "common.enums.CourseStatus",
        "QuestionStatusEnum": "common.enums.QuestionStatus",
        "QuestionTypeEnum": "common.enums.QuestionType",
        "ResourceTypeEnum": "common.enums.ResourceType",
        "ScoreAggregationEnum": "common.enums.ScoreAggregation",
        "MissingComponentPolicyEnum": "common.enums.MissingComponentPolicy",
        "TotalScoreRuleStatusEnum": "common.enums.TotalScoreRuleStatus",
        "NotificationTypeEnum": "common.enums.NotificationType",
    },
}

JWT_SECRET = os.getenv("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL", "1800"))
JWT_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL", "604800"))

RQ_QUEUES = {
    "default": {
        "URL": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        "DEFAULT_TIMEOUT": 600,
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "common.request_context.RequestIdFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
