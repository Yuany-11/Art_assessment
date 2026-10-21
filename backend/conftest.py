"""pytest 公共 fixture。"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import StudentProfile, TeacherProfile, User
from apps.organizations.models import Organization
from common.enums import AccountStatus, OrganizationLevel, Role, Subject

PASSWORD = "Art@2026"


@pytest.fixture
def orgs(db):
    province = Organization.objects.create(
        level=OrganizationLevel.PROVINCE, name="示例省", code="TEST-PROVINCE"
    )
    city = Organization.objects.create(
        level=OrganizationLevel.CITY, name="示例市", code="TEST-CITY", parent=province
    )
    district = Organization.objects.create(
        level=OrganizationLevel.DISTRICT, name="示例区", code="TEST-DISTRICT", parent=city
    )
    school = Organization.objects.create(
        level=OrganizationLevel.SCHOOL, name="示范中学", code="TEST-SCHOOL", parent=district
    )
    return {
        OrganizationLevel.PROVINCE: province,
        OrganizationLevel.CITY: city,
        OrganizationLevel.DISTRICT: district,
        OrganizationLevel.SCHOOL: school,
    }


@pytest.fixture
def make_user(orgs):
    def _make(username: str, role: str, org_level=None, **extra):
        extra.setdefault("real_name", username)
        user = User.objects.create_user(
            username=username,
            password=PASSWORD,
            role=role,
            org=orgs.get(org_level) if org_level else None,
            **extra,
        )
        return user

    return _make


@pytest.fixture
def teacher(make_user):
    user = make_user("teacher_music", Role.TEACHER, OrganizationLevel.SCHOOL)
    TeacherProfile.objects.create(
        user=user, teacher_no="T1001", subject=Subject.MUSIC, title="一级教师"
    )
    return user


@pytest.fixture
def student(make_user):
    user = make_user("student_001", Role.STUDENT, OrganizationLevel.SCHOOL)
    StudentProfile.objects.create(user=user, student_no="S20260001", grade=7)
    return user


@pytest.fixture
def school_admin(make_user):
    return make_user("school_admin", Role.SCHOOL_ADMIN, OrganizationLevel.SCHOOL)


@pytest.fixture
def question_admin(make_user):
    return make_user("question_admin", Role.QUESTION_ADMIN)


@pytest.fixture
def api_client():
    return APIClient()


def login(client, username: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login", {"username": username, "password": password}, format="json"
    )


def auth_header(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def disabled_user(make_user):
    user = make_user("disabled_user", Role.TEACHER, OrganizationLevel.SCHOOL)
    user.status = AccountStatus.DISABLED
    user.save(update_fields=["status", "updated_at"])
    return user
