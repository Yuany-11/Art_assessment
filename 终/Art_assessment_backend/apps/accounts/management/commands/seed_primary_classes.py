"""为真实学校补充小学部班级与学生账号，可重复执行。

默认在「成都市石室联合中学蜀华分校」（九年一贯制）下新增三年级（1）班、
六年级（1）班，每班 20 名学生，便于展示小学学段的班级与学生管理。

用法：
    python manage.py seed_primary_classes
    python manage.py seed_primary_classes --per-class 25
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
    (3, 1, "teacher_music"),
    (6, 1, "teacher_art"),
]

CHINESE_GRADE = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}

SURNAMES = (
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗",
    "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
)
GIVEN_MALE = (
    "一诺", "子墨", "梓豪", "浩然", "奕辰", "嘉树", "牧之", "星辰", "书言", "朗朗",
    "知远", "明礼", "思源", "亦航", "云帆", "景铄", "少卿", "砚舟", "清和", "照野",
)
GIVEN_FEMALE = (
    "一涵", "语汐", "可心", "沐言", "芷晴", "书宁", "念初", "星禾", "婉宁", "知夏",
    "安然", "清妍", "若溪", "舒窈", "南栀", "月白", "云汐", "甜心", "妙言", "小满",
)


def _unique_name(index: int, male: bool) -> str:
    """生成不与现有账号重复的姓名。"""
    given = GIVEN_MALE if male else GIVEN_FEMALE
    for offset in range(200):
        surname = SURNAMES[(index * 7 + offset) % len(SURNAMES)]
        candidate = surname + given[(index * 11 + offset * 3) % len(given)]
        if not User.objects.filter(real_name=candidate).exists():
            return candidate
    raise CommandError("无法生成不重复的学生姓名")


class Command(BaseCommand):
    help = "为九年一贯制学校补充小学部班级与学生（默认 2 个班 × 20 人）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--per-class", type=int, default=20,
            help="每个班级的学生人数，默认 20",
        )
        parser.add_argument(
            "--school-code", default="510105000001",
            help="目标学校组织编码，默认 510105000001（成都市石室联合中学蜀华分校）",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        per_class = options["per_class"]
        if per_class <= 0:
            raise CommandError("--per-class 必须大于 0")

        school = (
            Organization.objects.filter(
                code=options["school_code"],
                level=OrganizationLevel.SCHOOL,
                deleted_at__isnull=True,
            ).first()
            or Organization.objects.filter(
                level=OrganizationLevel.SCHOOL, deleted_at__isnull=True
            ).order_by("id").first()
        )
        if school is None:
            raise CommandError("未找到学校组织，请先执行 seed_organizations 或 realify_demo_data")

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
        music_teacher = teachers.get("teacher_music")
        art_teacher = teachers.get("teacher_art")

        password = os.getenv("DEMO_PASSWORD") or "Demo@123456"
        created_classes = 0
        created_students = 0
        updated_students = 0

        for grade, class_no, head_username in CLASSES:
            class_code = f"C2026{grade:02d}{class_no:02d}"
            classroom, created = Class.objects.get_or_create(
                class_code=class_code,
                defaults={
                    "name": f"{CHINESE_GRADE.get(grade, grade)}年级（{class_no}）班",
                    "grade": grade,
                    "school": school,
                    "head_teacher": teachers.get(head_username),
                    "description": "小学音乐、美术双学科教学班",
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
                male = index % 2 == 1
                real_name = _unique_name(grade * 100 + class_no * 10 + index, male)
                student, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "real_name": real_name,
                        "role": Role.STUDENT,
                        "org": school,
                        "phone": f"139{grade:02d}{class_no:02d}{index:04d}",
                        "gender": Gender.MALE if male else Gender.FEMALE,
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
                if not profile_created and (
                    profile.classroom_id != classroom.id or profile.grade != grade
                ):
                    profile.classroom = classroom
                    profile.grade = grade
                    profile.save(update_fields=["classroom", "grade", "updated_at"])
                    updated_students += 1

        student_total = StudentProfile.objects.filter(
            classroom__school=school, deleted_at__isnull=True, user__deleted_at__isnull=True
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"小学部初始化完成：新建 {created_classes} 个班级、{created_students} 名学生"
                f"（调整班级归属 {updated_students} 人）"
            )
        )
        self.stdout.write(
            f"{school.name} 现有 {Class.objects.filter(school=school, deleted_at__isnull=True).count()} 个班级、"
            f"{student_total} 名学生"
        )
        self.stdout.write(f"学生登录账号形如 student_3_1_01，密码：{password}")
