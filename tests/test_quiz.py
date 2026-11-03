from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quiz.generator import (  # noqa: E402
    EMOTION_LABELS,
    GENRE_LABELS,
    LABEL_MAP,
    MODE_LABELS,
    SKIP_MESSAGE,
    MOCK_LOW_CONFIDENCE,
    MOCK_MODEL_OUTPUT,
    QuizConfig,
    generate_questions,
    generate_questions_json,
    normalize_model_output,
    pick_distractors,
)


class LabelMapTests(unittest.TestCase):
    def test_label_map_covers_all_heads(self) -> None:
        self.assertEqual(LABEL_MAP["mode"][0], "大调")
        self.assertEqual(LABEL_MAP["mode"][1], "小调")
        self.assertEqual(LABEL_MAP["genre"][9], "流行")
        self.assertEqual(len(LABEL_MAP["genre"]), 13)
        self.assertEqual(len(LABEL_MAP["emotion"]), 4)


class NormalizeTests(unittest.TestCase):
    def test_rich_format(self) -> None:
        output = normalize_model_output(MOCK_MODEL_OUTPUT)
        self.assertEqual(output.genre.label_id, 9)
        self.assertAlmostEqual(output.genre.confidence, 0.81)
        self.assertEqual(output.emotion.label_id, 1)
        self.assertEqual(output.mode.label_id, 0)
        self.assertAlmostEqual(output.bpm, 104.3)
        self.assertAlmostEqual(output.score, 78.5)

    def test_flat_format(self) -> None:
        output = normalize_model_output(
            {"genre": 2, "genre_confidence": 0.7, "mode": 1, "mode_confidence": 0.9}
        )
        self.assertEqual(output.genre.label_id, 2)
        self.assertEqual(output.mode.label_id, 1)

    def test_infer_style_string_labels(self) -> None:
        output = normalize_model_output(MOCK_LOW_CONFIDENCE)
        self.assertEqual(output.genre.label_id, 2)  # Electronic
        self.assertEqual(output.emotion.label_id, 2)  # sad
        self.assertEqual(output.mode.label_id, 1)  # minor
        self.assertAlmostEqual(output.genre.confidence, 0.45)

    def test_infer_real_shape(self) -> None:
        # training/infer.py 的真实输出：genre 是一个概率字典
        output = normalize_model_output(
            {
                "genre": {"Blues": 0.02, "Pop": 0.74, "Rock": 0.24},
                "genre_probs": {"Blues": 0.02, "Pop": 0.74, "Rock": 0.24},
                "genre_top1": "Pop",
                "genre_confidence": 0.74,
                "emotion": "tense",
                "emotion_cn": "紧张",
                "emotion_confidence": 0.68,
                "mode": "minor",
                "mode_cn": "小调",
                "mode_confidence": 0.9,
                "bpm": 132.4,
            }
        )
        self.assertEqual(output.genre.label_id, 9)
        self.assertAlmostEqual(output.genre.confidence, 0.74)
        self.assertEqual(output.emotion.label_id, 3)
        self.assertEqual(output.mode.label_id, 1)

        payload = generate_questions(
            {
                "genre": {"Blues": 0.02, "Pop": 0.74, "Rock": 0.24},
                "genre_confidence": 0.74,
                "emotion": "tense",
                "emotion_confidence": 0.68,
                "mode": "minor",
                "mode_confidence": 0.9,
                "bpm": 132.4,
            },
            seed=2,
        )
        self.assertEqual(
            [q["topic"] for q in payload["questions"]],
            ["mode", "genre", "emotion", "bpm"],
        )

    def test_confidence_falls_back_to_probs(self) -> None:
        output = normalize_model_output(
            {"genre": "Rock", "genre_probs": {"Rock": 0.6, "Pop": 0.4}}
        )
        self.assertEqual(output.genre.label_id, 10)
        self.assertAlmostEqual(output.genre.confidence, 0.6)


class DistractorTests(unittest.TestCase):
    def test_excludes_correct_answer_and_is_unique(self) -> None:
        for seed in range(50):
            picked = pick_distractors(9, GENRE_LABELS, 3, random.Random(seed))
            self.assertEqual(len(picked), 3)
            self.assertNotIn(9, picked)
            self.assertEqual(len(set(picked)), 3)

    def test_pool_smaller_than_requested(self) -> None:
        picked = pick_distractors(0, MODE_LABELS, 3, None)
        self.assertEqual(picked, [1])


