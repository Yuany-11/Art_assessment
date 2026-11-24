"""离线评测出题服务：跑评测请求，统计格式合规、请求一致性与重复率。

只评"格式与结构"，不判答案事实正确率（需人工审核）。

用法（在 repo 目录下）：
    python -m model_b_qgen.eval_runner --requests ../data/09_qgen/eval/requests.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from .runtime import QgenRuntime

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUESTS = ROOT / "data" / "09_qgen" / "eval" / "requests.jsonl"
DEFAULT_OUT = ROOT / "logs" / "qgen_eval_report.json"


def bigrams(text: str) -> set[str]:
    text = re.sub(r"[\s　，。、；：！？（）()\dA-D.．]", "", text or "")
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", default=str(DEFAULT_REQUESTS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    requests = [json.loads(line) for line in Path(args.requests).open(encoding="utf-8") if line.strip()]
    if args.limit:
        requests = requests[: args.limit]

    runtime = QgenRuntime()
    results = []
    for index, request in enumerate(requests, 1):
        started = time.time()
        record = runtime.generate(request)
        record["elapsed"] = round(time.time() - started, 2)
        record["ok"] = record["parse_ok"] and not record["errors"]
        results.append(record)
        card = record.get("card") or {}
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

    stems = [bigrams((r.get("card") or {}).get("stem", "")) for r in ok_rows]
    dup_pairs = 0
    pairs = 0
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            pairs += 1
            if jaccard(stems[i], stems[j]) > 0.85:
                dup_pairs += 1

    report = {
        "total": total,
        "ok": len(ok_rows),
        "metrics": {
            "json_parse_rate": round(sum(1 for r in results if r["parse_ok"]) / total, 4) if total else 0,
            "valid_rate": round(len(ok_rows) / total, 4) if total else 0,
            "type_match_rate": round(type_matches / total, 4) if total else 0,
            "point_match_rate": round(point_matches / total, 4) if total else 0,
            "difficulty_match_rate": round(diff_matches / total, 4) if total else 0,
            "duplicate_pair_rate": round(dup_pairs / pairs, 4) if pairs else 0,
            "avg_seconds": round(statistics.mean([r["elapsed"] for r in results]), 2) if results else 0,
        },
        "by_type": dict(Counter(r["request"]["type"] for r in results)),
        "by_grade": dict(sorted(Counter(str(r["request"]["grade"]) for r in results).items())),
        "error_messages": dict(Counter(e for r in results for e in r["errors"])),
        "samples": [
            {"request": r["request"], "ok": r["ok"], "card": r.get("card"), "errors": r["errors"]}
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
        f"- 字段/答案格式合规率：{metrics['valid_rate']:.1%}",
        f"- 题型与请求一致：{metrics['type_match_rate']:.1%}",
        f"- 知识点与请求一致：{metrics['point_match_rate']:.1%}",
        f"- 难度与请求一致：{metrics['difficulty_match_rate']:.1%}",
        f"- 题干重复对占比：{metrics['duplicate_pair_rate']:.1%}",
        f"- 平均耗时：{metrics['avg_seconds']}s/题",
        "",
        "> 答案事实正确率需人工审核，不在本报告内。",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(f"报告：{out} / {md_path}")


if __name__ == "__main__":
    main()
