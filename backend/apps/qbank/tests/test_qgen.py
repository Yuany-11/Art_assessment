"""Model B 美术出题接入：导入过滤、目录接口与在线生成。"""
import json

import pytest
from django.test import override_settings

from apps.qbank.models import Chapter, Course, Question
from apps.qbank.qgen import import_cards

from conftest import auth_header, login

CHAPTER_NAMES = ["美术世界与线条", "色彩与生活", "设计与展示", "生肖的联想"]


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


@pytest.fixture
def art_catalog(question_admin):
    course = Course.objects.create(
        name="七年级美术（人美版）", subject="art", grade=7, sort_order=1
    )
    chapters = [
        Chapter.objects.create(course=course, name=name, sort_order=index)
        for index, name in enumerate(CHAPTER_NAMES, 1)
    ]
    return course, chapters


def _card(**overrides):
    card = {
        "id": "train-0001",
        "subject": "art",
        "grade": 7,
        "unit_id": "g7-u2",
        "unit_name": "色彩基础",
        "knowledge_point": "色相",
        "type": "single_choice",
        "difficulty": 1,
        "stem": "下列属于色彩三要素的是哪一组？",
        "options": [
            {"key": "A", "text": "红、黄、蓝"},
            {"key": "B", "text": "色相、明度、纯度"},
            {"key": "C", "text": "点、线、面"},
        ],
        "answer": {"value": "B"},
        "analysis": "色彩三要素是色相、明度和纯度。",
        "score": 5,
        "scoringMode": "auto",
        "source": "self_instruct",
        "review_status": "pending",
        "created_by": "model:Qwen2.5-3B-Instruct",
    }
    card.update(overrides)
    return card


