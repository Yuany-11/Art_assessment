"""美术出题服务：FastAPI 封装，后端通过 HTTP 调用。"""
from __future__ import annotations

import json
import os
import random
import re
import zlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .paths import PROJECT_ROOT
from .resources import attach_resources
from .runtime import QgenRuntime
from .test_page import TEST_PAGE

IMAGE_ROOT = Path(os.getenv("QGEN_IMAGE_ROOT", PROJECT_ROOT / "data" / "12_image_assets"))

app = FastAPI(title="Model B Question Generation", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
if IMAGE_ROOT.exists():
    app.mount("/resources", StaticFiles(directory=str(IMAGE_ROOT)), name="resources")
else:
    print(f"[warn] 静态资源目录不存在，/resources 未挂载：{IMAGE_ROOT}")
runtime = QgenRuntime(
    model_path=os.getenv("QGEN_MODEL"),
    adapter_path=os.getenv("QGEN_ADAPTER"),
    load_4bit=os.getenv("QGEN_LOAD_4BIT", "1") != "0",
    max_new_tokens=int(os.getenv("QGEN_MAX_NEW_TOKENS", "600")),
)


class GenerateRequest(BaseModel):
    unit_id: str
    knowledge_point: str
    type: str = Field(description="single_choice / multiple_choice / true_false / fill_blank / short_answer")
    difficulty: int = Field(default=1, ge=1, le=3)
    seed: int = Field(default=0, description="缓存分区用；不改采样随机性，同一 seed 重复请求直接命中缓存")
    request_id: str = ""
    with_image: bool = Field(default=True, description="要图题：该知识点有图题素材时返回带配图的题卡；传 false 返回纯文字题")


class GenerateBatchRequest(BaseModel):
    requests: list[GenerateRequest]


# 批量出题的图像题目标占比（年级 × 题型）。看图题集中在单选/判断，填空/简答较少；
# 初始值按常见学段题型分布设定，可按对方官方卷子的实际比例调整。
IMAGE_RATIO_BY_GRADE_TYPE = {
    1: {"single_choice": 0.50, "true_false": 0.45, "fill_blank": 0.25, "short_answer": 0.30},
    2: {"single_choice": 0.50, "true_false": 0.45, "fill_blank": 0.25, "short_answer": 0.30},
    3: {"single_choice": 0.40, "true_false": 0.35, "fill_blank": 0.20, "short_answer": 0.25},
    4: {"single_choice": 0.40, "true_false": 0.35, "fill_blank": 0.20, "short_answer": 0.25},
    5: {"single_choice": 0.35, "true_false": 0.30, "fill_blank": 0.15, "short_answer": 0.20},
    6: {"single_choice": 0.35, "true_false": 0.30, "fill_blank": 0.15, "short_answer": 0.20},
    7: {"single_choice": 0.30, "true_false": 0.25, "fill_blank": 0.10, "short_answer": 0.15},
    8: {"single_choice": 0.30, "true_false": 0.25, "fill_blank": 0.10, "short_answer": 0.15},
    9: {"single_choice": 0.30, "true_false": 0.25, "fill_blank": 0.10, "short_answer": 0.15},
}
# 年级总占比兜底（未列题型时用）
IMAGE_RATIO_BY_GRADE = {1: 0.40, 2: 0.40, 3: 0.30, 4: 0.30,
                        5: 0.25, 6: 0.25, 7: 0.20, 8: 0.20, 9: 0.20}


def plan_image_requests(requests: list[dict]) -> None:
    """按「年级 × 题型」目标占比，在命中图题库的请求里挑图题，其余转文字题。

    确定性地按 request_id 排序选取，同一批请求重复执行结果一致；
    调用方显式传 with_image=False 的请求一律不出图题。
    """
    from .image_bank import IMAGE_BANK

    groups: dict[tuple[int, str], list[int]] = {}
    for i, req in enumerate(requests):
        if req.get("with_image") is False:
            continue
        unit = runtime.units.get(req.get("unit_id"))
        if unit:
            key = (int(unit["grade"]), str(req.get("type")))
            groups.setdefault(key, []).append(i)

    plans: list[dict] = []
    for (grade, qtype), indexes in groups.items():
        ratio = IMAGE_RATIO_BY_GRADE_TYPE.get(grade, {}).get(qtype)
        if ratio is None:
            ratio = IMAGE_RATIO_BY_GRADE.get(grade, 0.25)
        candidates = [
            i for i in indexes
            if IMAGE_BANK.has(grade, requests[i].get("unit_id"),
                              requests[i].get("knowledge_point"), qtype)
        ]
        if not candidates:
            for i in indexes:
                requests[i]["with_image"] = False
            continue
        exact = len(indexes) * ratio
        base = min(int(exact), len(candidates))
        plans.append({
            "remainder": exact - int(exact),
            "tiebreak": zlib.crc32(f"{grade}|{qtype}".encode()),
            "indexes": indexes,
            "candidates": candidates,
            "target": base,
            "exact": exact,
        })

    # 最大余额法：先按整数部分分，剩余名额按小数部分从大到小补，
    # 避免小组四舍五入归零或保底后把小题量变成全图题。
    allocated = sum(p["target"] for p in plans)
    total_expected = round(sum(p["exact"] for p in plans))
    for plan in sorted(plans, key=lambda p: (-p["remainder"], p["tiebreak"])):
        if allocated >= total_expected:
            break
        if plan["target"] < len(plan["candidates"]):
            plan["target"] += 1
            allocated += 1

    for plan in plans:
        candidates = plan["candidates"]
        candidates.sort(key=lambda i: zlib.crc32(
            f"{requests[i].get('request_id', '')}|{requests[i].get('unit_id')}|"
            f"{requests[i].get('knowledge_point')}".encode()
        ))
        chosen = set(candidates[:plan["target"]])
        for i in plan["indexes"]:
            requests[i]["with_image"] = i in chosen





@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return TEST_PAGE


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": runtime.loaded,
        "model_path": str(runtime.model_path),
        "adapter": str(runtime.adapter_path) if runtime.adapter_path.exists() else None,
    }


