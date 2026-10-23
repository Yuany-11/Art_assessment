"""AUTH-02 刷新与令牌失效。"""
import pytest

from conftest import auth_header, login


@pytest.mark.django_db
def test_refresh_rotates_token(api_client, teacher):
    tokens = login(api_client, "teacher_music").json()["data"]
    response = api_client.post(
        "/api/v1/auth/refresh", {"refreshToken": tokens["refreshToken"]}, format="json"
    )
    assert response.status_code == 200
    new_tokens = response.json()["data"]
    assert new_tokens["token"] != tokens["token"]
    assert new_tokens["refreshToken"] != tokens["refreshToken"]

    reuse = api_client.post(
        "/api/v1/auth/refresh", {"refreshToken": tokens["refreshToken"]}, format="json"
    )
    assert reuse.status_code == 401
    assert reuse.json()["code"] == 401


@pytest.mark.django_db
def test_access_token_revoked_after_token_version_change(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    assert api_client.get("/api/v1/auth/me", **auth_header(token)).status_code == 200

    teacher.token_version += 1
    teacher.save(update_fields=["token_version", "updated_at"])

    response = api_client.get("/api/v1/auth/me", **auth_header(token))
    assert response.status_code == 401
    assert "重新登录" in response.json()["message"]


@pytest.mark.django_db
def test_access_token_revoked_after_logout(api_client, teacher):
    tokens = login(api_client, "teacher_music").json()["data"]
    logout = api_client.post(
        "/api/v1/auth/logout",
        {"refreshToken": tokens["refreshToken"]},
        format="json",
        **auth_header(tokens["token"]),
    )
    assert logout.status_code == 200
    assert logout.json()["data"]["loggedOut"] is True

    me = api_client.get("/api/v1/auth/me", **auth_header(tokens["token"]))
    assert me.status_code == 401

    reuse = api_client.post(
        "/api/v1/auth/refresh", {"refreshToken": tokens["refreshToken"]}, format="json"
    )
    assert reuse.status_code == 401


@pytest.mark.django_db
def test_invalid_access_token(api_client, teacher):
    response = api_client.get("/api/v1/auth/me", **auth_header("not-a-jwt"))
    assert response.status_code == 401
    assert response.json()["code"] == 401
