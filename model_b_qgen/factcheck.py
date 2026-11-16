"""答案级事实校验：拦下格式合规但答案、解析与事实卡不一致的题。"""
from __future__ import annotations

import re

SYNONYMS = {
    "前进": ("靠近", "接近", "向前", "显得近", "更近"),
    "后退": ("远离", "向后", "退后", "显得远", "更远"),
    "遮挡": ("挡住", "遮住"),
    "张贴": ("贴",),
    "鲜艳": ("鲜明",),
    "安静": ("宁静", "平静"),
    "热情": ("活力", "欢快"),
}


def norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text), flags=re.UNICODE).lower()


def expand(text: str) -> str:
    s = norm(text)
    extra = ""
    for key, alts in SYNONYMS.items():
        if key in s or any(alt in s for alt in alts):
            extra += key + "".join(alts)
    return s + extra


def bigrams(text: str) -> set[str]:
    s = expand(text)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _keywords(fact: dict) -> list[str]:
    return [norm(k) for k in (fact.get("must_include") or []) if norm(k)]


def _hit_count(text: str, fact: dict) -> int:
    hay = norm(text)
    return sum(1 for key in _keywords(fact) if key and key in hay)


def _rank_facts(text: str, facts: list[dict]) -> list[tuple[float, int, dict]]:
    text_bg = bigrams(text)
    ranked = []
    for fact in facts:
        score = jaccard(text_bg, bigrams(fact.get("claim", "")))
        ranked.append((score, _hit_count(text, fact), fact))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked


def _fact_corpus(facts: list[dict]) -> str:
    return " ".join(norm(f"{f.get('claim', '')}{f.get('answer', '')}") for f in facts)


def check_grounded(card: dict, facts: list[dict]) -> list[str]:
    """题干里的核心内容必须能在事实卡里找到。"""
    if not facts:
        return []
    stem = str(card.get("stem", ""))
    ranked = _rank_facts(stem, facts)
    score, hits, _ = ranked[0]
    if score >= 0.18 or hits >= 2:
        return []
    if card.get("type") in {"single_choice", "multiple_choice", "short_answer"}:
        return []
    stem_bg = bigrams(stem)
    for fact in facts:
        for item in fact.get("misconceptions") or []:
            if jaccard(stem_bg, bigrams(item)) >= 0.50:
                return []
    return [f"{card.get('id', '<无 id>')}: 题干内容无法由事实卡支撑（相似度 {score:.2f}，要点命中 {hits}）"]


FORWARD = ("前进", "靠近", "接近", "更近", "显得近")
BACKWARD = ("后退", "远离", "向后", "更远", "显得远")
DIRECTION = "|".join(FORWARD + BACKWARD)


def _warm_cool_expected(stem: str) -> bool | None:
    pairs: list[tuple[str, bool]] = []
    for color, direction in re.findall(rf"(冷|暖)[^，。；！？]{{0,10}}?({DIRECTION})", stem):
        pairs.append((color, direction in FORWARD))
    for direction, color in re.findall(rf"({DIRECTION})[^，。；！？]{{0,6}}?(冷|暖)", stem):
        pairs.append((color, direction in FORWARD))
    if not pairs:
        return None
    return all((color == "暖") == forward for color, forward in pairs)


def check_true_false(card: dict, facts: list[dict]) -> list[str]:
    if not facts:
        return []
    stem = str(card.get("stem", ""))
    if any("暖" in f.get("claim", "") and "冷" in f.get("claim", "") for f in facts):
        expected = _warm_cool_expected(stem)
        if expected is not None:
            actual = (card.get("answer") or {}).get("value")
            if actual is not expected:
                return [f"{card.get('id', '<无 id>')}: 冷暖方向与事实卡相反（应为 {expected}）"]
            return []
    ranked = _rank_facts(stem, facts)
    score, hits, best = ranked[0]

    mis_score = 0.0
    for fact in facts:
        for item in fact.get("misconceptions") or []:
            mis_score = max(mis_score, jaccard(bigrams(stem), bigrams(item)))

    expected: bool | None = None
    reason = ""
    if mis_score >= 0.50:
        expected, reason = False, "命中事实卡的常见错误表述"
    elif score >= 0.20 or hits >= 2:
        expected, reason = True, "与事实卡表述一致"

    if expected is None:
        return [f"{card.get('id', '<无 id>')}: 判断题无法由事实卡判定真假"]
    actual = (card.get("answer") or {}).get("value")
    if actual is not expected:
        return [f"{card.get('id', '<无 id>')}: 判断题答案与事实卡相反（{reason}，应为 {expected}）"]
    return []


