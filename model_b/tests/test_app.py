import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import app as app_module
import model_runtime
import scoring

client = TestClient(app_module.app)
TOKEN = {"X-Internal-Token": "dev-token"}


@pytest.fixture(autouse=True)
def _baseline_mode(monkeypatch):
    monkeypatch.setenv("ART_DISABLE_MODEL", "1")


def _img(color=(120, 60, 200), size=(320, 320), blur=False):
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:, :] = color
    yy, xx = np.mgrid[0:size[1], 0:size[0]]
    arr[:, :, 0] = (xx % 256)
    arr[:, :, 1] = (yy % 256)
    img = Image.fromarray(arr)
    return img


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_missing_token():
    r = client.post("/api/v1/ai/art/score", json={"imageUrl": "http://x/a.png", "studentId": 1})
    assert r.status_code == 401


def test_bad_rubric():
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={
            "imageUrl": "http://x/a.png",
            "studentId": 1,
            "rubric": {"composition": 50, "color": 50, "modeling": 50, "creativity": 50},
        },
    )
    assert r.status_code == 400


def test_score_success(monkeypatch):
    monkeypatch.setattr(scoring, "fetch_image", lambda url: _img())
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={"imageUrl": "http://x/a.png", "studentId": 1},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "degraded"
    assert data["fallbackUsed"] is True
    assert data["modelVersion"] == scoring.MODEL_VERSION
    for key in ("composition", "color", "modeling", "creativity", "total"):
        assert 0 <= data["scores"][key] <= 100
    assert data["level"] in ("excellent", "good", "pass", "fail")


def test_grayscale_lower_color(monkeypatch):
    rgb = scoring.score_image(_img())["scores"]["color"]
    gray = scoring.score_image(_img().convert("L").convert("RGB"))["scores"]["color"]
    assert gray < rgb


def test_blank_image(monkeypatch):
    blank = Image.new("RGB", (320, 320), (255, 255, 255))
    scores = scoring.score_image(blank)["scores"]
    assert scores["composition"] < 5
    assert scores["color"] < 5


def test_score_returns_warnings_and_flags(monkeypatch):
    monkeypatch.setattr(scoring, "fetch_image", lambda url: _img())
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={"imageUrl": "http://x/a.png", "studentId": 1},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data["warnings"], list)
    assert isinstance(data["contentFlags"], list)


def test_model_mode_success(monkeypatch):
    monkeypatch.delenv("ART_DISABLE_MODEL")
    monkeypatch.setattr(scoring, "fetch_image", lambda url: _img())
    monkeypatch.setattr(
        model_runtime,
        "predict",
        lambda img: {
            "scores": {"composition": 80.0, "color": 76.0, "modeling": 72.0, "creativity": 68.0},
            "rawScores": {"composition": 81.0, "color": 77.0, "modeling": 73.0, "creativity": 69.0},
            "flags": [],
            "modelVersion": "art-cnn-apddv2-v3.0+pencils-creativity-v1",
        },
    )
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={"imageUrl": "http://x/a.png", "studentId": 1},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "success"
    assert data["fallbackUsed"] is False
    assert data["modelVersion"].endswith("pencils-creativity-v1")
    assert data["scores"]["total"] == pytest.approx(74.0, abs=0.01)
    assert data["level"] == "pass"


def test_model_mode_rejects_document(monkeypatch):
    monkeypatch.delenv("ART_DISABLE_MODEL")
    monkeypatch.setattr(scoring, "fetch_image", lambda url: _img())
    monkeypatch.setattr(
        model_runtime,
        "predict",
        lambda img: {
            "scores": {"composition": 70.0, "color": 70.0, "modeling": 70.0, "creativity": 70.0},
            "rawScores": {},
            "flags": ["document"],
            "modelVersion": "test",
        },
    )
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={"imageUrl": "http://x/a.png", "studentId": 1},
    )
    assert r.status_code == 422


