"""Model B（美术出题模型）接入层。

职责边界：
* 只读取模型服务的 ``/health``、``/catalog``、``/generate``；
* 不调用模型的 ``/paper``、``/grade``，组卷与判分仍由现有业务负责；
* 生成/导入的题目一律以 ``pending`` 入库，不自动通过审核；
* 默认只接受单选、判断，填空题和简答题按现有产品规则丢弃。

模型服务不可用时全部降级：导入命令离线可用（只读 jsonl），在线生成返回 503。
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction

from common.enums import (
    FileCategory,
    QuestionStatus,
    QuestionType,
    ResourceType,
    Role,
    ScoringMode,
)
from common.exceptions import BusinessError

from .models import Chapter, Course, Question, QuestionOption, QuestionResource
from .stem_cleaner import clean_stem

PROVIDER = "model_b_qgen"
API_PROVIDER = "qgen_api"
DEFAULT_ALLOWED_TYPES = {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE}
DEFAULT_SCORES = {
    QuestionType.SINGLE_CHOICE: Decimal("5"),
    QuestionType.TRUE_FALSE: Decimal("2"),
}
DIFFICULTY_MAP = {1: 1, 2: 2, 3: 3}
QUESTION_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_QUESTION_IMAGES = 5

IMAGE_REFERENCE_PATTERN = re.compile(
    r"(下图|如图|图中|这幅|这幅画|以下画作|下列画作|第[一二三四五六七八九十\d]+幅|看图)"
)
SCORING_TALK_PATTERN = re.compile(
    r"(给满分|给主要分|给部分分|即可得分|酌情给分|按点给分|答对即可|视情况给分)"
)


class QgenSkip(Exception):
    """题目在转换/校验阶段被跳过，message 为可统计的原因码。"""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}:{detail}" if detail else reason)


@dataclass
class PreparedQuestion:
    course: Course
    chapter: Chapter
    grade: int
    type: str
    difficulty: int
    stem: str
    options: list[dict]
    answer: dict
    analysis: str
    score: Decimal
    knowledge_point: str
    source_meta: dict
    resources: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- 配置


def qgen_enabled() -> bool:
    return bool(getattr(settings, "QGEN_ENABLED", False))


def qgen_provider() -> str:
    value = str(getattr(settings, "QGEN_PROVIDER", "model_b") or "model_b").strip().lower()
    return value if value in {"model_b", "api"} else "model_b"


def allowed_types() -> set[str]:
    configured = getattr(settings, "QGEN_ALLOWED_TYPES", None)
    if not configured:
        return set(DEFAULT_ALLOWED_TYPES)
    result = set()
    for item in configured:
        if item in {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE}:
            result.add(item)
    return result or set(DEFAULT_ALLOWED_TYPES)


def with_image_enabled() -> bool:
    """是否向模型请求图题；服务没有同题型素材时会自动退回文字题。"""
    return bool(getattr(settings, "QGEN_WITH_IMAGE", True))


def _resource_url_base() -> str:
    return str(getattr(settings, "QGEN_RESOURCE_URL_BASE", "/resources") or "/resources").rstrip("/")


def pick_question_images(
    response_resources: list | None, card_resources: list | None
) -> list[dict]:
    """提取 role=question 的配图。

    服务返回的 ``resources`` 带 role，优先使用；题卡内的 ``resources`` 没有 role，
    按图题规则视为题干配图兜底。``role=reference`` 是教学参考图，不是题干配图，
    不入库、不展示。
    """
    for source in (response_resources or [], card_resources or []):
        images: list[dict] = []
        for item in source:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "image").strip().lower() != "image":
                continue
            if str(item.get("role") or "question").strip().lower() != "question":
                continue
            file = str(item.get("file") or "").strip().lstrip("/")
            if not file or ".." in Path(file).parts:
                continue
            if Path(file).suffix.lower() not in QUESTION_IMAGE_EXTS:
                continue
            image = {
                "file": file,
                "name": str(item.get("name") or Path(file).name).strip()[:100],
                "url": str(item.get("url") or "").strip(),
            }
            if image not in images:
                images.append(image)
        if images:
            return images[:MAX_QUESTION_IMAGES]
    return []


def unit_map_path() -> Path:
    configured = getattr(settings, "QGEN_UNIT_MAP_PATH", "")
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "apps" / "qbank" / "qgen_unit_map.json"


def default_bank_path() -> Path:
    configured = getattr(settings, "QGEN_BANK_PATH", "")
    if configured:
        return Path(configured)
    return Path(settings.PROJECT_ROOT) / "01_给后端A(1)" / "题库数据" / "train_clean_2698.jsonl"


def load_unit_map() -> dict[str, dict]:
    path = unit_map_path()
    if not path.exists():
        raise BusinessError(500, f"美术出题单元映射文件不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessError(500, f"美术出题单元映射文件无法读取：{exc}") from exc
    units = {}
    for item in payload.get("units", []):
        unit_id = item.get("unitId")
        if unit_id:
            units[unit_id] = item
    return units


# --------------------------------------------------------------------------- HTTP


def _http_json(method: str, path: str, payload: dict | None = None) -> dict:
    url = getattr(settings, "QGEN_URL", "http://127.0.0.1:8002").rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    token = getattr(settings, "QGEN_TOKEN", "")
    if token:
        headers["X-QGEN-TOKEN"] = token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            request, timeout=int(getattr(settings, "QGEN_TIMEOUT", 90))
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise BusinessError(502, f"美术出题服务返回错误：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BusinessError(
            503, "美术出题服务未启动或无法连接，请先启动 8002 服务"
        ) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BusinessError(502, "美术出题服务返回了非 JSON 内容") from exc


def service_health() -> dict:
    return _http_json("GET", "/health")


# --------------------------------------------------------------------------- 云 API

TYPE_LABELS = {
    QuestionType.SINGLE_CHOICE: "单选题",
    QuestionType.TRUE_FALSE: "判断题",
}

API_SYSTEM_PROMPT = """你是一名中小学美术出题老师，熟悉《义务教育艺术课程标准（2022年版）》。
根据给定的年级、单元、知识点、题型和难度，生成一道可以直接入库的美术题。

