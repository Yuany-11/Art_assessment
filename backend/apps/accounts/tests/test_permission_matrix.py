"""P8 回归：模块一/二 7 角色权限矩阵。"""
import pytest

from conftest import auth_header, login

ADMINS = {"school_admin", "district_admin", "city_admin", "province_admin"}
ALL_ROLES = {"student", "teacher", *ADMINS, "question_admin"}

ROLE_USERS = [
    ("student", "student_001"),
    ("teacher", "teacher_music"),
    ("school_admin", "school_admin"),
    ("district_admin", "district_admin"),
    ("city_admin", "city_admin"),
    ("province_admin", "province_admin"),
    ("question_admin", "question_admin"),
]

ENDPOINTS = [
    ("/api/v1/auth/me", ALL_ROLES),
    ("/api/v1/accounts", ADMINS),
    ("/api/v1/classes", {"teacher", *ADMINS}),
    ("/api/v1/questions", {"teacher", *ADMINS, "question_admin"}),
    ("/api/v1/courses", ALL_ROLES),
    ("/api/v1/logs", {"question_admin", "province_admin"}),
]

CASES = [
    (fixture, username, path, 200 if fixture in allowed else 403)
    for fixture, username in ROLE_USERS
    for path, allowed in ENDPOINTS
]


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name,username,path,expected", CASES)
def test_module12_permission_matrix(
    request, api_client, fixture_name, username, path, expected
):
    request.getfixturevalue(fixture_name)
    token = login(api_client, username).json()["data"]["token"]
    response = api_client.get(path, **auth_header(token))
    assert response.status_code == expected, (
        f"{fixture_name} {path}: {response.status_code} != {expected}"
    )
    assert response.json()["code"] == expected