def test_model_mode_rubric_weighting(monkeypatch):
    monkeypatch.delenv("ART_DISABLE_MODEL")
    monkeypatch.setattr(scoring, "fetch_image", lambda url: _img())
    monkeypatch.setattr(
        model_runtime,
        "predict",
        lambda img: {
            "scores": {"composition": 100.0, "color": 0.0, "modeling": 0.0, "creativity": 0.0},
            "rawScores": {},
            "flags": [],
            "modelVersion": "test",
        },
    )
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={
            "imageUrl": "http://x/a.png",
            "studentId": 1,
            "rubric": {"composition": 100, "color": 0, "modeling": 0, "creativity": 0},
        },
    )
    assert r.status_code == 200
    assert r.json()["data"]["scores"]["total"] == pytest.approx(100.0)


def test_document_image_rejected(monkeypatch):
    doc = Image.new("RGB", (800, 600), (255, 255, 255))
    draw = ImageDraw.Draw(doc)
    for i in range(10):
        for j in range(40):
            x, y = 40 + j * 17, 40 + i * 45
            draw.rectangle([x, y, x + 8, y + 10], fill=(0, 0, 0))
    monkeypatch.setattr(scoring, "fetch_image", lambda url: doc)
    r = client.post(
        "/api/v1/ai/art/score",
        headers=TOKEN,
        json={"imageUrl": "http://x/a.png", "studentId": 1},
    )
    assert r.status_code == 422
    assert "绘画" in r.json()["message"]


def test_blank_image_not_applicable():
    blank = Image.new("RGB", (320, 320), (255, 255, 255))
    result = scoring.score_image(blank)
    assert result["level"] == "not_applicable"
    assert "blank" in result["contentFlags"]


def test_line_drawing_not_flagged():
    line = Image.new("RGB", (400, 400), (255, 255, 255))
    draw = ImageDraw.Draw(line)
    draw.line([(60, 330), (200, 80), (340, 330)], fill=(0, 0, 0), width=5)
    draw.ellipse([150, 180, 250, 280], outline=(0, 0, 0), width=5)
    draw.arc([80, 220, 180, 330], start=200, end=340, fill=(0, 0, 0), width=5)
    flags = scoring.detect_content_flags(line)
    assert "document" not in flags
    assert "screenshot" not in flags
    assert "blank" not in flags


def test_colorful_long_border_not_screenshot():
    rng = np.random.default_rng(0)
    arr = rng.integers(40, 220, size=(512, 512, 3), dtype=np.uint8)
    for x in (30, 60, 450, 480):
        arr[:, x:x + 2] = (20, 20, 20)
    for y in (30, 60, 450, 480):
        arr[y:y + 2, :] = (20, 20, 20)
    flags = scoring.detect_content_flags(Image.fromarray(arr))
    assert "screenshot" not in flags
    assert "document" not in flags


def test_flat_ui_screenshot_flagged():
    arr = np.full((400, 700, 3), 245, dtype=np.uint8)
    arr[40:42, 20:680] = (30, 30, 30)
    arr[120:122, 20:680] = (30, 30, 30)
    for i in range(8):
        arr[160 + i * 18:168 + i * 18, 40:300] = (60, 60, 60)
    flags = scoring.detect_content_flags(Image.fromarray(arr))
    assert "screenshot" in flags or "document" in flags


def test_download_rejects_non_http():
    with pytest.raises(scoring.ScoringError) as exc:
        scoring.fetch_image("file:///etc/passwd")
    assert exc.value.status_code == 400


def test_learning_report():
    r = client.post(
        "/api/v1/ai/learning-report",
        headers=TOKEN,
        json={
            "studentId": 1,
            "records": [
                {"score": 60, "knowledgePoints": {"构图": 60}},
                {"score": 75, "knowledgePoints": {"构图": 72}},
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["trend"] == "上升"
    assert len(data["scoreTrend"]) == 2
    assert data["modelVersion"].startswith("art-report-rules")
