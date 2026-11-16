"""离线评测出题服务：跑评测请求，统计格式合规、请求一致性与重复率。

只评"格式与结构"，不判答案事实正确率（需人工审核）。

用法（在仓库根目录下）：
    python -m model_b_qgen.eval_runner --requests data/09_qgen/eval/requests.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from .paths import PROJECT_ROOT
from .runtime import QgenRuntime

ROOT = PROJECT_ROOT
DEFAULT_REQUESTS = ROOT / "data" / "09_qgen" / "eval" / "requests.jsonl"
DEFAULT_OUT = ROOT / "logs" / "qgen_eval_report.json"


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def stem_grams(text: str) -> set[str]:
    """与离线 scripts/validate_questions.py 同口径的 3-gram，查重结果才对得上。"""
    clean = re.sub(r"[\s\W_]+", "", text or "", flags=re.UNICODE).lower()
    if len(clean) < 3:
        return {clean} if clean else set()
    return {clean[i:i + 3] for i in range(len(clean) - 2)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", default=str(DEFAULT_REQUESTS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dedup-threshold", type=float, default=0.85,
                        help="题干 3-gram jaccard 超过该值即换 seed 重生成；<=0 关闭")
    parser.add_argument("--dedup-attempts", type=int, default=3)
    args = parser.parse_args()

    requests = [json.loads(line) for line in Path(args.requests).open(encoding="utf-8") if line.strip()]
    if args.limit:
        requests = requests[: args.limit]

    runtime = QgenRuntime()
    results = []
    accepted_grams: list[set[str]] = []
    dedup_regenerated = 0
    for index, request in enumerate(requests, 1):
        started = time.time()
        record = runtime.generate(request)
        original_request = record["request"]
        regen = 0
        if args.dedup_threshold > 0:
            for bump in range(1, args.dedup_attempts + 1):
                grams = stem_grams((record.get("card") or {}).get("stem", ""))
                if not grams or not any(jaccard(grams, other) > args.dedup_threshold
                                        for other in accepted_grams):
                    break
                retry = dict(request, seed=bump,
                             request_id=f"{request.get('request_id', '')}-d{bump}")
                record = runtime.generate(retry)
                # 对外仍记原请求，避免样本里出现 -d 序号
                record["request"] = original_request
                regen = bump
        if regen:
            dedup_regenerated += 1
        record["dedup_regenerated"] = regen
        card = record.get("card") or {}
        accepted_grams.append(stem_grams(card.get("stem", "")))
        record["with_image"] = bool(request.get("with_image"))
        record["elapsed"] = round(time.time() - started, 2)
        record["ok"] = (
            record.get("card") is not None
            and not record["errors"]
            and not record.get("answer_errors")
        )
        results.append(record)
        print(
            f"[{index}/{len(requests)}] ok={record['ok']} "
            f"parse={record['parse_ok']} errors={record['errors'][:2]} "
            f"{record['elapsed']}s {card.get('type', '')} {str(card.get('stem', ''))[:30]}"
        )

    total = len(results)
    ok_rows = [r for r in results if r["ok"]]
    type_matches = sum(1 for r in results if (r.get("card") or {}).get("type") == r["request"]["type"])
    point_matches = sum(1 for r in results if (r.get("card") or {}).get("knowledge_point") == r["request"]["knowledge_point"])
    diff_matches = sum(1 for r in results if (r.get("card") or {}).get("difficulty") == r["request"]["difficulty"])

    # 与离线 scripts/validate_questions.find_duplicates 同口径（3-gram，0.85）
    stems = [stem_grams((r.get("card") or {}).get("stem", "")) for r in ok_rows]
    dup_pairs = 0
    pairs = 0
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            pairs += 1
            if jaccard(stems[i], stems[j]) > 0.85:
                dup_pairs += 1

    attempts = [r.get("attempts", 1) for r in results]
    first_pass = sum(1 for r in results if r.get("attempts", 1) == 1)
    first_pass_ok = sum(1 for r in results if r.get("attempts", 1) == 1 and r["ok"])
    fact_ok = sum(1 for r in results if r.get("fact_ok", True))
    from_model = sum(1 for r in results if r.get("generated_by") == "model")
    from_template = sum(1 for r in results if r.get("generated_by") == "template")
    from_image = sum(1 for r in results if r.get("generated_by") == "image_bank")
    image_reqs = [r for r in results if r.get("with_image")]
    image_with_resource = sum(1 for r in image_reqs if (r.get("card") or {}).get("resources"))
    image_type_match = sum(
        1 for r in image_reqs if (r.get("card") or {}).get("type") == r["request"]["type"]
    )
    model_elapsed = [r["elapsed"] for r in results if r.get("generated_by") != "image_bank"]
    blocked = sum(1 for r in results if r.get("model_blocked"))
    provenance_blocked = sum(1 for r in results if r.get("provenance_blocked"))

    report = {
        "total": total,
        "ok": len(ok_rows),
        "metrics": {
            "json_parse_rate": round(sum(1 for r in results if r["parse_ok"]) / total, 4) if total else 0,
            "valid_rate": round(len(ok_rows) / total, 4) if total else 0,
            "first_pass_valid_rate": round(first_pass_ok / total, 4) if total else 0,
            "retried_requests": sum(1 for a in attempts if a > 1),
            "fact_ok_rate": round(fact_ok / total, 4) if total else 0,
            "model_generated": from_model,
            "template_fallback": from_template,
            "image_questions": from_image,
            "image_question_requests": len(image_reqs),
            "image_type_match_rate": round(image_type_match / len(image_reqs), 4) if image_reqs else 0,
            "image_with_resource_rate": round(image_with_resource / len(image_reqs), 4) if image_reqs else 0,
            "fact_blocked": blocked,
            "provenance_blocked": provenance_blocked,
            "forced_template": sum(1 for r in results if r.get("forced_template")),
            "dedup_regenerated": dedup_regenerated,
            "type_match_rate": round(type_matches / total, 4) if total else 0,
            "point_match_rate": round(point_matches / total, 4) if total else 0,
            "difficulty_match_rate": round(diff_matches / total, 4) if total else 0,
            "duplicate_pair_rate": round(dup_pairs / pairs, 4) if pairs else 0,
            "avg_seconds": round(statistics.mean([r["elapsed"] for r in results]), 2) if results else 0,
            "avg_seconds_model_only": round(statistics.mean(model_elapsed), 2) if model_elapsed else 0,
        },
        "by_type": dict(Counter(r["request"]["type"] for r in results)),
        "by_grade": dict(sorted(Counter(str(r["request"]["grade"]) for r in results).items())),
        "error_messages": dict(Counter(e for r in results for e in r["errors"])),
        "samples": [
            {"request": r["request"], "ok": r["ok"], "card": r.get("card"),
             "errors": r["errors"], "attempts": r.get("attempts", 1),
             "fact_ids": r.get("fact_ids", []), "fact_ok": r.get("fact_ok", True),
             "fact_errors": r.get("fact_errors", []),
             "answer_errors": r.get("answer_errors", []),
             "provenance_errors": r.get("provenance_errors", []),
             "provenance_blocked": r.get("provenance_blocked", False),
             "model_answer_errors": r.get("model_answer_errors", []),
             "model_errors": r.get("model_errors", []),
             "model_attempts": r.get("model_attempts", r.get("attempts", 1)),
             "forced_template": r.get("forced_template", False),
             "dedup_regenerated": r.get("dedup_regenerated", 0),
             "elapsed": r.get("elapsed"),
             "with_image": r.get("with_image", False),
             "generated_by": r.get("generated_by", "model")}
            for r in results
        ],
        "manual_check_note": "答案事实正确率需人工审核，本报告不包含该项。",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = out.with_suffix(".md")
    metrics = report["metrics"]
    lines = [
        "# 出题服务评测报告",
        "",
        f"- 请求数：{total}，通过校验：{report['ok']}",
        f"- JSON 合法率：{metrics['json_parse_rate']:.1%}",
        f"- 字段/答案格式合规率：{metrics['valid_rate']:.1%}"
        f"（首轮 {metrics['first_pass_valid_rate']:.1%}，重试 {metrics['retried_requests']} 题）",
        f"- 模型直接生成：{metrics['model_generated']}/{total}，模板兜底：{metrics['template_fallback']}/{total}",
        f"- 图像题：{metrics['image_questions']}/{metrics['image_question_requests']} 道"
        f"（请求带 with_image），带图 {metrics['image_with_resource_rate']:.1%}，"
        f"题型一致 {metrics['image_type_match_rate']:.1%}",
        f"- 事实层拦截（模型题被换成模板题）：{metrics['fact_blocked']}/{total}"
        f"，其中溯源拦截 {metrics['provenance_blocked']}/{total}",
        f"- 事实卡关键词命中：{metrics['fact_ok_rate']:.1%}（仅供参考，不等于正确率）",
        f"- 题型与请求一致：{metrics['type_match_rate']:.1%}",
        f"- 知识点与请求一致：{metrics['point_match_rate']:.1%}",
        f"- 难度与请求一致：{metrics['difficulty_match_rate']:.1%}",
        f"- 题干重复对占比：{metrics['duplicate_pair_rate']:.1%}"
        f"（批内去重重生成 {metrics['dedup_regenerated']} 题，3-gram 阈值 0.85）",
        f"- 平均耗时：{metrics['avg_seconds']}s/题（仅模型题 {metrics['avg_seconds_model_only']}s/题）",
        "",
        "> 答案事实正确率需人工审核，不在本报告内。",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"报告：{out} / {md_path}")


if __name__ == "__main__":
    main()
