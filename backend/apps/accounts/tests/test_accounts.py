"""ACC-01 ~ ACC-11 账号管理。"""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.accounts.models import User
from common.enums import AccountStatus, Role

from conftest import auth_header, login


def _token(api_client, username: str) -> str:
    response = login(api_client, username)
    assert response.status_code == 200, response.content
    return response.json()["data"]["token"]


@pytest.mark.django_db
def test_school_admin_creates_teacher(api_client, school_admin):
    token = _token(api_client, "school_admin")
    response = api_client.post(
        "/api/v1/accounts/teachers",
        {
            "username": "teacher1003",
            "realName": "周老师",
            "phone": "13800000004",
            "email": "teacher1003@example.com",
            "subject": "music",
            "title": "一级教师",
            "initialPassword": "Art@2026",
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["orgName"] == "示范中学"
    assert data["subject"] == "music"
    assert data["role"] == "teacher"


@pytest.mark.django_db
def test_teacher_cannot_create_account(api_client, teacher):
    token = _token(api_client, "teacher_music")
    response = api_client.post(
        "/api/v1/accounts/teachers",
        {"username": "x", "realName": "测试", "phone": "1", "subject": "music"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_school_admin_creates_student_in_class(api_client, school_admin, classroom):
    token = _token(api_client, "school_admin")
    response = api_client.post(
        "/api/v1/accounts/students",
        {
            "username": "student2026002",
            "studentNo": "S20260002",
            "realName": "陈小雨",
            "gender": "female",
            "grade": 7,
            "classId": classroom.id,
            "initialPassword": "Art@2026",
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classId"] == classroom.id
    assert data["className"] == classroom.name


@pytest.mark.django_db
def test_district_admin_creates_school(api_client, district_admin, orgs):
    token = _token(api_client, "district_admin")
    response = api_client.post(
        "/api/v1/accounts/schools",
        {
            "schoolCode": "SCH9001",
            "schoolName": "第二中学",
            "schoolType": "combined",
            "address": "示例路 2 号",
            "adminUsername": "school9001",
            "adminRealName": "孙校长",
            "adminPhone": "13700000001",
            "initialPassword": "School@2026",
        },
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["orgName"] == "第二中学"
    assert data["adminAccount"]["role"] == "school_admin"
    assert data["adminAccount"]["orgId"] == data["orgId"]


@pytest.mark.django_db
def test_province_creates_city_and_city_creates_district(api_client, province_admin, city_admin):
    province_token = _token(api_client, "province_admin")
    city_resp = api_client.post(
        "/api/v1/accounts/cities",
        {
            "cityCode": "CITY9001",
            "cityName": "新市",
            "adminUsername": "city9001",
            "adminRealName": "周局长",
            "adminPhone": "13500000001",
            "initialPassword": "City@2026",
        },
        format="json",
        **auth_header(province_token),
    )
    assert city_resp.status_code == 200
    assert city_resp.json()["data"]["adminAccount"]["role"] == "city_admin"

    city_token = _token(api_client, "city_admin")
    district_resp = api_client.post(
        "/api/v1/accounts/districts",
        {
            "districtCode": "DIST9001",
            "districtName": "新城区",
            "adminUsername": "district9001",
            "adminRealName": "刘主任",
            "adminPhone": "13600000001",
            "initialPassword": "District@2026",
        },
        format="json",
        **auth_header(city_token),
    )
    assert district_resp.status_code == 200
    assert district_resp.json()["data"]["adminAccount"]["role"] == "district_admin"


@pytest.mark.django_db
def test_account_list_scope_and_shape(api_client, school_admin, teacher, student):
    token = _token(api_client, "school_admin")
    response = api_client.get("/api/v1/accounts", **auth_header(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data.keys()) == {"total", "pages", "list"}
    roles = {item["role"] for item in data["list"]}
    assert roles == {"teacher", "student"}


@pytest.mark.django_db
def test_account_detail_teacher_scope(api_client, teacher, student, classroom):
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    token = _token(api_client, "teacher_music")
    response = api_client.get(
        f"/api/v1/accounts/{student.id}", **auth_header(token)
    )
    assert response.status_code == 200
    assert response.json()["data"]["studentNo"] == "S20260001"


@pytest.mark.django_db
def test_account_detail_teacher_forbidden_for_other_student(
    api_client, teacher, other_student, classroom
):
    token = _token(api_client, "teacher_music")
    response = api_client.get(
        f"/api/v1/accounts/{other_student.id}", **auth_header(token)
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_update_student_class_and_disable(api_client, school_admin, student, classroom):
    token = _token(api_client, "school_admin")
    response = api_client.patch(
        f"/api/v1/accounts/{student.id}",
        {"classId": classroom.id},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["classId"] == classroom.id

    disabled = api_client.patch(
        f"/api/v1/accounts/{student.id}",
        {"status": AccountStatus.DISABLED},
        format="json",
        **auth_header(token),
    )
    assert disabled.status_code == 200
    student.refresh_from_db()
    assert student.token_version == 1
    assert login(api_client, "student_001").status_code == 403


@pytest.mark.django_db
def test_delete_account_rules(api_client, school_admin, teacher, other_student, classroom):
    token = _token(api_client, "school_admin")
    blocked = api_client.delete(
        f"/api/v1/accounts/{teacher.id}", **auth_header(token)
    )
    assert blocked.status_code == 409

    deleted = api_client.delete(
        f"/api/v1/accounts/{other_student.id}", **auth_header(token)
    )
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True
    assert User.objects.filter(pk=other_student.id, deleted_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_reset_password(api_client, school_admin, student):
    token = _token(api_client, "school_admin")
    response = api_client.post(
        f"/api/v1/accounts/{student.id}/reset-password",
        {"newPassword": "NewPass123", "forceChange": True},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["temporaryPassword"] == "NewPass123"
    assert login(api_client, "student_001", "NewPass123").status_code == 200


@pytest.mark.django_db
def test_teacher_reset_student_password_scope(api_client, teacher, student, other_student, classroom):
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    token = _token(api_client, "teacher_music")

    allowed = api_client.post(
        f"/api/v1/accounts/{student.id}/reset-password",
        {},
        format="json",
        **auth_header(token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["temporaryPassword"]

    forbidden = api_client.post(
        f"/api/v1/accounts/{other_student.id}/reset-password",
        {},
        format="json",
        **auth_header(token),
    )
    assert forbidden.status_code == 403


@pytest.mark.django_db
def test_import_teachers_csv(api_client, school_admin):
    token = _token(api_client, "school_admin")
    content = (
        "登录账号,姓名,手机号,邮箱,任教学科,职称,班级号（多个用/分隔）,初始密码\n"
        "teacher_import,导入老师,13800000009,,music,,,Art@2026\n"
        "teacher_import2,导入老师二,13800000010,,art,,,Art@2026\n"
    ).encode("utf-8-sig")
    upload = SimpleUploadedFile("teachers.csv", content, content_type="text/csv")
    response = api_client.post(
        "/api/v1/accounts/teachers/import",
        {"file": upload, "overwrite": False},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["successCount"] == 2
    assert data["failCount"] == 0
    assert User.objects.filter(username="teacher_import").exists()


@pytest.mark.django_db
def test_import_teachers_xlsx(api_client, school_admin):
    token = _token(api_client, "school_admin")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["登录账号", "姓名", "手机号", "邮箱", "任教学科", "职称", "班级号（多个用/分隔）", "初始密码"])
    sheet.append(["teacher_xlsx", "表格老师", "13800000011", "", "art", "", "", "Art@2026"])
    buffer = BytesIO()
    workbook.save(buffer)
    upload = SimpleUploadedFile(
        "teachers.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response = api_client.post(
        "/api/v1/accounts/teachers/import",
        {"file": upload},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["successCount"] == 1
    assert User.objects.filter(username="teacher_xlsx", role=Role.TEACHER).exists()
