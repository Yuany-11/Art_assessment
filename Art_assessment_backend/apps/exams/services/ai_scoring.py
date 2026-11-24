"""音乐作品 AI 建议分。

唯一评分口径是 arteval-v4（8100）给出的规则参考分：0–100 分按本题满分
线性折算成 0–maxScore 的建议分。本模块**只产出参考值**，不写入
``AttemptAnswer.score``，也不会覆盖教师的人工评分，避免出现「模型算一遍、
后端规则再算一遍」的双重复核压分。

服务不可用、音频未分析或分析失败时返回带 ``status`` 的说明对象，评分页
照常可以人工打分。
"""
from __future__ import annotations

from django.conf import settings

from common.enums import QuestionType, ScoringMode
from common.utils import round2

AUDIO_SUGGESTION_TYPES = {QuestionType.AUDIO_UPLOAD}
ART_SUGGESTION_TYPES = {QuestionType.IMAGE_UPLOAD}
SOURCE_SCORE_MAX = 100.0
DISCLAIMER_SUFFIX = "AI 建议分已按本题满分折算，仅供教师参考，不会自动计入成绩。"


def _confidence(tags: dict) -> float | None:
    """置信度取三个模型头的均值；缺项时按已有项计算。

    置信度只用于提示「建议人工复核」，不参与分数计算，因此不会因为置信度低
    而保守压分。
    """
    values = [
        value
        for value in (
            tags.get("genreConfidence"),
            tags.get("emotionConfidence"),
            tags.get("modeConfidence"),
        )
        if isinstance(value, (int, float))
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _threshold() -> float:
    return float(getattr(settings, "AI_SCORE_CONFIDENCE_THRESHOLD", 0.4))


def build_suggestion(row, snapshot: dict, tags: dict | None) -> dict | None:
    """用已落库的音频分析结果构造建议分；没有分析结果时返回状态说明。"""
    if snapshot.get("type") not in AUDIO_SUGGESTION_TYPES:
        return None
    max_score = float(row.max_score or 0)
    if tags is None:
        return {
            "questionId": row.question_id,
            "status": "missing",
            "suggestedScore": None,
            "maxScore": round2(max_score),
            "rawScore": None,
            "grade": None,
            "confidence": None,
            "needsReview": True,
            "message": "未找到学生提交的音频文件",
            "disclaimer": getattr(settings, "AUDIO_TAGGER_DISCLAIMER", ""),
        }

    status = tags.get("status")
    if status != "completed":
        return {
            "questionId": row.question_id,
            "status": status or "pending",
            "suggestedScore": None,
            "maxScore": round2(max_score),
            "rawScore": None,
            "grade": None,
            "confidence": None,
            "needsReview": True,
            "message": (
                tags.get("errorMessage")
                or "音频尚未完成分析，可点击「生成 AI 建议分」"
            ),
            "disclaimer": getattr(settings, "AUDIO_TAGGER_DISCLAIMER", ""),
        }

    raw_score = tags.get("referenceScore")
    if raw_score is None:
        return {
            "questionId": row.question_id,
            "status": "failed",
            "suggestedScore": None,
            "maxScore": round2(max_score),
            "rawScore": None,
            "grade": tags.get("referenceGrade"),
            "confidence": _confidence(tags),
            "needsReview": True,
            "message": "音频分析未返回参考分",
            "disclaimer": getattr(settings, "AUDIO_TAGGER_DISCLAIMER", ""),
        }

    source_max = float(getattr(settings, "AI_SCORE_SOURCE_MAX", SOURCE_SCORE_MAX)) or SOURCE_SCORE_MAX
    suggested = float(raw_score) / source_max * max_score
    suggested = round2(min(max_score, max(0.0, suggested)))
    confidence = _confidence(tags)
    needs_review = confidence is None or confidence < _threshold()
    disclaimer = getattr(settings, "AUDIO_TAGGER_DISCLAIMER", "")
    return {
        "questionId": row.question_id,
        "status": "completed",
        "suggestedScore": suggested,
        "maxScore": round2(max_score),
        "rawScore": round2(float(raw_score)),
        "rawScoreMax": source_max,
        "grade": tags.get("referenceGrade"),
        "confidence": confidence,
        "needsReview": needs_review,
        "rubricId": tags.get("rubricId"),
        "analyzedAt": tags.get("analyzedAt"),
        "message": "",
        "disclaimer": f"{disclaimer}{DISCLAIMER_SUFFIX}" if disclaimer else DISCLAIMER_SUFFIX,
    }


def _file_for_answer(answer) -> object | None:
    if not isinstance(answer, dict):
        return None
    file_id = answer.get("fileId")
    if not file_id:
        return None
    from apps.files.models import FileObject

    return (
        FileObject.objects.filter(pk=file_id, deleted_at__isnull=True).first()
    )


def stored_suggestion(row, snapshot: dict) -> dict | None:
    """只读取已有分析结果，不触发模型推理；用于评分详情展示。"""
    question_type = snapshot.get("type")
    file_obj = _file_for_answer(row.answer)
    if question_type in ART_SUGGESTION_TYPES:
        from .art_scoring import build_suggestion as build_art_suggestion

        if not getattr(settings, "AI_SCORE_SUGGESTION_ENABLED", True):
            return None
        # 详情页只做本地规则计算，避免每次打开都访问外部评分服务。
        return build_art_suggestion(row, file_obj, allow_remote=False)
    if question_type not in AUDIO_SUGGESTION_TYPES:
        return None
    if file_obj is None:
        return build_suggestion(row, snapshot, None)
    from apps.files.audio_tags import analysis_payload

    try:
        tags = analysis_payload(file_obj, include_reference=True)
    except Exception:  # noqa: BLE001 - 展示层降级，不影响人工评分
        tags = None
    return build_suggestion(row, snapshot, tags)


def _ensure_tags(file_obj, *, force: bool) -> dict | None:
    from apps.files.audio_tags import analyze_audio, analysis_payload

    tags = analysis_payload(file_obj, include_reference=True)
    if tags is None:
        return None
    if tags.get("status") == "completed" and not force:
        return tags
    if tags.get("status") == "failed" and not force:
        return tags
    if not getattr(settings, "AUDIO_TAGGER_ENABLED", False):
        return tags
    analyze_audio(file_obj, force=force)
    return analysis_payload(file_obj, include_reference=True)


def suggest_attempt(attempt, *, force: bool = False) -> dict:
    """为答卷中的音乐作品题生成建议分；逐题失败不影响其他题目。"""
    if not getattr(settings, "AI_SCORE_SUGGESTION_ENABLED", True):
        return {
            "attemptId": attempt.id,
            "items": [],
            "confidenceThreshold": _threshold(),
            "sourceScoreMax": float(
                getattr(settings, "AI_SCORE_SOURCE_MAX", SOURCE_SCORE_MAX)
            ),
            "disclaimer": "AI 建议分功能已关闭",
        }
    snapshot = {q["questionId"]: q for q in attempt.questions_snapshot}
    items = []
    for row in attempt.answers.all():
        if row.scoring_mode == ScoringMode.AUTO:
            continue
        snap = snapshot.get(row.question_id, {})
        question_type = snap.get("type")
        if question_type in ART_SUGGESTION_TYPES:
            from .art_scoring import build_suggestion as build_art_suggestion

            items.append(
                build_art_suggestion(row, _file_for_answer(row.answer))
            )
            continue
        if question_type not in AUDIO_SUGGESTION_TYPES:
            continue
        file_obj = _file_for_answer(row.answer)
        if file_obj is None:
            items.append(build_suggestion(row, snap, None))
            continue
        try:
            tags = _ensure_tags(file_obj, force=force)
        except Exception as exc:  # noqa: BLE001 - 转成逐题错误
            items.append(
                {
                    "questionId": row.question_id,
                    "status": "failed",
                    "suggestedScore": None,
                    "maxScore": round2(float(row.max_score or 0)),
                    "rawScore": None,
                    "grade": None,
                    "confidence": None,
                    "needsReview": True,
                    "message": str(exc),
                    "disclaimer": getattr(settings, "AUDIO_TAGGER_DISCLAIMER", ""),
                }
            )
            continue
        built = build_suggestion(row, snap, tags)
        if built is not None:
            # 顺带返回最新标签，前端无需再单独刷新音频分析卡片。
            built["audioTags"] = tags
        items.append(built)

    return {
        "attemptId": attempt.id,
        "items": items,
        "confidenceThreshold": _threshold(),
        "sourceScoreMax": float(getattr(settings, "AI_SCORE_SOURCE_MAX", SOURCE_SCORE_MAX)),
        "disclaimer": getattr(settings, "AUDIO_TAGGER_DISCLAIMER", ""),
    }
