"""补齐演示班级的班主任与音乐/美术教师账号，可重复执行。

每个班级配置一名独立的班主任；同一名教师不会同时担任两个班级的班主任。
每个班级同时配置一名音乐教师和一名美术教师，所有出现在班级任课关系中的
教师都有对应的登录账号。

用法：
    python manage.py seed_teacher_roster
    python manage.py seed_teacher_roster --dry-run
"""
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import TeacherProfile, User
from apps.classes.models import Class, ClassTeacher
from apps.exams.models import Assessment
from apps.organizations.models import Organization
from common.enums import (
    AccountStatus,
    ClassStatus,
    Gender,
    OrganizationLevel,
    Role,
    ScopeType,
    Subject,
)

MUSIC = Subject.MUSIC
ART = Subject.ART

# 班级 code -> 班主任 / 音乐教师 / 美术教师（用户名）
ROSTER = [
    {"class_code": "C20260701", "head": "teacher", "music": "teacher_music", "art": "teacher_art"},
    {"class_code": "C20260702", "head": "teacher_wang", "music": "teacher_wang", "art": "teacher_art"},
    {"class_code": "C20260703", "head": "teacher_liu", "music": "teacher_music", "art": "teacher_liu"},
    {"class_code": "C20260801", "head": "teacher_zhou", "music": "teacher_zhou", "art": "teacher_art"},
    {"class_code": "C20260802", "head": "teacher_zhang", "music": "teacher", "art": "teacher_zhang"},
    {"class_code": "C20260301", "head": "teacher_he", "music": "teacher_he", "art": "teacher_art"},
    {"class_code": "C20260601", "head": "teacher_luo", "music": "teacher_music", "art": "teacher_luo"},
]

# 新增教师账号资料；已有账号保持原姓名与工号。
NEW_TEACHERS = {
    "teacher_wang": {
        "real_name": "王海涛", "gender": Gender.MALE, "subject": MUSIC,
        "title": "一级教师", "teacher_no": "T20260002", "phone": "13800002002",
    },
    "teacher_liu": {
        "real_name": "刘雅琴", "gender": Gender.FEMALE, "subject": ART,
        "title": "一级教师", "teacher_no": "T20260003", "phone": "13800002003",
    },
    "teacher_zhou": {
        "real_name": "周晓梅", "gender": Gender.FEMALE, "subject": MUSIC,
        "title": "二级教师", "teacher_no": "T20260004", "phone": "13800002004",
    },
    "teacher_zhang": {
        "real_name": "张建国", "gender": Gender.MALE, "subject": ART,
        "title": "高级教师", "teacher_no": "T20260005", "phone": "13800002005",
    },
    "teacher_he": {
        "real_name": "何晓燕", "gender": Gender.FEMALE, "subject": MUSIC,
        "title": "一级教师", "teacher_no": "T20260006", "phone": "13800002006",
    },
    "teacher_luo": {
        "real_name": "罗文静", "gender": Gender.FEMALE, "subject": ART,
        "title": "二级教师", "teacher_no": "T20260007", "phone": "13800002007",
    },
}


