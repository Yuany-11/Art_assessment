"""美术作品 AI 辅助评分（建议分）。

当前仓库没有美术评分模型权重。为保证接口可用且不伪装成模型结果，本模块：

* 配置了 ``ART_SCORER_URL`` 时调用外部评分服务；
* 未配置或调用失败时，用可解释的图像统计量（构图平衡、色彩丰富度、
  清晰度/对比度、画面完整度、创意复杂度）按 ``rules/art.yaml`` 的权重给出
  **规则式参考分**，并标记 ``degraded=true``、``method="rule_based"``；
* 置信度低于 0.60 时前端提示「建议人工复核」；
* 只返回建议，不写 ``AttemptAnswer.score`` / ``Score``，教师采纳后仍需保存。

规则式分数只用于排序和提示，不能替代教师判断。
"""
from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from django.conf import settings
from django.core.files.storage import default_storage
from PIL import Image, UnidentifiedImageError

from common.exceptions import BusinessError
from common.utils import round2

RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "art.yaml"
DISCLAIMER = "AI 建议分已按本题满分折算，仅供教师参考，不会自动计入成绩。"

DIMENSION_LABELS = {
    "composition": "构图",
    "color": "色彩",
    "technique": "造型/技法",
    "completeness": "完整性",
    "creativity": "创意表现",
}


@lru_cache(maxsize=1)
def load_rules() -> dict:
    try:
        with RULES_FILE.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _threshold() -> float:
    return float(getattr(settings, "ART_SCORER_CONFIDENCE_THRESHOLD", 0.6))


def _read_bytes(file_obj) -> bytes:
    if file_obj.storage_backend == "minio":
        from apps.files import minio as minio_storage

        return minio_storage.get_object_bytes(file_obj.object_key)
    with default_storage.open(file_obj.object_key, "rb") as handle:
        return handle.read()


