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
