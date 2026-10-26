"""音乐/美术模型评分规则库。

规则文件位于 ``exams/rules/*.yaml``，按“社会艺术水平考级”1-10 级
通用基线组织。模型只输出 0-1 的指标值，本服务负责：

1. 按学科/类别/级别解析规则；
2. 指标锚点插值，得到各维度得分；
3. 权重汇总、硬性封顶、等级判定；
4. 缺项或低置信度时转人工复核。

规则库是“评分口径”，不是考级机构的官方大纲；机构差异通过修改
weights / anchors / bandCutoffs 校准。
"""
import copy
from pathlib import Path

import yaml

from common.exceptions import BadRequest, NotFound
from common.utils import round2, round4

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
SUBJECTS = ("music", "art")
_CACHE = {}


class RuleConfigError(RuntimeError):
    """规则文件本身不合法，属于部署/配置错误。"""


def _path(subject):
    if subject not in SUBJECTS:
        raise NotFound(f"评分规则学科不存在：{subject}")
    return RULES_DIR / f"{subject}.yaml"


def _validate_cutoffs(cutoffs, where):
    for key in ("excellent", "good", "pass"):
        if key not in cutoffs:
            raise RuleConfigError(f"{where} 缺少 {key}")
        if not 0 <= float(cutoffs[key]) <= 1:
            raise RuleConfigError(f"{where} 的 {key} 必须在 0-1 之间")
    if not (
        float(cutoffs["excellent"])
        >= float(cutoffs["good"])
        >= float(cutoffs["pass"])
    ):
        raise RuleConfigError(f"{where} 必须满足 excellent >= good >= pass")


def _validate(lib, subject):
    if not isinstance(lib, dict):
        raise RuleConfigError(f"{subject}.yaml 顶层必须是对象")
    meta = lib.get("meta") or {}
    if meta.get("id") != subject:
        raise RuleConfigError(f"{subject}.yaml meta.id 必须为 {subject}")
    if not meta.get("version"):
        raise RuleConfigError(f"{subject}.yaml 缺少 meta.version")
    if not lib.get("levels"):
        raise RuleConfigError(f"{subject}.yaml 缺少 levels")
    levels = lib["levels"]
    if set(levels) != {str(i) for i in range(1, 11)}:
        raise RuleConfigError(f"{subject}.yaml 必须且只能包含 1-10 级")
    default_cutoffs = meta.get("defaultBandCutoffs") or {}
    _validate_cutoffs(default_cutoffs, f"{subject} 默认等级线")
    for level, profile in levels.items():
        _validate_cutoffs(
            profile.get("bandCutoffs") or default_cutoffs,
            f"{subject} {level} 级等级线",
        )
    anchors = lib.get("anchorProfiles") or {}
    if not anchors:
        raise RuleConfigError(f"{subject}.yaml 缺少 anchorProfiles")
    for name, points in anchors.items():
        if not isinstance(points, list) or len(points) < 2:
            raise RuleConfigError(f"{subject}.yaml 锚点 {name} 至少需要两个点")
        previous_x = -1.0
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise RuleConfigError(f"{subject}.yaml 锚点 {name} 必须为 [指标, 比例]")
            if float(point[0]) <= previous_x:
                raise RuleConfigError(f"{subject}.yaml 锚点 {name} 的指标值必须严格递增")
            previous_x = float(point[0])

    categories = lib.get("categories") or {}
    if not categories:
        raise RuleConfigError(f"{subject}.yaml 缺少 categories")
    for key, cat in categories.items():
        dimensions = cat.get("dimensions") or []
        if not dimensions:
            raise RuleConfigError(f"{subject}/{key} 缺少 dimensions")
        total_weight = 0.0
        metrics = set()
        for dim in dimensions:
            for field in ("key", "name", "weight", "metric", "anchor"):
                if field not in dim:
                    raise RuleConfigError(f"{subject}/{key} 维度缺少 {field}")
            if dim["anchor"] not in anchors:
                raise RuleConfigError(
                    f"{subject}/{key} 维度 {dim['key']} 引用了不存在的锚点 {dim['anchor']}"
                )
            if dim["metric"] in metrics:
                raise RuleConfigError(
                    f"{subject}/{key} 指标 {dim['metric']} 重复，会导致重复计分"
                )
            metrics.add(dim["metric"])
            total_weight += float(dim["weight"])
        if abs(total_weight - 1.0) > 1e-6:
            raise RuleConfigError(
                f"{subject}/{key} 维度权重之和为 {total_weight:.4f}，必须等于 1"
            )
        for cap in cat.get("caps") or []:
            if cap.get("metric") not in metrics:
                raise RuleConfigError(
                    f"{subject}/{key} 封顶规则引用了不存在的指标 {cap.get('metric')}"
                )
            if not 0 <= float(cap.get("maxRatio", -1)) <= 1:
                raise RuleConfigError(f"{subject}/{key} 封顶比例必须在 0-1 之间")


