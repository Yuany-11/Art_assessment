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
from common.exceptions import BadRequest, NotFound
from apps.exams.services import scoring_rules

logger = logging.getLogger(__name__)

RULE_SUBJECTS = ("music", "art")


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


def _rule_target(subject, question, rule_context=None):
    """确定评分类别与级别；题目快照的 ruleContext 优先，调用参数可覆盖。"""
    if subject not in RULE_SUBJECTS:
        return None, None
    context = question.get("ruleContext")
    context = context if isinstance(context, dict) else {}
    if isinstance(rule_context, dict):
        context = {**context, **rule_context}
    category = context.get("category")
    if not isinstance(category, str) or not category:
        category = scoring_rules.infer_category(subject, question.get("stem", ""))
    return category, context.get("level")


def analyze_answer(question, answer, max_score, subject=None, rule_context=None):
    """返回 {score, metrics?, analysis, degraded?}；不可用时抛 AIUnavailable。"""
    qtype = question.get("type")
    payload = {
        "questionStem": question.get("stem", ""),
        "answer": answer,
        "maxScore": max_score,
    }
    category, level = _rule_target(subject, question, rule_context)
    if subject in RULE_SUBJECTS and qtype in (
        QuestionType.AUDIO_UPLOAD, QuestionType.IMAGE_UPLOAD,
    ):
        try:
            payload["scoringRules"] = scoring_rules.model_rule_set(
                subject, category=category, level=level
            )
        except (BadRequest, NotFound) as exc:
            logger.warning("评分规则加载失败，按无规则调用模型：%s", exc)

    if qtype == QuestionType.AUDIO_UPLOAD:
        return _post("/api/v1/ai/music/analyze", payload)
    if qtype == QuestionType.IMAGE_UPLOAD:
        return _post("/api/v1/ai/art/score", payload)
    return _post("/api/v1/ai/learning-report", payload)


def _evaluate_rules(subject, question, result, max_score):
    metrics = result.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return None, None
    category, level = _rule_target(subject, question)
    if subject in RULE_SUBJECTS:
        categories = scoring_rules.load_library(subject)["categories"]
        model_category = result.get("category")
        if isinstance(model_category, str) and model_category in categories:
            category = model_category
    model_level = result.get("level")
    if level is None and isinstance(model_level, int) and not isinstance(model_level, bool):
        if 1 <= model_level <= 10:
            level = model_level
    if not category:
        logger.warning("题目未标注评分类别且无法从题干推断，规则分未应用")
        return None, None
    try:
        rule_result = scoring_rules.evaluate(
            subject, category, level=level, metrics=metrics,
            max_score=max_score, confidence=result.get("confidence"),
        )
    except (BadRequest, NotFound) as exc:
        logger.warning("规则评分失败，回退到模型原始分：%s", exc)
        return None, None
    return rule_result, category


def _merge_analysis(analysis, rule_result):
    summary = {
        "ruleId": rule_result["ruleId"],
        "ruleVersion": rule_result["ruleVersion"],
        "totalScore": rule_result["totalScore"],
        "bandLabel": rule_result["bandLabel"],
        "capsApplied": rule_result["capsApplied"],
        "warnings": rule_result["warnings"],
        "needsManualReview": rule_result["needsManualReview"],
    }
    suffix = json.dumps(summary, ensure_ascii=False)
    return f"{analysis}\n{suffix}".strip() if analysis else suffix


def reevaluate_attempt(attempt):
    """对 AI 评分题重新调用模型，只更新 ai_score / ai_analysis 建议值。

    返回 (updated_count, error)。任何失败都不改动最终得分。
    """
    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    subject = getattr(attempt.assessment, "subject", None)
    updated = 0
    for row in attempt.answers.filter(scoring_mode="ai"):
        question = snapshot.get(row.question_id, {})
        try:
            result = analyze_answer(
                question, row.answer, row.max_score,
                subject=subject, rule_context=question.get("ruleContext"),
            )
        except AIUnavailable as exc:
            attempt.ai_error = str(exc)[:255]
            attempt.save(update_fields=["ai_error", "updated_at"])
            return updated, str(exc)
        score = result.get("score")
        analysis = result.get("analysis") or result.get("comment")
        rule_result, _ = _evaluate_rules(subject, question, result, row.max_score)
        if rule_result and rule_result["totalScore"] is not None:
            score = rule_result["totalScore"]
            analysis = _merge_analysis(analysis, rule_result)
        if score is not None:
            row.ai_score = max(0, min(float(score), row.max_score))
            row.ai_analysis = analysis
            row.save(update_fields=["ai_score", "ai_analysis", "updated_at"])
            updated += 1
    return updated, ""
