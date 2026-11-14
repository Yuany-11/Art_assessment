"""知识卡模板兜底：模型题过不了事实校验时，直接由事实卡构造题目。"""
from __future__ import annotations

import re
import uuid

from .factcheck import norm


MIN_TRUE_FALSE_CHARS = 6
PREDICATE_WORDS = re.compile(
    r"是|有|能|会|要|让|使|把|被|为|用|画|做|叫|称|需|应|可|不|得|属于|包括|指|分"
    r"|象征|代表|表示|表现|体现|反映|构成|形成|决定|影响|注意|使用|采用|适合|避免"
    r"|保持|追求|强调|讲究|表达|突出|增强|产生|吸收|显得|变得|组织|安排|观察|欣赏"
    r"|涂|勾|描|剪|折|捏|调|选|配|比|常"
)


def _is_complete_sentence(text: str) -> bool:
    """判断题题干必须成句：至少 6 个字，且含谓词。碎片（如“两个消失点”）直接不用。"""
    clean = re.sub(r"[\s\W_]+", "", str(text))
    if len(clean) < MIN_TRUE_FALSE_CHARS:
        return False
    return bool(PREDICATE_WORDS.search(clean))


def _sentence(text: str) -> str:
    text = str(text).strip()
    if text and text[-1] not in "。！？":
        text += "。"
    return text


def _pick(items: list, seed: int):
    return items[seed % len(items)] if items else None


def _short_claim(fact: dict, limit: int = 48) -> str:
    claim = str(fact.get("claim", "")).strip()
    if len(claim) <= limit:
        return claim
    cut = max(claim.rfind("，", 0, limit), claim.rfind("；", 0, limit))
    return claim[: cut if cut > 10 else limit]


def _correct_option(fact: dict) -> str:
    claim = _short_claim(fact)
    return claim.rstrip("。")


CANDIDATE_STOP = {
    "可以", "能够", "一种", "以及", "或者", "因此", "所以", "我们", "他们",
    "这个", "那个", "什么", "怎么", "不是", "就是", "还有", "其中", "通过",
}


def _blank_key(claim: str, fact: dict) -> str | None:
    def once(key: str) -> bool:
        return len(key) >= 2 and claim.count(key) == 1

    for key in fact.get("must_include") or []:
        if once(str(key)):
            return str(key)
    for part in str(fact.get("answer", "")).replace("，", "、").split("、"):
        if once(part):
            return part
    for part in re.split(r"[，。；、]", claim):
        for word in re.findall(r"[一-龥]{2,3}", part):
            if word not in CANDIDATE_STOP and claim.count(word) == 1:
                return word
    return None


def _token_free(text: str, facts: list[dict]) -> bool:
    """干扰项是否与事实卡关键词完全无关（多选判多用，双向包含算命中）。"""
    hay = norm(text)
    if not hay:
        return False
    for item in facts:
        tokens = [norm(key) for key in (item.get("must_include") or [])]
        tokens.append(norm(item.get("answer", "")))
        tokens.append(norm(item.get("kp", "")))
        for token in tokens:
            if token and (token in hay or hay in token):
                return False
    return True


def _contains_each_other(left: str, right: str, min_chars: int = 3) -> bool:
    a, b = norm(left), norm(right)
    return bool(a and b and min(len(a), len(b)) >= min_chars and (a in b or b in a))


def _without_containment(correct: str, candidates: list[str]) -> list[str]:
    """去掉与正确项或已选干扰项互相包含的选项，避免单选多解。"""
    kept: list[str] = []
    for item in candidates:
        if any(_contains_each_other(item, other) for other in [correct] + kept):
            continue
        kept.append(item)
    return kept


def _distractors(fact: dict, facts: list[dict], extra: list[dict], seed: int) -> list[str]:
    pool: list[str] = []
    correct = _correct_option(fact)
    answer_text = norm(fact.get("answer", ""))
    for item in list(facts) + list(extra):
        if item is fact:
            continue
        for wrong in item.get("misconceptions") or []:
            text = str(wrong).strip().rstrip("。")
            if not text or text in pool:
                continue
            if norm(text) == norm(correct):
                continue
            if answer_text and answer_text in norm(text):
                continue
            pool.append(text)
    return pool