def load_library(subject):
    """按文件 mtime 缓存，修改 YAML 后无需重启即可生效。"""
    path = _path(subject)
    if not path.exists():
        raise NotFound(f"评分规则文件不存在：{path.name}")
    mtime = path.stat().st_mtime
    cached = _CACHE.get(subject)
    if cached and cached[0] == mtime:
        return cached[1]
    with path.open(encoding="utf-8") as handle:
        lib = yaml.safe_load(handle)
    if isinstance(lib, dict) and isinstance(lib.get("levels"), dict):
        # 兼容 YAML 中未加引号的数字级别键
        lib["levels"] = {str(key): value for key, value in lib["levels"].items()}
    _validate(lib, subject)
    _CACHE[subject] = (mtime, lib)
    return lib


def version(subject):
    return load_library(subject)["meta"]["version"]


def list_rules():
    subjects = []
    for subject in SUBJECTS:
        lib = load_library(subject)
        categories = []
        for key, cat in lib["categories"].items():
            categories.append({
                "key": key,
                "name": cat["name"],
                "modelScored": bool(cat.get("modelScored", True)),
                "evaluation": cat.get("evaluation", "model"),
                "note": cat.get("note"),
                "competencies": cat.get("competencies", []),
                "dimensions": [
                    {
                        "key": dim["key"],
                        "name": dim["name"],
                        "weight": float(dim["weight"]),
                        "metric": dim["metric"],
                        "competency": dim.get("competency"),
                        "required": bool(dim.get("required", True)),
                    }
                    for dim in cat["dimensions"]
                ],
            })
        subjects.append({
            "subject": subject,
            "name": lib["meta"]["name"],
            "version": lib["meta"]["version"],
            "standard": lib["meta"]["standard"],
            "standardNote": lib["meta"].get("standardNote"),
            "levels": [
                {
                    "level": int(level),
                    "label": profile["label"],
                    "stage": profile.get("stage"),
                    "expectation": profile.get("expectation"),
                }
                for level, profile in lib["levels"].items()
            ],
            "categories": categories,
        })
    return {"versions": {item["subject"]: item["version"] for item in subjects},
            "subjects": subjects}


def _level_profile(lib, level):
    if level in (None, ""):
        return {
            "level": None,
            "label": "通用",
            "stage": "通用",
            "expectation": "未指定考级级别，使用通用评分基线。",
            "bandCutoffs": lib["meta"]["defaultBandCutoffs"],
        }
    try:
        value = int(level)
    except (TypeError, ValueError):
        raise BadRequest("level 必须为 1-10 的整数")
    profile = lib["levels"].get(str(value))
    if profile is None:
        raise BadRequest("level 必须为 1-10 的整数")
    return {
        "level": value,
        "label": profile["label"],
        "stage": profile.get("stage"),
        "expectation": profile.get("expectation"),
        "bandCutoffs": profile.get("bandCutoffs") or lib["meta"]["defaultBandCutoffs"],
    }


def get_rule(subject, category, level=None):
    lib = load_library(subject)
    cat = lib["categories"].get(category)
    if cat is None:
        raise NotFound(f"评分规则类别不存在：{subject}/{category}")
    profile = _level_profile(lib, level)
    return {
        "subject": subject,
        "subjectName": lib["meta"]["name"],
        "version": lib["meta"]["version"],
        "standard": lib["meta"]["standard"],
        "standardNote": lib["meta"].get("standardNote"),
        "category": category,
        "categoryName": cat["name"],
        "modelScored": bool(cat.get("modelScored", True)),
        "evaluation": cat.get("evaluation", "model"),
        "note": cat.get("note"),
        "competencies": cat.get("competencies", []),
        "dimensions": copy.deepcopy(cat["dimensions"]),
        "caps": copy.deepcopy(cat.get("caps") or []),
        "levels": copy.deepcopy(lib["levels"]),
        "anchorProfiles": copy.deepcopy(lib["anchorProfiles"]),
        "defaultBandCutoffs": copy.deepcopy(lib["meta"]["defaultBandCutoffs"]),
        "levelProfile": profile,
    }


