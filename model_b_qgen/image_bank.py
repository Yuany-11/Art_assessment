"""图题通道：请求显式要图题（with_image=true）且该知识点有图题时，直接返回带图题卡。

Qwen2.5-3B 是纯文本模型，不能看图出题；图题由「图片 + 模板/人工绑定」产出的
图题库提供（176 道已入库 + 24 道低年级补题）。本通道把它们接进 /generate，
使出题接口本身能返回图像题，而不是等到后端组卷。
"""
from __future__ import annotations

import copy
import json
import zlib
from collections import defaultdict
from pathlib import Path

from .paths import PROJECT_ROOT

IMAGE_DIR = PROJECT_ROOT / "data" / "09_qgen" / "image_questions"
SOURCES = (
    IMAGE_DIR / "img_questions.jsonl",
    IMAGE_DIR / "low_grade_20261114.jsonl",
    IMAGE_DIR / "type_cover_20261114.jsonl",
)


def _load_cards() -> list[dict]:
    cards: list[dict] = []
    for path in SOURCES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            card = json.loads(line)
            if card.get("resources") and card.get("stem"):
                cards.append(card)
    return cards


def _as_record(normalized: dict, card: dict) -> dict:
    picked = copy.deepcopy(card)
    return {
        "request": normalized,
        "raw_output": "",
        "parse_ok": True,
        "card": picked,
        "errors": [],
        "fact_ids": [],
        "fact_errors": [],
        "answer_errors": [],
        "provenance_errors": [],
        "generated_by": "image_bank",
        "attempts": 1,
        "fact_ok": True,
        "image_question": True,
    }


class ImageBank:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.index: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
        for card in _load_cards():
            key = (int(card.get("grade", 0)), str(card.get("unit_id")), str(card.get("knowledge_point")))
            self.index[key].append(card)
        for pool in self.index.values():
            pool.sort(key=lambda c: (str(c.get("id", "")), int(c.get("difficulty", 1))))

    def __len__(self) -> int:
        return sum(len(pool) for pool in self.index.values())

    def has(self, grade: int, unit_id: str, knowledge_point: str, qtype: str | None = None) -> bool:
        pool = self.index.get((int(grade), unit_id, knowledge_point))
        if not pool:
            return False
        return any(c.get("type") == qtype for c in pool) if qtype else True

    def pick(self, normalized: dict) -> dict | None:
        key = (int(normalized.get("grade", 0)), normalized.get("unit_id"), normalized.get("knowledge_point"))
        pool = self.index.get(key)
        if not pool:
            return None
        # 题型必须一致：该知识点没有同题型图题时宁可走文字题，不能串成别的题型
        candidates = [c for c in pool if c.get("type") == normalized.get("type")]
        if not candidates:
            return None
        difficulty = int(normalized.get("difficulty", 1))
        gap = min(abs(int(c.get("difficulty", 1)) - difficulty) for c in candidates)
        candidates = [c for c in candidates if abs(int(c.get("difficulty", 1)) - difficulty) == gap]
        seed = zlib.crc32(
            f"{normalized.get('request_id', '')}|{normalized.get('seed', 0)}|{normalized.get('type', '')}".encode()
        )
        return _as_record(normalized, candidates[seed % len(candidates)])


IMAGE_BANK = ImageBank()
