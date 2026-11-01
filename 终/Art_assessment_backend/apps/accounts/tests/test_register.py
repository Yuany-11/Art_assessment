"""AUTH-08 / AUTH-09 学生自助注册。"""
import re

import pytest
from django.core import mail

from apps.accounts.models import StudentProfile, User
from common.enums import Role

from conftest import login


def _send_code(api_client, email: str) -> str:
    mail.outbox.clear()
    response = api_client.post(
        "/api/v1/auth/register/code", {"email": email}, format="json"
    )
    assert response.status_code == 200, response.content
    return re.search(r"\d{6}", mail.outbox[-1].body).group(0)


@pytest.mark.django_db
def test_send_code_and_register_then_login(api_client):
    email = "NewStudent@Example.com"
    code = _send_code(api_client, email)
    assert mail.outbox[-1].to == ["newstudent@example.com"]

    response = api_client.post(
        "/api/v1/auth/register",
        {"nickname": "新同学", "email": email, "code": code, "password": "Art@2026"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["data"]["registered"] is True

    user = User.objects.get(username="newstudent@example.com")
    assert user.role == Role.STUDENT
    assert user.real_name == "新同学"
    assert user.email == "newstudent@example.com"
    assert StudentProfile.objects.filter(user=user).exists()

    logged_in = login(api_client, "newstudent@example.com", "Art@2026")
    assert logged_in.status_code == 200
    assert logged_in.json()["data"]["user"]["role"] == Role.STUDENT


@pytest.mark.django_db
def test_register_rejects_invalid_code(api_client):
    email = "wrongcode@example.com"
    code = _send_code(api_client, email)
    wrong = "000000" if code != "000000" else "111111"
    response = api_client.post(
        "/api/v1/auth/register",
        {"nickname": "错码同学", "email": email, "code": wrong, "password": "Art@2026"},
        format="json",
    )
    assert response.status_code == 400
    assert "验证码" in response.json()["message"]
    assert not User.objects.filter(username=email).exists()


@pytest.mark.django_db
def test_register_rejects_registered_email(api_client):
    email = "duplicate@example.com"
    code = _send_code(api_client, email)
    first = api_client.post(
        "/api/v1/auth/register",
        {"nickname": "已注册", "email": email, "code": code, "password": "Art@2026"},
        format="json",
    )
    assert first.status_code == 200

    again = api_client.post(
        "/api/v1/auth/register/code", {"email": email}, format="json"
    )
    assert again.status_code == 409
    assert "已被注册" in again.json()["message"]


@pytest.mark.django_db
def test_register_rejects_weak_password(api_client):
    email = "weakpass@example.com"
    code = _send_code(api_client, email)
    response = api_client.post(
        "/api/v1/auth/register",
        {"nickname": "弱密码", "email": email, "code": code, "password": "12345678"},
        format="json",
    )
    assert response.status_code == 400
    assert "password" in response.json()["data"]["errors"]