def model_rule_set(subject, category=None, level=None):
    """给模型服务的精简规则集；未指定类别时下发该学科全部类别。"""
    lib = load_library(subject)
    data = {
        "subject": subject,
        "subjectName": lib["meta"]["name"],
        "version": lib["meta"]["version"],
        "standard": lib["meta"]["standard"],
        "levels": copy.deepcopy(lib["levels"]),
        "anchorProfiles": copy.deepcopy(lib["anchorProfiles"]),
        "defaultBandCutoffs": copy.deepcopy(lib["meta"]["defaultBandCutoffs"]),
        "outputSchema": copy.deepcopy(lib["meta"].get("modelOutputSchema")),
    }
    categories = lib["categories"]
    if category:
        cat = categories.get(category)
        if cat is None:
            raise NotFound(f"评分规则类别不存在：{subject}/{category}")
        data["category"] = category
        data["categoryName"] = cat["name"]
        data["dimensions"] = copy.deepcopy(cat["dimensions"])
        data["caps"] = copy.deepcopy(cat.get("caps") or [])
        data["note"] = cat.get("note")
    else:
        data["categories"] = {
            key: {
                "name": cat["name"],
                "modelScored": bool(cat.get("modelScored", True)),
                "evaluation": cat.get("evaluation", "model"),
                "note": cat.get("note"),
                "dimensions": copy.deepcopy(cat["dimensions"]),
                "caps": copy.deepcopy(cat.get("caps") or []),
            }
            for key, cat in categories.items()
        }
    data["levelProfile"] = _level_profile(lib, level)
    return data


def infer_category(subject, stem, default=None):
    """从题干关键词推断类别；推断不确定时返回 default（默认 None）。"""
    stem = stem or ""
    keyword_map = {
        "music": (
            ("solfege", ("视唱", "模唱", "练耳", "听辨")),
            ("theory", ("乐理", "音程", "和弦", "调式", "谱号", "术语")),
            ("vocal", ("演唱", "声乐", "唱歌")),
            ("instrumental", ("演奏", "钢琴", "小提琴", "古筝", "二胡", "器乐")),
        ),
        "art": (
            ("calligraphy", ("书法", "毛笔", "楷书", "行书", "隶书")),
            ("quick_sketch", ("速写",)),
            ("color", ("色彩", "水粉", "水彩", "油画")),
            ("children", ("儿童画", "创意画")),
            ("sketch", ("素描",)),
        ),
    }
    for category, keywords in keyword_map.get(subject, ()):
        if any(keyword in stem for keyword in keywords):
            return category
    return default


def _interpolate(points, value):
    value = max(0.0, min(1.0, float(value)))
    if value <= points[0][0]:
        return float(points[0][1])
    for left, right in zip(points, points[1:]):
        x1, y1 = float(left[0]), float(left[1])
        x2, y2 = float(right[0]), float(right[1])
        if value <= x2:
            if x2 == x1:
                return y2
            return y1 + (y2 - y1) * (value - x1) / (x2 - x1)
    return float(points[-1][1])


def _metric_value(raw):
    """兼容 0.8 与 {value: 0.8, confidence: 0.9} 两种写法。"""
    if isinstance(raw, dict):
        return raw.get("value"), raw.get("confidence")
    return raw, None


def _compare(value, op, target):
    return {
        "lt": value < target,
        "lte": value <= target,
        "gt": value > target,
        "gte": value >= target,
    }.get(op, False)


def _band_for_ratio(ratio, cutoffs):
    if ratio is None:
        return None
    if ratio >= float(cutoffs["excellent"]):
        return "excellent"
    if ratio >= float(cutoffs["good"]):
        return "good"
    if ratio >= float(cutoffs["pass"]):
        return "pass"
    return "fail"


BAND_LABELS = {
    "excellent": "优秀",
    "good": "良好",
    "pass": "合格",
    "fail": "不合格",
}