必须遵守：
1. 只输出一个 JSON 对象，不要输出解释、Markdown、代码块或多余文字。
2. 题干、选项、答案、解析全部使用简体中文。
3. 答案必须正确；不确定的画家、作品、年代不要编造。
4. 题目必须落在指定知识点上，不能超纲，也不能问其他单元的内容。
5. 单选题固定 4 个选项，只有一个正确答案；判断题答案只能是 true 或 false。
6. 解析必须说明为什么，不能只重复答案；不得写评分标准或得分话术。
7. 只输出这些字段：stem、options（仅单选题）、answer、analysis、score。
8. 题干必须自足，不能依赖图片；不得出现“下图、如图、图中、图片、附图、插图、
   几幅、第几幅、哪一幅、以下作品”等需要看图才能作答的表述。
9. 色彩知识按中小学教材口径：绘画三原色是红、黄、蓝；互补色为红—绿、
   蓝—橙、黄—紫。"""


def _api_configured() -> bool:
    return bool(
        getattr(settings, "QGEN_API_BASE", "")
        and getattr(settings, "QGEN_API_KEY", "")
        and getattr(settings, "QGEN_API_MODEL", "")
    )


def _api_messages(entry: dict, knowledge_point: str, card_type: str, difficulty: int) -> list[dict]:
    grade = int(entry["grade"])
    label = TYPE_LABELS.get(card_type, card_type)
    if card_type == QuestionType.SINGLE_CHOICE:
        rule = (
            'options 必须是 4 项，key 依次为 A、B、C、D，只有一个正确答案；'
            'answer 写成 {"value": "A"}。'
        )
        example = (
            '{"stem": "...", "options": [{"key": "A", "text": "..."}, '
            '{"key": "B", "text": "..."}, {"key": "C", "text": "..."}, '
            '{"key": "D", "text": "..."}], "answer": {"value": "A"}, '
            '"analysis": "...", "score": 5}'
        )
    else:
        rule = '不要输出 options；answer 写成 {"value": true} 或 {"value": false}。'
        example = (
            '{"stem": "...", "answer": {"value": true}, '
            '"analysis": "...", "score": 2}'
        )
    user = (
        f"年级：{grade}\n"
        f"单元：{entry.get('unitName') or entry.get('unitId')}\n"
        f"知识点：{knowledge_point}\n"
        f"题型：{label}（{card_type}）\n"
        f"难度：{difficulty}（1 最易，3 最难）\n\n"
        f"要求：{rule}\n"
        "示例格式（仅示意，不要照抄内容）：\n"
        f"{example}\n\n"
        "请生成 1 道新题，只输出 JSON。"
    )
    return [
        {"role": "system", "content": API_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _api_chat(messages: list[dict]) -> str:
    base = str(getattr(settings, "QGEN_API_BASE", "")).rstrip("/")
    key = str(getattr(settings, "QGEN_API_KEY", ""))
    model = str(getattr(settings, "QGEN_API_MODEL", ""))
    if not (base and key and model):
        raise BusinessError(
            503,
            "AI 出题接口未配置（QGEN_PROVIDER=api 时需要 QGEN_API_BASE、"
            "QGEN_API_KEY、QGEN_API_MODEL）",
        )
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(getattr(settings, "QGEN_API_TEMPERATURE", 0.7)),
        "stream": False,
    }
    request = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=int(getattr(settings, "QGEN_API_TIMEOUT", 60))
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise BusinessError(502, f"AI 出题接口返回错误：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BusinessError(
            503, "AI 出题接口无法连接，请检查网络和 QGEN_API_BASE"
        ) from exc
    try:
        data = json.loads(body)
        return str(data["choices"][0]["message"]["content"])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise BusinessError(502, "AI 出题接口返回格式不正确") from exc


def _extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[A-Za-z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise BusinessError(502, "AI 接口未返回 JSON 题卡")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BusinessError(502, "AI 接口返回的 JSON 无法解析") from exc
    if not isinstance(data, dict):
        raise BusinessError(502, "AI 接口返回的题卡格式不正确")
    return data


def _generate_via_api(entry: dict, unit_id: str, knowledge_point: str, card_type: str, difficulty: int) -> dict:
    content = _api_chat(_api_messages(entry, knowledge_point, card_type, difficulty))
    card = _extract_json_object(content)
    # 年级、单元、知识点、题型、难度由系统回填，避免模型改写请求参数。
    card.update(
        {
            "subject": "art",
            "grade": int(entry["grade"]),
            "unit_id": unit_id,
            "unit_name": entry.get("unitName"),
            "knowledge_point": knowledge_point,
            "type": card_type,
            "difficulty": difficulty,
            "source": "cloud_api",
            "created_by": f"api:{getattr(settings, 'QGEN_API_MODEL', '')}",
        }
    )
    return {
        "ok": True,
        "card": card,
        "parse_ok": True,
        "errors": [],
        "request": {
            "unit_id": unit_id,
            "knowledge_point": knowledge_point,
            "type": card_type,
            "difficulty": difficulty,
        },
        "provider": API_PROVIDER,
    }


# --------------------------------------------------------------------------- 目录


def _resolve_catalog(entry: dict) -> tuple[Course, Chapter]:
    course = (
        Course.objects.filter(
            subject="art", grade=entry["grade"], deleted_at__isnull=True
        )
        .order_by("id")
        .first()
    )
    if course is None:
        raise QgenSkip("course_missing", f"grade={entry['grade']}")
    chapter = course.chapters.filter(
        name=entry["chapter"], deleted_at__isnull=True
    ).first()
    if chapter is None:
        raise QgenSkip("chapter_missing", f"{entry['grade']}/{entry['chapter']}")
    return course, chapter


def catalog_for_client() -> dict:
    """返回已映射到系统课程/章节的下拉目录，不依赖模型服务。"""
    units = load_unit_map()
    grades: dict[int, list[dict]] = defaultdict(list)
    missing: list[dict] = []
    for unit_id, entry in units.items():
        try:
            course, chapter = _resolve_catalog(entry)
        except QgenSkip as exc:
            missing.append({"unitId": unit_id, "reason": exc.reason})
            continue
        grades[entry["grade"]].append(
            {
                "unitId": unit_id,
                "unitName": entry.get("unitName") or unit_id,
                "courseId": course.id,
                "courseName": course.name,
                "chapterId": chapter.id,
                "chapterName": chapter.name,
                "knowledgePoints": entry.get("knowledgePoints", []),
                "allowedTypes": [
                    item
                    for item in entry.get("allowedTypes", [])
                    if item in allowed_types()
                ],
                "difficultyRange": entry.get("difficultyRange", [1, 3]),
            }
        )
    api_mode = qgen_provider() == "api"
    return {
        "provider": API_PROVIDER if api_mode else PROVIDER,
        "enabled": qgen_enabled(),
        "withImage": with_image_enabled() and not api_mode,
        "allowedTypes": sorted(allowed_types()),
        "modelNote": (
            "题目由外部 AI 接口生成，仅作为待审草稿，必须由题库管理员逐条审核后才能使用。"
            if api_mode
            else "AI 生成的题目仅作为待审草稿，必须由题库管理员逐条审核后才能使用。"
        ),
        "grades": [
            {"grade": grade, "units": sorted(items, key=lambda x: x["unitId"])}
            for grade, items in sorted(grades.items())
        ],
        "missingMappings": missing,
    }


# --------------------------------------------------------------------------- 转换


def normalize_stem(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text), flags=re.UNICODE).lower()


def trigrams(text: str) -> frozenset[str]:
    if len(text) <= 3:
        return frozenset({text}) if text else frozenset()
    return frozenset(text[i : i + 3] for i in range(len(text) - 2))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _validate_options(card: dict) -> list[dict]:
    raw = card.get("options") or []
    if not isinstance(raw, list):
        raise QgenSkip("invalid_options")
    options = []
    keys = set()
    for item in raw:
        key = str(item.get("key") or "").strip()
        text = str(item.get("text") or "").strip()
        if not key or not text or key in keys:
            raise QgenSkip("invalid_options")
        keys.add(key)
        options.append({"key": key, "text": text})
    if len(options) < 2:
        raise QgenSkip("invalid_options")
    return options


def _validate_answer(card_type: str, answer: dict, options: list[dict]) -> dict:
    if not isinstance(answer, dict):
        raise QgenSkip("invalid_answer")
    if card_type == QuestionType.SINGLE_CHOICE:
        value = str(answer.get("value") or "").strip().upper()
        keys = {item["key"].upper() for item in options}
        if value not in keys:
            raise QgenSkip("invalid_answer")
        return {"value": value}
    if card_type == QuestionType.TRUE_FALSE:
        value = answer.get("value")
        if not isinstance(value, bool):
            raise QgenSkip("invalid_answer")
        return {"value": value}
    if card_type == QuestionType.FILL_BLANK:
        values = answer.get("values")
        if (
            not isinstance(values, list)
            or not values
            or any(not str(item).strip() for item in values)
        ):
            raise QgenSkip("invalid_answer")
        return {"values": [str(item).strip() for item in values]}
    raise QgenSkip("unsupported_type")


def prepare_card(
    card: dict,
    entry: dict | None = None,
    *,
    allow_fill_blank: bool = False,
    provider: str = PROVIDER,
    resources: list[dict] | None = None,
    fact_ids: list | None = None,
    generated_by: str | None = None,
) -> PreparedQuestion:
    """把 Model B 题卡转换成系统 Question 字段；不合法时抛 QgenSkip。"""
    if card.get("subject") != "art":
        raise QgenSkip("not_art")
    unit_id = card.get("unit_id") or (entry or {}).get("unitId")
    entry = entry or load_unit_map().get(unit_id)
    if entry is None:
        raise QgenSkip("unit_not_mapped", str(unit_id))
    try:
        grade = int(card.get("grade"))
    except (TypeError, ValueError):
        raise QgenSkip("invalid_grade")
    if grade != int(entry["grade"]):
        raise QgenSkip("grade_mismatch")

    card_type = str(card.get("type") or "")
    permitted = set(allowed_types())
    if card_type == QuestionType.FILL_BLANK and allow_fill_blank:
        permitted.add(QuestionType.FILL_BLANK)
    if card_type not in permitted:
        raise QgenSkip("type_filtered", card_type)

    try:
        difficulty = DIFFICULTY_MAP[int(card.get("difficulty", 1))]
    except (KeyError, TypeError, ValueError):
        raise QgenSkip("invalid_difficulty")

    course, chapter = _resolve_catalog(entry)

    stem = clean_stem(str(card.get("stem") or "")).strip()
    if not stem:
        raise QgenSkip("empty_stem")
    if len(stem) > 5000:
        raise QgenSkip("stem_too_long")
    options = _validate_options(card) if card_type == QuestionType.SINGLE_CHOICE else []
    question_images = pick_question_images(resources, card.get("resources"))
    # 题干依赖图片（“下图/如图/第几幅”等）时必须有题干配图；只有 reference
    # 参考图不算，避免出现学生看不到图的残题。
    if not question_images and (
        IMAGE_REFERENCE_PATTERN.search(stem)
        or any(IMAGE_REFERENCE_PATTERN.search(item["text"]) for item in options)
    ):
        raise QgenSkip("image_dependent")
    answer = _validate_answer(card_type, card.get("answer") or {}, options)

    analysis = str(card.get("analysis") or "").strip()
    if SCORING_TALK_PATTERN.search(analysis):
        raise QgenSkip("scoring_talk")
    analysis = analysis[:5000]

    knowledge_point = str(
        card.get("knowledge_point") or (entry or {}).get("unitName") or ""
    ).strip()[:128]
    source_meta = {
        "provider": provider,
        "rawId": card.get("id"),
        "source": card.get("source"),
        "createdBy": card.get("created_by"),
        "unitId": unit_id,
        "unitName": entry.get("unitName"),
        "knowledgePoint": knowledge_point,
        "difficulty": card.get("difficulty"),
        "originalScore": card.get("score"),
        "generatedBy": generated_by or card.get("generated_by"),
        "factIds": [
            str(item)
            for item in (fact_ids if fact_ids is not None else card.get("fact_ids") or [])
            if str(item).strip()
        ][:20],
        "resources": [
            {"file": item["file"], "name": item["name"], "role": "question"}
            for item in question_images
        ],
        "cardHash": hashlib.sha256(
            json.dumps(card, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
    }
    if card.get("notes"):
        source_meta["notes"] = str(card["notes"])[:500]
    return PreparedQuestion(
        course=course,
        chapter=chapter,
        grade=grade,
        type=card_type,
        difficulty=difficulty,
        stem=stem,
        options=options,
        answer=answer,
        analysis=analysis,
        score=DEFAULT_SCORES.get(card_type, Decimal("5")),
        knowledge_point=knowledge_point,
        source_meta=source_meta,
        resources=question_images,
    )


def _resolve_resource_url(resource: dict) -> str:
    """把服务返回的相对 URL 解析到 8002；拒绝指向其他主机的绝对 URL。"""
    raw = str(resource.get("url") or "").strip()
    if not raw:
        raw = f"{_resource_url_base()}/{resource['file']}"
    service = str(getattr(settings, "QGEN_URL", "")).rstrip("/")
    if raw.startswith(("http://", "https://")):
        allowed = [f"{service}/"] if service else []
        base = _resource_url_base()
        if base.startswith(("http://", "https://")):
            allowed.append(f"{base}/")
        if not any(raw.startswith(prefix) for prefix in allowed):
            raise QgenSkip("invalid_resource_url", raw[:120])
        return raw
    if not service:
        raise QgenSkip("invalid_resource_url", raw[:120])
    return f"{service}/{raw.lstrip('/')}"


def _download_image(url: str) -> tuple[bytes, str]:
    timeout = int(getattr(settings, "QGEN_RESOURCE_TIMEOUT", 30))
    max_bytes = int(getattr(settings, "QGEN_RESOURCE_MAX_BYTES", 10 * 1024 * 1024))
    request = urllib.request.Request(url, headers={"Accept": "image/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            mime = (
                (response.headers.get("Content-Type") or "")
                .split(";")[0]
                .strip()
                .lower()
            )
            content = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise BusinessError(
            502, f"题目配图下载失败（HTTP {exc.code}），请检查模型服务的图片资源"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BusinessError(
            503, "题目配图下载失败，请检查 8002 服务是否可访问"
        ) from exc
    if len(content) > max_bytes:
        raise BusinessError(502, "题目配图超过大小限制，已中止入库")
    if not mime.startswith("image/"):
        raise BusinessError(502, f"题目配图类型不正确：{mime or 'unknown'}")
    return content, mime


def _prepare_image_blobs(prepared: PreparedQuestion) -> list[tuple[str, bytes, str]]:
    """先下载全部配图再入库，避免下载失败留下半张图题。"""
    blobs = []
    for resource in prepared.resources:
        try:
            url = _resolve_resource_url(resource)
        except QgenSkip as exc:
            raise BusinessError(502, f"题目配图地址不合法：{exc.detail}") from exc
        content, mime = _download_image(url)
        # 保留模型给的展示名（如“均衡构图”），扩展名仍取自原始 file。
        suffix = Path(resource["file"]).suffix.lower()
        display = Path(str(resource.get("name") or Path(resource["file"]).stem)).name
        blobs.append((f"{display[:100]}{suffix}", content, mime))
    return blobs


def create_pending_question(prepared: PreparedQuestion, actor, request=None) -> Question:
    from apps.files.services import save_generated

    from .services import log_action

    image_blobs = _prepare_image_blobs(prepared)
    with transaction.atomic():
        question = Question.objects.create(
            subject="art",
            grade=prepared.grade,
            course=prepared.course,
            chapter=prepared.chapter,
            type=prepared.type,
            difficulty=prepared.difficulty,
            stem=prepared.stem,
            score=prepared.score,
            answer=prepared.answer,
            analysis=prepared.analysis,
            knowledge_point=prepared.knowledge_point,
            source_meta=prepared.source_meta,
            scoring_mode=ScoringMode.AUTO,
            status=QuestionStatus.PENDING,
            creator=actor,
        )
        for index, item in enumerate(prepared.options):
            QuestionOption.objects.create(
                question=question, key=item["key"], text=item["text"], sort_order=index
            )
        for index, (name, content, mime) in enumerate(image_blobs):
            try:
                file_obj = save_generated(
                    name,
                    content,
                    FileCategory.QUESTION_IMAGE,
                    uploader=actor,
                    mime_type=mime,
                    biz_id=question.id,
                    subject="art",
                )
            except BusinessError as exc:
                raise BusinessError(502, f"题目配图无法保存：{exc.message}") from exc
            QuestionResource.objects.create(
                question=question,
                file=file_obj,
                type=ResourceType.IMAGE,
                sort_order=index,
            )
    log_action(
        actor,
        "question.qgen_create",
        "question",
        question.id,
        f"AI 生成待审题 {question.id}（{prepared.type}，{prepared.knowledge_point}）",
        request,
    )
    return question


# --------------------------------------------------------------------------- 查重


def build_stem_index() -> dict[int, list[tuple[int | None, str, frozenset[str], int]]]:
    index: dict[int, list[tuple[int | None, str, frozenset[str], int]]] = defaultdict(list)
    rows = Question.objects.filter(
        deleted_at__isnull=True, subject="art"
    ).values_list("id", "grade", "stem")
    for question_id, grade, stem in rows:
        normalized = normalize_stem(stem)
        index[grade].append((question_id, normalized, trigrams(normalized), len(normalized)))
    return index


def find_duplicate(
    normalized: str,
    grade: int,
    index: dict[int, list[tuple[int | None, str, frozenset[str], int]]],
    threshold: float = 0.9,
) -> tuple[str, int | None] | None:
    if not normalized:
        return None
    grams = trigrams(normalized)
    length = len(normalized)
    for question_id, existing, existing_grams, existing_length in index.get(grade, []):
        if existing == normalized:
            return "duplicate", question_id
        if not existing_length or not length:
            continue
        ratio = min(length, existing_length) / max(length, existing_length)
        if ratio < 0.6:
            continue
        if _jaccard(grams, existing_grams) >= threshold:
            return "near_duplicate", question_id
    return None


# --------------------------------------------------------------------------- 导入


def import_cards(
    path: str | Path,
    actor=None,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    grade: int | None = None,
    allow_fill_blank: bool = False,
    near_duplicate_threshold: float = 0.9,
) -> dict:
    path = Path(path)
    if not path.exists():
        raise BusinessError(404, f"题卡文件不存在：{path}")
    units = load_unit_map()
    index = build_stem_index()

    report = {
        "path": str(path),
        "dryRun": dry_run,
        "read": 0,
        "created": 0,
        "skipped": defaultdict(int),
        "errors": [],
        "createdIds": [],
    }
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        if limit is not None and report["read"] >= limit:
            break
        report["read"] += 1
        try:
            card = json.loads(line)
        except json.JSONDecodeError:
            report["skipped"]["invalid_json"] += 1
            continue
        if grade is not None and card.get("grade") != grade:
            continue
        try:
            prepared = prepare_card(
                card, units.get(card.get("unit_id")), allow_fill_blank=allow_fill_blank
            )
        except QgenSkip as exc:
            report["skipped"][exc.reason] += 1
            continue

        duplicate = find_duplicate(
            normalize_stem(prepared.stem),
            prepared.grade,
            index,
            threshold=near_duplicate_threshold,
        )
        if duplicate:
            report["skipped"][duplicate[0]] += 1
            continue

        question = None
        if not dry_run:
            question = create_pending_question(prepared, actor)
        report["created"] += 1
        if question is not None:
            report["createdIds"].append(question.id)
        normalized = normalize_stem(prepared.stem)
        index[prepared.grade].append(
            (question.id if question else None, normalized, trigrams(normalized), len(normalized))
        )

    report["skipped"] = dict(report["skipped"])
    return report


# --------------------------------------------------------------------------- 在线生成


def generate_question(
    actor, payload: dict, request=None, *, dry_run: bool = False
) -> tuple[Question, list[str], dict]:
    if not qgen_enabled():
        raise BusinessError(503, "AI 出题服务未启用（QGEN_ENABLED=false）")
    unit_id = str(payload.get("unitId") or "").strip()
    knowledge_point = str(payload.get("knowledgePoint") or "").strip()
    card_type = str(payload.get("type") or "").strip()
    try:
        difficulty = int(payload.get("difficulty", 1))
    except (TypeError, ValueError):
        raise BusinessError(400, "难度必须为 1~3 的整数")

    entry = load_unit_map().get(unit_id)
    if entry is None:
        raise BusinessError(400, "单元不在美术出题目录中")
    if card_type not in allowed_types():
        raise BusinessError(400, "只支持单选和判断题")
    if knowledge_point not in entry.get("knowledgePoints", []):
        raise BusinessError(400, "知识点不在该单元的目录中")
    if difficulty not in {1, 2, 3}:
        raise BusinessError(400, "难度必须为 1~3")

    provider = qgen_provider()
    if provider == "api":
        result = _generate_via_api(entry, unit_id, knowledge_point, card_type, difficulty)
    else:
        request_payload = {
            "unit_id": unit_id,
            "knowledge_point": knowledge_point,
            "type": card_type,
            "difficulty": difficulty,
        }
        if with_image_enabled():
            request_payload["with_image"] = True
        result = _http_json("POST", "/generate", request_payload)
    if not result.get("ok") or not result.get("card"):
        errors = result.get("errors") or ["模型未返回可解析的题卡"]
        raise BusinessError(502, "生成失败：" + "；".join(str(item) for item in errors)[:300])

    source_provider = API_PROVIDER if provider == "api" else PROVIDER
    try:
        prepared = prepare_card(
            result["card"],
            entry,
            provider=source_provider,
            resources=result.get("resources"),
            fact_ids=result.get("fact_ids"),
            generated_by=result.get("generated_by"),
        )
    except QgenSkip as exc:
        raise BusinessError(502, f"生成结果未通过校验：{exc.reason}") from exc

    duplicate = find_duplicate(normalize_stem(prepared.stem), prepared.grade, build_stem_index())
    if duplicate:
        raise BusinessError(409, "生成的题目与题库已有题目重复，请换一个知识点或重试")

    if dry_run:
        question = Question(
            subject="art",
            grade=prepared.grade,
            course=prepared.course,
            chapter=prepared.chapter,
            type=prepared.type,
            difficulty=prepared.difficulty,
            stem=prepared.stem,
            score=prepared.score,
            answer=prepared.answer,
            analysis=prepared.analysis,
            knowledge_point=prepared.knowledge_point,
            source_meta=prepared.source_meta,
            scoring_mode=ScoringMode.AUTO,
            status=QuestionStatus.PENDING,
            creator=actor,
        )
    else:
        question = create_pending_question(prepared, actor, request)
    model_meta = {
        "provider": source_provider,
        "request": result.get("request"),
        "parseOk": result.get("parse_ok"),
        "model": prepared.source_meta.get("createdBy"),
        "generatedBy": result.get("generated_by"),
        "imageCount": len(prepared.resources),
    }
    return question, prepared.warnings, model_meta
