"""评测报告质量扫描：在人工抽审之外，机器先查可判定的硬伤。

用法：
    python scripts/scan_eval_quality.py logs/qgen_eval/v4_strict100_20261114.json
退出码非 0 表示发现疑似硬伤，报告写到同目录 *.scan.json。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "09_qgen" / "knowledge" / "kb_v1.jsonl"
sys.path.insert(0, str(ROOT / "scripts"))
from validate_questions import normalize  # noqa: E402


def load_facts() -> dict[str, dict]:
    facts = {}
    for line in KB.read_text(encoding="utf-8").splitlines():
        if line.strip():
            fact = json.loads(line)
            facts[fact["fact_id"]] = fact
    return facts


def supported(text: str, facts: list[dict], min_len: int = 4) -> bool:
    token = normalize(text)
    if len(token) < min_len:
        return False
    for fact in facts:
        claim = normalize(fact.get("claim", ""))
        if claim and (token in claim or claim in token):
            return True
    return False


def scan(samples: list[dict], facts: dict[str, dict]) -> dict[str, list]:
    issues: dict[str, list] = {
        "单选多解": [], "单选答案与解析不一致": [], "判断题答案与解析矛盾": [],
        "简答要求两点但不足两点": [], "作用题误用相调类事实": [],
        "重复题干": [], "超短题干(人工看)": [],
    }
    stems = Counter()
    for sample in samples:
        card = sample["card"]
        req = sample["request"]
        qtype = card.get("type")
        fact_list = [facts[i] for i in sample.get("fact_ids") or [] if i in facts]
        stem = str(card.get("stem", ""))
        stems[normalize(stem)] += 1
        tag = (req["grade"], req["knowledge_point"])

        if qtype == "single_choice":
            options = card.get("options") or []
            hits = [o["text"] for o in options if supported(o["text"], fact_list)]
            if len(hits) >= 2:
                issues["单选多解"].append((*tag, hits))
            answer_key = str(card.get("answer", {}).get("value", ""))
            correct = next((o["text"] for o in options if o["key"] == answer_key), "")
            analysis = normalize(card.get("analysis", ""))
            def mentioned(text: str) -> bool:
                token = normalize(text)
                return len(token) >= 3 and token in analysis
            # 解析点名“选项B正确”也算肯定，避免同义复述被误判
            affirmed = bool(re.search(
                rf"(选项|答案[是为]?)\s*{re.escape(answer_key.lower())}\s*(正确|对|无误)"
                rf"|选\s*{re.escape(answer_key.lower())}\s*(项)?\s*(正确|对)",
                analysis,
            ))
            # 图题解析是人工写的，常把选项换成同义表述（"各有一个消失点"对应"两个消失点"），
            # 字面规则会误报，图题单独人工抽审。
            if (not sample.get("with_image") and correct and not mentioned(correct)
                    and not affirmed and any(
                        mentioned(o["text"]) for o in options if o["key"] != answer_key)):
                issues["单选答案与解析不一致"].append((*tag, answer_key, correct))

        if qtype == "true_false":
            value = card.get("answer", {}).get("value")
            analysis = str(card.get("analysis", ""))
            if value is True and re.search(r"该说法(错误|不正确)|因此该说法错误", analysis):
                issues["判断题答案与解析矛盾"].append((*tag, value))
            if value is False and re.search(r"该说法(正确|无误)|因此该说法正确", analysis):
                issues["判断题答案与解析矛盾"].append((*tag, value))

        if qtype == "short_answer" and re.search(r"至少两点|两点以上", stem):
            text = str(card.get("answer", {}).get("text", ""))
            if sample.get("generated_by") == "template":
                groups = re.findall(r"（要点[:：]([^）)]*)）", text)
                points = sum(max(1, len([x for x in re.split(r"[、，；]", g) if x.strip()]))
                             for g in groups)
                covered = sum(
                    1 for fact in fact_list
                    if normalize(fact.get("claim", "")) and (
                        normalize(fact["claim"]) in normalize(text)
                        or normalize(fact.get("answer", "")) in normalize(text))
                )
                if points < 2 and covered < 2:
                    issues["简答要求两点但不足两点"].append(
                        (*tag, f"模板实际{max(points, covered)}点", text))

        if re.search(r"作用|效果|意义|好处", stem):
            for fact in fact_list:
                if re.search(r"相调|混合", str(fact.get("claim", ""))):
                    issues["作用题误用相调类事实"].append(
                        (*tag, fact["fact_id"], fact.get("claim", "")[:40]))

        if len(normalize(stem)) < 7:
            issues["超短题干(人工看)"].append((*tag, qtype, stem))

    issues["重复题干"] = [(k[:30], v) for k, v in stems.items() if v > 1]
    return issues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    args = parser.parse_args()
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    issues = scan(report["samples"], load_facts())

    hard_keys = ["单选多解", "单选答案与解析不一致", "判断题答案与解析矛盾",
                 "作用题误用相调类事实", "重复题干"]
    review_keys = ["简答要求两点但不足两点", "超短题干(人工看)"]
    hard = sum(len(issues[k]) for k in hard_keys)
    print(f"样本 {len(report['samples'])} 条，疑似硬伤 {hard} 条")
    for key in hard_keys:
        if issues[key]:
            print(f"\n[{key}] {len(issues[key])}")
            for item in issues[key]:
                print("  ", item)
    for key in review_keys:
        if issues[key]:
            print(f"\n[{key} · 需人工看] {len(issues[key])}")
            for item in issues[key][:8]:
                print("  ", item)

    out = report_path.with_suffix(".scan.json")
    out.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n报告：", out)
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
