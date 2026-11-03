"""规则引擎自动出题：把 CNN 的多任务预测结果变成可直接入库的客观题.

设计原则
--------
* **纯规则、零外部依赖**：不调用任何 LLM；同一个 ``seed`` + 同一份预测
  一定得到同一份试卷，便于教师端复现和组卷。
* **置信度闸门**：情感/调式预测不够确定时宁可不给题，也不出“错题”。
  低于阈值时返回的条目会带上 ``当前音频不适合生成此类题目`` 的提示。
* **干扰项来自同类标签池**：永远排除正确答案；标签池不够时自动降级
  （调式只有大调/小调两类，题目自然是二选一，而不是硬凑四个选项）。

题目均为 JSON 可序列化的字典，字段说明
--------------------------------------
``id``         题目编号（q1、q2 …），同一份试卷内唯一
``type``       ``single_choice``（单选）或 ``true_false``（判断）
``topic``      ``mode`` / ``genre`` / ``emotion`` / ``bpm``
``stem``       题干
``options``    选项列表，每项 ``{"key": "A", "text": "大调"}``
``answer``     正确选项的 key
``answer_text`` 正确选项的文字
``confidence`` 该题所依赖预测的置信度（判断题取 BPM 置信度，可为 0）
``explanation`` 解析（教师端可开关）
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 一、标签映射：模型输出 ID -> 可读文字
# ---------------------------------------------------------------------------
# 顺序必须与 training/labels/taxonomy.json 中的 genres / emotions 完全一致；
# 如果重新训练时调整了类别顺序，这里也要同步修改。
GENRE_LABELS: Dict[int, str] = {
    0: "布鲁斯",
    1: "古典",
    2: "电子",
    3: "实验音乐",
    4: "民谣",
    5: "放克/灵魂",
    6: "嘻哈",
    7: "恐怖氛围",
    8: "爵士",
    9: "流行",
    10: "摇滚",
    11: "影视原声",
    12: "世界音乐",
}

EMOTION_LABELS: Dict[int, str] = {
    0: "平静",
    1: "欢快",
    2: "悲伤",
    3: "紧张",
}

MODE_LABELS: Dict[int, str] = {
    0: "大调",
    1: "小调",
}

# 英文名只用于把 infer/score 输出的字符串预测对齐回 ID，不用于展示。
GENRE_NAMES: Dict[int, str] = {
    0: "Blues",
    1: "Classical",
    2: "Electronic",
    3: "Experimental",
    4: "Folk",
    5: "Funk/Soul",
    6: "Hip-Hop",
    7: "Horror",
    8: "Jazz",
    9: "Pop",
    10: "Rock",
    11: "Soundtrack",
    12: "World",
}

EMOTION_NAMES: Dict[int, str] = {
    0: "calm",
    1: "happy",
    2: "sad",
    3: "tense",
}

MODE_NAMES: Dict[int, str] = {
    0: "major",
    1: "minor",
}

# 对外的统一映射表：LABEL_MAP["genre"][9] -> "流行"
LABEL_MAP: Dict[str, Dict[int, str]] = {
    "genre": GENRE_LABELS,
    "emotion": EMOTION_LABELS,
    "mode": MODE_LABELS,
}

LABEL_NAMES: Dict[str, Dict[int, str]] = {
    "genre": GENRE_NAMES,
    "emotion": EMOTION_NAMES,
    "mode": MODE_NAMES,
}

SKIP_MESSAGE = "当前音频不适合生成此类题目"

# BPM 判断题的合理区间；超出说明预测明显异常，直接不出题
MIN_PLAUSIBLE_BPM = 30.0
MAX_PLAUSIBLE_BPM = 300.0


def _build_aliases(labels: Dict[int, str], names: Dict[int, str]) -> Dict[str, int]:
    """把中文名、英文名（以及“放克/灵魂”这类复合名拆分）映射回标签 ID。"""
    aliases: Dict[str, int] = {}
    for index, name in names.items():
        aliases[str(name).strip().lower()] = index
    for index, text in labels.items():
        aliases[str(text).strip().lower()] = index
        for part in str(text).replace("（", "/").replace("）", "/").split("/"):
            part = part.strip().lower()
            if part:
                aliases.setdefault(part, index)
    return aliases


LABEL_ALIASES: Dict[str, Dict[str, int]] = {
    topic: _build_aliases(LABEL_MAP[topic], LABEL_NAMES[topic]) for topic in LABEL_MAP
}


# ---------------------------------------------------------------------------
# 二、模型输出归一化
# ---------------------------------------------------------------------------
@dataclass
class Prediction:
    """单个分类任务的归一化结果。"""

    label_id: Optional[int] = None
    confidence: float = 0.0
    probs: Optional[List[float]] = None


@dataclass
class NormalizedOutput:
    """一次推理结果的统一视图（分类三任务 + BPM 回归 + 综合分）。"""

    genre: Prediction
    emotion: Prediction
    mode: Prediction
    bpm: Optional[float]
    bpm_confidence: float
    score: Optional[float]


def _to_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _lookup_id(value: Any, topic: str) -> Optional[int]:
    """把整数 ID / 数字字符串 / 中英文标签名统一转成标签 ID。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value in LABEL_MAP[topic] else None
    if isinstance(value, float):
        return int(value) if float(value).is_integer() and int(value) in LABEL_MAP[topic] else None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            number = int(text)
            return number if number in LABEL_MAP[topic] else None
        return LABEL_ALIASES[topic].get(text.lower())
    return None