def build_template_card(
    request: dict,
    facts: list[dict],
    extra_facts: list[dict] | None = None,
    seed: int = 0,
) -> dict | None:
    facts = [fact for fact in facts if fact.get("claim")]
    if not facts:
        return None
    fact = _pick(facts, seed)
    claim = str(fact["claim"]).strip()
    qtype = request["type"]
    extra = list(extra_facts or [])

    stem = ""
    options: list[dict] = []
    answer: dict = {}
    analysis = ""
    support_ids: list[str] = []  # 除主事实卡外，答案还引用了哪些卡
    score = 10 if qtype == "short_answer" else 5
    scoring = "manual" if qtype == "short_answer" else "auto"

    if qtype == "true_false":
        wrongs = [
            str(item).strip() for item in fact.get("misconceptions") or []
            if _is_complete_sentence(item)
        ]
        # 用高位决定“取易错说法还是取正确说法”，避免和选卡种子（seed % len(facts)）绑死，
        # 否则只有 facts[0] 那张卡能出“判断为错”的题。
        if wrongs and (seed // max(len(facts), 1)) % 3 == 0:
            stem = _sentence(_pick(wrongs, seed))
            answer = {"value": False}
            analysis = f"正确说法是：{_sentence(claim)}因此该说法错误。"
        else:
            if not _is_complete_sentence(claim):
                return None
            stem = _sentence(claim)
            answer = {"value": True}
            analysis = f"{_sentence(claim)}因此该说法正确。"

    elif qtype == "fill_blank":
        key = _blank_key(claim, fact)
        if not key:
            return None
        stem = claim.replace(key, "____", 1)
        answer = {"values": [key]}
        analysis = claim

    elif qtype in {"single_choice", "multiple_choice"}:
        correct = _correct_option(fact)
        wrongs = _distractors(fact, facts, extra, seed)
        wrongs = _without_containment(correct, wrongs)
        if qtype == "multiple_choice":
            others = [item for item in facts if item is not fact and item.get("claim")]
            if not others:
                return None
            second = _correct_option(_pick(others, seed))
            if norm(second) == norm(correct):
                return None
            # 干扰项不能命中本知识点任何事实卡关键词，否则离线判“多个选项符合事实卡”
            wrongs = [item for item in wrongs if _token_free(item, facts)][:2]
            options_text = [correct, second] + wrongs
            correct_keys = ["A", "B"]
        else:
            options_text = [correct] + wrongs[:3]
            correct_keys = ["A"]
        fillers = ["以上说法都不正确", "本题没有正确说法"]
        while len(options_text) < 4:
            options_text.append(fillers[len(options_text) - 2])
        options = [
            {"key": key, "text": text}
            for key, text in zip("ABCD", options_text[:4])
        ]
        stem = f"关于{request['knowledge_point']}，下列说法正确的是（ ）。"
        answer = {"value": "A"} if qtype == "single_choice" else {"values": correct_keys}
        analysis = f"正确答案：{_sentence(claim)}"

    elif qtype == "short_answer":
        # 题干写了“至少两点”，第二点必须是同知识点的另一张事实卡；
        # 同单元其他知识点的事实混进来会答非所问（互补色题混入“笔触”）
        partners = [
            item for item in facts
            if item.get("claim")
            and item.get("fact_id") != fact.get("fact_id")
            and item.get("claim") != claim
        ]
        partner = _pick(partners, seed) if partners else None
        if partner:
            stem = f"请说出{request['knowledge_point']}的相关要点（至少两点）。"
            answer = {"text": (
                f"{claim}（要点：{fact.get('answer', '')}）；"
                f"{partner['claim']}（要点：{partner.get('answer', '')}）"
            )}
            analysis = f"{_sentence(claim)}{_sentence(partner['claim'])}"
            if partner.get("fact_id"):
                support_ids.append(partner["fact_id"])
        else:
            stem = f"请简要说明{request['knowledge_point']}。"
            answer = {"text": f"{claim}（要点：{fact.get('answer', '')}）"}
            analysis = _sentence(claim)

    if not stem or not answer:
        return None

    if request["type"] == "fill_blank":
        blanks = stem.count("____")
        if blanks != len(answer["values"]):
            return None

    return {
        "id": f"tpl-{uuid.uuid4().hex[:12]}",
        "subject": "art",
        "grade": request["grade"],
        "unit_id": request["unit_id"],
        "unit_name": request["unit_name"],
        "knowledge_point": request["knowledge_point"],
        "type": qtype,
        "difficulty": request["difficulty"],
        "stem": stem,
        "options": options,
        "answer": answer,
        "analysis": analysis,
        "score": score,
        "scoringMode": scoring,
        "source": "self_instruct",
        "review_status": "pending",
        "created_by": "knowledge_template",
        "notes": f"模板兜底，依据 {'、'.join([fact.get('fact_id', '')] + support_ids)}",
        "generated_by": "template",
        "fact_ids": [fact.get("fact_id")] + support_ids,
    }
