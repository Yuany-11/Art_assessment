"""FILE-01 ~ FILE-02 文件上传与删除。"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.files.models import FileObject

from conftest import auth_header, login

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


def _png(name: str = "artwork.png"):
    return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")


@pytest.mark.django_db
def test_upload_and_delete_file(api_client, student):
    token = _token(api_client, "student_001")
    response = api_client.post(
        "/api/v1/files",
        {"file": _png(), "category": "student_work"},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mimeType"] == "image/png"
    assert data["url"].endswith(".png")

    deleted = api_client.delete(
        f"/api/v1/files/{data['fileId']}", **auth_header(token)
    )
    assert deleted.status_code == 200
    assert FileObject.objects.filter(pk=data["fileId"], deleted_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_upload_rejects_wrong_type(api_client, student):
    token = _token(api_client, "student_001")
    fake = SimpleUploadedFile("bad.png", b"not-an-image", content_type="image/png")
    response = api_client.post(
        "/api/v1/files",
        {"file": fake, "category": "question_image"},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 400
    assert "内容" in response.json()["message"]


@pytest.mark.django_db
def test_teacher_artwork_list_is_limited_to_own_classes(
    api_client, student, teacher, other_teacher, classroom
):
    from apps.classes.models import ClassTeacher

    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    ClassTeacher.objects.create(class_obj=classroom, teacher=teacher, subject="music")

    token = _token(api_client, "student_001")
    uploaded = api_client.post(
        "/api/v1/files",
        {"file": _png(), "category": "student_work"},
        format="multipart",
        **auth_header(token),
    ).json()["data"]

    teacher_token = _token(api_client, "teacher_music")
    listed = api_client.get(
        "/api/v1/files", {"category": "student_work"}, **auth_header(teacher_token)
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [uploaded["fileId"]]

    other_token = _token(api_client, "teacher_art")
    other_listed = api_client.get(
        "/api/v1/files", {"category": "student_work"}, **auth_header(other_token)
    )
    assert other_listed.status_code == 200
    assert other_listed.json()["data"] == []


@pytest.mark.django_db
def test_other_student_cannot_delete_file(api_client, student, other_student):
    token = _token(api_client, "student_001")
    uploaded = api_client.post(
        "/api/v1/files",
        {"file": _png(), "category": "student_work"},
        format="multipart",
        **auth_header(token),
    ).json()["data"]

    other_token = _token(api_client, "student_002")
    response = api_client.delete(
        f"/api/v1/files/{uploaded['fileId']}", **auth_header(other_token)
    )
    assert response.status_code == 403
