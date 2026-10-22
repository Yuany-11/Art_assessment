"""NT-01~03 通知中心与审核事件测试。"""
import pytest
from django.utils import timezone

from apps.accounts.permissions_map import permissions_for
from apps.notifications.models import Notification
from apps.qbank.models import Question
from apps.qbank.services import review_question
from common.enums import NotificationType, QuestionStatus, Role, Subject

from conftest import auth_header, login


def make_notification(user, ntype=NotificationType.SYSTEM, title="系统通知", read=False):
    return Notification.objects.create(
        user=user,
        type=ntype,
        title=title,
        content="内容",
        link="/notifications",
        read_at=timezone.now() if read else None,
    )


@pytest.mark.django_db
def test_list_notifications_with_unread_count(api_client, student):
    make_notification(student, title="较早通知", read=True)
    make_notification(student, title="通知一")
    make_notification(student, title="通知二")

    token = login(api_client, "student_001").json()["data"]["token"]
    response = api_client.get(
        "/api/v1/notifications?pageSize=2", **auth_header(token)
    )
    assert response.status_code == 200, response.content.decode()
    data = response.json()["data"]
    assert data["total"] == 3
    assert data["pages"] == 2
    assert data["unreadCount"] == 2
    assert len(data["list"]) == 2
    assert set(data["list"][0]) == {
        "id", "type", "title", "content", "link", "read", "createdAt"
    }


@pytest.mark.django_db
def test_filter_unread_only_and_type(api_client, student):
    make_notification(student, ntype=NotificationType.SYSTEM, title="系统")
    make_notification(
        student, ntype=NotificationType.QUESTION_REVIEW_APPROVED, title="审核通过"
    )
    token = login(api_client, "student_001").json()["data"]["token"]

    unread = api_client.get(
        "/api/v1/notifications?unreadOnly=true", **auth_header(token)
    ).json()["data"]
    assert unread["total"] == 2

    filtered = api_client.get(
        "/api/v1/notifications?type=system", **auth_header(token)
    ).json()["data"]
    assert filtered["total"] == 1
    assert filtered["list"][0]["type"] == "system"


@pytest.mark.django_db
def test_mark_read_is_idempotent(api_client, student):
    notification = make_notification(student)
    token = login(api_client, "student_001").json()["data"]["token"]

    first = api_client.patch(
        f"/api/v1/notifications/{notification.id}/read", **auth_header(token)
    )
    assert first.status_code == 200
    body = first.json()["data"]
    assert body["read"] is True
    assert body["readAt"]

    second = api_client.patch(
        f"/api/v1/notifications/{notification.id}/read", **auth_header(token)
    )
    assert second.status_code == 200
    assert second.json()["data"]["readAt"] == body["readAt"]


@pytest.mark.django_db
def test_cannot_read_other_users_notification(api_client, student, other_student):
    notification = make_notification(student)
    token = login(api_client, "student_002").json()["data"]["token"]
    response = api_client.patch(
        f"/api/v1/notifications/{notification.id}/read", **auth_header(token)
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_read_all_only_affects_current_user(api_client, student, other_student):
    make_notification(student)
    make_notification(student)
    other = make_notification(other_student)
    token = login(api_client, "student_001").json()["data"]["token"]

    first = api_client.patch("/api/v1/notifications/read-all", **auth_header(token))
    assert first.status_code == 200
    assert first.json()["data"]["updatedCount"] == 2

    second = api_client.patch("/api/v1/notifications/read-all", **auth_header(token))
    assert second.json()["data"]["updatedCount"] == 0

    other.refresh_from_db()
    assert other.read_at is None


@pytest.mark.django_db
def test_question_review_writes_notification(teacher, question_admin, course):
    question = Question.objects.create(
        subject=Subject.MUSIC,
        grade=7,
        course=course,
        type="single_choice",
        stem="审核通知测试题",
        score=5,
        answer={"value": "A"},
        status=QuestionStatus.PENDING,
        creator=teacher,
    )
    review_question(question_admin, question, "approve", "符合要求")
    notification = Notification.objects.get(user=teacher)
    assert notification.type == NotificationType.QUESTION_REVIEW_APPROVED
    assert notification.payload["questionId"] == question.id

    question.status = QuestionStatus.PENDING
    question.save(update_fields=["status", "updated_at"])
    review_question(question_admin, question, "reject", "题干不完整")
    assert Notification.objects.filter(
        user=teacher, type=NotificationType.QUESTION_REVIEW_REJECTED
    ).exists()


@pytest.mark.django_db
def test_paper_review_permission_matrix():
    for role in (
        Role.SCHOOL_ADMIN,
        Role.DISTRICT_ADMIN,
        Role.CITY_ADMIN,
        Role.PROVINCE_ADMIN,
    ):
        assert "paper.review" in permissions_for(role)
    assert "paper.review" not in permissions_for(Role.TEACHER)
    assert "paper.review" not in permissions_for(Role.QUESTION_ADMIN)
