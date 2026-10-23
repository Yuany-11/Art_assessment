"""QST-01 ~ QST-07、RES-01 ~ RES-02 试题与资源。"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.qbank.models import Question, QuestionResource

from conftest import auth_header, login

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


def _payload(course, chapter):
    return {
        "subject": "music",
        "grade": 7,
        "courseId": course.id,
        "chapterId": chapter.id,
        "type": "single_choice",
        "difficulty": 2,
        "stem": "聆听音频，判断这段旋律的拍号。",
        "score": 5,
        "options": [
            {"key": "A", "text": "2/4"},
            {"key": "B", "text": "3/4"},
            {"key": "C", "text": "4/4"},
        ],
        "answer": {"value": "B"},
        "analysis": "三拍子",
        "scoringMode": "auto",
    }


@pytest.mark.django_db
def test_teacher_create_and_visibility(api_client, teacher, question_admin, course, chapter):
    teacher_token = _token(api_client, "teacher_music")
    created = api_client.post(
        "/api/v1/questions", _payload(course, chapter), format="json", **auth_header(teacher_token)
    )
    assert created.status_code == 200
    data = created.json()["data"]
    assert data["status"] == "pending"
    assert len(data["options"]) == 3
    question_id = data["id"]

    public_list = api_client.get(
        "/api/v1/questions?scope=all", **auth_header(teacher_token)
    )
    # 教师默认可见：已通过题目 + 本人创建题目
    assert public_list.json()["data"]["total"] == 1

    mine = api_client.get("/api/v1/questions?scope=mine", **auth_header(teacher_token))
    assert mine.json()["data"]["total"] == 1

    admin_token = _token(api_client, "question_admin")
    admin_list = api_client.get("/api/v1/questions", **auth_header(admin_token))
    assert admin_list.json()["data"]["total"] == 1

    detail = api_client.get(
        f"/api/v1/questions/{question_id}", **auth_header(admin_token)
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["answer"] == {"value": "B"}


@pytest.mark.django_db
def test_question_review_flow(api_client, teacher, question_admin, course, chapter):
    teacher_token = _token(api_client, "teacher_music")
    question_id = api_client.post(
        "/api/v1/questions", _payload(course, chapter), format="json", **auth_header(teacher_token)
    ).json()["data"]["id"]

    admin_token = _token(api_client, "question_admin")
    no_comment = api_client.post(
        f"/api/v1/questions/{question_id}/review",
        {"action": "reject"},
        format="json",
        **auth_header(admin_token),
    )
    assert no_comment.status_code == 400

    rejected = api_client.post(
        f"/api/v1/questions/{question_id}/review",
        {"action": "reject", "comment": "音频不匹配"},
        format="json",
        **auth_header(admin_token),
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"

    updated = api_client.patch(
        f"/api/v1/questions/{question_id}",
        {"stem": "修改后的题干"},
        format="json",
        **auth_header(teacher_token),
    )
    assert updated.status_code == 200

    submitted = api_client.post(
        f"/api/v1/questions/{question_id}/submit-review",
        {"remark": "已修正"},
        format="json",
        **auth_header(teacher_token),
    )
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "pending"

    approved = api_client.post(
        f"/api/v1/questions/{question_id}/review",
        {"action": "approve", "comment": "通过"},
        format="json",
        **auth_header(admin_token),
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved"

    public_list = api_client.get("/api/v1/questions?scope=all", **auth_header(teacher_token))
    assert public_list.json()["data"]["total"] == 1


@pytest.mark.django_db
def test_question_validation(api_client, teacher, course, chapter):
    token = _token(api_client, "teacher_music")
    payload = _payload(course, chapter)
    payload["answer"] = {"value": "D"}
    response = api_client.post(
        "/api/v1/questions", payload, format="json", **auth_header(token)
    )
    assert response.status_code == 400

    payload = _payload(course, chapter)
    payload["options"] = [{"key": "A", "text": "2/4"}]
    response = api_client.post(
        "/api/v1/questions", payload, format="json", **auth_header(token)
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_resource_upload_and_reference_protection(
    api_client, teacher, question_admin, course, chapter
):
    admin_token = _token(api_client, "question_admin")
    file_resp = api_client.post(
        "/api/v1/files",
        {
            "file": SimpleUploadedFile("q.png", PNG_BYTES, content_type="image/png"),
            "category": "question_image",
        },
        format="multipart",
        **auth_header(admin_token),
    )
    file_id = file_resp.json()["data"]["fileId"]

    payload = _payload(course, chapter)
    payload["resourceFileIds"] = [file_id]
    question = api_client.post(
        "/api/v1/questions", payload, format="json", **auth_header(admin_token)
    )
    assert question.status_code == 200
    assert question.json()["data"]["resourceCount"] == 1

    delete_file = api_client.delete(
        f"/api/v1/files/{file_id}", **auth_header(admin_token)
    )
    assert delete_file.status_code == 409

    question_id = question.json()["data"]["id"]
    teacher_token = _token(api_client, "teacher_music")
    upload = api_client.post(
        f"/api/v1/questions/{question_id}/resources",
        {
            "files": [SimpleUploadedFile("q2.png", PNG_BYTES, content_type="image/png")],
            "type": "image",
        },
        format="multipart",
        **auth_header(teacher_token),
    )
    assert upload.status_code == 403

    resources = QuestionResource.objects.filter(question_id=question_id)
    assert resources.count() == 1


@pytest.mark.django_db
def test_resource_upload_and_delete_by_owner(api_client, teacher, question_admin, course, chapter):
    teacher_token = _token(api_client, "teacher_music")
    question_id = api_client.post(
        "/api/v1/questions", _payload(course, chapter), format="json", **auth_header(teacher_token)
    ).json()["data"]["id"]

    upload = api_client.post(
        f"/api/v1/questions/{question_id}/resources",
        {
            "files": [SimpleUploadedFile("q.png", PNG_BYTES, content_type="image/png")],
            "type": "image",
        },
        format="multipart",
        **auth_header(teacher_token),
    )
    assert upload.status_code == 200
    resource_id = upload.json()["data"][0]["resourceId"]

    deleted = api_client.delete(
        f"/api/v1/questions/{question_id}/resources/{resource_id}",
        **auth_header(teacher_token),
    )
    assert deleted.status_code == 200

    admin_token = _token(api_client, "question_admin")
    assert api_client.delete(
        f"/api/v1/questions/{question_id}", **auth_header(admin_token)
    ).status_code == 200
    assert Question.objects.filter(pk=question_id, deleted_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_question_delete_blocked_by_paper_reference(
    api_client, teacher, question_admin, course, chapter
):
    from apps.exams.models import Paper, PaperQuestion

    admin_token = _token(api_client, "question_admin")
    question_id = api_client.post(
        "/api/v1/questions", _payload(course, chapter), format="json", **auth_header(admin_token)
    ).json()["data"]["id"]

    paper = Paper.objects.create(
        title="引用保护试卷",
        subject="music",
        paper_type="formal",
        grade=7,
        scope_type="class",
        scope_id=1,
        scope_name="七年级（1）班",
        duration=45,
        creator=teacher,
    )
    PaperQuestion.objects.create(
        paper=paper,
        question_id=question_id,
        order=1,
        type="single_choice",
        stem="快照题干",
        score=5,
    )

    response = api_client.delete(
        f"/api/v1/questions/{question_id}", **auth_header(admin_token)
    )
    assert response.status_code == 409
    assert Question.objects.filter(pk=question_id, deleted_at__isnull=True).exists()


@pytest.mark.django_db
def test_resource_delete_blocked_by_published_paper(
    api_client, teacher, question_admin, course, chapter
):
    from apps.exams.models import Paper, PaperQuestion

    admin_token = _token(api_client, "question_admin")
    file_resp = api_client.post(
        "/api/v1/files",
        {
            "file": SimpleUploadedFile("q.png", PNG_BYTES, content_type="image/png"),
            "category": "question_image",
        },
        format="multipart",
        **auth_header(admin_token),
    )
    payload = _payload(course, chapter)
    payload["resourceFileIds"] = [file_resp.json()["data"]["fileId"]]
    created = api_client.post(
        "/api/v1/questions", payload, format="json", **auth_header(admin_token)
    ).json()["data"]
    question_id = created["id"]
    resource_id = created["resources"][0]["resourceId"]

    paper = Paper.objects.create(
        title="已发布试卷",
        subject="music",
        paper_type="formal",
        grade=7,
        scope_type="class",
        scope_id=1,
        scope_name="七年级（1）班",
        duration=45,
        status="published",
        creator=teacher,
    )
    PaperQuestion.objects.create(
        paper=paper,
        question_id=question_id,
        order=1,
        type="single_choice",
        stem="快照题干",
        score=5,
    )

    response = api_client.delete(
        f"/api/v1/questions/{question_id}/resources/{resource_id}",
        **auth_header(admin_token),
    )
    assert response.status_code == 409
    assert QuestionResource.objects.filter(pk=resource_id, deleted_at__isnull=True).exists()
