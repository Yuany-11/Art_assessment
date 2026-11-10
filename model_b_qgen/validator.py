"""校验美术出题题卡：字段、答案格式、目录对齐、难度、查重。

用法：
    python scripts/validate_questions.py data/09_qgen/golden/初中_20.jsonl
    python scripts/validate_questions.py data/09_qgen/golden/*.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"

TYPES = {"single_choice", "true_false", "fill_blank", "short_answer"}
SOURCES = {"golden", "public", "self_instruct"}
REVIEW_STATUSES = {"pending", "approved", "rejected"}
REQUIRED_FIELDS = [
    "id", "subject", "grade", "unit_id", "unit_name", "knowledge_point",
    "type", "difficulty", "stem", "answer", "analysis", "score",
    "scoringMode", "source", "review_status", "created_by",
]
CHOICE_TYPES = {"single_choice"}


def load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def unit_index(catalog: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for grade_key, grade_info in catalog["grades"].items():
        for unit in grade_info["units"]:
            item = dict(unit)
            item["grade"] = int(grade_key)
            item["band"] = grade_info["band"]
            index[unit["unit_id"]] = item
    return index


def normalize(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text), flags=re.UNICODE).lower()


def ngrams(text: str, n: int = 3) -> set[str]:
    s = normalize(text)
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def validate_card(card: dict, units: dict[str, dict], catalog: dict) -> list[str]:
    errors: list[str] = []
    qid = card.get("id", "<无 id>")

    missing = [field for field in REQUIRED_FIELDS if field not in card]
    if missing:
        return [f"{qid}: 缺少字段 {missing}"]

    if card["subject"] != "art":
        errors.append(f"{qid}: subject 必须是 art")
    if not isinstance(card["grade"], int) or not 1 <= card["grade"] <= 9:
        errors.append(f"{qid}: grade 必须是 1–9 的整数")
    if card["type"] not in TYPES:
        errors.append(f"{qid}: type 非法 {card['type']!r}")
    if not isinstance(card["difficulty"], int) or not 1 <= card["difficulty"] <= 3:
        errors.append(f"{qid}: difficulty 必须是 1–3")
    if card["source"] not in SOURCES:
        errors.append(f"{qid}: source 非法 {card['source']!r}")
    if card["review_status"] not in REVIEW_STATUSES:
        errors.append(f"{qid}: review_status 非法 {card['review_status']!r}")
    if not str(card["stem"]).strip():
        errors.append(f"{qid}: 题干为空")
    if re.search(r"[上下]图|如图|图中|图片|附图|插图|四幅|两幅|几幅|下列图|图形\s*[A-D]"
                 r"|哪一幅|第[一二三四五六七八九十]幅|下面的画|以下画作|以下作品|下列作品|标志[A-D]",
                 str(card["stem"])):
        errors.append(f"{qid}: 题干依赖图片，无法独立作答")
    if len(str(card["stem"])) > 5000:
        errors.append(f"{qid}: 题干超过 5000 字")
    if not str(card["analysis"]).strip():
        errors.append(f"{qid}: 解析为空")
    if not isinstance(card["score"], (int, float)) or not 0.5 <= card["score"] <= 100:
        errors.append(f"{qid}: score 必须在 0.5–100")

    unit = units.get(card["unit_id"])
    if not unit:
        errors.append(f"{qid}: unit_id 不在目录中 {card['unit_id']!r}")
    else:
        if unit["grade"] != card["grade"]:
            errors.append(f"{qid}: grade {card['grade']} 与单元年级 {unit['grade']} 不一致")
        if card["unit_name"] != unit["unit_name"]:
            errors.append(f"{qid}: unit_name 与目录不一致")
        if card["knowledge_point"] not in unit["knowledge_points"]:
            errors.append(f"{qid}: 知识点 {card['knowledge_point']!r} 不在单元知识点中")
        if card["type"] not in unit["allowed_types"]:
            errors.append(f"{qid}: 单元不允许题型 {card['type']}")
        low, high = unit["difficulty_range"]
        if not low <= card["difficulty"] <= high:
            errors.append(f"{qid}: 难度 {card['difficulty']} 超出单元范围 {low}-{high}")

    answer = card["answer"]
    options = card.get("options") or []
    if not isinstance(answer, dict):
        errors.append(f"{qid}: answer 必须是对象")
        return errors

    if card["type"] in CHOICE_TYPES:
        if len(options) != 4:
            errors.append(f"{qid}: 单选必须 4 个选项，当前 {len(options)} 个")
        keys = [opt.get("key") for opt in options]
        if any(not key for key in keys) or len(set(keys)) != len(keys):
            errors.append(f"{qid}: 选项 key 为空或重复")
        if any(not str(opt.get("text", "")).strip() for opt in options):
            errors.append(f"{qid}: 存在空选项文本")
        if answer.get("value") not in keys:
            errors.append(f"{qid}: 单选答案不在选项 key 中")
        if card["scoringMode"] != "auto":
            errors.append(f"{qid}: 选择题 scoringMode 必须是 auto")
    elif card["type"] == "true_false":
        if options:
            errors.append(f"{qid}: 判断题不应有 options")
        if not isinstance(answer.get("value"), bool):
            errors.append(f"{qid}: 判断题 answer.value 必须是布尔值")
        if card["scoringMode"] != "auto":
            errors.append(f"{qid}: 判断题 scoringMode 必须是 auto")
    elif card["type"] == "fill_blank":
        if options:
            errors.append(f"{qid}: 填空题不应有 options")
        values = answer.get("values")
        if not isinstance(values, list) or not values:
            errors.append(f"{qid}: 填空题 answer.values 必须是非空数组")
        else:
            if any(not str(item).strip() for item in values):
                errors.append(f"{qid}: 填空题存在空答案")
            blanks = len(re.findall(r"_{2,}", str(card["stem"])))
            if blanks and blanks != len(values):
                errors.append(f"{qid}: 填空题 {blanks} 个空但给了 {len(values)} 个答案")
        if card["scoringMode"] != "auto":
            errors.append(f"{qid}: 填空题 scoringMode 必须是 auto")
    elif card["type"] == "short_answer":
        if options:
            errors.append(f"{qid}: 解答题不应有 options")
        if not str(answer.get("text", "")).strip():
            errors.append(f"{qid}: 解答题 answer.text 不能为空")
        if card["scoringMode"] not in {"manual", "ai"}:
            errors.append(f"{qid}: 解答题 scoringMode 必须是 manual 或 ai")

    stem_text = str(card.get("stem", ""))
    analysis_text = str(card.get("analysis", ""))
    concept_text = f"{stem_text} {analysis_text}"
    if "三原色" in concept_text and "色光" not in concept_text:
        if re.search(r"红\s*[、,，和及]?\s*(?:蓝\s*[、,，和及]?\s*绿|绿\s*[、,，和及]?\s*蓝)"
                     r"|绿\s*[、,，和及]?\s*蓝\s*[、,，和及]?\s*红|红绿蓝|红蓝绿", analysis_text):
            errors.append(f"{qid}: 三原色表述错误（绘画三原色应为红黄蓝，不是红绿蓝）")
        if re.search(r"品红|青色", analysis_text):
            errors.append(f"{qid}: 三原色表述错误（混入了印刷/色光口径）")
        if card["type"] == "single_choice" and options and not re.search(r"不是|不属于|错误|除外", stem_text):
            texts = [str(opt.get("text", "")).strip() for opt in options]
            primaries = [t for t in texts if any(k in t for k in ("红色", "黄色", "蓝色"))]
            if len(primaries) >= 2 and re.search(r"哪一种|哪个|哪一组|哪项", stem_text):
                errors.append(f"{qid}: 三原色单选题存在多个正确选项")
            for opt in options:
                if opt.get("key") == answer.get("value") and "绿" in str(opt.get("text", "")):
                    errors.append(f"{qid}: 三原色答案不能是绿色")
        if card["type"] == "fill_blank":
            values = [str(item).strip() for item in (answer.get("values") or [])]
            if any(item in {"品红", "青", "青色", "绿色", "绿"} for item in values):
                errors.append(f"{qid}: 三原色填空答案错误")

    return errors


def find_duplicates(cards: list[dict], threshold: float = 0.85) -> list[tuple[str, str, float]]:
    grams = [(card.get("id", ""), ngrams(card.get("stem", ""))) for card in cards]
    duplicates = []
    for i in range(len(grams)):
        for j in range(i + 1, len(grams)):
            score = jaccard(grams[i][1], grams[j][1])
            if score > threshold:
                duplicates.append((grams[i][0], grams[j][0], round(score, 3)))
    return duplicates


def print_stats(cards: list[dict], units: dict[str, dict], catalog: dict) -> None:
    print(f"\n题卡总数：{len(cards)}")
    print("按年级：", dict(sorted(Counter(card.get("grade") for card in cards).items())))
    print("按题型：", dict(Counter(card.get("type") for card in cards)))
    print("按难度：", dict(sorted(Counter(card.get("difficulty") for card in cards).items())))

    selected_grades = {card.get("grade") for card in cards}
    all_points = {
        point
        for unit in units.values()
        if unit["grade"] in selected_grades
        for point in unit["knowledge_points"]
    }
    covered = {card.get("knowledge_point") for card in cards}
    covered &= all_points
    print(f"知识点覆盖：{len(covered)}/{len(all_points)}")
    if all_points - covered:
        print("未覆盖知识点：", sorted(all_points - covered)[:20])

    by_unit = Counter(card.get("unit_id") for card in cards)
    print("按单元：", dict(sorted(by_unit.items())))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="题卡 JSONL 文件")
    parser.add_argument("--threshold", type=float, default=0.85, help="查重 Jaccard 阈值")
    args = parser.parse_args()

    catalog = load_catalog()
    units = unit_index(catalog)
    cards: list[dict] = []
    all_errors: list[str] = []

    for path_text in args.files:
        path = Path(path_text)
        if not path.exists():
            all_errors.append(f"{path}: 文件不存在")
            continue
        with path.open(encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError as exc:
                    all_errors.append(f"{path}:{line_no}: JSON 解析失败 {exc}")
                    continue
                cards.append(card)
                all_errors.extend(validate_card(card, units, catalog))

    ids = [card.get("id") for card in cards]
    duplicate_ids = [qid for qid, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        all_errors.append(f"重复 id：{duplicate_ids}")

    duplicates = find_duplicates(cards, args.threshold)
    for left, right, score in duplicates:
        all_errors.append(f"疑似重复题干：{left} ↔ {right}（相似度 {score}）")

    print_stats(cards, units, catalog)

    if all_errors:
        print(f"\n发现 {len(all_errors)} 个问题：")
        for error in all_errors:
            print(" -", error)
        return 1

    print("\n校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
