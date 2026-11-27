"""健康检查视图 —— 用于 SLB / Nginx / 云监控探活。

复制到 backend/common/views.py 或 backend/config/urls.py 同目录。
在 urls.py 中挂载：path("health", health_check, name="health"),
"""
from django.http import JsonResponse
from django.db import connection
from redis import RedisError


def health_check(request):
    """轻量探活：返回 200 + 版本号。不做数据库/RDS 检查以防健康检查风暴。"""
    return JsonResponse({
        "status": "ok",
        "service": "art-assessment",
    })


def readiness_check(request):
    """就绪检查：验证 DB / Redis 连通性，SLB 用这个判断后端是否可接收流量。"""
    checks = {"db": False, "redis": False}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["db"] = True
    except Exception as e:
        checks["db_error"] = str(e)

    try:
        from django.core.cache import cache
        checks["redis"] = bool(cache.ping()) if hasattr(cache, "ping") else True
    except (ImportError, RedisError, Exception) as e:
        checks["redis_error"] = str(e)

    healthy = checks["db"] and checks["redis"]
    status = "ready" if healthy else "unhealthy"
    code = 200 if healthy else 503
    payload = {"status": status, "checks": checks, "service": "art-assessment"}
    return JsonResponse(payload, status=code)
