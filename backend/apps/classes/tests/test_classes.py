"""CLS-01 ~ CLS-14 班级管理。"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import StudentProfile
from apps.classes.models import Class, ClassTeacher, JoinRequest
from common.enums import Role

from conftest import auth_header, login


def _token(api_client, username: str) -> str:
    response = login(api_client, username)
    assert response.status_code == 200, response.content
    return response.json()["data"]["token"]


@pytest.mark.django_db
def test_teacher_creates_class_as_head(api_client, teacher):
    token = _token(api_client, "teacher_music")
    response = api_client.post(
        "/api/v1/classes",
        {"name": "八年级（3）班", "grade": 8, "description": "测试班级"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["headTeacherId"] == teacher.id
    assert data["classCode"].startswith("C")
    assert data["schoolName"] == "示范中学"


@pytest.mark.django_db
def test_school_admin_creates_class_with_head(api_client, school_admin, other_teacher):
    token = _token(api_client, "school_admin")
    response = api_client.post(
        "/api/v1/classes",
        {"name": "九年级（1）班", "grade": 9, "headTeacherId": other_teacher.id},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["headTeacherName"] == other_teacher.real_name


@pytest.mark.django_db
def test_class_list_scope(api_client, teacher, student, classroom):
    teacher_token = _token(api_client, "teacher_music")
    response = api_client.get("/api/v1/classes", **auth_header(teacher_token))
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1
    assert response.json()["data"]["list"][0]["id"] == classroom.id

    student_token = _token(api_client, "student_001")
    assert api_client.get("/api/v1/classes", **auth_header(student_token)).status_code == 403


@pytest.mark.django_db
def test_class_search_and_detail_scope(api_client, student, other_student, classroom):
    token = _token(api_client, "student_001")
    found = api_client.get(
        "/api/v1/classes/search", {"classCode": classroom.class_code}, **auth_header(token)
    )
    assert found.status_code == 200
    assert found.json()["data"]["name"] == classroom.name

    missing = api_client.get(
        "/api/v1/classes/search", {"classCode": "NOPE"}, **auth_header(token)
    )
    assert missing.status_code == 404

    assert api_client.get(f"/api/v1/classes/{classroom.id}", **auth_header(token)).status_code == 403

    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    assert api_client.get(f"/api/v1/classes/{classroom.id}", **auth_header(token)).status_code == 200

    other_token = _token(api_client, "student_002")
    assert api_client.get(f"/api/v1/classes/{classroom.id}", **auth_header(other_token)).status_code == 403


@pytest.mark.django_db
def test_class_update_permissions(api_client, teacher, other_teacher, classroom):
    ClassTeacher.objects.create(class_obj=classroom, teacher=other_teacher, subject="art")
    other_token = _token(api_client, "teacher_art")
    forbidden = api_client.patch(
        f"/api/v1/classes/{classroom.id}",
        {"name": "改名"},
        format="json",
        **auth_header(other_token),
    )
    assert forbidden.status_code == 403

    head_token = _token(api_client, "teacher_music")
    allowed = api_client.patch(
        f"/api/v1/classes/{classroom.id}",
        {"description": "更新简介"},
        format="json",
        **auth_header(head_token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["description"] == "更新简介"


@pytest.mark.django_db
def test_student_join_and_leave_flow(api_client, teacher, student, classroom):
    student_token = _token(api_client, "student_001")
    join = api_client.post(
        f"/api/v1/classes/{classroom.id}/join",
        {"reason": "本人为该班学生"},
        format="json",
        **auth_header(student_token),
    )
    assert join.status_code == 200
    request_id = join.json()["data"]["id"]

    teacher_token = _token(api_client, "teacher_music")
    review = api_client.post(
        f"/api/v1/classes/{classroom.id}/requests/{request_id}/review",
        {"action": "approve", "comment": "同意"},
        format="json",
        **auth_header(teacher_token),
    )
    assert review.status_code == 200
    assert review.json()["data"]["status"] == "approved"
    student.student_profile.refresh_from_db()
    assert student.student_profile.classroom_id == classroom.id

    leave = api_client.post(
        f"/api/v1/classes/{classroom.id}/leave",
        {"reason": "转学"},
        format="json",
        **auth_header(student_token),
    )
    leave_id = leave.json()["data"]["id"]
    reviewed_leave = api_client.post(
        f"/api/v1/classes/{classroom.id}/requests/{leave_id}/review",
        {"action": "approve"},
        format="json",
        **auth_header(teacher_token),
    )
    assert reviewed_leave.status_code == 200
    student.student_profile.refresh_from_db()
    assert student.student_profile.classroom_id is None


@pytest.mark.django_db
def test_change_class_requires_two_approvals(
    api_client, teacher, other_teacher, school_admin, student, classroom
):
    target = Class.objects.create(
        name="七年级（2）班",
        class_code="C20260702",
        grade=7,
        school=classroom.school,
        head_teacher=other_teacher,
        created_by=school_admin,
    )
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])

    student_token = _token(api_client, "student_001")
    change = api_client.post(
        f"/api/v1/classes/{classroom.id}/change",
        {"targetClassId": target.id, "reason": "课程调整"},
        format="json",
        **auth_header(student_token),
    )
    assert change.status_code == 200
    request_id = change.json()["data"]["id"]

    source_token = _token(api_client, "teacher_music")
    first = api_client.post(
        f"/api/v1/classes/{classroom.id}/requests/{request_id}/review",
        {"action": "approve"},
        format="json",
        **auth_header(source_token),
    )
    assert first.status_code == 200
    assert first.json()["data"]["status"] == "pending"

    target_token = _token(api_client, "teacher_art")
    second = api_client.post(
        f"/api/v1/classes/{target.id}/requests/{request_id}/review",
        {"action": "approve"},
        format="json",
        **auth_header(target_token),
    )
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "approved"
    student.student_profile.refresh_from_db()
    assert student.student_profile.classroom_id == target.id


@pytest.mark.django_db
def test_requests_list_and_students(api_client, teacher, student, classroom):
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    JoinRequest.objects.create(
        class_obj=classroom,
        requester=student,
        requester_role=Role.STUDENT,
        type="join",
        reason="测试",
    )
    token = _token(api_client, "teacher_music")

    requests = api_client.get(
        f"/api/v1/classes/{classroom.id}/requests", **auth_header(token)
    )
    assert requests.status_code == 200
    assert requests.json()["data"]["total"] == 1

    students = api_client.get(
        f"/api/v1/classes/{classroom.id}/students", **auth_header(token)
    )
    assert students.status_code == 200
    assert students.json()["data"]["list"][0]["studentNo"] == "S20260001"


@pytest.mark.django_db
def test_remove_student_keeps_account(api_client, teacher, student, classroom):
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    token = _token(api_client, "teacher_music")

    response = api_client.delete(
        f"/api/v1/classes/{classroom.id}/students/{student.id}", **auth_header(token)
    )
    assert response.status_code == 200
    student.student_profile.refresh_from_db()
    assert student.student_profile.classroom_id is None
    assert student.deleted_at is None


@pytest.mark.django_db
def test_delete_class_rules(api_client, teacher, student, classroom):
    token = _token(api_client, "teacher_music")
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])

    blocked = api_client.delete(f"/api/v1/classes/{classroom.id}", **auth_header(token))
    assert blocked.status_code == 409

    student.student_profile.classroom = None
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    deleted = api_client.delete(f"/api/v1/classes/{classroom.id}", **auth_header(token))
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True


@pytest.mark.django_db
def test_import_class_students_csv(api_client, teacher, classroom):
    token = _token(api_client, "teacher_music")
    content = (
        "学籍号,姓名,性别,年级,登录账号,手机号,监护人手机号\n"
        "S20260010,张小三,男,7,student_010,,13900000000\n"
        "S20260011,李小雨,女,8,student_011,,\n"
    ).encode("utf-8-sig")
    upload = SimpleUploadedFile("students.csv", content, content_type="text/csv")
    response = api_client.post(
        f"/api/v1/classes/{classroom.id}/students/import",
        {"file": upload, "mode": "append"},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["successCount"] == 1
    assert data["failCount"] == 1
    assert "年级" in data["errors"][0]["message"]
    assert StudentProfile.objects.filter(student_no="S20260010").exists()
