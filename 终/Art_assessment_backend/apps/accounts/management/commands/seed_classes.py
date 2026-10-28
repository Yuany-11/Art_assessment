"""批量补充演示班级与学生账号，可重复执行。

默认在「演示中学」下新增 4 个班级（七/八年级各 2 个），每班 20 名学生，
并把音乐、美术教师挂到班级上，便于教师端与学校管理端直接查看。

用法：
    python manage.py seed_classes
    python manage.py seed_classes --per-class 25
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import StudentProfile, User
from apps.classes.models import Class, ClassTeacher
from apps.organizations.models import Organization
from common.enums import (
    AccountStatus,
    ClassStatus,
    Gender,
    OrganizationLevel,
    Role,
    Subject,
)

# (年级, 班号, 班主任用户名)
CLASSES = [
    (7, 2, "teacher"),
    (7, 3, "teacher_art"),
    (8, 1, "teacher"),
    (8, 2, "teacher_art"),
]

SURNAMES = (
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗",
)
GIVEN_MALE = (
    "浩然", "子轩", "宇航", "博文", "嘉豪", "俊杰", "明轩", "天佑", "思远", "晨曦",
    "一鸣", "泽宇", "文博", "皓轩", "梓涵", "承泽", "睿哲", "家豪", "雨泽", "子墨",
)
GIVEN_FEMALE = (
    "雨涵", "欣怡", "梓涵", "诗琪", "梦瑶", "思彤", "可欣", "依诺", "语汐", "佳怡",
    "若曦", "梦洁", "欣然", "嘉怡", "静怡", "姝妍", "芷涵", "艺涵", "悦然", "书瑶",
)

CHINESE_GRADE = {7: "七", 8: "八", 9: "九"}


def _student_name(grade: int, class_no: int, index: int) -> tuple[str, str]:
    """按班级和序号稳定地生成姓名与性别。"""
    seed = grade * 1000 + class_no * 100 + index
    male = seed % 2 == 1
    given = GIVEN_MALE if male else GIVEN_FEMALE
    name = SURNAMES[seed % len(SURNAMES)] + given[(seed // len(SURNAMES)) % len(given)]
    return name, Gender.MALE if male else Gender.FEMALE


class Command(BaseCommand):
    help = "新增演示班级与学生账号（默认 4 个班 × 20 人，可重复执行）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--per-class", type=int, default=20,
            help="每个班级的学生人数，默认 20",
        )
        parser.add_argument(
            "--school-code", default="S001",
            help="目标学校组织编码，默认 S001（演示中学）",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        per_class = options["per_class"]
        if per_class <= 0:
            raise CommandError("--per-class 必须大于 0")

        school = (
            Organization.objects.filter(
                code=options["school_code"], deleted_at__isnull=True
            ).first()
            or Organization.objects.filter(
                level=OrganizationLevel.SCHOOL, deleted_at__isnull=True
            ).order_by("id").first()
        )
        if school is None:
            raise CommandError("未找到学校组织，请先执行 python manage.py seed_organizations")

        admin = User.objects.filter(
            username="school_admin", role=Role.SCHOOL_ADMIN, deleted_at__isnull=True
        ).first()
        teachers = {
            user.username: user
            for user in User.objects.filter(
                username__in=[item[2] for item in CLASSES]
                + ["teacher_music", "teacher_art"],
                deleted_at__isnull=True,
            )
        }
        music_teacher = teachers.get("teacher") or teachers.get("teacher_music")
        art_teacher = teachers.get("teacher_art")

        password = os.getenv("DEMO_PASSWORD") or "Demo@123456"
        created_classes = 0
        created_students = 0
        updated_students = 0

        for grade, class_no, head_username in CLASSES:
            class_code = f"DEMO-{grade}-{class_no}"
            classroom, created = Class.objects.get_or_create(
                class_code=class_code,
                defaults={
                    "name": f"{CHINESE_GRADE.get(grade, grade)}年级（{class_no}）班",
                    "grade": grade,
                    "school": school,
                    "head_teacher": teachers.get(head_username),
                    "description": "演示班级，音乐 / 美术双学科教学班",
                    "status": ClassStatus.ACTIVE,
                    "created_by": admin,
                },
            )
            if created:
                created_classes += 1
            elif classroom.deleted_at is not None:
                classroom.deleted_at = None
                classroom.school = school
                classroom.save(update_fields=["deleted_at", "school", "updated_at"])

            for teacher, subject in ((music_teacher, Subject.MUSIC), (art_teacher, Subject.ART)):
                if teacher is None:
                    continue
                ClassTeacher.objects.get_or_create(
                    class_obj=classroom,
                    teacher=teacher,
                    defaults={"subject": subject},
                )

            for index in range(1, per_class + 1):
                username = f"student_{grade}_{class_no}_{index:02d}"
                real_name, gender = _student_name(grade, class_no, index)
                student, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "real_name": real_name,
                        "role": Role.STUDENT,
                        "org": school,
                        "phone": f"138{grade:02d}{class_no:02d}{index:04d}",
                        "gender": gender,
                        "status": AccountStatus.ACTIVE,
                    },
                )
                if created:
                    student.set_password(password)
                    student.save(update_fields=["password", "updated_at"])
                    created_students += 1

                profile, profile_created = StudentProfile.objects.get_or_create(
                    user=student,
                    defaults={
                        "student_no": f"S2026{grade:02d}{class_no:02d}{index:03d}",
                        "grade": grade,
                        "guardian_phone": student.phone,
                        "classroom": classroom,
                    },
                )
                if not profile_created and profile.classroom_id != classroom.id:
                    profile.classroom = classroom
                    profile.grade = grade
                    profile.save(update_fields=["classroom", "grade", "updated_at"])
                    updated_students += 1

        student_total = StudentProfile.objects.filter(
            classroom__school=school, deleted_at__isnull=True, user__deleted_at__isnull=True
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"班级初始化完成：新建 {created_classes} 个班级、{created_students} 名学生"
                f"（调整班级归属 {updated_students} 人）"
            )
        )
        self.stdout.write(
            f"{school.name} 现有 {Class.objects.filter(school=school, deleted_at__isnull=True).count()} 个班级、"
            f"{student_total} 名学生"
        )
        self.stdout.write(
            f"学生登录账号形如 student_7_2_01，密码：{password}"
        )
