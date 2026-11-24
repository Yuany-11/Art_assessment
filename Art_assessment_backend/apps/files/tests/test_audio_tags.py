"""音频标签模型接入：上传、分析、权限、题库标签与相似推荐。"""
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.exams.presenters import grading_question_item
from apps.files.models import AudioAnalysis, FileObject
from apps.qbank.models import Chapter, Question, QuestionResource
from common.enums import AudioAnalysisStatus, QuestionType, ResourceType, ScoringMode

from conftest import auth_header, login

MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"0" * 64

SAMPLE_RESULT = {
    "arch": "v4",
    "duration_s": 30.0,
    "predictions": {
        "genre": "Pop",
        "genre_confidence": 0.63,
        "genre_probs": {"Pop": 0.63, "Rock": 0.2, "Folk": 0.17},
        "emotion": "happy",
        "emotion_cn": "欢快",
        "emotion_confidence": 0.68,
        "emotion_probs": {"calm": 0.1, "happy": 0.68, "sad": 0.1, "tense": 0.12},
        "mode": "major",
        "mode_cn": "大调",
        "mode_confidence": 0.76,
        "mode_probs": {"major": 0.76, "minor": 0.24},
        "bpm": 120.0,
        "key": "C major",
        "key_confidence": 0.2,
    },
    "score": {"total": 78.5, "grade": "中等", "dimensions": [], "penalties": []},
    "dsp": {"duration_s": 30.0, "clipping_ratio": 0.0, "silence_ratio": 0.0},
    "rubric": {"id": "default-v1"},
    "model": {"epoch": 40},
}


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


def _upload_mp3(api_client, student, subject="music"):
    token = _token(api_client, "student_001")
    response = api_client.post(
        "/api/v1/files",
        {
            "file": SimpleUploadedFile("song.mp3", MP3_BYTES, content_type="audio/mpeg"),
            "category": "student_work",
            "subject": subject,
        },
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200, response.content
    return response.json()["data"]["fileId"], token


@pytest.mark.django_db
def test_audio_upload_creates_pending_analysis(api_client, student):
    file_id, _ = _upload_mp3(api_client, student)
    analysis = AudioAnalysis.objects.get(file_id=file_id)
    assert analysis.status == AudioAnalysisStatus.PENDING


@pytest.mark.django_db
def test_student_can_analyze_own_audio_and_read_tags(
    api_client, student, monkeypatch
):
    file_id, token = _upload_mp3(api_client, student)
    monkeypatch.setattr(
        "apps.files.audio_tags._call_service", lambda file_obj, content: SAMPLE_RESULT
    )

    response = api_client.post(
        f"/api/v1/files/{file_id}/audio-analysis",
        {},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["genre"] == "Pop"
    assert data["genreLabel"] == "流行"
    assert data["emotionLabel"] == "欢快"
    assert data["bpm"] == 120.0
    # 学生看到的标签不包含规则参考分，避免被当成成绩。
    assert "referenceScore" not in data

    detail = api_client.get(
        f"/api/v1/files/{file_id}/audio-analysis", **auth_header(token)
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "completed"


@pytest.mark.django_db
def test_teacher_scope_and_reference_score(
    api_client, student, teacher, other_teacher, classroom, monkeypatch
):
    from apps.classes.models import ClassTeacher

    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    ClassTeacher.objects.get_or_create(
        class_obj=classroom, teacher=teacher, subject="music"
    )
    file_id, _ = _upload_mp3(api_client, student)
    monkeypatch.setattr(
        "apps.files.audio_tags._call_service", lambda file_obj, content: SAMPLE_RESULT
    )

    teacher_token = _token(api_client, "teacher_music")
    ok = api_client.post(
        f"/api/v1/files/{file_id}/audio-analysis",
        {},
        format="json",
        **auth_header(teacher_token),
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["data"]["referenceScore"] == 78.5

    art_token = _token(api_client, "teacher_art")
    denied = api_client.get(
        f"/api/v1/files/{file_id}/audio-analysis", **auth_header(art_token)
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_grading_question_item_includes_audio_tags(student):
    file_obj = FileObject.objects.create(
        uploader=student,
        category="student_work",
        original_name="answer.mp3",
        object_key="student_work/answer.mp3",
        mime_type="audio/mpeg",
        size=128,
        storage_backend="local",
        subject="music",
    )
    AudioAnalysis.objects.create(
        file=file_obj,
        status=AudioAnalysisStatus.COMPLETED,
        genre="Folk",
        genre_label="民谣",
        genre_confidence=0.5,
        emotion="calm",
        emotion_label="平静",
        emotion_confidence=0.6,
        mode="minor",
        mode_label="小调",
        mode_confidence=0.7,
        bpm=90.0,
        reference_score=70.0,
        reference_grade="中等",
        model_version="arteval-v4/epoch40",
    )
    row = SimpleNamespace(
        question_id=1,
        order=1,
        answer={"fileId": file_obj.id, "url": "/media/x.mp3"},
        max_score=20,
        score=None,
        comment=None,
    )
    payload = grading_question_item(
        row, {"type": "audio_upload", "stem": "演唱并上传音频"}
    )
    assert payload["audioTags"]["genreLabel"] == "民谣"
    assert payload["audioTags"]["referenceScore"] == 70.0


@pytest.mark.django_db
def test_question_audio_filter_and_similar(
    api_client, question_admin, course, chapter
):
    def make_question(stem, genre, emotion, bpm):
        question = Question.objects.create(
            subject="music",
            grade=7,
            course=course,
            chapter=chapter,
            type=QuestionType.LISTENING,
            difficulty=2,
            stem=stem,
            score=5,
            answer={"value": "A"},
            scoring_mode=ScoringMode.AUTO,
            status="approved",
            creator=question_admin,
        )
        file_obj = FileObject.objects.create(
            uploader=question_admin,
            category="question_audio",
            original_name=f"{stem}.mp3",
            object_key=f"question_audio/{question.id}.mp3",
            mime_type="audio/mpeg",
            size=1024,
            storage_backend="local",
        )
        QuestionResource.objects.create(
            question=question, file=file_obj, type=ResourceType.AUDIO
        )
        AudioAnalysis.objects.create(
            file=file_obj,
            status=AudioAnalysisStatus.COMPLETED,
            genre=genre,
            genre_label=genre,
            genre_confidence=0.6,
            emotion=emotion,
            emotion_label=emotion,
            emotion_confidence=0.6,
            mode="major",
            mode_label="大调",
            mode_confidence=0.6,
            bpm=bpm,
        )
        return question

    source = make_question("源音频", "Pop", "happy", 120)
    similar = make_question("相似音频", "Pop", "happy", 124)
    make_question("差异音频", "Classical", "sad", 60)

    token = _token(api_client, "question_admin")
    filtered = api_client.get(
        "/api/v1/questions",
        {"genre": "Pop", "hasAudioTags": "true"},
        **auth_header(token),
    )
    assert filtered.status_code == 200
    ids = [item["id"] for item in filtered.json()["data"]["list"]]
    assert source.id in ids and similar.id in ids

    response = api_client.get(
        f"/api/v1/questions/{source.id}/similar-audio",
        {"limit": 5},
        **auth_header(token),
    )
    assert response.status_code == 200, response.content
    data = response.json()["data"]
    assert data["source"]["genre"] == "Pop"
    assert data["items"][0]["id"] == similar.id
    assert data["items"][0]["similarity"] > 0.5
