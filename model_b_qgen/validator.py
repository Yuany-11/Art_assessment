"""校验美术出题题卡：字段、答案格式、目录对齐、难度、查重。

用法：
    python scripts/validate_questions.py data/09_qgen/golden/初中_20.jsonl
    python scripts/validate_questions.py data/09_qgen/golden/*.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .paths import PROJECT_ROOT

CATALOG_PATH = Path(os.getenv("QGEN_CATALOG", PROJECT_ROOT / "data" / "09_qgen" / "catalog_v2.json"))

TYPES = {"single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"}
SOURCES = {"golden", "public", "self_instruct"}
REVIEW_STATUSES = {"pending", "approved", "rejected"}
REQUIRED_FIELDS = [
    "id", "subject", "grade", "unit_id", "unit_name", "knowledge_point",
    "type", "difficulty", "stem", "answer", "analysis", "score",
    "scoringMode", "source", "review_status", "created_by",
]
CHOICE_TYPES = {"single_choice", "multiple_choice"}
TRIGGER_PREDICATES = ("显得", "变得", "看起来", "看上去", "似乎")
# 与 scripts/validate_questions.py 的离线口径保持一致
INTERNAL_FACT_WORDS = re.compile(r"根据事实卡|依据事实卡|按照事实卡|参考事实卡|事实卡中")
CLAIM_CONCLUSION = re.compile(r"该说法(?:正确|错误)")
ANALYSIS_CHOICE_WORDS = re.compile(
    r"选项|正确答案为\s*[A-DＡ-Ｄ]|每个选项|其他选项|以上选项"
    r"|(?:因此|所以)?选(?:择|用)?\s*[A-DＡ-Ｄ]\s*项?|故\s*[A-DＡ-Ｄ]\s*项"
)
BLANK_GLUE_CHARS = set("处的了着过时中上下来后前里外")
LEADING_PUNCT = "，。；、！？：,.!?;:（）()“”\"'"


def _blank_overlap(stem_text: str, values: list) -> str | None:
    """填空题：答案与空位前后文重叠，拼进句子会重复或读不通。"""
    parts = re.split(r"_{2,}", str(stem_text))
    if len(parts) - 1 != len(values) or not values:
        return None
    for index, value in enumerate(values):
        answer = str(value)
        if not answer:
            continue
        pre = parts[index]
        raw_post = parts[index + 1]
        for size in range(len(answer) - 1, 1, -1):
            if pre.endswith(answer[:size]):
                return answer[:size]
        # 分句边界后的复述是正常句式，只跳过空后文检查
        clause_break = raw_post[:1] in "，。；！？,.!?;:"
        post = "" if clause_break else raw_post.lstrip(LEADING_PUNCT)
        if post:
            # “____的颜色”答“相近颜色”会拼成“颜色的颜色”，剥掉结构助词再看
            after_de = post[1:] if post[:1] in "的地得" else post
            if after_de and len(answer) >= 2:
                for size in range(len(answer), 1, -1):
                    if after_de.startswith(answer[-size:]):
                        return answer[-size:]
            if after_de and answer[-1] in BLANK_GLUE_CHARS and after_de.startswith(answer[-1]):
                return answer[-1]
        window = pre[-6:] + "\n" + post[:6]
        for offset in range(len(answer) - 2):
            fragment = answer[offset:offset + 3]
            if fragment in window:
                return fragment
        # 长答案复述空前的主题词（"主色调是____"答"主色调加搭配色"），
        # 近处 6 字窗口看不到，放宽到 20 字仍只认 3-gram 重合
        if len(answer) >= 5:
            tail = pre[-20:]
            for offset in range(len(answer) - 2):
                fragment = answer[offset:offset + 3]
                if fragment in tail:
                    return fragment
    return None


def _leak_fragment(answer_text: str, stem_text: str, min_len: int = 10) -> str | None:
    """答案里有 >=min_len 字的片段直接出现在题干中（复述即可得分）。"""
    answer = re.sub(r"\s+", "", str(answer_text))
    stem = re.sub(r"\s+", "", str(stem_text))
    for index in range(0, len(answer) - min_len + 1):
        if answer[index:index + min_len] in stem:
            end = index + min_len
            while end < len(answer) and answer[index:end + 1] in stem:
                end += 1
            return answer[index:end]
    return None


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
    if re.search(r"[上下]图(?!案)|如图|图中|图片|附图|插图|四幅|两幅|几幅|下列图|图形\s*[A-D]"
                 r"|哪一幅|第[一二三四五六七八九十]幅|下面的画|以下画作|以下作品|下列作品|标志[A-D]"
                 r"|这[幅张]画|这[幅张]图|这[幅件]作品|该画|该图|该作品|本图"
                 r"|(?:以下|下列|下面|如下)[^，。？\n]{0,10}"
                 r"(?:作品|画作|图画|图案|图片|照片|剪纸|年画|素描|版画|油画|水彩)"
                 r"[^，。？\n]{0,6}(?:哪[一一个幅件种张]|第[一二三四五六七八九十]+[幅件张])"
                 r"|(?:以下|下列|下面|如下)[^，。？\n]{0,6}(?:哪[一一个幅件种张])"
                 r"[^，。？\n]{0,6}(?:作品|画作|图案|图片|剪纸|年画|绘画)",
                 str(card["stem"])):
        errors.append(f"{qid}: 题干依赖图片，无法独立作答")
    if len(str(card["stem"])) > 5000:
        errors.append(f"{qid}: 题干超过 5000 字")
    if card["type"] not in CHOICE_TYPES and re.search(
        r"(?:^|\n)\s*[A-D][．.、)）]\s*\S", str(card["stem"])
    ):
        errors.append(f"{qid}: 非选择题题干混入了 A/B/C/D 选项内容")
    if not str(card["analysis"]).strip():
        errors.append(f"{qid}: 解析为空")
    elif INTERNAL_FACT_WORDS.search(str(card["analysis"])):
        errors.append(f"{qid}: 解析出现“事实卡”内部字样")
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
            errors.append(f"{qid}: {card['type']} 必须 4 个选项，当前 {len(options)} 个")
        keys = [opt.get("key") for opt in options]
        if any(not key for key in keys) or len(set(keys)) != len(keys):
            errors.append(f"{qid}: 选项 key 为空或重复")
        if any(not str(opt.get("text", "")).strip() for opt in options):
            errors.append(f"{qid}: 存在空选项文本")
        if card["type"] == "single_choice":
            if answer.get("value") not in keys:
                errors.append(f"{qid}: 单选答案不在选项 key 中")
        else:
            values = answer.get("values")
            if not isinstance(values, list) or not 2 <= len(values) <= 3:
                errors.append(f"{qid}: 多选 answer.values 必须是 2–3 个选项 key")
            elif any(item not in keys for item in values) or len(set(values)) != len(values):
                errors.append(f"{qid}: 多选答案 key 非法或重复")
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
            if blanks == 0:
                errors.append(f"{qid}: 填空题题干没有空格（____）")
            elif blanks != len(values):
                errors.append(f"{qid}: 填空题 {blanks} 个空但给了 {len(values)} 个答案")
            else:
                pre = re.split(r"_{2,}", str(card["stem"]))[0].rstrip()
                if any(pre.endswith(word) for word in TRIGGER_PREDICATES) and any(
                    len(str(item)) > 3 for item in values
                ):
                    errors.append(f"{qid}: 空白紧跟“{pre[-2:]}”，答案过长，读进句子不通")
                overlap = _blank_overlap(str(card["stem"]), values)
                if overlap:
                    errors.append(
                        f"{qid}: 填空答案与题干前后文重叠“{overlap}”，拼进句子会重复不通"
                    )
                # 答案复述题干等于没答（与离线 validate_questions 同口径）
                stem_chars = set(normalize(re.sub(r"_{2,}", "", str(card["stem"]))))
                restated = [
                    str(item) for item in values
                    if len(normalize(item)) >= 5 and stem_chars
                    and len(set(normalize(item)) & stem_chars) / len(set(normalize(item))) >= 0.8
                ]
                if restated:
                    errors.append(f"{qid}: 填空答案基本重复题干 {restated}")
        if card["scoringMode"] != "auto":
            errors.append(f"{qid}: 填空题 scoringMode 必须是 auto")
    elif card["type"] == "short_answer":
        if options:
            errors.append(f"{qid}: 解答题不应有 options")
        if not str(answer.get("text", "")).strip():
            errors.append(f"{qid}: 解答题 answer.text 不能为空")
        if ANALYSIS_CHOICE_WORDS.search(str(card["analysis"])):
            errors.append(f"{qid}: 简答题解析出现“选项”措辞（简答题无选项）")
        fragment = _leak_fragment(answer.get("text", ""), card["stem"])
        if fragment:
            errors.append(f"{qid}: 题干已包含答案内容“{fragment[:20]}”，复述即可得分")
        if card["scoringMode"] not in {"manual", "ai"}:
            errors.append(f"{qid}: 解答题 scoringMode 必须是 manual 或 ai")

    stem_text = str(card.get("stem", ""))
    analysis_text = str(card.get("analysis", ""))
    if card["type"] != "true_false" and CLAIM_CONCLUSION.search(analysis_text):
        errors.append(f"{qid}: 非判断题解析使用“该说法”结论句")
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
                text = str(opt.get("text", "")).strip()
                if opt.get("key") == answer.get("value") and text in {"绿色", "绿"}:
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
