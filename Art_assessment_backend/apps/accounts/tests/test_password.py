"""AUTH-06 修改密码。"""
import pytest

from conftest import PASSWORD, auth_header, login


@pytest.mark.django_db
def test_change_password_wrong_old(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/password",
        {"oldPassword": "WrongPass1", "newPassword": "NewPass123"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 400
    assert "旧密码" in response.json()["message"]


@pytest.mark.django_db
def test_change_password_requires_strength(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/password",
        {"oldPassword": PASSWORD, "newPassword": "abcdefgh"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 400
    assert "newPassword" in response.json()["data"]["errors"]


@pytest.mark.django_db
def test_change_password_invalidates_tokens(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.patch(
        "/api/v1/auth/password",
        {"oldPassword": PASSWORD, "newPassword": "NewPass123"},
        format="json",
        **auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["reloginRequired"] is True

    old_token = api_client.get("/api/v1/auth/me", **auth_header(token))
    assert old_token.status_code == 401

    new_login = login(api_client, "teacher_music", "NewPass123")
    assert new_login.status_code == 200
