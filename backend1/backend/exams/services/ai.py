"""模型 A/B 推理接口适配层。

后端只做适配与降级：provider=none 或调用失败时不产生任何分数，
由教师在人工评分入口确认；原始模型结果与错误信息落库留痕。
"""
import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings

from common.enums import QuestionType

logger = logging.getLogger(__name__)


class AIUnavailable(Exception):
    pass


def ai_enabled():
    return settings.AI_PROVIDER not in ("", "none")


def _post(path, payload):
    if not ai_enabled() or not settings.AI_BASE_URL:
        raise AIUnavailable("AI 服务未配置")
    url = settings.AI_BASE_URL.rstrip("/") + path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=settings.AI_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        raise AIUnavailable(str(exc)) from exc


def analyze_answer(question, answer, max_score):
    """返回 {score, analysis, degraded?}；不可用时抛 AIUnavailable。"""
    qtype = question.get("type")
    if qtype == QuestionType.AUDIO_UPLOAD:
        return _post("/api/v1/ai/music/analyze", {
            "questionStem": question.get("stem", ""),
            "answer": answer,
            "maxScore": max_score,
        })
    if qtype == QuestionType.IMAGE_UPLOAD:
        return _post("/api/v1/ai/art/score", {
            "questionStem": question.get("stem", ""),
            "answer": answer,
            "maxScore": max_score,
        })
    return _post("/api/v1/ai/learning-report", {
        "questionStem": question.get("stem", ""),
        "answer": answer,
        "maxScore": max_score,
    })


def reevaluate_attempt(attempt):
    """对 AI 评分题重新调用模型，只更新 ai_score / ai_analysis 建议值。

    返回 (updated_count, error)。任何失败都不改动最终得分。
    """
    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    updated = 0
    for row in attempt.answers.filter(scoring_mode="ai"):
        question = snapshot.get(row.question_id, {})
        try:
            result = analyze_answer(question, row.answer, row.max_score)
        except AIUnavailable as exc:
            attempt.ai_error = str(exc)[:255]
            attempt.save(update_fields=["ai_error", "updated_at"])
            return updated, str(exc)
        score = result.get("score")
        if score is not None:
            row.ai_score = max(0, min(float(score), row.max_score))
            row.ai_analysis = result.get("analysis") or result.get("comment")
            row.save(update_fields=["ai_score", "ai_analysis", "updated_at"])
            updated += 1
    return updated, ""
