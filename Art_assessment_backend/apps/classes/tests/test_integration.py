"""P4 支撑：测评发布目标学生名单解析。"""
import pytest

from apps.accounts.models import StudentProfile, User
from apps.classes.integration import build_student_ref, resolve_target_students
from apps.classes.models import Class
from apps.organizations.models import Organization
from common.enums import OrganizationLevel, Role
from common.exceptions import BusinessError


@pytest.mark.django_db
def test_resolve_class_students(student, other_student, classroom):
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])
    other_student.student_profile.classroom = classroom
    other_student.student_profile.save(update_fields=["classroom", "updated_at"])

    result = resolve_target_students("class", [classroom.id], [7])
    assert {item.id for item in result} == {student.id, other_student.id}

    assert resolve_target_students("class", [classroom.id], [8]) == []


@pytest.mark.django_db
def test_resolve_school_and_district_scope(orgs, student, classroom):
    student.student_profile.classroom = classroom
    student.student_profile.save(update_fields=["classroom", "updated_at"])

    second_school = Organization.objects.create(
        level=OrganizationLevel.SCHOOL,
        parent=orgs[OrganizationLevel.DISTRICT],
        name="第二中学",
        code="TEST-SCHOOL-2",
    )
    second_student = User.objects.create_user(
        username="student_009",
        password="Art@2026",
        real_name="外校学生",
        role=Role.STUDENT,
        org=second_school,
    )
    StudentProfile.objects.create(
        user=second_student, student_no="S20260009", grade=7
    )

    school_students = resolve_target_students(
        "school", [orgs[OrganizationLevel.SCHOOL].id], [7]
    )
    assert {item.id for item in school_students} == {student.id}

    district_students = resolve_target_students(
        "district", [orgs[OrganizationLevel.DISTRICT].id], [7]
    )
    assert {item.id for item in district_students} == {student.id, second_student.id}

    ref = build_student_ref(student)
    assert ref["studentId"] == student.id
    assert ref["className"] == classroom.name
    assert ref["schoolName"] == "示范中学"


@pytest.mark.django_db
def test_resolve_invalid_target(student):
    with pytest.raises(BusinessError):
        resolve_target_students("unknown", [1])