def repair_fill_answer(stem: str, values: list[str], analysis: str) -> list[str] | None:
    """单空填空题：按解析中的对应片段纠正答案；无法可靠对齐时返回 None。"""
    if len(re.findall(r"_{2,}", str(stem))) != 1 or len(values) != 1:
        return None
    pre, post = re.split(r"_{2,}", str(stem), maxsplit=1)
    hay = re.sub(r"\s+", "", str(analysis))
    anchor = re.sub(r"\s+", "", pre)[-10:]
    if len(anchor) < 5 or anchor not in hay:
        return None
    start = hay.find(anchor) + len(anchor)
    tail = re.sub(r"\s+", "", post)
    end = None
    for length in range(min(6, len(tail)), 1, -1):
        pos = hay.find(tail[:length], start)
        if pos != -1:
            end = pos
            break
    if end is None:
        end = start
        while end < len(hay) and hay[end] not in "。；，、！？":
            end += 1
    candidate = hay[start:end]
    if not candidate or len(candidate) > 12 or norm(candidate) == norm(values[0]):
        return None
    return [candidate]


def check_fill_blank(card: dict, facts: list[dict]) -> list[str]:
    if not facts:
        return []
    corpus = _fact_corpus(facts)
    stem = norm(card.get("stem", ""))
    errors = []
    for value in (card.get("answer") or {}).get("values") or []:
        key = norm(value)
        if not key:
            errors.append(f"{card.get('id', '<无 id>')}: 填空答案为空")
        elif key not in corpus:
            errors.append(f"{card.get('id', '<无 id>')}: 填空答案“{value}”不在事实卡中")
        elif len(key) >= 2 and key in stem:
            errors.append(f"{card.get('id', '<无 id>')}: 填空答案“{value}”已出现在题干中（同义反复）")
    return errors


EQUIV = re.compile(r"([一-龥A-Za-z]{2,10})(?:就是|也就是|即|又称|也称|也叫)([一-龥A-Za-z]{2,10})")