def _parse_probs(raw_probs: Any, topic: str) -> Optional[List[float]]:
    labels = LABEL_MAP[topic]
    if isinstance(raw_probs, Mapping):
        values = [0.0] * len(labels)
        for key, value in raw_probs.items():
            index = _lookup_id(key, topic)
            number = _to_float(value)
            if index is None or number is None:
                continue
            values[index] = number
        return values if any(values) else None
    if isinstance(raw_probs, Sequence) and not isinstance(raw_probs, (str, bytes)):
        values = [_to_float(item) or 0.0 for item in raw_probs]
        if len(values) != len(labels):
            return None
        return values
    return None


def _parse_topic(raw: Mapping[str, Any], topic: str) -> Prediction:
    """解析单个分类任务，兼容富信息 / 平铺 / infer 输出三种写法。"""
    entry = raw.get(topic)
    label_id: Optional[int] = None
    confidence: Optional[float] = None
    probs: Optional[List[float]] = None

    if isinstance(entry, Mapping):
        for key in ("id", "label_id", "index", "class_id"):
            if key in entry:
                label_id = _lookup_id(entry[key], topic)
                break
        if label_id is None:
            for key in ("name", "label", "text"):
                if key in entry:
                    label_id = _lookup_id(entry[key], topic)
                    break
        for key in ("confidence", "prob", "probability", "score"):
            if key in entry:
                confidence = _to_float(entry[key])
                if confidence is not None:
                    break
        for key in ("probs", "probabilities", "distribution"):
            if key in entry:
                probs = _parse_probs(entry[key], topic)
                break
        # training/infer.py 直接返回 {"Blues": 0.01, ..., "Pop": 0.81}
        if probs is None and label_id is None:
            probs = _parse_probs(entry, topic)
    else:
        label_id = _lookup_id(entry, topic)

    # 平铺写法 / infer 输出：genre_confidence、genre_probs
    if confidence is None:
        confidence = _to_float(raw.get(f"{topic}_confidence"))
    if probs is None:
        probs = _parse_probs(raw.get(f"{topic}_probs"), topic)

    if probs is not None:
        if label_id is None:
            label_id = max(range(len(probs)), key=lambda index: probs[index])
        if confidence is None:
            confidence = probs[label_id]

    return Prediction(label_id=label_id, confidence=float(confidence or 0.0), probs=probs)


def _parse_scalar(value: Any, keys: Sequence[str]) -> Tuple[Optional[float], Optional[float]]:
    """解析 BPM / score 这类回归输出，返回 (数值, 置信度)。"""
    if isinstance(value, Mapping):
        number = None
        for key in keys:
            if key in value:
                number = _to_float(value[key])
                if number is not None:
                    break
        return number, _to_float(value.get("confidence"))
    return _to_float(value), None


def normalize_model_output(model_output: Mapping[str, Any]) -> NormalizedOutput:
    """把不同写法的模型输出统一成 :class:`NormalizedOutput`。

    支持三种输入（可混用）::

        # 1. 富信息写法
        {"genre": {"id": 9, "confidence": 0.81}, ...}

        # 2. 平铺写法
        {"genre": 9, "genre_confidence": 0.81, ...}

        # 3. training/infer.py 的真实输出
        {"genre": "Pop", "genre_probs": {"Pop": 0.81, ...},
         "genre_confidence": 0.81, ...}
    """
    if not isinstance(model_output, Mapping):
        raise TypeError("model_output 必须是字典")

    bpm, bpm_confidence = _parse_scalar(
        model_output.get("bpm"), ("bpm", "value", "tempo_bpm")
    )
    score, _ = _parse_scalar(model_output.get("score"), ("total", "score", "value"))

    return NormalizedOutput(
        genre=_parse_topic(model_output, "genre"),
        emotion=_parse_topic(model_output, "emotion"),
        mode=_parse_topic(model_output, "mode"),
        bpm=bpm,
        bpm_confidence=float(bpm_confidence or 0.0),
        score=score,
    )


