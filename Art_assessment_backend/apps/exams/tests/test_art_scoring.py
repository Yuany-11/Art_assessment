"""美术作品 AI 辅助评分：规则式降级、满分折算与低置信复核。"""
import io
from types import SimpleNamespace

import pytest
from django.test import override_settings
from PIL import Image, ImageDraw

from apps.exams.services import art_scoring


def _png_bytes() -> bytes:
    image = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 160, 200), fill=(220, 40, 40))
    draw.ellipse((170, 60, 300, 190), fill=(30, 80, 200))
    draw.line((10, 220, 310, 30), fill=(20, 20, 20), width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _row(max_score=20.0, score=12.0):
    return SimpleNamespace(question_id=501, max_score=max_score, score=score)


@override_settings(ART_SCORER_ENABLED=True, ART_SCORER_URL="")
def test_rule_based_suggestion_scales_to_max_score(monkeypatch):
    monkeypatch.setattr(art_scoring, "_read_bytes", lambda file_obj: _png_bytes())
    row = _row(max_score=20.0)
    item = art_scoring.build_suggestion(row, object())

    assert item["status"] == "completed"
    assert item["degraded"] is True
    assert item["method"] == "rule_based"
    assert item["confidence"] == 0.35
    assert item["needsReview"] is True
    assert 0 <= item["rawScore"] <= 100
    assert item["suggestedScore"] == round(item["rawScore"] / 100 * 20.0, 2)
    assert len(item["dimensions"]) == 5
    assert abs(sum(dim["weight"] for dim in item["dimensions"]) - 1.0) < 1e-6
    # 规则式建议不写教师分。
    assert row.score == 12.0


@override_settings(ART_SCORER_ENABLED=False)
def test_disabled_scorer_returns_explicit_item(monkeypatch):
    monkeypatch.setattr(art_scoring, "_read_bytes", lambda file_obj: _png_bytes())
    item = art_scoring.build_suggestion(_row(), object())
    assert item["status"] == "disabled"
    assert item["suggestedScore"] is None
    assert item["message"] == "未启用美术 AI 评分"


@override_settings(ART_SCORER_ENABLED=True, ART_SCORER_URL="")
def test_unreadable_image_degrades_without_raising(monkeypatch):
    monkeypatch.setattr(art_scoring, "_read_bytes", lambda file_obj: b"not-an-image")
    item = art_scoring.build_suggestion(_row(), object())
    assert item["status"] == "failed"
    assert item["suggestedScore"] is None
    assert "无法" in item["message"]


@override_settings(ART_SCORER_ENABLED=True, ART_SCORER_URL="")
def test_missing_file_is_reported():
    item = art_scoring.build_suggestion(_row(), None)
    assert item["status"] == "missing"


def test_answer_photo_files_are_limited_to_three():
    from apps.exams.services.attempt import _validate_answer_payload
    from common.exceptions import BadRequest

    attempt = SimpleNamespace(
        questions_snapshot=[{"questionId": 1, "type": "image_upload"}]
    )
    with pytest.raises(BadRequest):
        _validate_answer_payload(
            attempt,
            [{"questionId": 1, "answer": {"files": [{}, {}, {}, {}]}}],
        )
