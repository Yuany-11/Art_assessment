"""ACC-04 导入任务：同步/异步与任务查询。"""
import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import ImportTask, User
from apps.accounts.services.account_import import _task_id
from apps.accounts.tasks import run_teacher_import
from common.enums import Role

from conftest import auth_header, login


def _token(api_client, username: str) -> str:
    return login(api_client, username).json()["data"]["token"]


def _csv(rows: int) -> bytes:
    lines = ["登录账号,姓名,手机号,邮箱,任教学科,职称,班级号（多个用/分隔）,初始密码"]
    for index in range(rows):
        lines.append(f"bulk_{index},批量老师{index},1380000{index:04d},,music,,,Art@2026")
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


@pytest.mark.django_db
def test_sync_import_creates_task_and_can_be_queried(api_client, school_admin, teacher):
    token = _token(api_client, "school_admin")
    response = api_client.post(
        "/api/v1/accounts/teachers/import",
        {"file": SimpleUploadedFile("t.csv", _csv(2), content_type="text/csv")},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    task = ImportTask.objects.get(task_id=data["taskId"])
    assert task.status == ImportTask.Status.COMPLETED
    assert task.success_count == 2

    status_resp = api_client.get(
        f"/api/v1/accounts/imports/{data['taskId']}", **auth_header(token)
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "completed"
    assert status_resp.json()["data"]["successCount"] == 2

    teacher_token = _token(api_client, "teacher_music")
    forbidden = api_client.get(
        f"/api/v1/accounts/imports/{data['taskId']}", **auth_header(teacher_token)
    )
    assert forbidden.status_code == 403


@pytest.mark.django_db
def test_large_import_is_queued(api_client, school_admin, monkeypatch):
    captured = {}

    def fake_enqueue(task_id, actor_id, file_key, default_password, overwrite):
        captured.update(
            {
                "task_id": task_id,
                "actor_id": actor_id,
                "file_key": file_key,
                "overwrite": overwrite,
            }
        )

    monkeypatch.setattr(
        "apps.accounts.services.account_import._enqueue_teacher_import", fake_enqueue
    )

    token = _token(api_client, "school_admin")
    response = api_client.post(
        "/api/v1/accounts/teachers/import",
        {"file": SimpleUploadedFile("big.csv", _csv(201), content_type="text/csv")},
        format="multipart",
        **auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["total"] == 201
    assert captured["task_id"] == data["taskId"]
    assert captured["file_key"].startswith("imports/")
    assert default_storage.exists(captured["file_key"])

    task = ImportTask.objects.get(task_id=data["taskId"])
    assert task.status == ImportTask.Status.QUEUED
    assert task.file_key == captured["file_key"]
    assert User.objects.filter(username="bulk_0").count() == 0


@pytest.mark.django_db
def test_worker_task_imports_rows(school_admin):
    task_id = _task_id()
    file_key = default_storage.save(
        f"imports/{task_id}.csv", SimpleUploadedFile("w.csv", _csv(2), content_type="text/csv")
    )
    ImportTask.objects.create(
        task_id=task_id,
        task_type="teacher_import",
        status=ImportTask.Status.QUEUED,
        requested_by=school_admin,
        total=2,
        file_key=file_key,
    )

    run_teacher_import(task_id, school_admin.id, file_key, None, False)

    task = ImportTask.objects.get(task_id=task_id)
    assert task.status == ImportTask.Status.COMPLETED
    assert task.success_count == 2
    assert User.objects.filter(username="bulk_0", role=Role.TEACHER).exists()
    assert not default_storage.exists(file_key)
