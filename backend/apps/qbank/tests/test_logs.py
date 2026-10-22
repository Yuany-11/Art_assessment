"""LOG-01 ~ LOG-02 操作日志。"""
import pytest

from apps.qbank.models import OperationLog

from conftest import auth_header, login


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


@pytest.mark.django_db
def test_logs_recorded_and_scope(api_client, question_admin, province_admin):
    admin_token = _token(api_client, "question_admin")
    created = api_client.post(
        "/api/v1/courses",
        {"name": "日志课程", "subject": "music", "grade": 7},
        format="json",
        **auth_header(admin_token),
    )
    assert created.status_code == 200

    logs = api_client.get("/api/v1/logs", **auth_header(admin_token))
    assert logs.status_code == 200
    data = logs.json()["data"]
    assert data["total"] >= 1
    assert all(item["resourceType"] in {"question", "course", "chapter", "resource"} for item in data["list"])

    account_log = OperationLog.objects.create(
        operator=question_admin,
        operator_role="question_admin",
        action="account.update",
        resource_type="account",
        resource_id=1,
        description="账号操作",
    )

    hidden = api_client.get(f"/api/v1/logs/{account_log.id}", **auth_header(admin_token))
    assert hidden.status_code == 404

    province_token = _token(api_client, "province_admin")
    visible = api_client.get(
        f"/api/v1/logs/{account_log.id}", **auth_header(province_token)
    )
    assert visible.status_code == 200
    assert visible.json()["data"]["action"] == "account.update"


@pytest.mark.django_db
def test_teacher_cannot_read_logs(api_client, teacher):
    token = _token(api_client, "teacher_music")
    assert api_client.get("/api/v1/logs", **auth_header(token)).status_code == 403