class GenerateTests(unittest.TestCase):
    def test_high_confidence_generates_four_questions(self) -> None:
        payload = generate_questions(MOCK_MODEL_OUTPUT, seed=42)
        self.assertEqual(len(payload["questions"]), 4)
        self.assertEqual(payload["skipped"], [])

        topics = [question["topic"] for question in payload["questions"]]
        self.assertEqual(topics, ["mode", "genre", "emotion", "bpm"])

        mode_question, genre_question, emotion_question, bpm_question = (
            payload["questions"]
        )

        self.assertEqual(mode_question["type"], "single_choice")
        self.assertEqual(mode_question["stem"], "请听音频，判断这段音乐的调式是？")
        self.assertEqual(mode_question["answer_text"], "大调")
        # 只有两个调式，干扰项只有一个，题目降级为二选一
        self.assertEqual(len(mode_question["options"]), 2)

        self.assertEqual(genre_question["type"], "single_choice")
        self.assertEqual(genre_question["stem"], "请听音频，判断这段音乐属于哪种流派？")
        self.assertEqual(len(genre_question["options"]), 4)
        options = [option["text"] for option in genre_question["options"]]
        self.assertEqual(options.count("流行"), 1)
        answer = genre_question["answer"]
        picked = next(o for o in genre_question["options"] if o["key"] == answer)
        self.assertEqual(picked["text"], "流行")

        self.assertEqual(emotion_question["stem"], "请听音频，判断这段音乐的情绪是？")
        self.assertEqual(emotion_question["answer_text"], "欢快")
        self.assertEqual(len(emotion_question["options"]), 4)

        self.assertEqual(bpm_question["type"], "true_false")
        self.assertEqual(
            bpm_question["stem"], "这段音乐的速度大约在 90-120 BPM 之间。"
        )
        self.assertEqual(bpm_question["answer"], "A")  # 104.3 在区间内

    def test_bpm_out_of_range_answers_false(self) -> None:
        output = dict(MOCK_MODEL_OUTPUT)
        output["bpm"] = 70.0
        payload = generate_questions(output, seed=1)
        bpm_question = next(q for q in payload["questions"] if q["topic"] == "bpm")
        self.assertEqual(bpm_question["answer"], "B")
        self.assertEqual(bpm_question["answer_text"], "错误")

    def test_low_confidence_is_skipped(self) -> None:
        payload = generate_questions(MOCK_LOW_CONFIDENCE, seed=7)
        skipped_topics = {entry["topic"] for entry in payload["skipped"]}
        self.assertEqual(skipped_topics, {"mode", "emotion"})
        for entry in payload["skipped"]:
            self.assertEqual(entry["message"], SKIP_MESSAGE)

        # 其余题型仍可出题
        topics = [q["topic"] for q in payload["questions"]]
        self.assertEqual(topics, ["genre", "bpm"])

    def test_emotion_threshold(self) -> None:
        payload = generate_questions(MOCK_LOW_CONFIDENCE, seed=7, topics=["emotion"])
        self.assertEqual(payload["questions"], [])
        self.assertEqual(payload["skipped"][0]["topic"], "emotion")
        self.assertEqual(payload["skipped"][0]["message"], SKIP_MESSAGE)

        payload = generate_questions(MOCK_MODEL_OUTPUT, seed=7, topics=["emotion"])
        self.assertEqual(len(payload["questions"]), 1)

    def test_spec_three_topics_only(self) -> None:
        # 只要需求里列的三种题型时，用 topics 排除情绪题
        payload = generate_questions(
            MOCK_MODEL_OUTPUT, seed=7, topics=["mode", "genre", "bpm"]
        )
        self.assertEqual(
            [q["topic"] for q in payload["questions"]], ["mode", "genre", "bpm"]
        )

    def test_mode_threshold_is_strict(self) -> None:
        output = dict(MOCK_MODEL_OUTPUT)
        output["mode"] = {"id": 1, "confidence": 0.5}  # 恰好等于阈值，应被拦下
        payload = generate_questions(output, seed=3, topics=["mode"])
        self.assertEqual(payload["questions"], [])
        self.assertIn("阈值", payload["skipped"][0]["reason"])

    def test_bpm_near_boundary_is_skipped(self) -> None:
        output = dict(MOCK_MODEL_OUTPUT)
        output["bpm"] = 90.5
        payload = generate_questions(output, seed=3, topics=["bpm"])
        self.assertEqual(payload["questions"], [])
        self.assertEqual(payload["skipped"][0]["topic"], "bpm")

    def test_seed_is_reproducible(self) -> None:
        first = generate_questions_json(MOCK_MODEL_OUTPUT, seed=11)
        second = generate_questions_json(MOCK_MODEL_OUTPUT, seed=11)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["meta"]["question_count"], 4)

    def test_custom_config(self) -> None:
        config = QuizConfig(bpm_range=(60.0, 90.0), distractor_count=2)
        payload = generate_questions(MOCK_MODEL_OUTPUT, config=config, seed=5)
        genre_question = next(q for q in payload["questions"] if q["topic"] == "genre")
        self.assertEqual(len(genre_question["options"]), 3)  # 正确 + 2 干扰
        bpm_question = next(q for q in payload["questions"] if q["topic"] == "bpm")
        self.assertEqual(bpm_question["answer"], "B")  # 104.3 不在 60-90


if __name__ == "__main__":
    unittest.main()
