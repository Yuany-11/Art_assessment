"""AUTH-04 / AUTH-05 当前用户与资料修改。"""
import pytest

from conftest import auth_header, login


@pytest.mark.django_db
def test_me_requires_login(api_client):
    response = api_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"code", "message", "data"}


@pytest.mark.django_db
def test_me_returns_profile(api_client, student):
    token = login(api_client, "student_001").json()["data"]["token"]
    response = api_client.get("/api/v1/auth/me", **auth_header(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["studentNo"] == "S20260001"
    assert data["grade"] == 7
    assert data["schoolName"] == "示范中学"
    assert data["districtName"] == "示例区"
    assert data["cityName"] == "示例市"
    assert data["className"] is None


@pytest.mark.django_db
def test_update_profile(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/me",
        {"realName": "李老师改", "phone": "13800000001"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["realName"] == "李老师改"
    assert data["phone"] == "13800000001"
    assert data["teacherNo"] == "T1001"
    assert data["subject"] == "music"
    assert data["teacherSubjects"] == ["music"]
    assert data["isHeadTeacher"] is False
    assert data["title"] == "一级教师"


@pytest.mark.django_db
def test_me_teacher_identities(api_client, teacher, classroom):
    """教师的任教学科与班主任身份由任教记录、班级关系推导。"""
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.get("/api/v1/auth/me", **auth_header(token))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["teacherSubjects"] == ["music"]
    assert data["isHeadTeacher"] is True


@pytest.mark.django_db
def test_update_profile_rejects_blank_nullable(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/me", {"phone": ""}, format="json", **auth_header(token)
    )
    assert response.status_code == 400
    errors = response.json()["data"]["errors"]
    assert "phone" in errors


@pytest.mark.django_db
def test_update_profile_rejects_unknown_field(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/me", {"role": "school_admin"}, format="json", **auth_header(token)
    )
    assert response.status_code == 400
    assert "role" in response.json()["data"]["errors"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "phone",
    ["1380000000", "138000000012", "23800000001", "1380000000a", "138 0000 0001"],
)
def test_update_profile_rejects_invalid_mobile(api_client, teacher, phone):
    """手机号必须是 11 位、以 1 开头；位数不足或超长都应被拒绝。"""
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/me", {"phone": phone}, format="json", **auth_header(token)
    )
    assert response.status_code == 400
    assert "phone" in response.json()["data"]["errors"]


@pytest.mark.django_db
def test_update_profile_accepts_valid_mobile_and_avatar(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/me",
        {"phone": "13912345678", "avatarUrl": "/media/avatar/abc.png"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["phone"] == "13912345678"
    assert data["avatarUrl"] == "/media/avatar/abc.png"


@pytest.mark.django_db
def test_update_profile_rejects_unsafe_avatar_url(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/me", {"avatarUrl": "javascript:alert(1)"}, format="json", **auth_header(token)
    )
    assert response.status_code == 400
    assert "avatarUrl" in response.json()["data"]["errors"]


@pytest.mark.django_db
def test_me_exposes_subject_question_type_mapping(api_client, other_teacher):
    token = login(api_client, "teacher_art").json()["data"]["token"]
    data = api_client.get("/api/v1/auth/me", **auth_header(token)).json()["data"]
    assert data["allowedSubjects"] == ["art"]
    assert "image_upload" in data["allowedQuestionTypes"]
    assert "audio_choice_judge" not in data["allowedQuestionTypes"]
    assert data["questionTypesBySubject"]["art"] == [
        "single_choice",
        "multiple_choice",
        "true_false",
        "fill_blank",
        "image_upload",
        "image_choice_judge",
    ]


def test_auth_config_exposes_student_no_rule(api_client):
    response = api_client.get("/api/v1/auth/config")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["studentNoMinLength"] == 6
    assert data["studentNoMaxLength"] == 20
    assert data["studentNoPattern"] == r"^[A-Za-z0-9]{6,20}$"
    assert "6~20 位" in data["studentNoHint"]