def evaluate(subject, category, level=None, metrics=None, max_score=100, confidence=None):
    lib = load_library(subject)
    cat = lib["categories"].get(category)
    if cat is None:
        raise NotFound(f"评分规则类别不存在：{subject}/{category}")
    if not isinstance(metrics, dict) or not metrics:
        raise BadRequest("metrics 不能为空")
    try:
        max_score = float(max_score)
    except (TypeError, ValueError):
        raise BadRequest("maxScore 必须为数字")
    if max_score <= 0:
        raise BadRequest("maxScore 必须大于 0")

    profile = _level_profile(lib, level)
    cutoffs = profile["bandCutoffs"]
    warnings = []
    metric_values = {}
    metric_confidences = []

    known = {dim["metric"] for dim in cat["dimensions"]}
    for key, raw in metrics.items():
        value, item_confidence = _metric_value(raw)
        if value is None:
            warnings.append(f"指标 {key} 缺少 value，已忽略")
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise BadRequest(f"指标 {key} 必须为 0-1 的数字")
        value = float(value)
        if not 0 <= value <= 1:
            raise BadRequest(f"指标 {key} 必须在 0-1 之间")
        if key not in known:
            warnings.append(f"未知指标 {key}，已忽略")
            continue
        metric_values[key] = value
        if isinstance(item_confidence, (int, float)) and not isinstance(item_confidence, bool):
            metric_confidences.append(float(item_confidence))

    if confidence is None and metric_confidences:
        confidence = min(metric_confidences)
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            raise BadRequest("confidence 必须为 0-1 的数字")
        if not 0 <= confidence <= 1:
            raise BadRequest("confidence 必须在 0-1 之间")

    dimensions = []
    missing = []
    total_weight = 0.0
    weighted_ratio = 0.0
    competency_weight = {}
    competency_ratio = {}

    for dim in cat["dimensions"]:
        value = metric_values.get(dim["metric"])
        if value is None:
            if dim.get("required", True):
                missing.append(dim["metric"])
            continue
        ratio = _interpolate(lib["anchorProfiles"][dim["anchor"]], value)
        weight = float(dim["weight"])
        total_weight += weight
        weighted_ratio += ratio * weight
        band = _band_for_ratio(ratio, cutoffs)
        dimensions.append({
            "key": dim["key"],
            "name": dim["name"],
            "weight": round4(weight),
            "metric": dim["metric"],
            "metricValue": round4(value),
            "ratio": round4(ratio),
            "score": round2(ratio * weight * max_score),
            "maxScore": round2(weight * max_score),
            "band": band,
            "bandLabel": BAND_LABELS.get(band),
            "descriptor": (dim.get("descriptors") or {}).get(band),
            "competency": dim.get("competency"),
        })
        competency = dim.get("competency")
        if competency:
            competency_weight[competency] = competency_weight.get(competency, 0) + weight
            competency_ratio[competency] = (
                competency_ratio.get(competency, 0) + ratio * weight
            )

    total_ratio = None
    total_score = None
    caps_applied = []
    if not missing and total_weight > 0:
        total_ratio = weighted_ratio / total_weight
        for cap in cat.get("caps") or []:
            value = metric_values.get(cap["metric"])
            if value is None:
                continue
            if _compare(value, cap.get("op"), float(cap.get("value", 0))):
                max_ratio = float(cap["maxRatio"])
                if total_ratio > max_ratio:
                    total_ratio = max_ratio
                    caps_applied.append({
                        "metric": cap["metric"],
                        "metricValue": round4(value),
                        "maxRatio": round4(max_ratio),
                        "reason": cap.get("reason"),
                    })
                    warnings.append(
                        f"指标 {cap['metric']} 触发封顶，总分不超过 {round4(max_ratio)}"
                    )
        total_score = round2(total_ratio * max_score)
    elif missing:
        warnings.append("缺少必填指标：" + "、".join(missing))

    band = _band_for_ratio(total_ratio, cutoffs)
    needs_manual = bool(missing) or (confidence is not None and confidence < 0.60)
    if cat.get("modelScored") is False:
        warnings.append("该类别以自动判分为主，模型分仅作参考")
    if confidence is not None and confidence < 0.60:
        warnings.append("模型置信度低于 0.60，建议人工复核")

    competencies = {
        name: round4(competency_ratio[name] / weight)
        for name, weight in competency_weight.items()
        if weight > 0
    }

    return {
        "ruleId": f"{subject}.{category}",
        "ruleVersion": lib["meta"]["version"],
        "standard": lib["meta"]["standard"],
        "subject": subject,
        "category": category,
        "categoryName": cat["name"],
        "level": profile["level"],
        "levelLabel": profile["label"],
        "levelExpectation": profile.get("expectation"),
        "maxScore": round2(max_score),
        "totalScore": total_score,
        "ratio": round4(total_ratio) if total_ratio is not None else None,
        "band": band,
        "bandLabel": BAND_LABELS.get(band),
        "pass": (total_ratio is not None and total_ratio >= float(cutoffs["pass"])),
        "dimensions": dimensions,
        "competencies": competencies,
        "capsApplied": caps_applied,
        "confidence": round4(confidence) if confidence is not None else None,
        "warnings": warnings,
        "needsManualReview": needs_manual,
    }
