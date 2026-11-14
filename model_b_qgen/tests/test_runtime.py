"""runtime 层测试：溯源开关、请求缓存、重试上限、resources 字段。全部离线，不加载模型。"""
from __future__ import annotations

import json
import os
import time
import unittest
from unittest import mock

from model_b_qgen.factcheck import (
    check_analysis_provenance,
    check_short_answer_direction,
    check_short_answer_domain,
    check_short_answer_negation,
    check_single_choice_analysis_consistency,
    check_single_choice_containment,
    check_single_choice_multi,
    check_single_choice_polarity,
)
from model_b_qgen.fallback import build_template_card
from model_b_qgen.resources import DEFAULT_MAP_PATH, RESOURCE_MAP, attach_resources, load_resource_map
from model_b_qgen.runtime import QgenRuntime
from model_b_qgen.validator import validate_card


class FakeRuntime(QgenRuntime):
    """把生成换成一串预置文本，其余（校验、兜底、缓存）走真实逻辑。"""

    def __init__(self, outputs: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.outputs = list(outputs)
        self.raw_calls = 0

    def load(self) -> None:  # 不加载模型
        return

    def _raw_outputs(self, normalized: list[dict]) -> list[str]:
        self.raw_calls += 1
        if not self.outputs:
            raise AssertionError("模型被多调用了一次，预置输出不够")
        return [self.outputs.pop(0)]


def _fixture() -> tuple[dict, dict]:
    """挑一个真实单元 + 知识点，返回 (请求, 事实卡)。"""
    runtime = QgenRuntime()
    for (unit_id, kp), items in sorted(runtime.facts.items()):
        unit = runtime.units.get(unit_id)
        if not unit or kp not in unit["knowledge_points"]:
            continue
        if "true_false" not in unit["allowed_types"]:
            continue
        fact = items[0]
        if not fact.get("claim"):
            continue
        request = {
            "unit_id": unit_id,
            "knowledge_point": kp,
            "type": "true_false",
            "difficulty": unit["difficulty_range"][0],
            "seed": 0,
        }
        return request, fact
    raise unittest.SkipTest("事实卡里没有可用的判断题单元")


def _card_json(claim: str, analysis: str) -> str:
    return json.dumps(
        {"stem": claim, "answer": {"value": True}, "analysis": analysis, "score": 5},
        ensure_ascii=False,
    )


class ProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request, cls.fact = _fixture()
        cls.claim = cls.fact["claim"]

    def test_analysis_provenance_flags_fabrication(self) -> None:
        card = {"id": "c1", "analysis": "《睡莲》是莫奈的作品，体现了印象派对光色的追求。"}
        errors = check_analysis_provenance(card, [self.fact])
        self.assertTrue(errors, "编造的解析应被溯源规则拦下")

    def test_analysis_provenance_accepts_grounded_analysis(self) -> None:
        card = {"id": "c2", "analysis": f"{self.claim}因此该说法正确。"}
        self.assertEqual(check_analysis_provenance(card, [self.fact]), [])

    def test_fabricated_analysis_skips_retry_strict_on(self) -> None:
        bad = _card_json(self.claim, "《睡莲》是莫奈的作品，体现了印象派对光色的追求。因此该说法正确。")
        runtime = FakeRuntime([bad], cache_size=0, provenance_strict=True)
        record = runtime.generate(self.request)
        self.assertEqual(runtime.raw_calls, 1, "溯源不过时不应再重试")
        self.assertTrue(record["provenance_blocked"])
        self.assertTrue(record["provenance_errors"])
        self.assertEqual(record["generated_by"], "template")
        self.assertIsNotNone(record["card"])
        self.assertIn("model_answer_errors", record, "模型那一轮的 answer_errors 要留档")

    def test_wrong_answer_skips_retry_strict_on(self) -> None:
        # 事实卡说该说法成立，模型给 False -> 答案与事实卡相反
        wrong = json.dumps(
            {"stem": self.claim, "answer": {"value": False},
             "analysis": f"{self.claim}因此该说法错误。", "score": 5},
            ensure_ascii=False,
        )
        runtime = FakeRuntime([wrong], cache_size=0, provenance_strict=True)
        record = runtime.generate(self.request)
        self.assertEqual(runtime.raw_calls, 1, "答案不在事实卡上时不应再重试")
        self.assertTrue(record["model_answer_errors"])
        self.assertTrue(record["provenance_blocked"])
        self.assertEqual(record["generated_by"], "template")

    def test_wrong_answer_retries_when_switch_off(self) -> None:
        wrong = json.dumps(
            {"stem": self.claim, "answer": {"value": False},
             "analysis": f"{self.claim}因此该说法错误。", "score": 5},
            ensure_ascii=False,
        )
        good = _card_json(self.claim, f"{self.claim}因此该说法正确。")
        runtime = FakeRuntime([wrong, good], cache_size=0, provenance_strict=False)
        record = runtime.generate(self.request)
        self.assertEqual(runtime.raw_calls, 2, "开关关闭时保留旧的重试行为")
        self.assertFalse(record.get("provenance_blocked", False))
        self.assertEqual(record["generated_by"], "model")

    def test_fabricated_analysis_retried_by_offline_check_when_switch_off(self) -> None:
        # 溯源开关只关掉覆盖率那条；离线校验器（解析未体现事实卡依据）仍会拦，照样重试。
        bad = _card_json(self.claim, "《睡莲》是莫奈的作品，体现了印象派对光色的追求。因此该说法正确。")
        good = _card_json(self.claim, f"{self.claim}因此该说法正确。")
        runtime = FakeRuntime([bad, good], cache_size=0, provenance_strict=False)
        record = runtime.generate(self.request)
        self.assertEqual(runtime.raw_calls, 2, "离线校验不过应重试")
        self.assertEqual(record["provenance_errors"], [], "开关关闭时不计算溯源覆盖率")
        self.assertEqual(record["generated_by"], "model")


class AttemptsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request, cls.fact = _fixture()

    def test_default_max_attempts_is_two(self) -> None:
        self.assertEqual(QgenRuntime().max_attempts, 2)

    def test_structural_error_stops_after_two_attempts(self) -> None:
        runtime = FakeRuntime(["这不是 JSON", "仍然不是 JSON"], cache_size=0)
        record = runtime.generate(self.request)
        self.assertEqual(runtime.raw_calls, 2)
        self.assertEqual(record["attempts"], 2)
        self.assertEqual(record["generated_by"], "template")


class CacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request, cls.fact = _fixture()
        cls.payload = _card_json(cls.fact["claim"], f"{cls.fact['claim']}因此该说法正确。")

    def test_second_request_hits_cache_and_is_fast(self) -> None:
        runtime = FakeRuntime([self.payload], cache_size=8)
        first = runtime.generate(self.request)
        self.assertFalse(first["cache_hit"])
        started = time.perf_counter()
        second = runtime.generate(dict(self.request))
        elapsed = time.perf_counter() - started
        self.assertTrue(second["cache_hit"])
        self.assertLess(elapsed, 1.0, f"缓存命中耗时 {elapsed:.3f}s")
        self.assertEqual(runtime.raw_calls, 1, "命中缓存不应再调模型")
        info = runtime.cache_info()
        self.assertEqual((info["hits"], info["misses"]), (1, 1))
        self.assertEqual(info["size"], 1)

    def test_cached_record_is_a_copy(self) -> None:
        runtime = FakeRuntime([self.payload], cache_size=8)
        first = runtime.generate(self.request)
        first["generated_by"] = "被外部改过"
        first["card"]["stem"] = "被外部改过"
        second = runtime.generate(dict(self.request))
        self.assertNotEqual(second["generated_by"], "被外部改过")
        self.assertNotEqual(second["card"]["stem"], "被外部改过")

    def test_seed_partitions_cache(self) -> None:
        runtime = FakeRuntime([self.payload, self.payload], cache_size=8)
        runtime.generate(self.request)
        runtime.generate({**self.request, "seed": 1})
        self.assertEqual(runtime.raw_calls, 2)
        self.assertEqual(runtime.cache_info()["size"], 2)

    def test_cache_is_bounded(self) -> None:
        runtime = FakeRuntime([self.payload] * 3, cache_size=2)
        for seed in range(3):
            runtime.generate({**self.request, "seed": seed})
        self.assertEqual(runtime.cache_info()["size"], 2)

    def test_batch_reuses_single_request_cache(self) -> None:
        runtime = FakeRuntime([self.payload], cache_size=8)
        runtime.generate(self.request)
        records = runtime.generate_many([dict(self.request)])
        self.assertEqual(runtime.raw_calls, 1)
        self.assertTrue(records[0]["cache_hit"])


class ResourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.request, self.fact = _fixture()
        self.card = {"id": "c1", "type": "true_false"}
        self.key = (self.request["unit_id"], self.request["knowledge_point"])
        self._saved = dict(RESOURCE_MAP)

    def tearDown(self) -> None:
        RESOURCE_MAP.clear()
        RESOURCE_MAP.update(self._saved)

    def test_mapping_file_is_loaded_and_url_filled(self) -> None:
        if not DEFAULT_MAP_PATH.exists():
            self.skipTest(f"映射表不存在：{DEFAULT_MAP_PATH}")
        mapping = load_resource_map()
        self.assertTrue(mapping, "映射表应能解析出内容")
        unit_id, knowledge_point = next(iter(mapping))
        items = attach_resources({"unit_id": unit_id, "knowledge_point": knowledge_point})
        self.assertTrue(items)
        first = items[0]
        self.assertIn("file", first, "file 必须保留")
        self.assertEqual(first["url"], f"/resources/{first['file']}")
        self.assertNotIn("url", RESOURCE_MAP[(unit_id, knowledge_point)][0], "映射表本身不被改写")

    def test_unmapped_knowledge_point_is_empty(self) -> None:
        RESOURCE_MAP.clear()
        self.assertEqual(attach_resources(self.request, self.card), [])

    def test_url_base_comes_from_env(self) -> None:
        RESOURCE_MAP[self.key] = [{"type": "image", "file": "images/x.jpg", "name": "示例"}]
        with mock.patch.dict(os.environ, {"QGEN_RESOURCE_URL_BASE": "/media/question_image/"}):
            items = attach_resources(self.request, self.card)
        self.assertEqual(items[0]["url"], "/media/question_image/images/x.jpg")
        self.assertEqual(items[0]["file"], "images/x.jpg")

    def test_returned_items_are_copies(self) -> None:
        RESOURCE_MAP[self.key] = [{"type": "image", "file": "images/x.jpg", "name": "示例"}]
        items = attach_resources(self.request, self.card)
        items[0]["url"] = "改坏了"
        self.assertNotIn("url", RESOURCE_MAP[self.key][0])

    def test_generate_response_has_resources_field(self) -> None:
        from model_b_qgen import app as api

        RESOURCE_MAP[self.key] = [{"type": "image", "file": "images/x.jpg", "name": "示例"}]
        payload = _card_json(self.fact["claim"], f"{self.fact['claim']}因此该说法正确。")
        fake = FakeRuntime([payload, payload], cache_size=0)
        original = api.runtime
        api.runtime = fake
        try:
            response = api.generate(api.GenerateRequest(**self.request, with_image=False))
            self.assertEqual(response["resources"], [{"type": "image", "file": "images/x.jpg",
                                                     "name": "示例", "role": "reference",
                                                     "url": "/resources/images/x.jpg"}])
            batch = api.generate_batch(
                api.GenerateBatchRequest(requests=[api.GenerateRequest(**self.request, with_image=False)])
            )
            self.assertEqual(batch["items"][0]["resources"], response["resources"])
        finally:
            api.runtime = original


class FallbackTemplateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.request = {"unit_id": "g1-u1", "unit_name": "色彩", "grade": 1,
                        "knowledge_point": "涂色方法", "type": "short_answer",
                        "difficulty": 1, "seed": 0}
        self.facts = [
            {"fact_id": "f1", "claim": "涂色要顺着一个方向涂，颜色才均匀。",
             "answer": "顺一个方向", "must_include": ["方向", "均匀"], "misconceptions": []},
            {"fact_id": "f2", "claim": "涂色时不出轮廓线，画面才干净。",
             "answer": "不出轮廓线", "must_include": ["轮廓线", "干净"], "misconceptions": []},
        ]

    def test_short_answer_two_facts_fill_two_points(self) -> None:
        card = build_template_card(self.request, self.facts, [], 0)
        self.assertIn("至少两点", card["stem"])
        self.assertIn(self.facts[0]["claim"], card["answer"]["text"])
        self.assertIn(self.facts[1]["claim"], card["answer"]["text"])
        self.assertEqual(card["fact_ids"], ["f1", "f2"], "两点分别来自两张卡，fact_ids 都要留档")

    def test_short_answer_single_fact_drops_two_point_wording(self) -> None:
        card = build_template_card(self.request, self.facts[:1], [], 0)
        self.assertNotIn("至少两点", card["stem"])
        self.assertTrue(card["stem"].startswith("请简要说明"))

    def test_true_false_fragment_stem_rejected(self) -> None:
        facts = [{"fact_id": "f3", "claim": "两个消失点",
                  "answer": "两个", "must_include": ["两个"], "misconceptions": []}]
        self.assertIsNone(build_template_card({**self.request, "type": "true_false"}, facts, [], 0))

    def test_true_false_skips_fragment_misconception(self) -> None:
        facts = [{"fact_id": "f4", "claim": "一点透视只有一个消失点。",
                  "answer": "一个消失点", "must_include": ["一个", "消失点"],
                  "misconceptions": ["两个消失点"]}]
        card = build_template_card({**self.request, "type": "true_false"}, facts, [], 0)
        self.assertIsNotNone(card)
        self.assertNotEqual(card["stem"], "两个消失点。")


class AnswerRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = [
            {"fact_id": "c1", "claim": "补色相调会使颜色变灰、纯度降低。",
             "answer": "相调变灰降纯度", "must_include": ["变灰", "降低"], "misconceptions": []},
        ]

    def test_single_choice_multi_solution_flagged(self) -> None:
        card = {
            "id": "q1", "type": "single_choice",
            "options": [
                {"key": "A", "text": "补色相调会使颜色变灰"},
                {"key": "B", "text": "纯度降低"},
                {"key": "C", "text": "完全不搭边的干扰项一"},
                {"key": "D", "text": "完全不搭边的干扰项二"},
            ],
            "answer": {"value": "A"},
        }
        errors = check_single_choice_multi(card, self.facts)
        self.assertTrue(errors)
        self.assertIn("单选题出现", errors[0])

    def test_single_choice_unique_answer_passes(self) -> None:
        card = {
            "id": "q2", "type": "single_choice",
            "options": [
                {"key": "A", "text": "补色相调会使颜色变灰"},
                {"key": "B", "text": "完全不搭边的干扰项一"},
                {"key": "C", "text": "完全不搭边的干扰项二"},
                {"key": "D", "text": "完全不搭边的干扰项三"},
            ],
            "answer": {"value": "A"},
        }
        self.assertEqual(check_single_choice_multi(card, self.facts), [])

    def test_short_answer_function_question_blocks_mix_fact(self) -> None:
        card = {"id": "q3", "type": "short_answer",
                "stem": "色块并置有什么作用？", "answer": {"text": "降低纯度使颜色柔和。"}}
        self.assertTrue(check_short_answer_domain(card, self.facts))

    def test_short_answer_non_function_question_passes(self) -> None:
        card = {"id": "q4", "type": "short_answer",
                "stem": "补色相调会怎样？", "answer": {"text": "降低纯度使颜色柔和。"}}
        self.assertEqual(check_short_answer_domain(card, self.facts), [])

    def test_function_rule_ignores_harmonize_wording(self) -> None:
        facts = [{"fact_id": "c2", "claim": "暖色调和冷色调能让画面更协调。",
                  "answer": "冷暖调和", "must_include": ["暖色", "冷色"], "misconceptions": []}]
        card = {"id": "q5", "type": "short_answer",
                "stem": "暖色调和冷色调有什么作用？", "answer": {"text": "暖色调和冷色调能让画面更协调。"}}
        self.assertEqual(check_short_answer_domain(card, facts), [], "「调和」不算相调类事实卡")


class ChoicePolarityRuleTest(unittest.TestCase):
    """否定极性守卫：“不会/不能/不是/不”之差的选项对，答案键必须与解析结论一致。"""

    def _card(self, answer: str, analysis: str) -> dict:
        return {
            "id": "p1", "type": "single_choice",
            "options": [
                {"key": "A", "text": "冷色背景衬托暖色主体，主体会更突出"},
                {"key": "B", "text": "冷色背景衬托暖色主体，主体不会更突出"},
                {"key": "C", "text": "冷色让画面全部变暗"},
                {"key": "D", "text": "暖色会降低画面纯度"},
            ],
            "answer": {"value": answer},
            "analysis": analysis,
        }

    def test_answer_key_contradicts_positive_analysis(self) -> None:
        card = self._card("B", "冷色背景衬托暖色主体，主体会更突出。因此选择 B。")
        errors = check_single_choice_polarity(card, [])
        self.assertTrue(errors)
        self.assertIn("答案键与解析极性矛盾", errors[0])

    def test_matching_answer_key_passes(self) -> None:
        self.assertEqual(
            check_single_choice_polarity(self._card("A", "冷色背景衬托暖色主体，主体会更突出。"), []),
            [],
        )

    def test_negative_analysis_matches_negative_option(self) -> None:
        card = self._card("B", "冷色背景下，主体不会更突出。")
        self.assertEqual(check_single_choice_polarity(card, []), [])

    def test_non_single_choice_skipped(self) -> None:
        card = self._card("B", "主体会更突出。")
        card["type"] = "multiple_choice"
        self.assertEqual(check_single_choice_polarity(card, []), [])


class ChoiceContainmentRuleTest(unittest.TestCase):
    """选项包含关系守卫：子串包含且都无否定词 → 单选多解。"""

    def _card(self, a: str, b: str) -> dict:
        return {
            "id": "c1", "type": "single_choice",
            "options": [{"key": "A", "text": a}, {"key": "B", "text": b},
                        {"key": "C", "text": "画面构图讲究均衡"}, {"key": "D", "text": "线条决定画面动势"}],
            "answer": {"value": "B"},
            "analysis": "消失点在视平线上。",
        }

    def test_substring_option_flagged(self) -> None:
        errors = check_single_choice_containment(self._card("视平线上", "消失点在视平线上"), [])
        self.assertTrue(errors)
        self.assertIn("单选多解", errors[0])

    def test_negated_option_not_flagged(self) -> None:
        self.assertEqual(check_single_choice_containment(self._card("视平线上", "消失点不在视平线上"), []), [])

    def test_short_options_not_flagged(self) -> None:
        self.assertEqual(check_single_choice_containment(self._card("构图", "均衡构图"), []), [])

    def test_unrelated_options_pass(self) -> None:
        self.assertEqual(check_single_choice_containment(self._card("近大远小", "消失点在视平线上"), []), [])


class AnalysisConsistencyRuleTest(unittest.TestCase):
    """解析一致性守卫：选中项要被解析肯定，且不能同时肯定别的选项。"""

    def test_answer_contradicts_analysis(self) -> None:
        # fixed4 eval-0073：解析说纯度是鲜艳程度，答案却选“明暗程度”
        card = {
            "id": "a1", "type": "single_choice",
            "options": [
                {"key": "A", "text": "纯度是颜色的鲜艳程度"},
                {"key": "B", "text": "纯度是颜色的明暗程度"},
                {"key": "C", "text": "纯度是颜色的深浅程度"},
                {"key": "D", "text": "纯度是颜色的明度"},
            ],
            "answer": {"value": "B"},
            "analysis": "纯度是颜色的鲜艳程度，也叫饱和度，而明暗则描述了颜色的深浅程度。",
        }
        errors = check_single_choice_analysis_consistency(card, [])
        self.assertTrue(errors)
        self.assertIn("答案与解析不一致", errors[0])

    def test_analysis_supports_two_options(self) -> None:
        # fixed4 eval-0008：解析说“对折或角对角折”，答案单选 B
        card = {
            "id": "a2", "type": "single_choice",
            "options": [
                {"key": "A", "text": "随意折"},
                {"key": "B", "text": "对折"},
                {"key": "C", "text": "对角折"},
                {"key": "D", "text": "不用压折痕"},
            ],
            "answer": {"value": "B"},
            "analysis": "在折纸时，把纸对折或角对角折，边和角要对齐，作品才平整。",
        }
        errors = check_single_choice_analysis_consistency(card, [])
        self.assertTrue(errors)
        self.assertIn("单选多解", errors[0])

    def test_consistent_answer_passes(self) -> None:
        card = {
            "id": "a3", "type": "single_choice",
            "options": [
                {"key": "A", "text": "纯度是颜色的鲜艳程度"},
                {"key": "B", "text": "纯度是颜色的明暗程度"},
                {"key": "C", "text": "纯度是颜色的深浅程度"},
                {"key": "D", "text": "纯度是颜色的明度"},
            ],
            "answer": {"value": "A"},
            "analysis": "纯度是颜色的鲜艳程度，也叫饱和度。",
        }
        self.assertEqual(check_single_choice_analysis_consistency(card, []), [])

    def test_negated_option_not_counted(self) -> None:
        card = {
            "id": "a4", "type": "single_choice",
            "options": [
                {"key": "A", "text": "鲜艳程度"},
                {"key": "B", "text": "明暗程度"},
                {"key": "C", "text": "深浅程度"},
                {"key": "D", "text": "明度"},
            ],
            "answer": {"value": "A"},
            "analysis": "纯度不是明暗程度，而是鲜艳程度。",
        }
        self.assertEqual(check_single_choice_analysis_consistency(card, []), [])

    def test_non_single_choice_skipped(self) -> None:
        card = {"id": "a5", "type": "multiple_choice",
                "options": [{"key": "A", "text": "对折"}, {"key": "B", "text": "对角折"}],
                "answer": {"values": ["A", "B"]},
                "analysis": "对折或角对角折都可以。"}
        self.assertEqual(check_single_choice_analysis_consistency(card, []), [])


class DirectionRuleTest(unittest.TestCase):
    facts = [{"fact_id": "d1", "claim": "光从左上方照来，亮部在左上，暗部和投影在右下。",
              "answer": "亮部迎光，暗部背光", "must_include": ["亮部", "暗部", "投影"],
              "misconceptions": []}]

    def test_wrong_shadow_direction_flagged(self) -> None:
        card = {"id": "s1", "type": "short_answer", "stem": "描述光源照来时的明暗。",
                "answer": {"text": "亮部在左上，暗部在右下，投影在左下。"}}
        self.assertTrue(check_short_answer_direction(card, self.facts))

    def test_matching_direction_passes(self) -> None:
        card = {"id": "s2", "type": "short_answer", "stem": "描述光源照来时的明暗。",
                "answer": {"text": "亮部在左上，暗部和投影在右下。"}}
        self.assertEqual(check_short_answer_direction(card, self.facts), [])

    def test_direction_without_subject_passes(self) -> None:
        card = {"id": "s3", "type": "short_answer", "stem": "投影在哪个方向？",
                "answer": {"text": "投影和光源方向相反，在右下方。"}}
        self.assertEqual(check_short_answer_direction(card, self.facts), [])


class OfflineParityTest(unittest.TestCase):
    """复核方用的 scripts/validate_questions.py 三条口径，运行时必须同样拦住。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = QgenRuntime()
        cls.request, cls.fact = _fixture()
        cls.units, cls.catalog = cls.runtime.units, cls.runtime.catalog

    def _card(self, **overrides) -> dict:
        card = {
            "id": "q1", "subject": "art", "grade": 1, "unit_id": "g1-u1",
            "unit_name": "色彩", "knowledge_point": "涂色方法", "type": "short_answer",
            "difficulty": 1, "stem": "简述涂色方法。", "options": [],
            "answer": {"text": "涂色要顺着一个方向。"},
            "analysis": "涂色要顺着一个方向，颜色才均匀。", "score": 10,
            "scoringMode": "manual", "source": "self_instruct",
            "review_status": "pending", "created_by": "knowledge_template",
        }
        card.update(overrides)
        return card

    def test_internal_fact_wording_rejected(self) -> None:
        card = self._card(analysis="正确答案依据事实卡：涂色要顺着一个方向。")
        self.assertTrue(any("事实卡" in e for e in validate_card(card, self.units, self.catalog)))

    def test_claim_conclusion_rejected_for_non_true_false(self) -> None:
        card = self._card(analysis="涂色要顺着一个方向。因此该说法正确。")
        self.assertTrue(any("该说法" in e for e in validate_card(card, self.units, self.catalog)))

    def test_claim_conclusion_allowed_for_true_false(self) -> None:
        card = self._card(type="true_false", answer={"value": True}, scoringMode="auto",
                          analysis="涂色要顺着一个方向。因此该说法正确。")
        self.assertFalse(any("该说法" in e for e in validate_card(card, self.units, self.catalog)))

    def test_fill_blank_answer_restating_stem_rejected(self) -> None:
        card = self._card(type="fill_blank", scoringMode="auto", stem="____会让人产生不同感受。",
                          answer={"values": ["会让人产生不同感受"]}, analysis="颜色会让人产生不同感受。")
        self.assertTrue(any("重复题干" in e for e in validate_card(card, self.units, self.catalog)))

    def test_short_answer_negation_of_fact_rejected(self) -> None:
        facts = [{"fact_id": "f1", "claim": "光源方向决定物体的亮部、暗部和投影的位置。",
                  "answer": "决定亮暗和投影", "must_include": ["亮部", "暗部", "投影"],
                  "misconceptions": []}]
        card = {"id": "q2", "type": "short_answer", "stem": "简述光源方向的影响。",
                "answer": {"text": "光源方向决定亮部和投影，但不影响暗部的位置。"}}
        self.assertTrue(check_short_answer_negation(card, facts))

    def test_short_answer_negation_allowed_when_claim_is_negative(self) -> None:
        facts = [{"fact_id": "f2", "claim": "涂色时不出轮廓线，画面才干净。",
                  "answer": "不出轮廓线", "must_include": ["轮廓线", "干净"], "misconceptions": []}]
        card = {"id": "q3", "type": "short_answer", "stem": "涂色要注意什么？",
                "answer": {"text": "涂色时不出轮廓线，画面才干净。"}}
        self.assertEqual(check_short_answer_negation(card, facts), [])

    def test_templates_pass_offline_validator(self) -> None:
        total = 0
        for (unit_id, kp), _ in sorted(self.runtime.facts.items()):
            unit = self.units.get(unit_id)
            if not unit or kp not in unit["knowledge_points"]:
                continue
            for qtype in unit["allowed_types"]:
                for difficulty in range(unit["difficulty_range"][0], unit["difficulty_range"][1] + 1):
                    total += 1
                    request = {"unit_id": unit_id, "unit_name": unit["unit_name"],
                               "grade": unit["grade"], "knowledge_point": kp, "type": qtype,
                               "difficulty": difficulty, "seed": 0,
                               "request_id": f"{unit_id}-{kp}-{qtype}-{difficulty}"}
                    record = self.runtime._fallback(request)
                    self.assertEqual(record.get("errors"), [], f"{request} 模板没过校验")
                    self.assertIsNotNone(record.get("card"), f"{request} 模板兜底不可用")
                    card = record["card"]
                    self.assertEqual(check_single_choice_polarity(card, []), [],
                                     f"{request} 模板触发极性守卫")
                    self.assertEqual(check_single_choice_containment(card, []), [],
                                     f"{request} 模板触发包含守卫")
                    self.assertEqual(check_single_choice_analysis_consistency(card, []), [],
                                     f"{request} 模板触发解析一致性守卫")
        self.assertGreater(total, 0)


class TemplateSeedTest(unittest.TestCase):
    def test_difficulty_changes_template_card(self) -> None:
        runtime = QgenRuntime()
        unit = runtime.units["g6-u2"]
        stems = {}
        for difficulty in (1, 2, 3):
            record = runtime._fallback({
                "unit_id": "g6-u2", "unit_name": unit["unit_name"], "grade": 6,
                "knowledge_point": "色彩象征", "type": "true_false",
                "difficulty": difficulty, "seed": 0, "request_id": f"eval-00{difficulty}",
            })
            stems[difficulty] = record["card"]["stem"]
        self.assertEqual(len(set(stems.values())), 3, f"三个难度出了重题：{stems}")

    def test_same_request_is_stable(self) -> None:
        runtime = QgenRuntime()
        request = {"unit_id": "g6-u2", "unit_name": "色彩与情感", "grade": 6,
                   "knowledge_point": "色彩象征", "type": "true_false",
                   "difficulty": 2, "seed": 0, "request_id": "eval-0002"}
        first = runtime._fallback(request)["card"]["stem"]
        second = runtime._fallback(request)["card"]["stem"]
        self.assertEqual(first, second)


class ForcedTemplateTest(unittest.TestCase):
    def test_forced_template_skips_model(self) -> None:
        runtime = FakeRuntime([], cache_size=0)
        request = {"unit_id": "g1-u4", "knowledge_point": "看画说感受",
                   "type": "single_choice", "difficulty": 1}
        record = runtime.generate(request)
        self.assertEqual(runtime.raw_calls, 0, "强制模板的请求不应调模型")
        self.assertTrue(record.get("forced_template"))
        self.assertEqual(record["generated_by"], "template")
        self.assertIsNotNone(record["card"])


if __name__ == "__main__":
    unittest.main()