@app.get("/catalog")
def catalog() -> dict:
    return runtime.catalog


@app.get("/image_coverage")
def image_coverage() -> dict:
    """有同题型图素材的 (年级, 单元, 知识点, 题型)，测试页据此优先抽图题。"""
    from .image_bank import IMAGE_BANK

    items = [
        [grade, unit_id, knowledge_point, qtype]
        for (grade, unit_id, knowledge_point), pool in IMAGE_BANK.index.items()
        for qtype in sorted({str(card.get("type")) for card in pool})
    ]
    return {"items": items}


BANK_PATH = Path(
    os.getenv(
        "QGEN_BANK",
        Path(__file__).resolve().parents[2] / "data" / "09_qgen" / "final" / "train_clean.jsonl",
    )
)
DEFAULT_SCORES = {"single_choice": 5, "true_false": 2, "fill_blank": 4, "short_answer": 10}
_bank: list[dict] | None = None


def bank() -> list[dict]:
    global _bank
    if _bank is None:
        if not BANK_PATH.exists():
            raise FileNotFoundError(f"题库文件不存在：{BANK_PATH}")
        with BANK_PATH.open(encoding="utf-8") as fh:
            _bank = [json.loads(line) for line in fh if line.strip()]
    return _bank


DEMO_PATH = Path(
    os.getenv(
        "QGEN_DEMO",
        Path(__file__).resolve().parents[2] / "data" / "09_qgen" / "demo" / "fixed_demo_grade3.json",
    )
)


@app.get("/demo")
def demo(with_answer: bool = True) -> dict:
    """固定演示卷：不随机、不调用模型，题目来自待审题库。"""
    if not DEMO_PATH.exists():
        raise HTTPException(status_code=404, detail=f"演示卷不存在：{DEMO_PATH}")
    with DEMO_PATH.open(encoding="utf-8") as fh:
        paper = json.load(fh)
    if not with_answer:
        for card in paper["cards"]:
            card.pop("answer", None)
            card.pop("analysis", None)
    return paper


