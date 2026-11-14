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

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "09_qgen" / "catalog_v2.json"
KB_PATH = ROOT / "data" / "09_qgen" / "knowledge" / "kb_v1.jsonl"

TYPES = {"single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"}
SOURCES = {"golden", "public", "self_instruct", "image_template"}
REVIEW_STATUSES = {"pending", "approved", "rejected"}
REQUIRED_FIELDS = [
    "id", "subject", "grade", "unit_id", "unit_name", "knowledge_point",
    "type", "difficulty", "stem", "answer", "analysis", "score",
    "scoringMode", "source", "review_status", "created_by",
]
CHOICE_TYPES = {"single_choice", "multiple_choice"}


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


def load_fact_index(path: Path | str = KB_PATH) -> dict[tuple[str, str], list[dict]]:
    index: dict[tuple[str, str], list[dict]] = {}
    path = Path(path)
    if not path.exists():
        return index
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            fact = json.loads(line)
            index.setdefault((fact["unit_id"], fact["kp"]), []).append(fact)
    return index


def fact_tokens(fact: dict) -> list[str]:
    tokens: list[str] = [str(fact.get("kp", ""))]
    answer = fact.get("answer")
    if isinstance(answer, list):
        tokens.extend(str(item) for item in answer)
    elif answer not in (None, ""):
        tokens.append(str(answer))
    tokens.extend(str(item) for item in (fact.get("must_include") or []))
    return [token for token in tokens if normalize(token)]


def misconception_tokens(fact: dict) -> list[str]:
    return [str(item) for item in (fact.get("misconceptions") or []) if normalize(item)]


def answer_tokens(fact: dict) -> list[str]:
    answer = fact.get("answer")
    if isinstance(answer, list):
        raw = [str(item) for item in answer]
    elif answer not in (None, ""):
        raw = re.split(r"[、,，;；/]", str(answer))
    else:
        raw = []
    return [token for token in (t.strip() for t in raw) if normalize(token)]


def hit_token(text: str, tokens: list[str]) -> bool:
    """答案或解析是否命中事实卡关键词（双向包含，容忍“红”与“红色”）。"""
    target = normalize(text)
    if not target:
        return False
    for token in tokens:
        key = normalize(token)
        if key and (key in target or target in key):
            return True
    return False


def hit_claim(text: str, facts: list[dict]) -> bool:
    """答案是否直接摘自事实卡陈述，用于定义类填空（如“色调”“按题材”）。"""
    target = normalize(text)
    if not target:
        return False
    return any(target in normalize(str(fact.get("claim", ""))) for fact in facts)


def option_text(card: dict, key: str) -> str:
    for option in card.get("options") or []:
        if isinstance(option, dict) and option.get("key") == key:
            return str(option.get("text", ""))
    return ""


def claim_overlap(text: str, facts: list[dict]) -> float:
    grams = ngrams(text)
    best = 0.0
    for fact in facts:
        statements = [str(fact.get("claim", ""))]
        statements.extend(str(item) for item in (fact.get("misconceptions") or []))
        for statement in statements:
            best = max(best, jaccard(grams, ngrams(statement)))
    return best


