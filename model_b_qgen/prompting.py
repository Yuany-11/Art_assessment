"""出题提示词共用逻辑。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .paths import PROJECT_ROOT

BASE = Path(__file__).resolve().parent
CATALOG_PATH = Path(os.getenv("QGEN_CATALOG", PROJECT_ROOT / "data" / "09_qgen" / "catalog_v2.json"))
FACT_PATH = Path(os.getenv("QGEN_FACTS", PROJECT_ROOT / "data" / "09_qgen" / "knowledge" / "kb_v1.jsonl"))
PROMPT_DIR = BASE / "prompts"

TYPE_LABELS = {
    "single_choice": "选择",
    "multiple_choice": "多选",
    "true_false": "判断",
    "fill_blank": "填空",
    "short_answer": "解答",
}

TYPE_RULES = {
    "single_choice": "4 个选项、key 为 A/B/C/D、只有一个正确答案；干扰项要是同学段容易混淆的概念，不能凑数；题干必须能脱离图片独立作答，不得出现“第几幅、哪一幅、下面的画作、以下画作、以下作品、下列作品、画面中哪、标志A-D、图中”等看图表述。",
    "multiple_choice": "4 个选项、key 为 A/B/C/D、有 2–3 个正确答案，answer 写 {\"values\":[\"A\",\"C\"]}；题干要写清判断依据，且必须能脱离图片独立作答。",
    "true_false": "只出教材或常识中能明确判定真假的陈述，答案只能是布尔值 true 或 false；解析最后一句必须写“因此该说法正确。”或“因此该说法错误。”，且 answer 必须与该结论一致；真实的陈述不少于三分之一。",
    "fill_blank": "1–3 个空，answer.values 按题干空格顺序给出唯一短答案，必须是具体内容（词语/数字），绝对不能是 A/B/C/D 或“选项X”；答案词语必须出现在解析中；解析不得出现“该说法正确/错误”，也不得写评分话术。",
    "short_answer": "answer.text 写 2–4 个得分点；题干要说明从哪个角度作答；解析必须解释答案依据，不得出现“给主要分、给满分、可加分、即可得分、这是从…作答”等评分话术。",
}

DIFFICULTY_DESC = {
    1: "基础识记，直接回忆课本概念或常识",
    2: "理解应用，需要比较、判断或简单分析",
    3: "综合运用，需要结合作品或方法进行分析说明",
}

LANGUAGE_RULES = {
    "1-2": "句子不超过 25 字，不用“构图、明度、笔触”等术语，多用“哪个、是不是”。",
    "3-4": "可引入对比色、主体、疏密；出现术语时用一句大白话解释。",
    "5-6": "可出现透视、明暗、色调；题干不超过 60 字。",
    "7-9": "可用美术史、风格、形式语言；解答题题干不超过 120 字，必须指明作答角度。",
}

TYPE_EXAMPLES = {
    "single_choice": {
        "stem": "标准大气压下，水的沸点是多少摄氏度？（ ）",
        "options": [{"key": "A", "text": "90"}, {"key": "B", "text": "100"},
                    {"key": "C", "text": "110"}, {"key": "D", "text": "120"}],
        "answer": {"value": "B"},
        "analysis": "标准大气压下，水的沸点是100摄氏度。",
        "score": 5,
    },
    "multiple_choice": {
        "stem": "以下属于可再生能源的有（ ）。",
        "options": [{"key": "A", "text": "太阳能"}, {"key": "B", "text": "风能"},
                    {"key": "C", "text": "煤炭"}, {"key": "D", "text": "水能"}],
        "answer": {"values": ["A", "B", "D"]},
        "analysis": "太阳能、风能、水能可以持续再生；煤炭属于不可再生能源。",
        "score": 5,
    },
    "true_false": {
        "stem": "剪纸是中国民间美术的一种。",
        "answer": {"value": True},
        "analysis": "剪纸在民间流传广泛，常用于节庆装饰，属于民间美术。因此该说法正确。",
        "score": 5,
    },
    "fill_blank": {
        "stem": "色彩三要素是____、____和____。",
        "answer": {"values": ["色相", "明度", "纯度"]},
        "analysis": "色相指颜色种类，明度指明暗程度，纯度指鲜艳程度。",
        "score": 5,
    },
    "short_answer": {
        "stem": "简述对称构图的特点。",
        "answer": {"text": "画面左右或上下对应，视觉上稳定、庄重；但处理不好容易呆板，常配合局部变化增加生气。"},
        "analysis": "对称构图通过左右或上下的对应关系形成稳定、庄重的视觉效果；若缺少局部变化，画面容易显得呆板。",
        "score": 10,
    },
}


def load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_facts(path: Path | None = None) -> dict[tuple[str, str], list[dict]]:
    facts: dict[tuple[str, str], list[dict]] = {}
    source = Path(path or FACT_PATH)
    if not source.exists():
        return facts
    with source.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            fact = json.loads(line)
            facts.setdefault((fact["unit_id"], fact["kp"]), []).append(fact)
    return facts


def facts_block(facts: list[dict]) -> str:
    lines = [
        "本题以第 1 条事实为主要依据，其余事实只作背景。",
        "只准考察下面事实卡写到的内容，不得补充卡外的作品、画家、文化常识或延伸例子；"
        "填空题答案、选择题正确选项必须是卡中原句里出现过的词。",
        "",
        "本题依据的事实卡（题干、答案、解析必须与之一致，不得编造卡外事实）：",
    ]
    for index, fact in enumerate(facts, 1):
        line = f"{index}. 事实：{fact.get('claim', '')} → 正确答案：{fact.get('answer', '')}"
        wrong = "；".join(str(item) for item in (fact.get("misconceptions") or []))
        if wrong:
            line += f"；常见错误：{wrong}"
        lines.append(line)
    return "\n".join(lines)


def unit_index(catalog: dict) -> dict[str, dict]:
    index = {}
    for grade_key, grade_info in catalog["grades"].items():
        for unit in grade_info["units"]:
            item = dict(unit)
            item["grade"] = int(grade_key)
            item["band"] = grade_info["band"]
            index[unit["unit_id"]] = item
    return index


def build_messages(request: dict, catalog: dict, facts: list[dict] | None = None) -> list[dict]:
    units = unit_index(catalog)
    unit = units[request["unit_id"]]
    band = unit["band"]
    qtype = request["type"]
    difficulty = request["difficulty"]
    example = json.dumps(TYPE_EXAMPLES[qtype], ensure_ascii=False, separators=(",", ":"))

    system = (PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
    template = (PROMPT_DIR / "user_template.txt").read_text(encoding="utf-8")
    user = template.format(
        grade=request["grade"],
        band=band,
        unit_name=unit["unit_name"],
        knowledge_point=request["knowledge_point"],
        type_label=TYPE_LABELS[qtype],
        type=qtype,
        difficulty=difficulty,
        difficulty_desc=DIFFICULTY_DESC[difficulty],
        type_rule=TYPE_RULES[qtype],
        language_rule=LANGUAGE_RULES[band],
        example=example,
    )
    if facts:
        block = facts_block(facts)
        marker = "格式示例"
        position = user.find(marker)
        if position == -1:
            user = f"{user}\n\n{block}"
        else:
            user = f"{user[:position]}{block}\n\n{user[position:]}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_json_object(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None