class Command(BaseCommand):
    help = "为演示班级补齐独立班主任、音乐/美术教师账号（可重复执行）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="只检查，不写入数据库"
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        password = os.getenv("DEMO_PASSWORD") or "Demo@123456"

        school = (
            Organization.objects.filter(
                level=OrganizationLevel.SCHOOL, deleted_at__isnull=True
            )
            .order_by("id")
            .first()
        )
        if school is None:
            self.stdout.write(self.style.ERROR("未找到学校组织，请先初始化组织数据"))
            return

        entries = []
        for item in ROSTER:
            classroom = Class.objects.filter(
                class_code=item["class_code"], deleted_at__isnull=True
            ).first()
            if classroom is None:
                self.stdout.write(
                    self.style.WARNING(f"跳过 {item['class_code']}：班级不存在")
                )
                continue
            users = {}
            for key in ("head", "music", "art"):
                user = self._ensure_teacher(
                    item[key], school, password, dry_run=dry_run
                )
                if user is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"跳过 {classroom.name}：教师账号 {item[key]} 不可用"
                        )
                    )
                    users = {}
                    break
                users[key] = user
            if users:
                entries.append((classroom, users))

        if dry_run:
            for classroom, users in entries:
                self.stdout.write(
                    f"[预览] {classroom.name}：班主任 {users['head'].real_name}，"
                    f"音乐 {users['music'].real_name}，美术 {users['art'].real_name}"
                )
            self._audit()
            return

        reassigned = 0
        with transaction.atomic():
            # 先清空本次管理班级的班主任，避免调整过程中出现同一位班主任
            # 短暂管理两个班级的情况。
            for classroom, _users in entries:
                if classroom.head_teacher_id is not None:
                    classroom.head_teacher = None
                    classroom.save(update_fields=["head_teacher", "updated_at"])

            for classroom, users in entries:
                classroom.head_teacher = users["head"]
                classroom.save(update_fields=["head_teacher", "updated_at"])
                reassigned += self._sync_subject_teachers(classroom, users)

        for classroom, users in entries:
            self.stdout.write(
                f"  {classroom.name}：班主任 {users['head'].real_name}，"
                f"音乐 {users['music'].real_name}，美术 {users['art'].real_name}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"教师配置完成：{len(entries)} 个班级，"
                f"转交 {reassigned} 场测评给新任课教师"
            )
        )
        self._audit()

    # ------------------------------------------------------------------
    def _ensure_teacher(self, username: str, school: Organization, password: str, dry_run: bool):
        info = NEW_TEACHERS.get(username, {})
        user = User.objects.filter(username=username, deleted_at__isnull=True).first()
        if user is None:
            if dry_run:
                return User(
                    username=username,
                    real_name=info.get("real_name", username),
                    role=Role.TEACHER,
                    org=school,
                )
            user = User.objects.create_user(
                username=username,
                password=password,
                real_name=info.get("real_name", username),
                role=Role.TEACHER,
                org=school,
                phone=info.get("phone"),
                gender=info.get("gender", Gender.UNKNOWN),
                status=AccountStatus.ACTIVE,
            )
        elif user.role != Role.TEACHER:
            self.stdout.write(
                self.style.ERROR(f"账号 {username} 不是教师角色，无法配置为任课教师")
            )
            return None
        elif not dry_run and (user.org_id != school.id or user.status != AccountStatus.ACTIVE):
            user.org = school
            user.status = AccountStatus.ACTIVE
            user.save(update_fields=["org", "status", "updated_at"])

        if not dry_run and info:
            profile, created = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "teacher_no": info.get("teacher_no"),
                    "subject": info.get("subject"),
                    "title": info.get("title"),
                },
            )
            if not created:
                changed = []
                if not profile.subject and info.get("subject"):
                    profile.subject = info["subject"]
                    changed.append("subject")
                if not profile.title and info.get("title"):
                    profile.title = info["title"]
                    changed.append("title")
                if changed:
                    profile.save(update_fields=[*changed, "updated_at"])
        elif dry_run and not hasattr(user, "teacher_profile"):
            pass
        return user

    def _sync_subject_teachers(self, classroom: Class, users: dict) -> int:
        old_teachers = {
            subject: ClassTeacher.objects.filter(
                class_obj=classroom, subject=subject
            )
            .values_list("teacher_id", flat=True)
            .first()
            for subject in (MUSIC, ART)
        }
        ClassTeacher.objects.filter(class_obj=classroom).delete()
        ClassTeacher.objects.bulk_create(
            [
                ClassTeacher(
                    class_obj=classroom, teacher=users[key], subject=subject
                )
                for key, subject in (("music", MUSIC), ("art", ART))
            ]
        )
        moved = 0
        for key, subject in (("music", MUSIC), ("art", ART)):
            old_id = old_teachers.get(subject)
            if old_id and old_id != users[key].id:
                moved += self._reassign_assessments(
                    classroom, subject, old_id, users[key]
                )
        return moved

    def _reassign_assessments(
        self, classroom: Class, subject: str, old_teacher_id: int, new_teacher
    ) -> int:
        """把本班该学科测评的发布人/试卷创建人转给新的任课教师。"""
        old_teacher = User.objects.filter(pk=old_teacher_id).first()
        if old_teacher is None:
            return 0
        moved = 0
        queryset = Assessment.objects.filter(
            subject=subject,
            publisher=old_teacher,
            target_type=ScopeType.CLASS,
            deleted_at__isnull=True,
        ).select_related("paper")
        for assessment in queryset:
            if (assessment.target_ids or []) != [classroom.id]:
                continue
            assessment.publisher = new_teacher
            assessment.save(update_fields=["publisher", "updated_at"])
            if assessment.paper.creator_id == old_teacher.id:
                paper = assessment.paper
                paper.creator = new_teacher
                paper.save(update_fields=["creator", "updated_at"])
            moved += 1
        return moved

    def _audit(self) -> None:
        self.stdout.write("\n账号与班级配置检查：")
        classes = list(
            Class.objects.filter(
                deleted_at__isnull=True, status=ClassStatus.ACTIVE
            ).select_related("head_teacher")
        )
        heads = {}
        problems = []
        for classroom in classes:
            if classroom.head_teacher_id is None:
                problems.append(f"{classroom.name} 没有班主任")
            else:
                heads.setdefault(classroom.head_teacher_id, []).append(classroom)
            for subject, label in ((MUSIC, "音乐"), (ART, "美术")):
                count = ClassTeacher.objects.filter(
                    class_obj=classroom, subject=subject
                ).count()
                if count != 1:
                    problems.append(f"{classroom.name} 有 {count} 位{label}教师")
        for teacher_id, headed in heads.items():
            if len(headed) > 1:
                teacher = User.objects.filter(pk=teacher_id).first()
                names = "、".join(item.name for item in headed)
                problems.append(
                    f"{getattr(teacher, 'real_name', teacher_id)} 同时担任 {names} 的班主任"
                )

        teachers = User.objects.filter(
            role=Role.TEACHER, deleted_at__isnull=True
        ).count()
        students = User.objects.filter(
            role=Role.STUDENT, deleted_at__isnull=True
        ).count()
        self.stdout.write(f"  有效教师账号 {teachers} 个，学生账号 {students} 个")
        if problems:
            for problem in problems:
                self.stdout.write(self.style.WARNING(f"  ! {problem}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "  每个班级各有一位班主任、一位音乐教师、一位美术教师，"
                    "且班主任不跨班管理。"
                )
            )
