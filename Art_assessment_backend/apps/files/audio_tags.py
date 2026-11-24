"""音频标签分析：调用独立部署的 arteval-v4 推理服务。

服务只输出曲风/情绪/调式/BPM 等标签和一份规则参考分，不参与自动判分，
也不写入任何成绩字段。服务不可用时所有调用方都应能降级继续工作。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from common.enums import AudioAnalysisStatus
from common.exceptions import BusinessError

from .models import AudioAnalysis, FileObject

GENRE_LABELS = {
    "Blues": "布鲁斯",
    "Classical": "古典",
    "Electronic": "电子",
    "Experimental": "实验",
    "Folk": "民谣",
    "Funk/Soul": "放克/灵魂",
    "Hip-Hop": "嘻哈",
    "Horror": "恐怖",
    "Jazz": "爵士",
    "Pop": "流行",
    "Rock": "摇滚",
    "Soundtrack": "原声",
    "World": "世界音乐",
}
EMOTION_LABELS = {"calm": "平静", "happy": "欢快", "sad": "悲伤", "tense": "紧张"}
MODE_LABELS = {"major": "大调", "minor": "小调"}

AUDIO_MIME_PREFIX = "audio/"
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac")


def is_audio_file(file_obj: FileObject) -> bool:
    mime = (file_obj.mime_type or "").lower()
    if mime.startswith(AUDIO_MIME_PREFIX):
        return True
    name = (file_obj.original_name or "").lower()
    return name.endswith(AUDIO_EXTS)


def ensure_pending(file_obj: FileObject) -> AudioAnalysis | None:
    """音频文件创建一条待分析记录；图片等非音频文件直接跳过。"""
    if not is_audio_file(file_obj):
        return None
    analysis, _ = AudioAnalysis.objects.get_or_create(file=file_obj)
    return analysis


def _read_bytes(file_obj: FileObject) -> bytes:
    if file_obj.storage_backend == "minio":
        from . import minio as minio_storage

        return minio_storage.get_object_bytes(file_obj.object_key)
    with default_storage.open(file_obj.object_key, "rb") as handle:
        return handle.read()


def _call_service(file_obj: FileObject, content: bytes) -> dict:
    request = urllib.request.Request(
        f"{settings.AUDIO_TAGGER_URL}/analyze",
        data=content,
        method="POST",
        headers={
            "Content-Type": file_obj.mime_type or "application/octet-stream",
            "X-File-Name": file_obj.original_name[:200],
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.AUDIO_TAGGER_TIMEOUT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"分析服务返回 {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"无法连接音频分析服务：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("音频分析服务返回了无法解析的内容") from exc
    if not isinstance(payload, dict) or "predictions" not in payload:
        raise RuntimeError("音频分析服务返回格式不正确")
    return payload


def _compose_model_version(result: dict) -> str:
    model = result.get("model") or {}
    arch = str(result.get("arch") or "v4")
    epoch = model.get("epoch")
    return f"arteval-{arch}" + (f"/epoch{epoch}" if epoch else "")


def _apply_result(analysis: AudioAnalysis, result: dict) -> AudioAnalysis:
    predictions = result.get("predictions") or {}
    scored = result.get("score") or {}
    dsp = result.get("dsp") or {}
    rubric = result.get("rubric") or {}

    genre = str(predictions.get("genre") or "")
    emotion = str(predictions.get("emotion") or "")
    mode = str(predictions.get("mode") or "")

    analysis.status = AudioAnalysisStatus.COMPLETED
    analysis.genre = genre
    analysis.genre_label = GENRE_LABELS.get(genre, genre)
    analysis.genre_confidence = predictions.get("genre_confidence")
    analysis.genre_probs = predictions.get("genre_probs") or {}
    analysis.emotion = emotion
    analysis.emotion_label = predictions.get("emotion_cn") or EMOTION_LABELS.get(
        emotion, emotion
    )
    analysis.emotion_confidence = predictions.get("emotion_confidence")
    analysis.emotion_probs = predictions.get("emotion_probs") or {}
    analysis.mode = mode
    analysis.mode_label = predictions.get("mode_cn") or MODE_LABELS.get(mode, mode)
    analysis.mode_confidence = predictions.get("mode_confidence")
    analysis.mode_probs = predictions.get("mode_probs") or {}
    analysis.bpm = predictions.get("bpm")
    analysis.key = str(predictions.get("key") or "")[:32]
    analysis.duration = result.get("duration_s") or dsp.get("duration_s")
    analysis.reference_score = scored.get("total")
    analysis.reference_grade = str(scored.get("grade") or "")[:16]
    analysis.metrics = dsp
    analysis.dimensions = scored.get("dimensions") or []
    analysis.penalties = scored.get("penalties") or []
    analysis.model_version = _compose_model_version(result)[:64]
    analysis.rubric_id = str(rubric.get("id") or "")[:64]
    analysis.raw = result
    analysis.error_message = ""
    analysis.analyzed_at = timezone.now()
    analysis.save()
    return analysis


def analyze_audio(file_obj: FileObject, *, force: bool = False) -> AudioAnalysis:
    """同步调用推理服务并落库；失败时记录 failed 后抛出可展示的业务错误。"""
    if not is_audio_file(file_obj):
        raise BusinessError(400, "该文件不是音频，无法生成音频标签")
    if not settings.AUDIO_TAGGER_ENABLED:
        raise BusinessError(503, "音频分析服务未启用，请联系管理员")

    analysis, _ = AudioAnalysis.objects.get_or_create(file=file_obj)
    if (
        analysis.status == AudioAnalysisStatus.COMPLETED
        and analysis.analyzed_at
        and not force
    ):
        return analysis

    try:
        content = _read_bytes(file_obj)
        if not content:
            raise RuntimeError("音频文件为空")
        result = _call_service(file_obj, content)
    except Exception as exc:  # noqa: BLE001 - 失败统一转业务错误
        analysis.status = AudioAnalysisStatus.FAILED
        analysis.error_message = str(exc)[:1000]
        analysis.save(update_fields=["status", "error_message", "updated_at"])
        raise BusinessError(502, f"音频分析失败：{exc}") from exc

    return _apply_result(analysis, result)


def analysis_payload(
    file_obj: FileObject, *, include_reference: bool = True
) -> dict | None:
    """给前端展示的音频标签；没有分析记录时返回 pending 占位。"""
    if not is_audio_file(file_obj):
        return None
    item = AudioAnalysis.objects.filter(file=file_obj).first()
    if item is None:
        return {
            "fileId": file_obj.id,
            "status": "pending",
            "analyzedAt": None,
            "disclaimer": settings.AUDIO_TAGGER_DISCLAIMER,
        }
    data = {
        "fileId": file_obj.id,
        "status": item.status,
        "genre": item.genre or None,
        "genreLabel": item.genre_label or None,
        "genreConfidence": item.genre_confidence,
        "genreProbs": item.genre_probs,
        "emotion": item.emotion or None,
        "emotionLabel": item.emotion_label or None,
        "emotionConfidence": item.emotion_confidence,
        "emotionProbs": item.emotion_probs,
        "mode": item.mode or None,
        "modeLabel": item.mode_label or None,
        "modeConfidence": item.mode_confidence,
        "modeProbs": item.mode_probs,
        "bpm": item.bpm,
        # BPM/调式是信号估计值，存在倍频歧义；前端必须标注“估计值”。
        "bpmIsEstimate": True,
        "segments": ((item.raw or {}).get("predictions") or {}).get("segments"),
        "key": item.key or None,
        "duration": item.duration,
        "metrics": item.metrics,
        "modelVersion": item.model_version or None,
        "rubricId": item.rubric_id or None,
        "analyzedAt": (
            item.analyzed_at.isoformat() if item.analyzed_at else None
        ),
        "errorMessage": item.error_message or None,
        "disclaimer": settings.AUDIO_TAGGER_DISCLAIMER,
    }
    if include_reference:
        score_meta = (item.raw or {}).get("score") or {}
        data.update(
            {
                "referenceScore": item.reference_score,
                "referenceGrade": item.reference_grade or None,
                "rawReferenceScore": score_meta.get("rawTotal"),
                "calibrated": bool(score_meta.get("calibrated")),
                "dimensions": item.dimensions,
                "penalties": item.penalties,
            }
        )
    return data


def tags_for_file(file_obj: FileObject | None) -> dict | None:
    if file_obj is None:
        return None
    return analysis_payload(file_obj)


def status_label(status: str) -> str:
    return {
        AudioAnalysisStatus.PENDING: "待分析",
        AudioAnalysisStatus.COMPLETED: "已完成",
        AudioAnalysisStatus.FAILED: "分析失败",
    }.get(status, status)


def format_analyzed_at(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