def _equivalence_pairs(facts: list[dict]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for fact in facts:
        for left, right in EQUIV.findall(str(fact.get("claim", ""))):
            left, right = norm(left), norm(right)
            if left and right and left != right:
                pairs.add((left, right))
    return pairs


def check_choice(card: dict, facts: list[dict], extra_facts: list[dict] | None = None) -> list[str]:
    if not facts:
        return []
    options = card.get("options") or []
    answer = card.get("answer") or {}
    if card.get("type") == "single_choice":
        keys = [answer.get("value")]
    else:
        keys = list(answer.get("values") or [])
    correct = [opt for opt in options if opt.get("key") in keys]
    if not correct:
        return []

    errors = []
    texts = [norm(opt.get("text", "")) for opt in options]
    if len(set(texts)) < len(texts):
        errors.append(f"{card.get('id', '<无 id>')}: 存在文本完全相同的选项")

    for left, right in _equivalence_pairs(list(facts) + list(extra_facts or [])):
        left_only = [opt for opt, text in zip(options, texts) if left in text and right not in text]
        right_only = [opt for opt, text in zip(options, texts) if right in text and left not in text]
        if left_only and right_only:
            errors.append(
                f"{card.get('id', '<无 id>')}: 选项同时出现同义概念“{left}”和“{right}”，答案不唯一"
            )
            break

    for opt in correct:
        text = str(opt.get("text", ""))
        supported = any(
            _hit_count(text, fact) >= 1
            or jaccard(bigrams(text), bigrams(fact.get("claim", ""))) >= 0.20
            for fact in facts
        )
        if not supported:
            errors.append(
                f"{card.get('id', '<无 id>')}: 正确选项“{text[:20]}”无事实卡依据"
            )

    stem = str(card.get("stem", ""))
    if card.get("type") == "single_choice" and not re.search(r"不是|不属于|不正确|错误|除外", stem):
        for fact in facts:
            answer_text = norm(fact.get("answer", ""))
            if len(answer_text) < 2:
                continue
            matched = [
                opt for opt in options
                if answer_text in norm(opt.get("text", ""))
            ]
            if len(matched) >= 2:
                errors.append(
                    f"{card.get('id', '<无 id>')}: 多个选项包含完整正确答案，答案不唯一"
                )
                break
        # 与事实卡答案逐字相同的选项没被标为答案（近义改写不查，只查整句一致）
        for fact in facts:
            answer_text = norm(fact.get("answer", ""))
            if len(answer_text) < 6:
                continue
            exact = [opt for opt in options if norm(opt.get("text", "")) == answer_text]
            if len(exact) == 1 and exact[0].get("key") != answer.get("value"):
                errors.append(
                    f"{card.get('id', '<无 id>')}: 答案标为 {answer.get('value')}，"
                    f"但选项 {exact[0].get('key')} 与事实卡答案“{fact.get('answer')}”一致"
                )
                break
    return errors


SHORT_ANSWER_COVERAGE = 0.30


def check_short_answer(card: dict, facts: list[dict]) -> list[str]:
    if not facts:
        return []
    text = str((card.get("answer") or {}).get("text", ""))
    if not any(_hit_count(text, fact) >= 1 for fact in facts):
        return [f"{card.get('id', '<无 id>')}: 简答答案未覆盖事实卡任何要点"]
    answer_bg = bigrams(text)
    corpus_bg = bigrams(_fact_corpus(facts))
    coverage = len(answer_bg & corpus_bg) / len(answer_bg) if answer_bg else 1.0
    if coverage < SHORT_ANSWER_COVERAGE:
        return [
            f"{card.get('id', '<无 id>')}: 简答答案仅 {coverage:.0%} 内容来自事实卡，"
            f"其余为卡外补充，可能编造"
        ]
    return []


TRUE_WORDS = re.compile(r"确实|的确|是对的|是正确的|符合事实|说法成立|属实的")
FALSE_TAIL = re.compile(r"因此.{0,6}(错误|不正确|不对|不成立)")


def check_analysis_consistency(card: dict) -> list[str]:
    """解析的结论必须和答案方向一致。"""
    if card.get("type") != "true_false":
        return []
    analysis = str(card.get("analysis", ""))
    actual = (card.get("answer") or {}).get("value")
    errors = []

    if actual is False and TRUE_WORDS.search(analysis) and FALSE_TAIL.search(analysis):
        errors.append(f"{card.get('id', '<无 id>')}: 解析承认题干成立却判错，答案与解析矛盾")
    if actual is True and re.search(r"因此.{0,6}(错误|不正确|不对|不成立)", analysis):
        errors.append(f"{card.get('id', '<无 id>')}: 答案判对但解析结论说错误")
    return errors


MULTI_OPTION_MIN_CHARS = 4


def check_single_choice_multi(card: dict, facts: list[dict]) -> list[str]:
    """单选题多解守卫：≥2 个选项是事实卡原句的片段，就说明题干问不出唯一答案。

    只对模型直出卡调用（模板干扰项来自 misconceptions，不走这条），
    避免把模板卡误判成多解。
    """
    if card.get("type") != "single_choice" or not facts:
        return []
    claims = [norm(fact.get("claim", "")) for fact in facts if fact.get("claim")]
    if not claims:
        return []
    hits = []
    for option in card.get("options") or []:
        text = norm(option.get("text", ""))
        if len(text) < MULTI_OPTION_MIN_CHARS:
            continue
        if any(text in claim for claim in claims):
            hits.append(str(option.get("key")))
    if len(hits) >= 2:
        return [
            f"{card.get('id', '<无 id>')}: 选项 {'/'.join(hits)} 都是事实卡原句片段，"
            f"单选题出现 {len(hits)} 个可判对的答案"
        ]
    return []


FUNCTION_WORDS = re.compile(r"作用|效果|意义")
# “调和”不算：暖色调和冷色调是正常说法，不是相调变灰那类事实卡
MIX_WORDS = ("相调", "混合")


def check_short_answer_domain(card: dict, facts: list[dict]) -> list[str]:
    """作用/效果/意义题不得引用“相调、混合、调和”类事实卡。

    例：问“色块并置有什么作用”，答案却写“降低纯度使颜色柔和”，
    那是互补色相调的效果，不是并置的效果。
    """
    if card.get("type") != "short_answer" or not facts:
        return []
    if not FUNCTION_WORDS.search(str(card.get("stem") or "")):
        return []
    text = str((card.get("answer") or {}).get("text", ""))
    if not text:
        return []
    for fact in facts:
        claim = str(fact.get("claim") or "")
        if not any(word in claim for word in MIX_WORDS):
            continue
        if _hit_count(text, fact) >= 1 or jaccard(bigrams(text), bigrams(claim)) >= 0.20:
            return [
                f"{card.get('id', '<无 id>')}: 作用题引用了“{claim[:16]}”这类相调/混合事实卡，"
                f"答的不是本知识点问的作用"
            ]
    return []


NEGATION_HEAD = r"(?:不|没有|不会|并非|不能)"


def _negated(key: str, text: str) -> bool:
    pattern = NEGATION_HEAD + r"[^，。；！？]{0,3}" + re.escape(key)
    return re.search(pattern, str(text)) is not None


def check_short_answer_negation(card: dict, facts: list[dict]) -> list[str]:
    """简答答案不得否定事实卡要点。

    例：事实卡说“光源方向决定物体的亮部、暗部和投影的位置”，
    答案却写“但不影响暗部的位置”，把反例当成正确结论。
    事实卡自己的 claim 里就是否定表述（“不出轮廓线”）时不算冲突。
    """
    if card.get("type") != "short_answer" or not facts:
        return []
    text = str((card.get("answer") or {}).get("text", ""))
    if not text:
        return []
    for fact in facts:
        claim = str(fact.get("claim") or "")
        for key in fact.get("must_include") or []:
            key = str(key).strip()
            if len(key) < 2:
                continue
            if _negated(key, text) and not _negated(key, claim):
                return [
                    f"{card.get('id', '<无 id>')}: 答案否定事实卡要点“{key}”，"
                    f"与事实卡“{claim[:16]}”矛盾"
                ]
    return []


NEGATION_WORDS = ("不会", "不能", "不是", "不")
CONTAIN_MIN_CHARS = 3
CHOICE_NEGATIONS = ("不", "没", "非", "无")


def _negation_variants(text: str) -> list[str]:
    """去掉否定词后的候选写法。

    “不会”既要试去掉整个词，也要试只去掉“不”（另一项通常保留“会”），
    否则“主体会更突出 / 主体不会更突出”这种对子认不出来。
    """
    s = norm(text)
    variants: list[str] = []
    for word in NEGATION_WORDS:
        if word in s:
            variants.append(s.replace(word, "", 1))
            if word != "不" and word.startswith("不"):
                variants.append(s.replace("不", "", 1))
    return variants


def _choice_pair(card: dict) -> list[tuple[dict, dict]]:
    options = [opt for opt in card.get("options") or [] if isinstance(opt, dict)]
    return [(options[i], options[j]) for i in range(len(options)) for j in range(i + 1, len(options))]


def check_single_choice_polarity(card: dict, facts: list[dict]) -> list[str]:
    """不定项极性守卫：只有“不会/不能/不是/不”之差的选项对，答案键必须和解析结论一致。

    例：A“主体会更突出”、B“主体不会更突出”，解析说“主体会更突出”，答案却标 B。
    """
    if card.get("type") != "single_choice":
        return []
    analysis = norm(card.get("analysis", ""))
    if not analysis:
        return []
    answer_key = str((card.get("answer") or {}).get("value", ""))
    for left, right in _choice_pair(card):
        left_n, right_n = norm(left.get("text", "")), norm(right.get("text", ""))
        if not left_n or not right_n:
            continue
        positive = negated = None
        if right_n in _negation_variants(left_n):
            positive, negated = right, left
        elif left_n in _negation_variants(right_n):
            positive, negated = left, right
        if positive is None:
            continue
        pos_in = norm(positive.get("text", "")) in analysis
        neg_in = norm(negated.get("text", "")) in analysis
        if neg_in:
            expected = str(negated.get("key"))
        elif pos_in:
            expected = str(positive.get("key"))
        else:
            continue
        if answer_key != expected:
            return [
                f"{card.get('id', '<无 id>')}: 答案是 {answer_key}，但解析结论对应 "
                f"{expected}（{'否定' if neg_in else '肯定'}式），答案键与解析极性矛盾"
            ]
    return []


def _has_choice_negation(text: str) -> bool:
    return any(word in norm(text) for word in CHOICE_NEGATIONS)


def check_single_choice_containment(card: dict, facts: list[dict]) -> list[str]:
    """选项包含关系守卫：一个选项是另一个的子串且都无否定词，单选题必然有多个可判对的答案。"""
    if card.get("type") != "single_choice":
        return []
    for left, right in _choice_pair(card):
        left_n, right_n = norm(left.get("text", "")), norm(right.get("text", ""))
        if len(left_n) < CONTAIN_MIN_CHARS or len(right_n) < CONTAIN_MIN_CHARS:
            continue
        if not (left_n in right_n or right_n in left_n):
            continue
        if _has_choice_negation(left_n) or _has_choice_negation(right_n):
            continue
        return [
            f"{card.get('id', '<无 id>')}: 选项 {left.get('key')}“{left.get('text', '')[:14]}”"
            f"包含于 {right.get('key')}“{right.get('text', '')[:14]}”，单选多解"
        ]
    return []


COLD_WARM_RANK = {"红": 10, "橙": 9, "黄": 8, "绿": 5, "蓝": 2, "紫": 1}


def check_single_choice_color_comparison(card: dict) -> list[str]:
    """比较型选项（“A比B冷/暖”）按暖色排序判定，多解或答案非真都拦。"""
    if card.get("type") != "single_choice":
        return []

    def rank(word: str) -> int | None:
        return COLD_WARM_RANK.get(word.strip().replace("色", ""))

    truths: list[tuple[str, bool]] = []
    for opt in card.get("options") or []:
        match = re.fullmatch(r"(.+?)比(.+?)(冷|暖)。?", str(opt.get("text", "")).strip())
        if not match:
            continue
        left, right = rank(match.group(1)), rank(match.group(2))
        if left is None or right is None:
            continue
        truths.append((str(opt.get("key")), left < right if match.group(3) == "冷" else left > right))
    if len(truths) < 2:
        return []

    true_keys = [key for key, ok in truths if ok]
    answer = (card.get("answer") or {}).get("value")
    qid = card.get("id", "<无 id>")
    if len(true_keys) > 1:
        return [f"{qid}: 比较型选项有多个正确项 {true_keys}，单选多解"]
    if not true_keys or answer not in true_keys:
        return [f"{qid}: 比较型单选答案 {answer!r} 与冷暖关系不符"]
    return []


ANALYSIS_MATCH_MIN = 2
NEGATION_CONTEXT = (
    "不是", "而非", "并非", "不能", "不可", "不应", "不要", "不会", "不算",
    "不同于", "而不是",
)


def _mentioned_in(analysis: str, text: str) -> bool:
    """选项表述是否出现在解析里；紧跟“不是/而非”等否定语境的出现不算肯定。"""
    token = norm(text)
    if len(token) < ANALYSIS_MATCH_MIN:
        return False
    start = 0
    while True:
        index = analysis.find(token, start)
        if index < 0:
            return False
        context = analysis[max(0, index - 4):index]
        if not any(context.endswith(word) for word in NEGATION_CONTEXT):
            return True
        start = index + 1


def check_single_choice_analysis_consistency(card: dict, facts: list[dict]) -> list[str]:
    """单选答案必须与解析同向：选中项要被解析肯定，且解析不能同时肯定别的选项。

    - 选中项没被解析肯定、别的选项被肯定 → 答案与解析不一致（如解析说纯度是鲜艳程度，答案选“明暗程度”）；
    - 选中项和别的选项都被肯定 → 单选多解（如“对折或角对角折”却单选 B）。
    相互包含的选项视为同一表述，不重复计数。
    """
    if card.get("type") != "single_choice":
        return []
    analysis = norm(card.get("analysis", ""))
    if not analysis:
        return []
    qid = card.get("id", "<无 id>")
    options = [opt for opt in card.get("options") or [] if isinstance(opt, dict)]
    answer_key = str((card.get("answer") or {}).get("value", ""))
    selected = next((opt for opt in options if str(opt.get("key")) == answer_key), None)
    if selected is None:
        return []
    selected_text = norm(selected.get("text", ""))
    if len(selected_text) < ANALYSIS_MATCH_MIN:
        return []
    selected_ok = _mentioned_in(analysis, selected.get("text", ""))
    rivals = []
    for opt in options:
        if opt is selected:
            continue
        text = norm(opt.get("text", ""))
        if len(text) < ANALYSIS_MATCH_MIN or text in selected_text or selected_text in text:
            continue
        if _mentioned_in(analysis, opt.get("text", "")):
            rivals.append(opt)
    if rivals and not selected_ok:
        rival = rivals[0]
        return [
            f"{qid}: 答案是 {answer_key}“{selected.get('text', '')}”，但解析结论对应 "
            f"{rival.get('key')}“{rival.get('text', '')}”，答案与解析不一致"
        ]
    if rivals and selected_ok:
        keys = "、".join(str(opt.get("key")) for opt in rivals[:2])
        return [f"{qid}: 解析同时肯定 {answer_key} 与 {keys}，单选多解"]
    return []


DIRECTION_SUBJECTS = ("亮部", "暗部", "投影", "影子", "高光")
DIRECTIONS = ("左上", "左下", "右上", "右下", "上方", "下方",
              "左侧", "右侧", "左边", "右边", "上面", "下面")
DIRECTION_RE = re.compile(rf"({'|'.join(DIRECTIONS)})")
CLAUSE_BREAK = re.compile(r"[，。；！？,;!?]")


def _direction_pairs(text: str) -> dict[str, set[str]]:
    """逐个主体找它后面同一分句里最近的方位。

    不用 findall 一次吃完，是因为“暗部和投影在右下”里 投影 会被 暗部 的匹配吞掉。
    """
    text = str(text)
    pairs: dict[str, set[str]] = {}
    for subject in DIRECTION_SUBJECTS:
        for match in re.finditer(re.escape(subject), text):
            tail = CLAUSE_BREAK.split(text[match.end():match.end() + 10])[0]
            direction = DIRECTION_RE.search(tail)
            if direction:
                pairs.setdefault(subject, set()).add(direction.group(1))
    return pairs


def check_short_answer_direction(card: dict, facts: list[dict]) -> list[str]:
    """简答答案的方位不能和事实卡相反。

    例：事实卡“暗部和投影在右下”，答案写“投影在左下”。
    同一主体两边都给了方位、且没有任何一个方位重合，才算矛盾；
    只说“投影背光”这种不带方位的表述不判。
    """
    if card.get("type") != "short_answer" or not facts:
        return []
    answer_pairs = _direction_pairs((card.get("answer") or {}).get("text", ""))
    if not answer_pairs:
        return []
    fact_pairs: dict[str, set[str]] = {}
    for fact in facts:
        text = f"{fact.get('claim', '')}{fact.get('answer', '')}"
        for subject, directions in _direction_pairs(text).items():
            fact_pairs.setdefault(subject, set()).update(directions)
    for subject, directions in answer_pairs.items():
        expected = fact_pairs.get(subject)
        if expected and not (directions & expected):
            return [
                f"{card.get('id', '<无 id>')}: 答案说{subject}在{'/'.join(sorted(directions))}，"
                f"事实卡是{'/'.join(sorted(expected))}，方位矛盾"
            ]
    return []


ANALYSIS_COVERAGE_MIN = 0.15
WORK_TITLE = re.compile(r"《([^》]{1,30})》")


def check_analysis_provenance(
    card: dict,
    facts: list[dict],
    min_coverage: float = ANALYSIS_COVERAGE_MIN,
) -> list[str]:
    """解析的关键内容必须出自事实卡原文。

    两条硬信号，命中任一条就认为解析在编造卡外内容：
    1. 解析与事实卡原文（claim + answer）的二元组覆盖率低于阈值；
    2. 解析提到《作品名》但事实卡里没有这个作品。
    只作阻断判据用，不放进 check_card，避免改变既有评测口径。
    """
    if not facts:
        return []
    analysis = str(card.get("analysis") or "")
    corpus = _fact_corpus(facts)
    errors: list[str] = []

    analysis_bg = bigrams(analysis)
    if analysis_bg:
        corpus_bg = bigrams(corpus)
        coverage = len(analysis_bg & corpus_bg) / len(analysis_bg)
        if coverage < min_coverage:
            errors.append(
                f"{card.get('id', '<无 id>')}: 解析仅 {coverage:.0%} 内容出自事实卡原文"
                f"（阈值 {min_coverage:.0%}），疑似补充卡外知识"
            )

    outside = [
        title for title in WORK_TITLE.findall(analysis)
        if norm(title) and norm(title) not in corpus
    ]
    if outside:
        errors.append(
            f"{card.get('id', '<无 id>')}: 解析提到事实卡外的作品《{outside[0]}》"
        )
    return errors


def check_card(card: dict, facts: list[dict], extra_facts: list[dict] | None = None) -> list[str]:
    """返回事实层错误；空列表表示答案能由事实卡支撑。"""
    if not facts:
        return []
    qtype = card.get("type")
    errors: list[str] = []
    errors.extend(check_grounded(card, facts))
    if qtype == "true_false":
        errors.extend(check_true_false(card, facts))
    elif qtype == "fill_blank":
        errors.extend(check_fill_blank(card, facts))
    elif qtype in {"single_choice", "multiple_choice"}:
        errors.extend(check_choice(card, facts, extra_facts))
    elif qtype == "short_answer":
        errors.extend(check_short_answer(card, facts))
    errors.extend(check_analysis_consistency(card))
    return errors
