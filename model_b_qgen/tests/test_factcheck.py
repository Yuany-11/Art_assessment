"""用人工核对发现的真实错题做回归。"""
from __future__ import annotations

from model_b_qgen.factcheck import check_card

FACTS = {
    "形状组合": [
        {
            "fact_id": "g1-u2-形状组合-03",
            "claim": "形状之间相互遮挡时，前面的形状画完整，后面的形状只画露出的部分。",
            "answer": "前完整、后露部分",
            "must_include": ["遮挡", "前", "后"],
            "misconceptions": ["后面的形状把被挡住的部分也画出来"],
        }
    ],
    "年画": [
        {
            "fact_id": "g3-u4-年画-01",
            "claim": "年画是春节张贴的民间绘画，题材有门神、娃娃、戏曲故事等。",
            "answer": "春节张贴、门神娃娃戏曲",
            "must_include": ["春节", "门神", "娃娃"],
            "misconceptions": ["年画是西方油画"],
        }
    ],
    "色调": [
        {
            "fact_id": "g6-u2-色调-03",
            "claim": "色调可以表达季节、时间和情绪，如暖色调表现温暖。",
            "answer": "表达季节时间和情绪",
            "must_include": ["季节", "情绪"],
            "misconceptions": ["色调没有作用"],
        }
    ],
    "色彩象征": [
        {
            "fact_id": "g6-u2-色彩象征-02",
            "claim": "绿色常象征生命、自然和环保，蓝色常象征科技和冷静。",
            "answer": "绿生命环保，蓝科技冷静",
            "must_include": ["绿", "生命", "蓝", "科技"],
            "misconceptions": ["绿色象征科技"],
        }
    ],
    "冷暖情感": [
        {
            "fact_id": "g6-u2-冷暖情感-01",
            "claim": "暖色常表达热情、温暖、欢快，冷色常表达安静、冷静、忧郁。",
            "answer": "暖热情，冷安静",
            "must_include": ["暖", "热情", "冷", "安静"],
            "misconceptions": ["暖色让人忧郁"],
        }
    ],
    "结构": [
        {
            "fact_id": "g7-u1-结构-03",
            "claim": "理解结构能帮助画准透视和明暗，避免形体变形。",
            "answer": "帮助透视明暗",
            "must_include": ["结构", "透视", "明暗"],
            "misconceptions": ["结构不影响明暗"],
        }
    ],
    "冷暖色": [
        {
            "fact_id": "g7-u2-冷暖色-03",
            "claim": "冷暖对比能表现空间和情绪，暖色前进，冷色后退。",
            "answer": "暖前进冷后退",
            "must_include": ["暖", "前进", "冷", "后退"],
            "misconceptions": ["冷色前进"],
        }
    ],
}


def card(**kwargs):
    base = {
        "id": "t-1",
        "type": "true_false",
        "stem": "",
        "options": [],
        "answer": {},
        "analysis": "",
    }
    base.update(kwargs)
    return base


def test_reject_contradictory_true_false():
    c = card(
        stem="两个圆圈叠加，下面的圆圈会遮挡住上面的圆圈。",
        answer={"value": False},
        analysis="当两个圆圈叠加时，下面的圆圈确实会遮挡住上面的圆圈，但不会画出被遮挡部分的内容。因此该说法错误。",
    )
    assert check_card(c, FACTS["形状组合"])


def test_reject_unsupported_blue_mood():
    c = card(
        stem="在西方文化中，蓝色通常代表悲伤和忧郁。",
        answer={"value": False},
        analysis="在西方文化中，蓝色确实常被用来象征悲伤和忧郁。因此该说法错误。",
    )
    assert check_card(c, FACTS["色彩象征"])


def test_reject_unsupported_blue_peace():
    c = card(
        stem="在西方文化中，蓝色通常被用来代表和平与宁静。",
        answer={"value": False},
        analysis="西方文化中，蓝色常象征科技和冷静，而非和平与宁静。因此该说法错误。",
    )
    assert check_card(c, FACTS["色彩象征"])


