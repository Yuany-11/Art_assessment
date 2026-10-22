"""结构化输出模型与 JSON Schema 校验.

本模块是推理结果的唯一契约来源：所有 backend 都必须产出 ``AnalysisResult``。
字段含义见 ``docs/04_output_schema.md``，机器可读契约见
``schemas/music_analysis.schema.json``。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0.0"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "music_analysis.schema.json"

MODES = ("major", "minor")
MOOD_LABELS = ("happy", "calm", "sad", "tense", "neutral")
ENERGY_LABELS = ("low", "medium", "high")
BRIGHTNESS_LABELS = ("dark", "balanced", "bright")
TEXTURE_LABELS = ("harmonic", "mixed", "percussive")
KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass
class ModelInfo:
    name: str
    version: str
    backend: str
    device: str
    runtime_ms: float


@dataclass
class AudioInfo:
    filename: str
    format: str
    duration_sec: float
    sample_rate: int
    channels: int
    analyzed_duration_sec: float
    truncated: bool


@dataclass
class Summary:
    key: Optional[str]
    tempo_bpm: Optional[float]
    energy: Optional[str]
    mood: Optional[str]
    valence: Optional[float]
    arousal: Optional[float]
    tags: List[str] = field(default_factory=list)


@dataclass
class RhythmInfo:
    tempo_bpm: Optional[float]
    tempo_confidence: Optional[float]
    beat_count: int
    beat_regularity: Optional[float]
    onset_rate_per_sec: Optional[float]
    offbeat_energy_ratio: Optional[float]
    time_signature: Optional[str]


@dataclass
class TonalityInfo:
    key: Optional[str]
    mode: Optional[str]
    key_confidence: Optional[float]
    tuning_cents: Optional[float]
    chroma_profile: Optional[Dict[str, float]]


@dataclass
class DynamicsInfo:
    loudness_db: Optional[float]
    dynamic_range_db: Optional[float]
    peak_dbfs: Optional[float]
    silence_ratio: Optional[float]
    clipping_ratio: Optional[float]


@dataclass
class TimbreInfo:
    brightness: Optional[str]
    spectral_centroid_hz: Optional[float]
    spectral_rolloff_hz: Optional[float]
    spectral_flatness: Optional[float]
    zero_crossing_rate: Optional[float]
    harmonic_ratio: Optional[float]
    texture: Optional[str]


@dataclass
class MoodInfo:
    valence: Optional[float]
    arousal: Optional[float]
    label: Optional[str]
    confidence: Optional[float]
    model: str = "russell-circumplex-heuristic"


@dataclass
class SectionInfo:
    index: int
    label: str
    start_sec: float
    end_sec: float
    duration_sec: float
    energy: str
    energy_db: float


@dataclass
class StructureInfo:
    section_count: int
    sections: List[SectionInfo] = field(default_factory=list)


@dataclass
class QualityInfo:
    usable: bool
    flags: List[str] = field(default_factory=list)
    checks: Dict[str, bool] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    schema_version: str
    analysis_id: str
    created_at: str
    model: ModelInfo
    audio: AudioInfo
    summary: Summary
    rhythm: RhythmInfo
    tonality: TonalityInfo
    dynamics: DynamicsInfo
    timbre: TimbreInfo
    mood: MoodInfo
    structure: StructureInfo
    quality: QualityInfo
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _jsonable(asdict(self))

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def null_result(
    *,
    analysis_id: str,
    created_at: str,
    model: ModelInfo,
    audio: AudioInfo,
    warnings: List[str],
    quality: QualityInfo,
    metadata: Optional[Dict[str, Any]] = None,
) -> AnalysisResult:
    """构造“无法进行内容分析”时的合法结果（如静音、超短音频）。"""
    return AnalysisResult(
        schema_version=SCHEMA_VERSION,
        analysis_id=analysis_id,
        created_at=created_at,
        model=model,
        audio=audio,
        summary=Summary(None, None, None, None, None, None, []),
        rhythm=RhythmInfo(None, None, 0, None, None, None, None),
        tonality=TonalityInfo(None, None, None, None, None),
        dynamics=DynamicsInfo(None, None, None, None, None),
        timbre=TimbreInfo(None, None, None, None, None, None, None),
        mood=MoodInfo(None, None, None, None),
        structure=StructureInfo(0, []),
        quality=quality,
        warnings=warnings,
        metadata=metadata or {},
    )


def load_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    with open(path or SCHEMA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_result(result: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> List[str]:
    """按仓库内 JSON Schema 做轻量校验，返回错误列表（空列表表示通过）。

    只实现本项目 schema 用到的关键字，避免引入 jsonschema 依赖。
    """
    root = schema or load_schema()
    errors: List[str] = []
    _validate(result, root, root, "$", errors)
    return errors


def _resolve_ref(ref: str, root: Dict[str, Any]) -> Dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"仅支持本地 $ref: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _matches_type(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    return True


def _is_valid(value: Any, schema: Dict[str, Any], root: Dict[str, Any]) -> bool:
    trial: List[str] = []
    _validate(value, schema, root, "$", trial)
    return not trial


def _validate(value: Any, schema: Dict[str, Any], root: Dict[str, Any], path: str, errors: List[str]) -> None:
    if "$ref" in schema:
        _validate(value, _resolve_ref(schema["$ref"], root), root, path, errors)
        return

    if "anyOf" in schema:
        if not any(_is_valid(value, option, root) for option in schema["anyOf"]):
            errors.append(f"{path}: 不满足 anyOf 约束")
        return

    if "type" in schema:
        type_names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_matches_type(value, name) for name in type_names):
            errors.append(f"{path}: 类型应为 {type_names}，实际为 {type(value).__name__}")
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 值 {value!r} 应等于常量 {schema['const']!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 值 {value!r} 不在枚举 {schema['enum']} 中")

    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: 字符串长度 {len(value)} < minLength {schema['minLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")

    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: 缺少必填字段 {name!r}")
        for name, subschema in schema.get("properties", {}).items():
            if name in value:
                _validate(value[name], subschema, root, f"{path}.{name}", errors)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: 数组长度 {len(value)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: 数组长度 {len(value)} > maxItems {schema['maxItems']}")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(item, schema["items"], root, f"{path}[{index}]", errors)


def _jsonable(value: Any) -> Any:
    """把 numpy 标量/数组等转换为标准 JSON 类型，并清理 NaN/Inf。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    # numpy 标量 / 数组
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _jsonable(item())
        except (ValueError, TypeError):
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _jsonable(tolist())
    return value
