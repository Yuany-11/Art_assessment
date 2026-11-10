"""提示词与校验器的离线测试，不加载模型。"""
from __future__ import annotations

import unittest

from model_b_qgen.prompting import build_messages, load_catalog, parse_json_object, unit_index
from model_b_qgen.validator import validate_card


class PromptingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()
        cls.units = unit_index(cls.catalog)

    def test_build_messages_has_anti_copy_rule(self) -> None:
        unit = next(u for u in self.units.values() if "fill_blank" in u["allowed_types"])
        request = {
            "unit_id": unit["unit_id"],
            "grade": unit["grade"],
            "knowledge_point": unit["knowledge_points"][0],
            "type": "fill_blank",
            "difficulty": unit["difficulty_range"][0],
        }
        messages = build_messages(request, self.catalog)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("只输出 JSON", messages[1]["content"])
        self.assertIn(unit["unit_name"], messages[1]["content"])

    def test_parse_json_object_with_fence(self) -> None:
        self.assertEqual(parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json_object('说明文字 {"a": 2} 结束'), {"a": 2})
        self.assertIsNone(parse_json_object("没有 JSON"))


class ValidatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog()
        cls.units = unit_index(cls.catalog)

    def _base_card(self) -> dict:
        unit = next(u for u in self.units.values() if "fill_blank" in u["allowed_types"])
        return {
            "id": "test-1",
            "subject": "art",
            "grade": unit["grade"],
            "unit_id": unit["unit_id"],
            "unit_name": unit["unit_name"],
            "knowledge_point": unit["knowledge_points"][0],
            "type": "fill_blank",
            "difficulty": unit["difficulty_range"][0],
            "stem": "测试题干____。",
            "options": [],
            "answer": {"values": ["色相"]},
            "analysis": "测试解析。",
            "score": 5,
            "scoringMode": "auto",
            "source": "golden",
            "review_status": "pending",
            "created_by": "test",
        }

    def test_valid_card_passes(self) -> None:
        self.assertEqual(validate_card(self._base_card(), self.units, self.catalog), [])

    def test_wrong_answer_shape_rejected(self) -> None:
        card = self._base_card()
        card["answer"] = {"text": "色相"}
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("answer.values" in error for error in errors))

    def test_missing_unit_rejected(self) -> None:
        card = self._base_card()
        card["unit_id"] = "not-exist"
        errors = validate_card(card, self.units, self.catalog)
        self.assertTrue(any("unit_id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