@app.get("/paper")
def paper(
    grade: int,
    unit_id: str | None = None,
    difficulty: int | None = None,
    single_choice: int = 5,
    true_false: int = 5,
    fill_blank: int = 4,
    short_answer: int = 2,
    with_answer: bool = True,
) -> dict:
    """从交付题库组一套试卷，秒级返回，不调用模型。"""
    if not 1 <= grade <= 9:
        raise HTTPException(status_code=400, detail="grade 必须是 1–9")
    wanted = {
        "single_choice": single_choice,
        "true_false": true_false,
        "fill_blank": fill_blank,
        "short_answer": short_answer,
    }
    if any(count < 0 for count in wanted.values()):
        raise HTTPException(status_code=400, detail="各题型数量不能为负")

    cards = [card for card in bank() if card["grade"] == grade]
    if unit_id:
        cards = [card for card in cards if card["unit_id"] == unit_id]
    if difficulty:
        cards = [card for card in cards if card["difficulty"] == difficulty]
    if not cards:
        raise HTTPException(status_code=404, detail="该范围内没有题卡")

    picked: list[dict] = []
    shortfalls: dict[str, int] = {}
    for qtype, count in wanted.items():
        pool = [card for card in cards if card["type"] == qtype]
        random.shuffle(pool)
        taken = pool[:count]
        if len(taken) < count:
            shortfalls[qtype] = count - len(taken)
        for card in taken:
            item = dict(card)
            item["score"] = DEFAULT_SCORES[qtype]
            item["review_status"] = item.get("review_status", "pending")
            if not with_answer:
                item.pop("answer", None)
                item.pop("analysis", None)
            picked.append(item)

    for number, item in enumerate(picked, 1):
        item["question_no"] = number
    return {
        "grade": grade,
        "unit_id": unit_id,
        "difficulty": difficulty,
        "count": len(picked),
        "total_score": sum(item["score"] for item in picked),
        "shortfalls": shortfalls,
        "source": str(BANK_PATH),
        "notice": "题目来自待审题库，入库或用于正式测评前必须人工复核。",
        "cards": picked,
    }


class GradeItem(BaseModel):
    id: str
    response: Any = None


class GradeRequest(BaseModel):
    items: list[GradeItem]


def _norm_answer(text: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(text)).lower()


@app.post("/grade")
def grade(payload: GradeRequest) -> dict:
    """学生提交后判分；答案与解析只在这里返回，组卷接口不返回。"""
    index = {card["id"]: card for card in bank()}
    results: list[dict] = []
    total = 0.0
    earned = 0.0
    manual = 0
    for item in payload.items:
        card = index.get(item.id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"题卡不存在：{item.id}")
        max_score = float(card.get("score", 0))
        total += max_score
        correct: bool | None = None
        response = item.response

        if card["type"] == "single_choice":
            correct = str(response or "").strip().upper() == str(card["answer"]["value"]).upper()
        elif card["type"] == "true_false":
            if isinstance(response, bool):
                correct = response == card["answer"]["value"]
            else:
                text = str(response or "").strip().lower()
                correct = (
                    (text in {"true", "正确", "对", "是"} and card["answer"]["value"] is True)
                    or (text in {"false", "错误", "错", "否"} and card["answer"]["value"] is False)
                )
            if correct is None:
                correct = False
        elif card["type"] == "fill_blank":
            expected = [str(v) for v in card["answer"].get("values", [])]
            given = response if isinstance(response, list) else [response]
            correct = bool(expected) and len(given) == len(expected) and all(
                _norm_answer(g) and _norm_answer(g) == _norm_answer(e)
                for g, e in zip(given, expected)
            )
        else:
            manual += 1

        score = max_score if correct else 0.0
        earned += score
        results.append(
            {
                "id": card["id"],
                "question_no": len(results) + 1,
                "type": card["type"],
                "stem": card["stem"],
                "response": response,
                "correct": correct,
                "score": score,
                "max_score": max_score,
                "answer": card["answer"],
                "analysis": card["analysis"],
                "needs_manual": correct is None,
            }
        )

    return {
        "count": len(results),
        "total_score": total,
        "earned_score": round(earned, 1),
        "manual_pending": manual,
        "items": results,
    }


@app.post("/generate")
def generate(payload: GenerateRequest) -> dict:
    try:
        record = runtime.generate(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record["ok"] = (
        record.get("card") is not None
        and not record["errors"]
        and not record.get("answer_errors")
    )
    record["needs_fact_review"] = bool(record.get("answer_errors"))
    record["resources"] = attach_resources(payload.model_dump(), record.get("card"))
    return record


@app.post("/generate_batch")
def generate_batch(payload: GenerateBatchRequest) -> dict:
    try:
        payloads = [item.model_dump() for item in payload.requests]
        plan_image_requests(payloads)
        records = runtime.generate_many(payloads)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    for record, item in zip(records, payload.requests):
        record["ok"] = (
            record["parse_ok"]
            and not record["errors"]
            and not record.get("answer_errors")
            and record.get("card") is not None
        )
        record["needs_fact_review"] = bool(record.get("answer_errors"))
        record["resources"] = attach_resources(item.model_dump(), record.get("card"))
    return {
        "count": len(records),
        "ok": sum(1 for record in records if record["ok"]),
        "items": records,
    }
