"""统一分页与统一错误结构。"""
from types import SimpleNamespace

import pytest

from common.pagination import StandardPagination

from conftest import auth_header, login


def test_pagination_shape():
    pagination = StandardPagination()
    pagination.page_size = 10
    pagination.page = SimpleNamespace(paginator=SimpleNamespace(count=25))
    response = pagination.get_paginated_response([])
    assert response.data == {
        "code": 200,
        "message": "success",
        "data": {"total": 25, "pages": 3, "list": []},
    }


@pytest.mark.django_db
def test_unauthenticated_error_shape(api_client):
    response = api_client.get("/api/v1/auth/me")
    body = response.json()
    assert response.status_code == 401
    assert body["code"] == 401
    assert body["data"] is None
    assert isinstance(body["message"], str)


@pytest.mark.django_db
def test_validation_error_shape(api_client, teacher):
    response = api_client.post("/api/v1/auth/login", {"username": ""}, format="json")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == 400
    assert "errors" in body["data"]
    assert "password" in body["data"]["errors"]


@pytest.mark.django_db
def test_request_id_header(api_client, teacher):
    token = login(api_client, "teacher_music").json()["data"]["token"]
    response = api_client.get("/api/v1/auth/me", **auth_header(token))
    assert response.headers.get("X-Request-Id")