def _load_image(content: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("图片无法解析") from exc
    image = image.convert("RGB")
    image.thumbnail((512, 512))
    return image


def _metrics(image: Image.Image) -> dict:
    arr = np.asarray(image, dtype=np.float32) / 255.0
    gray = arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114
    height, width = gray.shape

    rg = arr[..., 0] - arr[..., 1]
    yb = 0.5 * (arr[..., 0] + arr[..., 1]) - arr[..., 2]
    colorfulness = float(
        np.sqrt(rg.std() ** 2 + yb.std() ** 2)
        + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    )

    if height > 2 and width > 2:
        lap = (
            4 * gray[1:-1, 1:-1]
            - gray[:-2, 1:-1]
            - gray[2:, 1:-1]
            - gray[1:-1, :-2]
            - gray[1:-1, 2:]
        )
        sharpness = float(lap.var())
        edge = float(
            (np.abs(np.diff(gray, axis=1)).mean() + np.abs(np.diff(gray, axis=0)).mean()) / 2
        )
    else:
        sharpness = 0.0
        edge = 0.0

    left, right = gray[:, : width // 2].sum(), gray[:, width // 2 :].sum()
    top, bottom = gray[: height // 2, :].sum(), gray[height // 2 :, :].sum()
    left_right = 1 - abs(left - right) / max(left + right, 1e-6)
    top_bottom = 1 - abs(top - bottom) / max(top + bottom, 1e-6)
    edge_balance = float((left_right + top_bottom) / 2)

    block = 16
    h16, w16 = height // block * block, width // block * block
    if h16 and w16:
        blocks = gray[:h16, :w16].reshape(
            h16 // block, block, w16 // block, block
        ).transpose(0, 2, 1, 3).reshape(-1, block, block)
        content_ratio = float((blocks.std(axis=(1, 2)) > 0.02).mean())
    else:
        content_ratio = 0.0

    hsv = np.asarray(image.convert("HSV"), dtype=np.float32) / 255.0
    saturated = hsv[..., 1] > 0.15
    hue_bins = np.minimum((hsv[..., 0] * 12).astype(int), 11)
    color_variety = (
        len(set(hue_bins[saturated].tolist())) / 12 if saturated.any() else 0.0
    )

    return {
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
        "colorfulness": colorfulness,
        "sharpness": sharpness,
        "edge": edge,
        "edge_balance": edge_balance,
        "content_ratio": content_ratio,
        "color_variety": color_variety,
    }


def _norm(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return float(np.clip(value / cap, 0.0, 1.0) * 100)


def _level(total: float, rules: dict) -> str:
    for item in rules.get("levels") or []:
        if total >= float(item.get("min", 0)):
            return str(item.get("label") or "")
    return ""


def _score_metrics(metrics: dict, rules: dict) -> tuple[float, list[dict]]:
    limits = rules.get("limits") or {}
    weights = rules.get("weights") or {}

    brightness = metrics["brightness"]
    brightness_score = float(
        np.clip(100 - max(0.0, abs(brightness - 0.55) - 0.35) * 200, 0, 100)
    )
    scores = {
        "composition": 0.6 * _norm(metrics["edge_balance"], 1.0)
        + 0.4 * _norm(metrics["edge"], 0.12),
        "color": 0.6 * _norm(metrics["colorfulness"], float(limits.get("colorfulness", 60)))
        + 0.4 * metrics["color_variety"] * 100,
        "technique": 0.6
        * _norm(metrics["sharpness"], float(limits.get("sharpness", 0.02)))
        + 0.4 * _norm(metrics["contrast"], 0.25),
        "completeness": 0.7 * metrics["content_ratio"] * 100
        + 0.3 * brightness_score,
        "creativity": 0.5 * metrics["color_variety"] * 100
        + 0.5 * _norm(metrics["edge"], 0.12),
    }
    dimensions = []
    total = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        score = round2(float(np.clip(scores.get(key, 0.0), 0.0, 100.0)))
        dimensions.append(
            {
                "key": key,
                "label": DIMENSION_LABELS.get(key, key),
                "score": score,
                "weight": float(weight),
                "maxScore": 100,
            }
        )
        total += score * float(weight)
        weight_sum += float(weight)
    total = total / weight_sum if weight_sum else 0.0
    return round2(float(np.clip(total, 0.0, 100.0))), dimensions


def _rule_based(content: bytes, rules: dict) -> dict:
    image = _load_image(content)
    metrics = _metrics(image)
    total, dimensions = _score_metrics(metrics, rules)
    return {
        "rawScore": total,
        "confidence": float(rules.get("confidence", 0.35)),
        "grade": _level(total, rules),
        "dimensions": dimensions,
        "analysis": (
            "规则式参考分：根据画面构图平衡、色彩丰富度、清晰度与对比度、"
            "画面完整度和色彩/边缘复杂度估算，不是模型对作品质量的判断，"
            "请教师结合评分标准人工复核。"
        ),
        "method": "rule_based",
        "degraded": True,
    }


def _remote(content: bytes, file_obj, rules: dict) -> dict:
    url = str(getattr(settings, "ART_SCORER_URL", "") or "").strip()
    if not url:
        raise BusinessError(503, "未配置美术评分服务")
    payload = json.dumps(
        {
            "fileBase64": base64.b64encode(content).decode("ascii"),
            "mimeType": file_obj.mime_type,
            "filename": file_obj.original_name,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=int(getattr(settings, "ART_SCORER_TIMEOUT", 60))
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise BusinessError(503, "美术评分服务不可用") from exc
    raw = data.get("rawScore", data.get("score", data.get("total")))
    if raw is None:
        raise BusinessError(502, "美术评分服务未返回分数")
    dimensions = []
    for item in data.get("dimensions") or []:
        if not isinstance(item, dict):
            continue
        dimensions.append(
            {
                "key": str(item.get("key") or ""),
                "label": str(
                    item.get("label") or DIMENSION_LABELS.get(item.get("key"), item.get("key") or "")
                ),
                "score": round2(float(item.get("score") or 0)),
                "weight": float(item.get("weight") or 0),
                "maxScore": float(item.get("maxScore") or 100),
            }
        )
    confidence = data.get("confidence")
    return {
        "rawScore": round2(float(raw)),
        "confidence": float(confidence) if confidence is not None else None,
        "grade": str(data.get("grade") or _level(float(raw), rules)),
        "dimensions": dimensions,
        "analysis": str(data.get("analysis") or "由外部美术评分服务返回。"),
        "method": str(data.get("method") or "remote"),
        "degraded": bool(data.get("degraded", False)),
    }


def _item(row, *, status: str, message: str = "", **extra) -> dict:
    max_score = round2(float(row.max_score or 0))
    item = {
        "questionId": row.question_id,
        "status": status,
        "suggestedScore": None,
        "maxScore": max_score,
        "rawScore": None,
        "rawScoreMax": 100.0,
        "grade": None,
        "confidence": None,
        "needsReview": True,
        "message": message,
        "disclaimer": DISCLAIMER,
        "dimensions": [],
        "method": None,
        "degraded": True,
    }
    item.update(extra)
    return item


def build_suggestion(row, file_obj, *, allow_remote: bool = True) -> dict:
    if not getattr(settings, "ART_SCORER_ENABLED", True):
        return _item(row, status="disabled", message="未启用美术 AI 评分")
    if file_obj is None:
        return _item(row, status="missing", message="未找到学生提交的图片作品")

    rules = load_rules()
    try:
        content = _read_bytes(file_obj)
    except Exception as exc:  # noqa: BLE001 - 降级返回，不影响人工评分
        return _item(row, status="failed", message=f"无法读取图片：{exc}")

    result = None
    if allow_remote and getattr(settings, "ART_SCORER_URL", ""):
        try:
            result = _remote(content, file_obj, rules)
        except BusinessError:
            result = None
    if result is None:
        try:
            result = _rule_based(content, rules)
        except ValueError as exc:
            return _item(row, status="failed", message=str(exc))

    max_score = float(row.max_score or 0)
    raw_score = float(np.clip(float(result["rawScore"]), 0.0, 100.0))
    suggested = round2(min(max_score, max(0.0, raw_score / 100.0 * max_score)))
    confidence = result.get("confidence")
    needs_review = confidence is None or float(confidence) < _threshold()
    return _item(
        row,
        status="completed",
        suggestedScore=suggested,
        rawScore=round2(raw_score),
        grade=result.get("grade"),
        confidence=confidence,
        needsReview=needs_review,
        dimensions=result.get("dimensions") or [],
        method=result.get("method"),
        degraded=bool(result.get("degraded")),
        analysis=result.get("analysis"),
        message="规则式参考分，不是模型评分" if result.get("degraded") else "",
    )
