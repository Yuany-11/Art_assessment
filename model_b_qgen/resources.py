"""题卡配图/资源挂载。

资源项格式与 data/09_qgen/image_questions/img_questions.jsonl 一致：

    {"type": "image", "file": "images/53577.jpg", "name": "…"}

映射表 data/09_qgen/image_questions/mapping_20261114.json 的 "map" 段，
键为 "unit_id||knowledge_point"，值为图列表；这里原样填进 RESOURCE_MAP。

attach_resources 只在返回时补一个 url（QGEN_RESOURCE_URL_BASE + "/" + file），
file 保留不动：前端类型只认 {type, name, url?}，file 用于后端静态目录和留档。
映射表里没有的知识点返回空列表，绝不凭空生成图片地址。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .paths import PROJECT_ROOT

DEFAULT_MAP_PATH = PROJECT_ROOT / "data" / "09_qgen" / "image_questions" / "mapping_20261114.json"
DEFAULT_URL_BASE = "/resources"


def load_resource_map(path: str | Path | None = None) -> dict[tuple[str, str], list[dict]]:
    """读映射表；文件缺失或格式不对时返回空表，服务照常起。"""
    source = Path(path or os.getenv("QGEN_RESOURCE_MAP") or DEFAULT_MAP_PATH)
    if not source.exists():
        return {}
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw = data.get("map") or {}
    mapping: dict[tuple[str, str], list[dict]] = {}
    for key, items in raw.items():
        if "||" not in str(key) or not isinstance(items, list):
            continue
        unit_id, knowledge_point = str(key).split("||", 1)
        clean = [dict(item) for item in items if isinstance(item, dict)]
        if clean:
            mapping[(unit_id, knowledge_point)] = clean
    return mapping


RESOURCE_MAP: dict[tuple[str, str], list[dict]] = load_resource_map()


def resource_url(file: str, base: str | None = None) -> str:
    prefix = (base or os.getenv("QGEN_RESOURCE_URL_BASE") or DEFAULT_URL_BASE).rstrip("/")
    return f"{prefix}/{str(file).lstrip('/')}"


def attach_resources(request: dict | None, card: dict | None = None) -> list[dict]:
    """按 (unit_id, knowledge_point) 查映射，返回补好 url 的资源列表副本。

    图题卡自带 resources（题目本身的配图）时优先用卡上的，不再叠加映射配图。
    """
    role = "question"
    if card and isinstance(card.get("resources"), list) and card["resources"]:
        items = card["resources"]
    elif request:
        key = (str(request.get("unit_id") or ""), str(request.get("knowledge_point") or ""))
        items = RESOURCE_MAP.get(key) or []
        role = "reference"  # 映射图只是教学参考资料，不是题目配图
    else:
        items = []
    result: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        entry.setdefault("role", role)
        file = entry.get("file")
        if file:
            entry["url"] = resource_url(str(file))
        result.append(entry)
    return result