def test_reject_fill_blank_outside_fact():
    c = card(
        type="fill_blank",
        stem="画面中的______色调通常表现了秋天的气息。",
        answer={"values": ["黄色"]},
        analysis="画面中的黄色色调通常表现了秋天的气息。",
    )
    assert check_card(c, FACTS["色调"])


def test_accept_grounded_fill_blank():
    c = card(
        type="fill_blank",
        stem="年画是一种____的民间绘画。",
        answer={"values": ["春节张贴"]},
        analysis="年画是中国传统节日春节时张贴的一种民间绘画形式。",
    )
    assert check_card(c, FACTS["年画"]) == []


def test_accept_true_warm_forward():
    c = card(
        stem="暖色比冷色更接近观者，显得向前。",
        answer={"value": True},
        analysis="暖色有前进感，冷色后退。因此该说法正确。",
    )
    assert check_card(c, FACTS["冷暖色"]) == []


def test_accept_true_cool_calm():
    c = card(
        stem="冷色常让人感到宁静平静。",
        answer={"value": True},
        analysis="冷色常表达安静、冷静。因此该说法正确。",
    )
    assert check_card(c, FACTS["冷暖情感"]) == []


def test_reject_wrong_topic_structure():
    c = card(
        type="fill_blank",
        stem="达芬奇的作品《最后的晚餐》通过______表现了人物之间的空间关系。",
        answer={"values": ["透视"]},
        analysis="达芬奇在《最后的晚餐》中运用了透视手法表现空间关系。",
    )
    assert check_card(c, FACTS["结构"])


def test_reject_choice_without_support():
    c = card(
        type="single_choice",
        stem="关于画面的安排，下列描述正确的是（ ）。",
        options=[
            {"key": "A", "text": "画面中央放置所有的主题元素"},
            {"key": "B", "text": "主体在画面的中心，周围留有空间"},
            {"key": "C", "text": "主体集中在画面的一角，留白较多"},
            {"key": "D", "text": "主体在画面四边，均匀分布"},
        ],
        answer={"value": "B"},
        analysis="主体在画面中心，周围留有空间。",
    )
    assert check_card(c, FACTS["形状组合"])


def test_reject_choice_key_on_wrong_option():
    c = card(
        type="single_choice",
        stem="关于冷暖色的说法，正确的是（ ）。",
        options=[
            {"key": "A", "text": "暖前进冷后退"},
            {"key": "B", "text": "冷色比暖色更靠前"},
            {"key": "C", "text": "冷暖不影响空间"},
            {"key": "D", "text": "暖色总是后退"},
        ],
        answer={"value": "B"},
        analysis="暖色前进，冷色后退。",
    )
    assert check_card(c, FACTS["冷暖色"])


def test_accept_choice_key_on_matching_option():
    c = card(
        type="single_choice",
        stem="关于冷暖色的说法，正确的是（ ）。",
        options=[
            {"key": "A", "text": "冷色比暖色更靠前"},
            {"key": "B", "text": "暖前进冷后退"},
            {"key": "C", "text": "冷暖不影响空间"},
            {"key": "D", "text": "暖色总是后退"},
        ],
        answer={"value": "B"},
        analysis="暖色前进，冷色后退。",
    )
    assert check_card(c, FACTS["冷暖色"]) == []


def test_reject_cool_forward():
    c = card(
        stem="冷色比暖色更靠近观者。",
        answer={"value": True},
        analysis="冷色前进。因此该说法正确。",
    )
    assert check_card(c, FACTS["冷暖色"])


def test_reject_wrong_false_claim():
    c = card(
        stem="年画是西方油画。",
        answer={"value": True},
        analysis="年画确实是西方油画。因此该说法正确。",
    )
    assert check_card(c, FACTS["年画"])
