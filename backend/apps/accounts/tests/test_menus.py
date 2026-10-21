"""AUTH-07 角色菜单。"""
import pytest
from django.core.management import call_command

from common.enums import OrganizationLevel, Role

from conftest import auth_header, login


@pytest.mark.django_db
def test_menus_for_every_role(api_client, make_user):
    call_command("seed_menus")
    role_org = {
        Role.STUDENT: OrganizationLevel.SCHOOL,
        Role.TEACHER: OrganizationLevel.SCHOOL,
        Role.SCHOOL_ADMIN: OrganizationLevel.SCHOOL,
        Role.DISTRICT_ADMIN: OrganizationLevel.DISTRICT,
        Role.CITY_ADMIN: OrganizationLevel.CITY,
        Role.PROVINCE_ADMIN: OrganizationLevel.PROVINCE,
        Role.QUESTION_ADMIN: None,
    }

    for role, org_level in role_org.items():
        username = f"menu_{role}"
        make_user(username, role, org_level)
        token = login(api_client, username).json()["data"]["token"]
        response = api_client.get("/api/v1/auth/menus", **auth_header(token))
        assert response.status_code == 200
        tree = response.json()["data"]
        assert tree, f"{role} 菜单不应为空"
        assert all(item["id"].split(".")[0] for item in tree)


@pytest.mark.django_db
def test_student_menu_has_no_qbank(api_client, student):
    call_command("seed_menus")
    token = login(api_client, "student_001").json()["data"]["token"]
    tree = api_client.get("/api/v1/auth/menus", **auth_header(token)).json()["data"]
    paths = [node["path"] for node in tree]
    assert not any(path.startswith("/qbank") for path in paths)
    assert "/student/home" in paths
