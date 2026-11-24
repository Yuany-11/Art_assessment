"""CRS-01 ~ CRS-05、CHP-01 ~ CHP-05 课程与章节。"""
import pytest

from apps.qbank.models import Chapter, Course

from conftest import auth_header, login


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


@pytest.mark.django_db
def test_question_admin_creates_course_and_chapter(api_client, question_admin):
    token = _token(api_client, "question_admin")
    course_resp = api_client.post(
        "/api/v1/courses",
        {"name": "七年级美术鉴赏", "subject": "art", "grade": 7, "description": "美术课程"},
        format="json",
        **auth_header(token),
    )
    assert course_resp.status_code == 200
    course_id = course_resp.json()["data"]["id"]
    assert course_resp.json()["data"]["chapterCount"] == 0

    chapter_resp = api_client.post(
        f"/api/v1/courses/{course_id}/chapters",
        {"name": "第一单元 色彩", "sortOrder": 1},
        format="json",
        **auth_header(token),
    )
    assert chapter_resp.status_code == 200
    chapter_id = chapter_resp.json()["data"]["id"]

    chapters = api_client.get(
        f"/api/v1/courses/{course_id}/chapters", **auth_header(token)
    )
    assert chapters.json()["data"][0]["id"] == chapter_id

    detail = api_client.get(f"/api/v1/chapters/{chapter_id}", **auth_header(token))
    assert detail.status_code == 200
    assert detail.json()["data"]["courseName"] == "七年级美术鉴赏"


@pytest.mark.django_db
def test_student_course_visibility(api_client, student, course, chapter):
    token = _token(api_client, "student_001")
    listing = api_client.get("/api/v1/courses", **auth_header(token))
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1

    course.status = "disabled"
    course.save(update_fields=["status", "updated_at"])
    listing = api_client.get("/api/v1/courses", **auth_header(token))
    assert listing.json()["data"]["total"] == 0
    assert api_client.get(
        f"/api/v1/courses/{course.id}", **auth_header(token)
    ).status_code == 403

    # 题库按年级分册，学生可跨年级浏览已启用课程，避免未建册年级看到空课堂。
    course.status = "active"
    course.grade = 8
    course.save(update_fields=["status", "grade", "updated_at"])
    assert api_client.get(
        f"/api/v1/courses/{course.id}", **auth_header(token)
    ).status_code == 200


@pytest.mark.django_db
def test_chapter_knowledge_content_visible_and_editable(
    api_client, question_admin, student, course, chapter
):
    token = _token(api_client, "question_admin")
    updated = api_client.patch(
        f"/api/v1/chapters/{chapter.id}",
        {"content": "第一章知识讲解：认识四分音符与八分音符。"},
        format="json",
        **auth_header(token),
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["content"].startswith("第一章知识讲解")

    student_token = _token(api_client, "student_001")
    listing = api_client.get(
        f"/api/v1/courses/{course.id}/chapters", **auth_header(student_token)
    )
    assert listing.status_code == 200
    assert (
        listing.json()["data"][0]["content"]
        == "第一章知识讲解：认识四分音符与八分音符。"
    )


@pytest.mark.django_db
def test_student_sees_all_chapter_questions_with_answers(
    api_client, student, question_admin, course, chapter
):
    from apps.qbank.models import Question, QuestionOption

    approved = []
    for stem, qtype, status in (
        ("四分音符唱几拍？", "single_choice", "approved"),
        ("以下哪些是打击乐器？", "multiple_choice", "approved"),
        ("请演唱一段旋律。", "audio_upload", "approved"),
        ("未审核题目", "single_choice", "pending"),
    ):
        question = Question.objects.create(
            subject="music",
            grade=7,
            course=course,
            chapter=chapter,
            type=qtype,
            difficulty=2,
            stem=stem,
            score=5,
            answer={"value": "A"} if qtype == "single_choice" else {"values": ["A", "C"]},
            analysis=f"{stem}的解析",
            scoring_mode="auto",
            status=status,
            creator=question_admin,
        )
        if qtype == "single_choice":
            QuestionOption.objects.create(
                question=question, key="A", text="一拍", sort_order=1
            )
        if status == "approved":
            approved.append(question)

    token = _token(api_client, "student_001")
    response = api_client.get(
        f"/api/v1/chapters/{chapter.id}/questions", **auth_header(token)
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["chapter"]["id"] == chapter.id
    assert body["total"] == 3
    stems = {item["stem"] for item in body["questions"]}
    assert stems == {"四分音符唱几拍？", "以下哪些是打击乐器？", "请演唱一段旋律。"}
    assert "未审核题目" not in stems
    first = next(item for item in body["questions"] if item["stem"] == "四分音符唱几拍？")
    assert first["options"][0]["key"] == "A"
    assert first["answer"] == {"value": "A"}
    assert first["analysis"] == "四分音符唱几拍？的解析"
    assert "creatorName" not in first


@pytest.mark.django_db
def test_chapter_questions_hidden_for_disabled_course(
    api_client, student, course, chapter
):
    course.status = "disabled"
    course.save(update_fields=["status", "updated_at"])
    token = _token(api_client, "student_001")
    assert api_client.get(
        f"/api/v1/chapters/{chapter.id}/questions", **auth_header(token)
    ).status_code == 403
    assert api_client.get(
        "/api/v1/chapters/999999/questions", **auth_header(token)
    ).status_code == 404


@pytest.mark.django_db
def test_teacher_cannot_create_course(api_client, teacher):
    token = _token(api_client, "teacher_music")
    response = api_client.post(
        "/api/v1/courses",
        {"name": "非法课程", "subject": "music", "grade": 7},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_course_update_subject_conflict(api_client, question_admin, course, chapter):
    from apps.qbank.models import Question

    Question.objects.create(
        subject="music",
        grade=7,
        course=course,
        chapter=chapter,
        type="single_choice",
        difficulty=1,
        stem="题干",
        score=5,
        answer={"value": "A"},
        scoring_mode="auto",
        creator=question_admin,
    )
    token = _token(api_client, "question_admin")
    response = api_client.patch(
        f"/api/v1/courses/{course.id}",
        {"subject": "art"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_delete_course_and_chapter_rules(api_client, question_admin, course, chapter):
    token = _token(api_client, "question_admin")
    blocked = api_client.delete(
        f"/api/v1/courses/{course.id}", **auth_header(token)
    )
    assert blocked.status_code == 409

    deleted_chapter = api_client.delete(
        f"/api/v1/chapters/{chapter.id}", **auth_header(token)
    )
    assert deleted_chapter.status_code == 200

    deleted_course = api_client.delete(
        f"/api/v1/courses/{course.id}", **auth_header(token)
    )
    assert deleted_course.status_code == 200
    assert Course.objects.filter(pk=course.id, deleted_at__isnull=True).count() == 0
    assert Chapter.objects.filter(pk=chapter.id, deleted_at__isnull=True).count() == 0
