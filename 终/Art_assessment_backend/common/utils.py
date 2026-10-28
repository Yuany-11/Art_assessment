"""通用工具：数值、时间、幂等缓存与判分辅助。"""
import hashlib
import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache
from django.utils import timezone

IDEMPOTENCY_PREFIX = "idem:"


def now():
    return timezone.now()


def round2(value):
    """分数保留 2 位小数，使用四舍五入（非银行家舍入）。"""
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def round4(value):
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def iso(dt):
    if dt is None:
        return None
    return dt.astimezone(timezone.get_current_timezone()).isoformat()


def date_str(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.get_current_timezone()).date().isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)


def _idempotency_key(user_id, key: str) -> str:
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"{IDEMPOTENCY_PREFIX}{user_id}:{digest}"


def idempotency_get(user_id, key: str):
    if not key:
        return None
    return cache.get(_idempotency_key(user_id, key))


def idempotency_set(user_id, key: str, data, ttl: int) -> None:
    if not key:
        return
    cache.set(_idempotency_key(user_id, key), data, ttl)


def normalize_answer(answer):
    """稳定序列化答案，便于判分与日志比对。"""
    return json.dumps(answer, ensure_ascii=False, sort_keys=True, default=str)


def level_for(total_score, max_score):
    """按得分率计算等级。"""
    from common.enums import Level

    if not max_score or max_score <= 0:
        return Level.FAIL
    rate = total_score / max_score
    if rate >= 0.9:
        return Level.EXCELLENT
    if rate >= 0.8:
        return Level.GOOD
    if rate >= 0.6:
        return Level.PASS
    return Level.FAIL
