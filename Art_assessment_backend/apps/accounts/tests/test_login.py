"""AUTH-01 登录。"""
import pytest

from conftest import PASSWORD, login


@pytest.mark.django_db
def test_login_success(api_client, teacher):
    response = login(api_client, "teacher_music")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["tokenType"] == "Bearer"
    assert data["expiresIn"] == 1800
    assert data["refreshExpiresIn"] == 604800
    assert data["token"] and data["refreshToken"]
    assert data["user"]["role"] == "teacher"
    assert data["user"]["schoolName"] == "示范中学"
    assert "paper.create" in data["user"]["permissions"]


@pytest.mark.django_db
def test_login_with_student_no(api_client, student):
    response = login(api_client, "S20260001")
    assert response.status_code == 200
    assert response.json()["data"]["user"]["role"] == "student"


@pytest.mark.django_db
def test_login_wrong_password(api_client, teacher):
    response = login(api_client, "teacher_music", "WrongPass1")
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 401
    assert body["data"] is None
    assert body["message"] == "账号或密码错误"


@pytest.mark.django_db
def test_login_disabled_account(api_client, disabled_user):
    response = login(api_client, "disabled_user", PASSWORD)
    assert response.status_code == 403
    assert "禁用" in response.json()["message"]


@pytest.mark.django_db
def test_login_role_mismatch(api_client, teacher):
    response = api_client.post(
        "/api/v1/auth/login",
        {"username": "teacher_music", "password": PASSWORD, "role": "student"},
        format="json",
    )
    assert response.status_code == 403
    assert "角色" in response.json()["message"]


@pytest.mark.django_db
def test_login_rejects_unknown_field(api_client, teacher):
    response = api_client.post(
        "/api/v1/auth/login",
        {"username": "teacher_music", "password": PASSWORD, "extra": "x"},
        format="json",
    )
    assert response.status_code == 400
    assert "extra" in response.json()["data"]["errors"]
