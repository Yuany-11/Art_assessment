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


@pytest.mark.django_db
def test_account_and_class_audit_visible_only_to_province(
    api_client, school_admin, question_admin, province_admin
):
    admin_token = _token(api_client, "school_admin")
    account_resp = api_client.post(
        "/api/v1/accounts/teachers",
        {
            "username": "audit_teacher",
            "realName": "审计老师",
            "phone": "13800001234",
            "subject": "music",
            "initialPassword": "Art@2026",
        },
        format="json",
        **auth_header(admin_token),
    )
    assert account_resp.status_code == 200

    class_resp = api_client.post(
        "/api/v1/classes",
        {"name": "审计班", "grade": 7},
        format="json",
        **auth_header(admin_token),
    )
    assert class_resp.status_code == 200

    question_token = _token(api_client, "question_admin")
    qbank_logs = api_client.get("/api/v1/logs?pageSize=100", **auth_header(question_token))
    actions = {item["action"] for item in qbank_logs.json()["data"]["list"]}
    assert "account.create_teacher" not in actions
    assert "class.create" not in actions

    province_token = _token(api_client, "province_admin")
    province_logs = api_client.get(
        "/api/v1/logs?pageSize=100", **auth_header(province_token)
    )
    province_actions = {item["action"] for item in province_logs.json()["data"]["list"]}
    assert "account.create_teacher" in province_actions
    assert "class.create" in province_actions