# ---------------------------------------------------------------------------
# 三、出题配置与干扰项
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class QuizConfig:
    """出题策略。阈值按“严格大于”判断，等于阈值也会被拦截。"""

    emotion_min_confidence: float = 0.6  # 情感头准确率低，要求 > 0.6
    mode_min_confidence: float = 0.5  # 调式 > 0.5
    genre_min_confidence: float = 0.0  # 需求未规定；需要更严可调高
    bpm_min_confidence: float = 0.0  # 0 表示不按置信度过滤 BPM
    bpm_range: Tuple[float, float] = (90.0, 120.0)  # 判断题的区间
    bpm_boundary_margin: float = 2.0  # 距离区间边界小于该值时不出题
    distractor_count: int = 3  # 干扰项数量；标签池不足时自动减少
    option_keys: Tuple[str, ...] = ("A", "B", "C", "D")


def pick_distractors(
    correct_id: int,
    label_map: Mapping[int, str],
    count: int = 3,
    rng: Optional[random.Random] = None,
) -> List[int]:
    """从同类别标签池中随机抽取 ``count`` 个错误标签（排除正确答案）。

    标签池不足以凑满 ``count`` 时返回全部剩余标签，调用方据此生成
    二选一/三选一题目，而不是重复或编造选项。
    """
    rng = rng or random.Random()
    pool = [label_id for label_id in label_map if label_id != correct_id]
    if count >= len(pool):
        return list(pool)
    return rng.sample(pool, count)


def build_single_choice(
    topic: str,
    correct_id: int,
    stem: str,
    confidence: float,
    config: QuizConfig,
    rng: random.Random,
) -> Dict[str, Any]:
    """组装一道单选题：正确答案 + 干扰项，打乱顺序后编号 A/B/C/D。"""
    labels = LABEL_MAP[topic]
    option_ids = [correct_id] + pick_distractors(
        correct_id, labels, config.distractor_count, rng
    )
    rng.shuffle(option_ids)

    options = [
        {"key": config.option_keys[index], "text": labels[label_id]}
        for index, label_id in enumerate(option_ids)
    ]
    answer_index = option_ids.index(correct_id)
    answer_key = config.option_keys[answer_index]

    return {
        "type": "single_choice",
        "topic": topic,
        "stem": stem,
        "options": options,
        "answer": answer_key,
        "answer_text": labels[correct_id],
        "confidence": round(float(confidence), 4),
        "explanation": f"模型判断为{labels[correct_id]}（置信度 {confidence:.0%}）。",
    }


def _skip(topic: str, reason: str) -> Dict[str, Any]:
    """低于阈值/数据缺失时的占位条目，前端可直接展示提示语。"""
    return {
        "type": "skipped",
        "topic": topic,
        "message": SKIP_MESSAGE,
        "reason": reason,
    }


def describe_score(score: Optional[float]) -> Optional[str]:
    """把综合分映射成教师端可读的等级（仅用于展示，不单独出题）。"""
    if score is None:
        return None
    if score >= 85:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "合格"
    return "待改进"


