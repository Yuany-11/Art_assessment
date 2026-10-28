"""生成 7 类角色的演示账号，可重复执行。"""
import os

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import StudentProfile, TeacherProfile, User
from apps.classes.models import Class, ClassTeacher
from apps.organizations.models import Organization
from common.enums import AccountStatus, OrganizationLevel, Role, Subject

DEMO_USERS = [
    # username, real_name, role, org_level, extra
    ("province_admin", "省管理员", Role.PROVINCE_ADMIN, OrganizationLevel.PROVINCE, {}),
    ("city_admin", "市州管理员", Role.CITY_ADMIN, OrganizationLevel.CITY, {}),
    ("district_admin", "区县管理员", Role.DISTRICT_ADMIN, OrganizationLevel.DISTRICT, {}),
    ("school_admin", "学校管理员", Role.SCHOOL_ADMIN, OrganizationLevel.SCHOOL, {}),
    ("question_admin", "题库管理员", Role.QUESTION_ADMIN, None, {}),
    (
        "teacher_music",
        "李老师",
        Role.TEACHER,
        OrganizationLevel.SCHOOL,
        {"teacher_no": "T1001", "subject": Subject.MUSIC, "title": "一级教师"},
    ),
    (
        "teacher_art",
        "赵老师",
        Role.TEACHER,
        OrganizationLevel.SCHOOL,
        {"teacher_no": "T1002", "subject": Subject.ART, "title": "二级教师"},
    ),
    (
        "student_001",
        "王小明",
        Role.STUDENT,
        OrganizationLevel.SCHOOL,
        {"student_no": "S20260001", "grade": 7},
    ),
    (
        "student_002",
        "李小红",
        Role.STUDENT,
        OrganizationLevel.SCHOOL,
        {"student_no": "S20260002", "grade": 7},
    ),
]


class Command(BaseCommand):
    help = "初始化演示账号（密码取 DEMO_PASSWORD，未配置则随机生成）"

    def handle(self, *args, **options):
        orgs = {
            org.level: org
            for org in Organization.objects.filter(deleted_at__isnull=True, code__startswith="DEMO-")
        }
        if not orgs:
            raise CommandError("未找到演示组织，请先执行 python manage.py seed_organizations")

        # 未配置 DEMO_PASSWORD 时使用统一演示密码，保证新机器初始化后能直接登录。
        password = os.getenv("DEMO_PASSWORD") or "Demo@123456"
        created_count = 0
        classroom, _ = Class.objects.get_or_create(
            school=orgs[OrganizationLevel.SCHOOL],
            class_code="DEMO-ACC-7-1",
            defaults={"name": "七年级（1）班", "grade": 7},
        )

        for username, real_name, role, org_level, extra in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "real_name": real_name,
                    "role": role,
                    "org": orgs.get(org_level) if org_level else None,
                    "status": AccountStatus.ACTIVE,
                },
            )
            if created:
                user.set_password(password)
                user.save(update_fields=["password", "updated_at"])
                created_count += 1

            if role == Role.TEACHER:
                TeacherProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "teacher_no": extra.get("teacher_no"),
                        "subject": extra.get("subject"),
                        "title": extra.get("title"),
                    },
                )
                if extra.get("subject"):
                    ClassTeacher.objects.get_or_create(
                        teacher=user,
                        class_obj=classroom,
                        defaults={"subject": extra["subject"]},
                    )
                if username == "teacher_music" and classroom.head_teacher_id is None:
                    classroom.head_teacher = user
                    classroom.save(update_fields=["head_teacher", "updated_at"])
            elif role == Role.STUDENT:
                profile, created = StudentProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "student_no": extra.get("student_no"),
                        "grade": extra.get("grade"),
                        "classroom": classroom,
                    },
                )
                if not created and profile.classroom_id is None:
                    profile.classroom = classroom
                    profile.save(update_fields=["classroom", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(f"演示账号初始化完成：新建 {created_count} 个，共 {len(DEMO_USERS)} 个")
        )
        self.stdout.write(f"演示账号密码：{password}")
