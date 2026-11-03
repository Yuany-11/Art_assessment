"""自动出题模块：用 CNN 的预测结果 + 规则引擎生成客观题（不依赖外部 LLM）。

常用入口::

    from quiz import generate_questions, generate_questions_json

    payload = generate_questions({"genre": {"id": 9, "confidence": 0.81}, ...})
    print(generate_questions_json(model_output, seed=42))
"""

from .generator import (
    EMOTION_LABELS,
    GENRE_LABELS,
    LABEL_MAP,
    MODE_LABELS,
    SKIP_MESSAGE,
    Prediction,
    QuizConfig,
    describe_score,
    generate_questions,
    generate_questions_json,
    normalize_model_output,
    pick_distractors,
)

__all__ = [
    "EMOTION_LABELS",
    "GENRE_LABELS",
    "LABEL_MAP",
    "MODE_LABELS",
    "SKIP_MESSAGE",
    "Prediction",
    "QuizConfig",
    "describe_score",
    "generate_questions",
    "generate_questions_json",
    "normalize_model_output",
    "pick_distractors",
]