# ---------------------------------------------------------------------------
# 四、模板组装器
# ---------------------------------------------------------------------------
def generate_questions(
    model_output: Mapping[str, Any],
    *,
    config: Optional[QuizConfig] = None,
    seed: Optional[int] = None,
    topics: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """根据一次模型预测生成题目列表。

    参数
    ----
    model_output:
        模型预测字典，支持 :func:`normalize_model_output` 中的三种写法。
    config:
        出题策略，默认 :class:`QuizConfig`（情感 > 0.6、调式 > 0.5）。
    seed:
        随机种子；传入相同 seed 可复现同一份选项顺序。
    topics:
        只生成指定题型，可选 ``"mode"`` / ``"genre"`` / ``"emotion"`` /
        ``"bpm"``；默认四种都生成。

    返回
    ----
    ``{"questions": [...], "skipped": [...], "meta": {...}}``，
    其中 ``skipped`` 的条目就是“当前音频不适合生成此类题目”的提示。
    """
    config = config or QuizConfig()
    rng = random.Random(seed) if seed is not None else random.Random()
    output = normalize_model_output(model_output)
    wanted = set(topics) if topics else {"mode", "genre", "emotion", "bpm"}

    questions: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    def emit_choice(topic: str, prediction: Prediction, stem: str, minimum: float) -> None:
        if prediction.label_id is None:
            skipped.append(_skip(topic, "模型未给出可用的标签"))
            return
        if prediction.confidence <= minimum:
            skipped.append(
                _skip(
                    topic,
                    f"置信度 {prediction.confidence:.2f} 未超过阈值 {minimum:.2f}",
                )
            )
            return
        questions.append(
            build_single_choice(
                topic, prediction.label_id, stem, prediction.confidence, config, rng
            )
        )

    # 题型 1：听辨调式
    if "mode" in wanted:
        emit_choice(
            "mode",
            output.mode,
            "请听音频，判断这段音乐的调式是？",
            config.mode_min_confidence,
        )

    # 题型 2：听辨流派
    if "genre" in wanted:
        emit_choice(
            "genre",
            output.genre,
            "请听音频，判断这段音乐属于哪种流派？",
            config.genre_min_confidence,
        )

    # 题型 2.5：听辨情绪（需求未列入三种题型，但情感阈值只有在能出情绪
    # 题时才有意义，因此默认开启；只想出调式/流派/BPM 时传 topics 排除）
    if "emotion" in wanted:
        emit_choice(
            "emotion",
            output.emotion,
            "请听音频，判断这段音乐的情绪是？",
            config.emotion_min_confidence,
        )

    # 题型 3：判断 BPM 速度范围（陈述句 + 正确/错误）
    if "bpm" in wanted:
        value = output.bpm
        low, high = config.bpm_range
        if value is None:
            skipped.append(_skip("bpm", "模型未给出 BPM 预测"))
        elif not (MIN_PLAUSIBLE_BPM <= value <= MAX_PLAUSIBLE_BPM):
            skipped.append(_skip("bpm", f"BPM {value:.1f} 超出合理范围"))
        elif 0.0 < output.bpm_confidence <= config.bpm_min_confidence:
            skipped.append(
                _skip(
                    "bpm",
                    f"BPM 置信度 {output.bpm_confidence:.2f} 未超过阈值 "
                    f"{config.bpm_min_confidence:.2f}",
                )
            )
        elif (
            abs(value - low) < config.bpm_boundary_margin
            or abs(value - high) < config.bpm_boundary_margin
        ):
            # 贴着 90/120 的边界时，“大约在区间内”本身就有歧义，不出题
            skipped.append(_skip("bpm", f"BPM {value:.1f} 接近区间边界，易产生歧义"))
        else:
            in_range = low <= value <= high
            questions.append(
                {
                    "type": "true_false",
                    "topic": "bpm",
                    "stem": f"这段音乐的速度大约在 {low:g}-{high:g} BPM 之间。",
                    "options": [
                        {"key": "A", "text": "正确"},
                        {"key": "B", "text": "错误"},
                    ],
                    "answer": "A" if in_range else "B",
                    "answer_text": "正确" if in_range else "错误",
                    "confidence": round(float(output.bpm_confidence), 4),
                    "explanation": (
                        f"模型估计速度为 {value:.1f} BPM，"
                        f"{'落在' if in_range else '不在'} {low:g}-{high:g} BPM "
                        f"区间内，因此该说法{'正确' if in_range else '错误'}。"
                    ),
                }
            )

    # 统一编号，保证同一份试卷内唯一且顺序稳定
    for index, question in enumerate(questions, 1):
        question["id"] = f"q{index}"

    return {
        "questions": questions,
        "skipped": skipped,
        "meta": {
            "question_count": len(questions),
            "bpm": output.bpm,
            "score": output.score,
            "score_level": describe_score(output.score),
        },
    }


def generate_questions_json(
    model_output: Mapping[str, Any],
    *,
    config: Optional[QuizConfig] = None,
    seed: Optional[int] = None,
    topics: Optional[Sequence[str]] = None,
    indent: Optional[int] = 2,
) -> str:
    """与 :func:`generate_questions` 相同，但直接返回 JSON 字符串。"""
    payload = generate_questions(model_output, config=config, seed=seed, topics=topics)
    return json.dumps(payload, ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# 五、本地自测
# ---------------------------------------------------------------------------
# 模拟模型输出：高置信度、全部题目都能生成
MOCK_MODEL_OUTPUT: Dict[str, Any] = {
    "genre": {"id": 9, "confidence": 0.81},
    "emotion": {"id": 1, "confidence": 0.72},
    "mode": {"id": 0, "confidence": 0.66},
    "bpm": 104.3,
    "score": 78.5,
}

# 低置信度版本：情感 0.42、调式 0.41，两种选择题都应被拦下
MOCK_LOW_CONFIDENCE: Dict[str, Any] = {
    "genre": "Electronic",
    "genre_probs": {"Electronic": 0.45, "Rock": 0.3, "Pop": 0.25},
    "emotion": "sad",
    "emotion_confidence": 0.42,
    "mode": "minor",
    "mode_confidence": 0.41,
    "bpm": 126.0,
    "score": 58.0,
}


if __name__ == "__main__":
    print("=" * 60)
    print("示例 1：高置信度预测")
    print("=" * 60)
    print(generate_questions_json(MOCK_MODEL_OUTPUT, seed=42))

    print()
    print("=" * 60)
    print("示例 2：低置信度预测（情感/调式被阈值拦截）")
    print("=" * 60)
    print(generate_questions_json(MOCK_LOW_CONFIDENCE, seed=42))