def fact_errors(card: dict, facts: list[dict]) -> list[str]:
    """用事实卡校验答案与解析，抓事实编造和判断反向。"""
    qid = card.get("id", "<无 id>")
    if not facts:
        return [f"{qid}: 知识点没有事实卡，无法核对事实"]

    errors: list[str] = []
    all_tokens: list[str] = []
    wrong_tokens: list[str] = []
    for fact in facts:
        all_tokens.extend(fact_tokens(fact))
        wrong_tokens.extend(misconception_tokens(fact))
    all_tokens = list(dict.fromkeys(all_tokens))
    wrong_tokens = list(dict.fromkeys(wrong_tokens))

    qtype = card["type"]
    answer = card.get("answer") or {}
    if qtype == "single_choice":
        stem = str(card.get("stem", ""))
        options = [opt for opt in card.get("options") or [] if isinstance(opt, dict)]
        correct_key = str(answer.get("value", ""))
        correct = option_text(card, correct_key)
        negative = bool(re.search(r"不是|不属于|不正确|错误|不包括|除外", stem))
        if negative:
            if hit_token(correct, all_tokens):
                errors.append(f"{qid}: 否定题的正确选项不应命中事实卡")
            others = [opt for opt in options if opt.get("key") != correct_key]
            missed = [opt for opt in others
                      if not hit_token(str(opt.get("text", "")), all_tokens)]
            if missed:
                errors.append(f"{qid}: 否定题有其他选项未命中事实卡，无法判定")
        elif not hit_token(correct, all_tokens) and not hit_claim(correct, facts):
            errors.append(f"{qid}: 正确选项未命中事实卡关键词（{correct!r}）")
        # 用本知识点全部事实卡的词表判断唯一性：命中两个以上选项即报警。
        # 只看"最相似那一张卡"的 answer 会漏判——例如“三间色是橙绿紫”的答案
        # 整串拆不出单个颜色，选项“橙色”匹配不上，但另一张卡的 must_include 能。
        # 词面唯一性检查实测误杀约 7 成（“背景”“轮廓”等卡内相关概念会被
        # 误判成第二个正确答案），不在这里淘汰；多答案改由提示词约束 + 多选题承接。
        # 编造数值：答案或题干里的数字必须能在事实卡里找到
        facts_text = " ".join(str(f.get("claim", "")) + str(f.get("answer", ""))
                              for f in facts)
        fake_nums = [n for n in re.findall(r"\d+(?:\.\d+)?", correct + stem)
                     if n not in facts_text]
        if fake_nums:
            errors.append(f"{qid}: 答案含事实卡没有的数字 {fake_nums}")
        if re.search(r"最强|最大|最小|最好|最高|最低|最重要|最突出|最常见", correct + stem) \
                and "最" not in facts_text:
            errors.append(f"{qid}: 答案含最高级表述，事实卡没有比较依据")
        analysis_text = str(card.get("analysis", ""))
        for opt in options:
            key = str(opt.get("key", ""))
            if not key or key == correct_key:
                continue
            if re.search(rf"(?:选项\s*|答案\s*)?{key}\s*(?:也|同样)?(?:是)?正确的", analysis_text) \
                    and not re.search(rf"{key}\s*(?:不|并非)(?:是)?正确的", analysis_text):
                errors.append(f"{qid}: 解析承认选项 {key} 也正确")
        periods = re.findall(r"北宋|南宋|唐代|唐朝|元代|元朝|明代|明朝|清代|清朝|东晋|文艺复兴", stem)
        if periods:
            for opt in options:
                if opt.get("key") == correct_key:
                    continue
                text = str(opt.get("text", "")).strip()
                if len(text) < 2:
                    continue
                pos = analysis_text.find(text)
                if pos >= 0:
                    window = analysis_text[pos:pos + len(text) + 18]
                    if any(period in window for period in periods):
                        errors.append(f"{qid}: 解析显示选项 {opt.get('key')} 也符合同一朝代")
    elif qtype == "multiple_choice":
        options = [opt for opt in card.get("options") or [] if isinstance(opt, dict)]
        values = [str(v) for v in (answer.get("values") or [])]
        if not 2 <= len(values) <= 3:
            errors.append(f"{qid}: 多选答案必须是 2–3 个选项")
        for key in values:
            text = option_text(card, key)
            if not hit_token(text, all_tokens) and not hit_claim(text, facts):
                errors.append(f"{qid}: 多选正确选项 {key} 未命中事实卡（{text!r}）")
        hits = [opt for opt in options
                if hit_token(str(opt.get("text", "")), all_tokens)]
        if options and len(hits) != len(values):
            errors.append(f"{qid}: 多选题有 {len(hits)} 个选项符合事实卡，与答案数 {len(values)} 不符")
    elif qtype == "fill_blank":
        values = answer.get("values") or []
        bad = [str(v) for v in values
               if not hit_token(str(v), all_tokens) and not hit_claim(str(v), facts)]
        if bad:
            errors.append(f"{qid}: 填空答案未命中事实卡关键词 {bad}")
    elif qtype == "true_false":
        stem = str(card.get("stem", ""))
        truth = answer.get("value")
        # 只取与题干最接近的那条事实卡，避免把另一张卡的正确说法当成易错项
        best_fact = max(facts, key=lambda fact: claim_overlap(stem, [fact]))
        best_tokens = fact_tokens(best_fact)
        best_wrong = misconception_tokens(best_fact)
        analysis_text = str(card.get("analysis", ""))
        analysis_hits = hit_token(analysis_text, all_tokens)
        if not hit_token(stem, best_tokens + best_wrong) and not analysis_hits:
            errors.append(f"{qid}: 判断题干未命中事实卡关键词")
        if claim_overlap(stem, [best_fact]) < 0.1 and not analysis_hits:
            errors.append(f"{qid}: 判断题干与事实卡陈述关联过低")
        if truth is True and hit_token(stem, best_wrong):
            errors.append(f"{qid}: 判断题把事实卡的易错说法判为正确")
        stem_norm = normalize(stem)
        claim_norm = normalize(str(best_fact.get("claim", "")))
        if len(stem_norm) >= 8 and stem_norm in claim_norm and truth is not True:
            errors.append(f"{qid}: 判断题干与事实卡陈述一致，应判正确")
        if len(stem_norm) >= 6 and any(stem_norm in normalize(w) for w in best_wrong) \
                and truth is not False:
            errors.append(f"{qid}: 判断题干与事实卡易错说法一致，应判错误")
        claim_sim = jaccard(ngrams(stem), ngrams(str(best_fact.get("claim", ""))))
        wrong_sim = max((jaccard(ngrams(stem), ngrams(w)) for w in best_wrong), default=0.0)
        if truth is False and claim_sim >= 0.55 and claim_sim > wrong_sim + 0.08:
            errors.append(f"{qid}: 判断题干与事实卡陈述高度相似，应判正确")
        if truth is True and wrong_sim >= 0.55 and wrong_sim > claim_sim + 0.08:
            errors.append(f"{qid}: 判断题干与事实卡易错说法高度相似，应判错误")
        negation = re.search(r"不|没有|不能|并非|无法|错误", stem)
        wrong_embedded = any(normalize(w) in stem_norm for w in best_wrong if normalize(w))
        if truth is False and not negation and not wrong_embedded:
            errors.append(f"{qid}: 错误陈述既无否定词，也不含事实卡易错说法")
    elif qtype == "short_answer":
        text = str(answer.get("text", ""))
        if not hit_token(text, all_tokens) and not hit_claim(text, facts):
            errors.append(f"{qid}: 解答题答案未命中事实卡关键词")

    if not hit_token(str(card.get("analysis", "")), all_tokens):
        errors.append(f"{qid}: 解析未体现事实卡关键依据")
    return errors


