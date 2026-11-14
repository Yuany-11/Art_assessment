"""答案语法纠偏、简答解析措辞、题干泄题三条规则的离线测试。"""
from __future__ import annotations

import unittest

from model_b_qgen.factcheck import repair_fill_answer
from model_b_qgen.fallback import build_template_card
from model_b_qgen.prompting import load_catalog, unit_index
from model_b_qgen.validator import _blank_overlap, validate_card


class RepairFillAnswerTest(unittest.TestCase):
    def test_repairs_noun_to_predicate(self) -> None:
        stem = "一幅画要有主色调，其他颜色围绕主色调________。"
        analysis = "一幅画要有主色调，其他颜色围绕主色调搭配。注意搭配颜色时要注意面积大小。"
        self.assertEqual(repair_fill_answer(stem, ["搭配色"], analysis), ["搭配"])

    def test_keeps_answer_when_already_fits(self) -> None:
        stem = "冷和暖是相互____出来的，不是绝对的。"
        analysis = "冷和暖是相互比较出来的，不是绝对的。"
        self.assertIsNone(repair_fill_answer(stem, ["比较"], analysis))

    def test_skips_when_anchor_too_short(self) -> None:
        stem = "将_________的颜色放在一起，画面显得鲜艳、醒目。"
        analysis = "把差别很大的颜色放在一起，画面显得鲜艳、醒目。"
        self.assertIsNone(repair_fill_answer(stem, ["差别大"], analysis))

    def test_skips_multi_blank(self) -> None:
        stem = "常见的基本形状包括____、____、____。"
        analysis = "常见的基本形状包括圆形、正方形和三角形。"
        self.assertIsNone(repair_fill_answer(stem, ["圆形", "正方形", "三角形"], analysis))


class BlankOverlapTest(unittest.TestCase):
    def test_rejects_answer_repeating_post(self) -> None:
        stem = "年画是________张贴的民间绘画，题材有门神、娃娃、戏曲故事等。"
        self.assertEqual(_blank_overlap(stem, ["春节张贴"]), "张贴")

    def test_rejects_answer_repeating_pre(self) -> None:
        stem = "画球体时要注意____，亮部与暗部要统一。"
        self.assertEqual(_blank_overlap(stem, ["注意光源"]), "注意")

    def test_rejects_restating_pre_phrase(self) -> None:
        stem = "在一幅画中，主色调是________，其他颜色围绕它进行搭配。"
        self.assertEqual(_blank_overlap(stem, ["主色调加搭配色"]), "主色调")

    def test_rejects_long_answer_restating_far_subject(self) -> None:
        stem = "在一幅画中，主色调为蓝色，搭配色为绿色，这种搭配方式称为__________。"
        self.assertEqual(_blank_overlap(stem, ["主色调加搭配色"]), "搭配色")

    def test_rejects_answer_already_listed_in_stem(self) -> None:
        stem = "圆形、正方形、三角形是_________。"
        self.assertIsNotNone(_blank_overlap(stem, ["圆形、正方形、三角形"]))

    def test_allows_long_answer_with_new_wording(self) -> None:
        stem = "水彩画的特点是画面________。"
        self.assertIsNone(_blank_overlap(stem, ["透明轻快、湿润流畅"]))

    def test_rejects_repeated_glue_char(self) -> None:
        stem = "在两点透视中，物体的两个侧面通过________消失。"
        self.assertEqual(_blank_overlap(stem, ["角对观察者"]), None)
        stem = "黄金分割点大约在画面的____处。"
        self.assertEqual(_blank_overlap(stem, ["约0.618处"]), "处")

    def test_allows_short_answer_before_color(self) -> None:
        stem = "在冷暖对比中，____色比红色冷，但比蓝色暖。"
        self.assertIsNone(_blank_overlap(stem, ["橙"]))

    def test_allows_answer_repeating_far_stem_text(self) -> None:
        stem = "涂色时尽量不要涂出轮廓线，需要留白的地方要留出来。正确的做法是________。"
        self.assertIsNone(_blank_overlap(stem, ["不涂出轮廓，注意留白"]))

    def test_allows_yellow_tone(self) -> None:
        stem = "画面中的______色调通常表现了秋天的气息。"
        self.assertIsNone(_blank_overlap(stem, ["黄色"]))

    def test_rejects_multi_blank_duplication(self) -> None:
        stem = "黄金分割点大约在画面的____处。黄金分割比约为1比____。"
        self.assertEqual(_blank_overlap(stem, ["0.618处", "1比1.618"]), "处")
        stem = "水彩画用水______颜料，画面______、轻快。"
        self.assertEqual(_blank_overlap(stem, ["调和", "透明轻快"]), "轻快")

    def test_allows_normal_multi_blank(self) -> None:
        stem = "常见的基本形状包括____、____和____。"
        self.assertIsNone(_blank_overlap(stem, ["圆形", "正方形", "三角形"]))

    def test_rejects_answer_ending_with_color_before_de(self) -> None:
        stem = "在画面中，把_________的颜色放在一起，画面显得柔和、和谐。"
        self.assertEqual(_blank_overlap(stem, ["相近颜色"]), "颜色")

    def test_allows_possessive_after_blank(self) -> None:
        stem = "绘画中，____的运用很重要。"
        self.assertIsNone(_blank_overlap(stem, ["对比色"]))

    def test_allows_repeat_after_clause_comma(self) -> None:
        stem = "____，形式要服务于功能。"
        self.assertIsNone(_blank_overlap(stem, ["功能决定形式"]))


class QualityRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()
        cls.units = unit_index(cls.catalog)
        cls.fill_unit = next(u for u in cls.units.values() if "fill_blank" in u["allowed_types"])
        cls.short_unit = next(u for u in cls.units.values() if "short_answer" in u["allowed_types"])

    def _fill_card(self, stem: str, values: list[str]) -> dict:
        unit = self.fill_unit
        return {
            "id": "t-fill",
            "subject": "art",
            "grade": unit["grade"],
            "unit_id": unit["unit_id"],
            "unit_name": unit["unit_name"],
            "knowledge_point": unit["knowledge_points"][0],
            "type": "fill_blank",
            "difficulty": unit["difficulty_range"][0],
            "stem": stem,
            "options": [],
            "answer": {"values": values},
            "analysis": "测试解析。",
            "score": 5,
            "scoringMode": "auto",
            "source": "golden",
            "review_status": "pending",
            "created_by": "test",
        }

    def _short_card(self, stem: str, answer: str, analysis: str) -> dict:
        unit = self.short_unit
        return {
            "id": "t-short",
            "subject": "art",
            "grade": unit["grade"],
            "unit_id": unit["unit_id"],
            "unit_name": unit["unit_name"],
            "knowledge_point": unit["knowledge_points"][0],
            "type": "short_answer",
            "difficulty": unit["difficulty_range"][0],
            "stem": stem,
            "options": [],
            "answer": {"text": answer},
            "analysis": analysis,
            "score": 10,
            "scoringMode": "manual",
            "source": "golden",
            "review_status": "pending",
            "created_by": "test",
        }

    def test_rejects_deictic_work_stem(self) -> None:
        card = self._fill_card("以下哪种剪纸作品的线条分布最疏松？____", ["线条稀疏"])
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("依赖图片" in error for error in errors))

    def test_allows_artist_knowledge_stem(self) -> None:
        card = self._short_card(
            "下列哪位画家的作品更倾向于写意风格？",
            "徐渭的作品更倾向于写意风格。",
            "徐渭是明代写意花鸟画家。",
        )
        errors = validate_card(card, self.units, self.catalog)
        self.assertFalse(any("依赖图片" in error for error in errors))

    def test_predicate_blank_rejects_long_answer(self) -> None:
        card = self._fill_card("在风景画中，近处的树木比远处的山显得____。", ["近大远小"])
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("答案过长" in error for error in errors))

    def test_predicate_blank_accepts_adjective(self) -> None:
        card = self._fill_card("在风景画中，近处的树木比远处的山显得____。", ["大"])
        errors = validate_card(card, self.units, self.catalog)
        self.assertFalse(any("答案过长" in error for error in errors))

    def test_short_answer_analysis_rejects_choice_wording(self) -> None:
        card = self._short_card("简述环境设计应满足的需求。", "满足使用需求、美观和生态。", "正确答案为 B，即满足使用需求、美观和生态。")
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("选项" in error for error in errors))

    def test_short_answer_analysis_rejects_selection_wording(self) -> None:
        card = self._short_card(
            "简述主题创作的要求及表现形式。",
            "明确主题，选择合适的内容和形式；内容与形式统一，形式服务于主题表达。",
            "主题创作要求内容与形式统一，形式服务于主题表达，因此选择B项。",
        )
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("选项" in error for error in errors))

    def test_short_answer_rejects_stem_leak(self) -> None:
        card = self._short_card(
            "请说明色彩三要素。色相是色彩三要素之一，另外两个是明度和纯度。",
            "色相是色彩三要素之一，另外两个是明度和纯度。",
            "色相、明度、纯度是色彩三要素。",
        )
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("题干已包含答案内容" in error for error in errors))

    def test_short_answer_normal_passes(self) -> None:
        card = self._short_card(
            "简述欣赏作品时可以从哪些方面描述。",
            "可以从内容、色彩、构图和感受四个方面描述。",
            "可以从内容、色彩、构图和感受四个方面进行描述。",
        )
        self.assertEqual(validate_card(card, self.units, self.catalog), [])

    def test_template_short_answer_does_not_leak(self) -> None:
        unit = self.short_unit
        request = {
            "unit_id": unit["unit_id"],
            "unit_name": unit["unit_name"],
            "grade": unit["grade"],
            "knowledge_point": unit["knowledge_points"][0],
            "type": "short_answer",
            "difficulty": unit["difficulty_range"][0],
        }
        facts = [{
            "fact_id": "t-fact",
            "claim": "色相是色彩三要素之一，另外两个是明度和纯度。",
            "answer": "色相、明度、纯度",
            "must_include": ["色相"],
            "misconceptions": [],
        }]
        card = build_template_card(request, facts, [], 0)
        self.assertIsNotNone(card)
        self.assertEqual(validate_card(card, self.units, self.catalog), [])


if __name__ == "__main__":
    unittest.main()