def _write_cards(tmp_path, cards):
    path = tmp_path / "cards.jsonl"
    path.write_text(
        "\n".join(json.dumps(card, ensure_ascii=False) for card in cards) + "\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.django_db
def test_import_filters_types_and_duplicates(art_catalog, question_admin, tmp_path):
    course, chapters = art_catalog
    Question.objects.create(
        subject="art",
        grade=7,
        course=course,
        chapter=chapters[1],
        type="single_choice",
        difficulty=2,
        stem="色彩的三要素包括色相、明度和纯度。",
        score=5,
        answer={"value": "A"},
        analysis="已有题",
        scoring_mode="auto",
        status="approved",
        creator=question_admin,
    )
    cards = [
        _card(),
        _card(
            id="train-0002",
            type="true_false",
            stem="明度是指色彩的明暗程度。",
            options=[],
            answer={"value": True},
        ),
        _card(id="train-0003", stem="色彩的三要素包括色相、明度和纯度。"),
        _card(id="train-0004", type="short_answer", answer={"text": "主观答案"}),
        _card(id="train-0005", type="fill_blank", answer={"values": ["色相"]}),
        _card(id="train-0006", stem="以下画作中，哪一幅是梵高的作品？"),
        _card(id="train-0007", analysis="答对即可得分"),
        _card(id="train-0008", unit_id="g7-u9"),
    ]
    report = import_cards(_write_cards(tmp_path, cards), question_admin)

    assert report["read"] == 8
    assert report["created"] == 2
    assert report["skipped"]["type_filtered"] == 2
    assert report["skipped"]["duplicate"] == 1
    assert report["skipped"]["image_dependent"] == 1
    assert report["skipped"]["scoring_talk"] == 1
    assert report["skipped"]["unit_not_mapped"] == 1

    created = Question.objects.filter(creator=question_admin).exclude(
        stem="色彩的三要素包括色相、明度和纯度。"
    )
    assert created.count() == 2
    for question in created:
        assert question.status == "pending"
        assert question.subject == "art"
        assert question.chapter_id in {item.id for item in chapters}
        assert question.knowledge_point == "色相"
        assert question.source_meta["provider"] == "model_b_qgen"
        assert question.source_meta["unitId"] == "g7-u2"
    assert not Question.objects.filter(type__in=["short_answer", "fill_blank"]).exists()


@pytest.mark.django_db
def test_qgen_catalog_endpoint(api_client, art_catalog, question_admin):
    token = _token(api_client, "question_admin")
    response = api_client.get(
        "/api/v1/questions/qgen/catalog", **auth_header(token)
    )
    assert response.status_code == 200
    data = response.json()["data"]
    grade = next(item for item in data["grades"] if item["grade"] == 7)
    assert len(grade["units"]) == 4
    unit = next(item for item in grade["units"] if item["unitId"] == "g7-u2")
    assert unit["chapterName"] == "色彩与生活"
    assert unit["allowedTypes"] == ["single_choice", "true_false"]
    assert "色相" in unit["knowledgePoints"]


@pytest.mark.django_db
@override_settings(QGEN_ENABLED=True, QGEN_PROVIDER="model_b")
def test_qgen_generate_creates_pending(
    api_client, art_catalog, question_admin, monkeypatch
):
    def fake_http(method, path, payload=None):
        assert path == "/generate"
        return {
            "ok": True,
            "request": payload,
            "parse_ok": True,
            "errors": [],
            "card": _card(id="gen-1", stem="色相指的是色彩的哪一属性？"),
        }

    monkeypatch.setattr("apps.qbank.qgen._http_json", fake_http)
    token = _token(api_client, "question_admin")
    response = api_client.post(
        "/api/v1/questions/qgen/generate",
        {
            "unitId": "g7-u2",
            "knowledgePoint": "色相",
            "type": "single_choice",
            "difficulty": 1,
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["question"]["status"] == "pending"
    assert data["question"]["subject"] == "art"
    assert data["question"]["knowledgePoint"] == "色相"
    assert data["model"]["provider"] == "model_b_qgen"
    question = Question.objects.get(pk=data["question"]["id"])
    assert question.creator_id == question_admin.id
    assert question.source_meta["rawId"] == "gen-1"


@pytest.mark.django_db
@override_settings(
    QGEN_ENABLED=True,
    QGEN_PROVIDER="api",
    QGEN_API_BASE="https://example.test/v1",
    QGEN_API_KEY="test-key",
    QGEN_API_MODEL="test-model",
)
def test_qgen_generate_via_api(api_client, art_catalog, question_admin, monkeypatch):
    def fake_chat(messages):
        assert messages[0]["role"] == "system"
        assert "色相" in messages[1]["content"]
        return json.dumps(
            {
                "stem": "色相指的是色彩的哪一属性？",
                "options": [
                    {"key": "A", "text": "色彩的相貌"},
                    {"key": "B", "text": "色彩的明暗程度"},
                    {"key": "C", "text": "色彩的鲜艳程度"},
                    {"key": "D", "text": "色彩的面积大小"},
                ],
                "answer": {"value": "A"},
                "analysis": "色相是色彩的首要特征，指色彩的相貌。",
                "score": 5,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("apps.qbank.qgen._api_chat", fake_chat)
    token = _token(api_client, "question_admin")
    response = api_client.post(
        "/api/v1/questions/qgen/generate",
        {
            "unitId": "g7-u2",
            "knowledgePoint": "色相",
            "type": "single_choice",
            "difficulty": 1,
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["question"]["status"] == "pending"
    assert data["model"]["provider"] == "qgen_api"
    question = Question.objects.get(pk=data["question"]["id"])
    assert question.source_meta["provider"] == "qgen_api"
    assert question.answer == {"value": "A"}
    assert question.options.count() == 4


@pytest.mark.django_db
@override_settings(
    QGEN_ENABLED=True,
    QGEN_PROVIDER="api",
    QGEN_API_BASE="",
    QGEN_API_KEY="",
    QGEN_API_MODEL="",
)
def test_qgen_api_not_configured(api_client, art_catalog, question_admin):
    token = _token(api_client, "question_admin")
    response = api_client.post(
        "/api/v1/questions/qgen/generate",
        {
            "unitId": "g7-u2",
            "knowledgePoint": "色相",
            "type": "single_choice",
            "difficulty": 1,
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(QGEN_ENABLED=False)
def test_qgen_generate_disabled(api_client, art_catalog, question_admin):
    token = _token(api_client, "question_admin")
    response = api_client.post(
        "/api/v1/questions/qgen/generate",
        {
            "unitId": "g7-u2",
            "knowledgePoint": "色相",
            "type": "single_choice",
            "difficulty": 1,
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 503


@pytest.mark.django_db
def test_qgen_requires_question_admin(api_client, art_catalog, teacher):
    token = _token(api_client, "teacher_music")
    response = api_client.get(
        "/api/v1/questions/qgen/catalog", **auth_header(token)
    )
    assert response.status_code == 403


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_pick_question_images_keeps_only_question_roles():
    from apps.qbank.qgen import pick_question_images

    images = pick_question_images(
        [
            {
                "type": "image",
                "file": "images/reference.jpg",
                "role": "reference",
                "url": "/resources/images/reference.jpg",
            },
            {"type": "image", "file": "../evil.png", "role": "question"},
            {
                "type": "image",
                "file": "teaching/25_balance_comp.png",
                "name": "均衡构图",
                "role": "question",
                "url": "/resources/teaching/25_balance_comp.png",
            },
        ],
        None,
    )
    # reference 参考图、路径穿越和非图片文件都不能入库。
    assert images == [
        {
            "file": "teaching/25_balance_comp.png",
            "name": "均衡构图",
            "url": "/resources/teaching/25_balance_comp.png",
        }
    ]


@pytest.mark.django_db
def test_prepare_card_rejects_image_stem_with_reference_only(art_catalog):
    from apps.qbank.qgen import QgenSkip, prepare_card, load_unit_map

    entry = load_unit_map()["g7-u2"]
    with pytest.raises(QgenSkip) as exc:
        prepare_card(
            _card(stem="下图画面采用了哪种构图方式？"),
            entry,
            resources=[
                {
                    "type": "image",
                    "file": "images/reference.jpg",
                    "role": "reference",
                    "url": "/resources/images/reference.jpg",
                }
            ],
        )
    assert exc.value.reason == "image_dependent"


@pytest.mark.django_db
@override_settings(QGEN_ENABLED=True, QGEN_PROVIDER="model_b", QGEN_WITH_IMAGE=True)
def test_qgen_generate_with_image_saves_question_resource(
    api_client, art_catalog, question_admin, monkeypatch, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path

    def fake_http(method, path, payload=None):
        assert path == "/generate"
        # 图题必须显式向 8002 请求 with_image。
        assert payload["with_image"] is True
        return {
            "ok": True,
            "request": payload,
            "parse_ok": True,
            "errors": [],
            "generated_by": "image_bank",
            "fact_ids": ["fact-001"],
            "card": _card(
                id="img-g7-u2-1",
                stem="图中画面左右不完全对称，但视觉重量相当，这种构图叫？",
                source="image_template",
                created_by="template:image_question",
            ),
            "resources": [
                {
                    "type": "image",
                    "file": "teaching/25_balance_comp.png",
                    "name": "均衡构图",
                    "role": "question",
                    "url": "/resources/teaching/25_balance_comp.png",
                },
                {
                    "type": "image",
                    "file": "images/reference.jpg",
                    "name": "参考图",
                    "role": "reference",
                    "url": "/resources/images/reference.jpg",
                },
            ],
        }

    monkeypatch.setattr("apps.qbank.qgen._http_json", fake_http)
    monkeypatch.setattr(
        "apps.qbank.qgen._download_image",
        lambda url: (PNG_BYTES, "image/png"),
    )
    token = _token(api_client, "question_admin")
    response = api_client.post(
        "/api/v1/questions/qgen/generate",
        {
            "unitId": "g7-u2",
            "knowledgePoint": "色相",
            "type": "single_choice",
            "difficulty": 1,
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["model"]["generatedBy"] == "image_bank"
    assert data["model"]["imageCount"] == 1
    assert len(data["question"]["resources"]) == 1
    # 配图下载后落入本地媒体库，前端拿到的是 /media/... 可访问地址。
    assert data["question"]["resources"][0]["url"].startswith(
        "/media/question_image/"
    )
    assert data["question"]["resources"][0]["name"] == "均衡构图.png"

    question = Question.objects.get(pk=data["question"]["id"])
    resource = question.resources.get()
    assert resource.type == "image"
    assert resource.file.category == "question_image"
    assert resource.file.size == len(PNG_BYTES)
    assert question.source_meta["factIds"] == ["fact-001"]
    assert question.source_meta["generatedBy"] == "image_bank"
    assert question.source_meta["resources"] == [
        {
            "file": "teaching/25_balance_comp.png",
            "name": "均衡构图",
            "role": "question",
        }
    ]