def validate_card(card: dict, units: dict[str, dict], catalog: dict,
                  fact_index: dict[tuple[str, str], list[dict]] | None = None) -> list[str]:
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
    stem_text = str(card["stem"])
    has_image = any(isinstance(res, dict) and res.get("type") == "image" and res.get("file")
                    for res in card.get("resources") or [])
    if not has_image and (
            re.search(r"[上下]图|如图|(?<![构意地蓝试制])图中|图片|附图|插图|四幅|两幅图|几幅图"
                      r"|下列图(?!形)|图形\s*[A-D]|哪一幅|第[一二三四五六七八九十]幅|下面的画"
                      r"|以下画作|以下作品|下列作品|标志[A-D]|这[幅张组]画|那[幅张]画|步骤图|示意图|所给图", stem_text)
            or ("两幅" in stem_text and "《" not in stem_text)):
        errors.append(f"{qid}: 题干依赖图片，无法独立作答")
    if len(str(card["stem"])) > 5000:
        errors.append(f"{qid}: 题干超过 5000 字")
    if not str(card["analysis"]).strip():
        errors.append(f"{qid}: 解析为空")
    elif re.search(r"根据事实卡|依据事实卡|按照事实卡|参考事实卡|事实卡中", str(card["analysis"])):
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
            errors.append(f"{qid}: 选择题必须 4 个选项，当前 {len(options)} 个")
        bad_opts = [opt for opt in options if not isinstance(opt, dict)]
        if bad_opts:
            errors.append(f"{qid}: 选项必须是对象(key/text)，当前有 {len(bad_opts)} 个不是")
            return errors
        keys = [opt.get("key") for opt in options]
        if any(not key for key in keys) or len(set(keys)) != len(keys):
            errors.append(f"{qid}: 选项 key 为空或重复")
        if any(not str(opt.get("text", "")).strip() for opt in options):
            errors.append(f"{qid}: 存在空选项文本")
        texts = [str(opt.get("text", "")).strip() for opt in options]
        if len(texts) != len(set(texts)):
            errors.append(f"{qid}: 选项文本重复，答案不唯一")
        if card["type"] == "multiple_choice":
            values = answer.get("values")
            if not isinstance(values, list) or not 2 <= len(values) <= 3:
                errors.append(f"{qid}: 多选答案必须是 2–3 个 key")
            else:
                if len(set(values)) != len(values):
                    errors.append(f"{qid}: 多选答案有重复 key")
                if not set(str(v) for v in values) <= set(keys):
                    errors.append(f"{qid}: 多选答案不在选项 key 中")
        elif answer.get("value") not in keys:
            errors.append(f"{qid}: 单选答案不在选项 key 中")
        if card["scoringMode"] != "auto":
            errors.append(f"{qid}: 选择题 scoringMode 必须是 auto")
    elif card["type"] == "true_false":
        if options:
            errors.append(f"{qid}: 判断题不应有 options")
        if not isinstance(answer.get("value"), bool):
            errors.append(f"{qid}: 判断题 answer.value 必须是布尔值")
        analysis_tail = next(
            (part for part in reversed(re.split(r"[。！？!?]", str(card.get("analysis", "")))) if part.strip()),
            "",
        )
        expected = None
        if "正确" in analysis_tail and "错误" not in analysis_tail:
            expected = True
        elif "错误" in analysis_tail and "正确" not in analysis_tail:
            expected = False
        if expected is not None and isinstance(answer.get("value"), bool) and answer["value"] != expected:
            errors.append(f"{qid}: 答案 {answer['value']} 与解析结论相反")
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
            letters = [v for v in values if re.fullmatch(r"[A-Da-d]", str(v).strip())]
            if letters:
                errors.append(f"{qid}: 填空答案不能是选项字母 {letters}")
            elif any(re.search(r"选项|答案\s*[A-D]", str(v)) for v in values):
                errors.append(f"{qid}: 填空答案含选项字样")
            blanks = len(re.findall(r"_{2,}", str(card["stem"])))
            if blanks and blanks != len(values):
                errors.append(f"{qid}: 填空题 {blanks} 个空但给了 {len(values)} 个答案")
            # 答案复述题干等于没答，如题干“____对人的情绪有影响”答“颜色影响情绪心理”
            stem_chars = set(normalize(re.sub(r"_{2,}", "", str(card["stem"]))))
            restated = [str(v) for v in values
                        if len(normalize(v)) >= 5 and stem_chars
                        and len(set(normalize(v)) & stem_chars) / len(set(normalize(v))) >= 0.8]
            if restated:
                errors.append(f"{qid}: 填空答案基本重复题干 {restated}")
        if card["scoringMode"] != "auto":
            errors.append(f"{qid}: 填空题 scoringMode 必须是 auto")
    elif card["type"] == "short_answer":
        if options:
            errors.append(f"{qid}: 解答题不应有 options")
        if not str(answer.get("text", "")).strip():
            errors.append(f"{qid}: 解答题 answer.text 不能为空")
        if card["scoringMode"] not in {"manual", "ai"}:
            errors.append(f"{qid}: 解答题 scoringMode 必须是 manual 或 ai")

    analysis_all = str(card.get("analysis", ""))
    if card["type"] not in CHOICE_TYPES and re.search(r"选项\s*[A-D]", analysis_all):
        errors.append(f"{qid}: 非选择题解析引用选项字母")
    if card["type"] != "true_false" and re.search(r"该说法(?:正确|错误)", analysis_all):
        errors.append(f"{qid}: 非判断题解析使用“该说法”结论句")
    if re.search(r"课标\s*2022|课程标准[（(]?2022|学段[)）]", analysis_all):
        errors.append(f"{qid}: 解析引用内部资料出处")

    if fact_index is not None:
        facts = fact_index.get((str(card.get("unit_id", "")),
                                str(card.get("knowledge_point", ""))), [])
        errors.extend(fact_errors(card, facts))

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
    parser.add_argument("--kb", default=str(KB_PATH), help="事实卡 jsonl")
    parser.add_argument("--no-fact-check", action="store_true", help="跳过事实卡核对")
    args = parser.parse_args()

    catalog = load_catalog()
    units = unit_index(catalog)
    fact_index = None if args.no_fact_check else load_fact_index(args.kb)
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
                all_errors.extend(validate_card(card, units, catalog, fact_index))

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
