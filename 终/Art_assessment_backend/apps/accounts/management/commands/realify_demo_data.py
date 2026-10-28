"""清理演示业务记录，并把组织、班级、账号与题目替换为真实信息。

保留：演示账号本身（用户名与密码不变）、班级、课程章节、题库试题、菜单。
删除：试卷、测评、答卷、成绩、证书、错题、学情报告、通知、审核/操作日志、
      入班申请、导入任务，以及这些记录产生的上传文件。

随后：
- 合并重复的两套演示组织树，保留一套并改为真实省/市/区/学校；
- 合并重复的「七年级（1）班」，班级号改为真实学年度编码；
- 教师、管理员、学生改为真实姓名（学生的姓名按固定规则生成，可重复执行）；
- 删除 5 道 ``[演示]`` 试题与「[演示] 七年级音乐」课程；
- 去掉 3500 道题库题目前的「【音乐】/【美术】」标记。

命令可重复执行：已清理或已改名的数据不会再次改动。

用法::

    python manage.py realify_demo_data --dry-run   # 只预览
    python manage.py realify_demo_data             # 实际执行
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import ImportTask as AccountImportTask
from apps.accounts.models import StudentProfile, TeacherProfile, User
from apps.classes.models import Class, ClassTeacher, JoinRequest
from apps.exams.models import (
    Assessment,
    Attempt,
    Certificate,
    GradingLog,
    ImportTask as ExamImportTask,
    LearningReport,
    Notification,
    Paper,
    PaperQuestion,
    PaperReviewLog,
    Score,
    TotalScoreRule,
    WrongQuestion,
)
from apps.files.models import FileObject
from apps.organizations.models import Organization
from apps.qbank.models import Chapter, Course, OperationLog, Question, QuestionResource
from common.enums import Gender, Role, SchoolType

# 组织：保留演示中学所在的一套树（P00/C00/D00/S001），改为四川省内的真实学校。
# legacy_codes 用于把旧版本已改过的行政区划再次迁移到当前取值。
ORG_RENAMES = {
    "P00": {"name": "四川省", "code": "510000", "legacy_codes": ["P00", "430000"]},
    "C00": {"name": "成都市", "code": "510100", "legacy_codes": ["C00", "430100"]},
    "D00": {"name": "青羊区", "code": "510105", "legacy_codes": ["D00", "430105"]},
    "S001": {
        "name": "成都市石室联合中学蜀华分校",
        "code": "510105000001",
        "legacy_codes": ["S001", "430105000001"],
        "school_type": SchoolType.COMBINED,
        "address": "四川省成都市青羊区蜀华街43号",
    },
}

# 需要删除的重复组织（自下而上，父级有 PROTECT）。
DEMO_ORG_CODES = ["DEMO-SCHOOL", "DEMO-DISTRICT", "DEMO-CITY", "DEMO-PROVINCE"]

# 班级号改为「入学年份 + 年级 + 班序」。
CLASS_RENAMES = {
    "DEMO-7-1": ("C20260701", "七年级（1）班"),
    "DEMO-7-2": ("C20260702", "七年级（2）班"),
    "DEMO-7-3": ("C20260703", "七年级（3）班"),
    "DEMO-8-1": ("C20260801", "八年级（1）班"),
    "DEMO-8-2": ("C20260802", "八年级（2）班"),
}

# 班级：班主任 + 科任教师（用户名固定，便于重复执行）。
CLASS_TEACHERS = {
    "C20260701": {
        "head": "teacher",
        "teachers": {"teacher": "music", "teacher_music": "music", "teacher_art": "art"},
    },
    "C20260702": {"head": "teacher_music", "teachers": {"teacher_music": "music", "teacher_art": "art"}},
    "C20260703": {"head": "teacher_art", "teachers": {"teacher_music": "music", "teacher_art": "art"}},
    "C20260801": {"head": "teacher", "teachers": {"teacher": "music", "teacher_art": "art"}},
    "C20260802": {"head": "teacher_art", "teachers": {"teacher": "music", "teacher_art": "art"}},
}

# 管理账号、教师与四个演示学生改为真实姓名。
USER_RENAMES = {
    "province_admin": ("周立新", Gender.MALE),
    "city_admin": ("陈建平", Gender.MALE),
    "district_admin": ("刘敏", Gender.FEMALE),
    "school_admin": ("王建国", Gender.MALE),
    "question_admin": ("孙倩", Gender.FEMALE),
    "teacher": ("陈志远", Gender.MALE),
    "teacher_music": ("李静", Gender.FEMALE),
    "teacher_art": ("赵敏", Gender.FEMALE),
    "student": ("王浩然", Gender.MALE),
    "student2": ("李雨桐", Gender.FEMALE),
    "student_001": ("张子涵", Gender.FEMALE),
    "student_002": ("刘思远", Gender.MALE),
}

TEACHER_TITLES = {
    "teacher": "一级教师",
    "teacher_music": "高级教师",
    "teacher_art": "二级教师",
}

RESERVED_NAMES = {name for name, _ in USER_RENAMES.values()}

SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "高", "林", "罗",
    "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
    "彭", "曾", "肖", "田", "董", "袁", "潘", "蒋", "蔡", "余",
    "杜", "叶", "程", "苏", "魏", "吕", "丁", "任", "沈", "姚",
    "卢", "姜", "崔", "钟", "谭", "陆", "汪", "范", "金", "石",
]

MALE_GIVEN = [
    "子轩", "宇航", "俊杰", "雨泽", "梓豪", "天佑", "明轩", "嘉诚", "奕辰", "博文",
    "皓轩", "志强", "文博", "泽宇", "冠霖", "睿哲", "晨阳", "俊熙", "子墨", "浩宇",
    "一鸣", "思齐", "承泽", "景行", "书航", "弘毅", "修远", "亦凡", "卓然", "星宇",
    "皓宇", "子豪", "嘉豪", "家乐", "天宇", "志豪", "伟诚", "明哲", "俊宇", "子航",
    "泽楷", "文轩", "子骞", "昊然", "昱辰", "锦程", "振宇", "世杰", "国栋", "立轩",
    "海涛", "春晖", "启航", "望舒", "其琛", "远航", "润泽", "宏图", "少华", "秉文",
]

FEMALE_GIVEN = [
    "欣怡", "可欣", "梦洁", "若曦", "思彤", "雨涵", "佳怡", "心怡", "语嫣", "晓彤",
    "诗涵", "怡然", "静怡", "思琪", "雅琪", "梦瑶", "雨萱", "可馨", "梓涵", "紫涵",
    "欣妍", "婉清", "语彤", "书瑶", "沐晴", "念慈", "艺涵", "嘉怡", "若彤", "雨欣",
    "静雯", "佳琪", "思妍", "梦琪", "紫萱", "晓萱", "诗琪", "雅雯", "瑾萱", "依诺",
    "芷若", "初瑶", "听雨", "映雪", "傲晴", "妙可", "书蕾", "采薇", "向晚", "灵萱",
    "清越", "星月", "月婵", "云舒", "南乔", "亦菲", "甜甜", "婧怡", "泓萱", "朵拉",
]

RECORD_MODELS = [
    (Certificate, "证书"),
    (Notification, "通知"),
    (LearningReport, "学情报告"),
    (WrongQuestion, "错题"),
    (GradingLog, "评分日志"),
    (Score, "成绩"),
    (Attempt, "答卷"),
    (ExamImportTask, "测评导入任务"),
    (Assessment, "测评"),
    (PaperReviewLog, "试卷审核日志"),
    (PaperQuestion, "试卷题目"),
    (Paper, "试卷"),
    (JoinRequest, "入班申请"),
    (OperationLog, "操作日志"),
    (TotalScoreRule, "总分规则"),
    (AccountImportTask, "账号导入任务"),
]


class Command(BaseCommand):
    help = "把学校、班级、教师、学生和题目改为真实信息（可选清空演示记录）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只打印将要执行的操作，不写入数据库",
        )
        parser.add_argument(
            "--purge-records",
            action="store_true",
            help="同时清空试卷、测评、答卷、成绩等全部业务记录（仅首次清理演示数据时使用）",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        purge_records = bool(options["purge_records"])
        prefix = "[预览] " if dry_run else ""
        self.stdout.write(self.style.MIGRATE_HEADING(f"{prefix}清理演示数据并替换为真实信息"))

        with transaction.atomic():
            if purge_records:
                self._purge_records(dry_run)
            else:
                self.stdout.write("\n保留现有业务记录（如需清空请加 --purge-records）")
            self._merge_duplicate_class(dry_run)
            self._merge_demo_orgs(dry_run)
            self._rename_orgs(dry_run)
            self._rename_classes(dry_run)
            self._rename_users(dry_run)
            self._sync_student_grades(dry_run)
            self._clean_questions(dry_run)
            self._clean_texts(dry_run)
            if dry_run:
                transaction.set_rollback(True)

        if not dry_run:
            if purge_records:
                self._purge_files()
            self.stdout.write(self.style.SUCCESS("完成：组织/账号/班级/题目已替换为真实信息。"))
        else:
            self.stdout.write(self.style.WARNING("预览结束，未写入任何更改。"))

    # ---- 各步骤 ---------------------------------------------------------

    def _purge_records(self, dry_run: bool) -> None:
        self.stdout.write("\n清理演示业务记录：")
        for model, label in RECORD_MODELS:
            count = model.objects.count()
            if not count:
                continue
            if not dry_run:
                model.objects.all().delete()
            self.stdout.write(f"  删除{label} {count} 条")

    def _merge_duplicate_class(self, dry_run: bool) -> None:
        target = (
            Class.objects.filter(class_code="C20260701").first()
            or Class.objects.filter(class_code="DEMO-7-1").first()
        )
        source = Class.objects.filter(class_code="DEMO-ACC-7-1").first()
        if not source or not target or source.pk == target.pk:
            return
        moved = StudentProfile.objects.filter(classroom=source).update(classroom=target)
        ClassTeacher.objects.filter(class_obj=source).delete()
        if not dry_run:
            Class.objects.filter(pk=source.pk).delete()
        self.stdout.write(
            f"\n合并重复班级：{source.class_code} → {target.class_code}，迁移学生 {moved} 名"
        )

    def _merge_demo_orgs(self, dry_run: bool) -> None:
        real_school = (
            Organization.objects.filter(code="510105000001").first()
            or Organization.objects.filter(code="430105000001").first()
            or Organization.objects.filter(code="S001").first()
        )
        if real_school is None:
            return
        for code in DEMO_ORG_CODES:
            org = Organization.objects.filter(code=code).first()
            if org is None:
                continue
            moved_users = User.objects.filter(org=org).update(org=real_school)
            moved_classes = Class.objects.filter(school=org).update(school=real_school)
            if not dry_run:
                Organization.objects.filter(pk=org.pk).delete()
            self.stdout.write(
                f"删除重复组织 {code}，迁移账号 {moved_users} 个、班级 {moved_classes} 个"
            )

    def _rename_orgs(self, dry_run: bool) -> None:
        self.stdout.write("\n更新组织信息：")
        for values in ORG_RENAMES.values():
            org = Organization.objects.filter(code=values["code"]).first()
            if org is None:
                org = Organization.objects.filter(
                    code__in=values.get("legacy_codes", [])
                ).first()
            if org is None:
                continue
            changed = []
            for field, value in values.items():
                if field == "legacy_codes":
                    continue
                if getattr(org, field) != value:
                    setattr(org, field, value)
                    changed.append(field)
            if changed and not dry_run:
                org.save(update_fields=[*changed, "updated_at"])
            self.stdout.write(
                f"  {values['name']}（{values['code']}）"
                + (f" 更新 {', '.join(changed)}" if changed else " 无变化")
            )

    def _rename_classes(self, dry_run: bool) -> None:
        self.stdout.write("\n更新班级信息：")
        teacher_usernames = {name for values in CLASS_TEACHERS.values() for name in values["teachers"]}
        teacher_users = list(User.objects.filter(username__in=teacher_usernames))
        for old_code, (new_code, name) in CLASS_RENAMES.items():
            cls = Class.objects.filter(class_code=new_code).first()
            old = Class.objects.filter(class_code=old_code).first()
            if cls is not None and old is not None and cls.pk != old.pk:
                moved = StudentProfile.objects.filter(classroom=old).count()
                if not dry_run:
                    StudentProfile.objects.filter(classroom=old).update(classroom=cls)
                    ClassTeacher.objects.filter(class_obj=old).delete()
                    Class.objects.filter(pk=old.pk).delete()
                self.stdout.write(f"  合并重复班级 {old_code} → {new_code}，迁移学生 {moved} 名")
            cls = cls or old
            if cls is None:
                continue
            head = self._user(CLASS_TEACHERS.get(new_code, {}).get("head"))
            if not dry_run:
                cls.name = name
                cls.class_code = new_code
                cls.head_teacher = head
                cls.save(update_fields=["name", "class_code", "head_teacher", "updated_at"])
                ClassTeacher.objects.filter(
                    class_obj=cls, teacher__in=teacher_users
                ).delete()
                for username, subject in CLASS_TEACHERS.get(new_code, {}).get("teachers", {}).items():
                    teacher = self._user(username)
                    if teacher is not None:
                        ClassTeacher.objects.create(
                            class_obj=cls, teacher=teacher, subject=subject
                        )
            self.stdout.write(f"  {name}（{new_code}）")

    def _rename_users(self, dry_run: bool) -> None:
        self.stdout.write("\n更新账号姓名：")
        for username, (real_name, gender) in USER_RENAMES.items():
            changed = User.objects.filter(username=username).update(
                real_name=real_name, gender=gender
            )
            self.stdout.write(f"  {username} → {real_name}" + ("" if changed else "（未找到）"))

        for username, title in TEACHER_TITLES.items():
            if not dry_run:
                TeacherProfile.objects.filter(user__username=username).update(title=title)

        numbered = list(
            User.objects.filter(role=Role.STUDENT, username__startswith="student_")
            .exclude(username__in=USER_RENAMES)
            .order_by("id")
        )
        if not numbered:
            return
        male_names = self._build_names(MALE_GIVEN, (len(numbered) + 1) // 2)
        female_names = self._build_names(FEMALE_GIVEN, len(numbered) // 2)
        for index, user in enumerate(numbered):
            is_male = index % 2 == 0
            real_name = (male_names if is_male else female_names)[index // 2]
            if not dry_run:
                User.objects.filter(pk=user.pk).update(
                    real_name=real_name,
                    gender=Gender.MALE if is_male else Gender.FEMALE,
                )
        self.stdout.write(f"  其余 {len(numbered)} 名学生已生成真实姓名")

    def _sync_student_grades(self, dry_run: bool) -> None:
        if dry_run:
            return
        for cls in Class.objects.all():
            StudentProfile.objects.filter(classroom=cls).update(grade=cls.grade)

    def _clean_questions(self, dry_run: bool) -> None:
        self.stdout.write("\n清理题目：")
        demo_questions = Question.objects.filter(
            Q(course_id=1) | Q(stem__startswith="[演示]")
        )
        demo_count = demo_questions.count()
        if demo_count and not dry_run:
            demo_questions.delete()
        self.stdout.write(f"  删除演示试题 {demo_count} 道")

        course = (
            Course.objects.filter(name__contains="[演示]").order_by("id").first()
            or Course.objects.filter(pk=1).first()
        )
        if course is not None:
            if not dry_run:
                Chapter.objects.filter(course=course).delete()
                Course.objects.filter(pk=course.pk).delete()
            self.stdout.write(f"  删除演示课程「{course.name}」")

        prefixed = Question.objects.filter(
            Q(stem__startswith="【音乐】") | Q(stem__startswith="【美术】")
        )
        stripped = prefixed.count()
        if stripped and not dry_run:
            rows = list(prefixed)
            for question in rows:
                question.stem = question.stem[4:]
            Question.objects.bulk_update(rows, ["stem"], batch_size=500)
        self.stdout.write(f"  去除学科前缀的试题 {stripped} 道")

    def _clean_texts(self, dry_run: bool) -> None:
        """清理简介、审核意见等字段中的演示字样。"""
        class_descriptions = Class.objects.filter(description__contains="演示").count()
        course_descriptions = Course.objects.filter(description__contains="演示").count()
        review_comments = Question.objects.filter(review_comment__contains="演示").count()
        self.stdout.write(
            f"  清理演示文案：班级 {class_descriptions} 个、课程 {course_descriptions} 门、"
            f"试题审核意见 {review_comments} 条"
        )
        if dry_run:
            return
        Class.objects.filter(description__contains="演示").update(
            description="音乐、美术双学科教学班"
        )
        for course_name, description in (
            ("七年级音乐（人教版）", "依据人教版七年级音乐教材编排的课程"),
            ("七年级美术（人美版）", "依据人美版七年级美术教材编排的课程"),
        ):
            Course.objects.filter(
                name=course_name, description__contains="演示"
            ).update(description=description)
        Question.objects.filter(review_comment__contains="演示").update(
            review_comment="批量导入，审核通过"
        )

    # ---- 文件 -----------------------------------------------------------

    def _purge_files(self) -> None:
        keep_ids = set(QuestionResource.objects.values_list("file_id", flat=True))
        orphans = FileObject.objects.exclude(pk__in=keep_ids)
        keys = list(orphans.values_list("object_key", flat=True))
        for key in keys:
            try:
                default_storage.delete(key)
            except Exception:  # pragma: no cover - 文件已丢失时忽略
                pass
        deleted = orphans.count()
        orphans.delete()

        # 删除磁盘上没有 FileObject 记录的残留文件（历史演示数据直接写入 media/）。
        remaining = set(FileObject.objects.values_list("object_key", flat=True))
        media_root = Path(settings.MEDIA_ROOT)
        stray = 0
        if media_root.is_dir():
            for path in media_root.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(media_root).as_posix()
                if relative in remaining:
                    continue
                try:
                    path.unlink()
                    stray += 1
                except OSError:  # pragma: no cover
                    pass
            for path in sorted(media_root.rglob("*"), reverse=True):
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()

        self.stdout.write(f"\n清理文件：删除登记文件 {deleted} 个、磁盘残留 {stray} 个")

    # ---- 工具 -----------------------------------------------------------

    def _user(self, username: str | None):
        if not username:
            return None
        return User.objects.filter(username=username).first()

    def _build_names(self, given_pool: list[str], count: int) -> list[str]:
        """用固定规则生成互不重复的真实姓名，保证可重复执行结果一致。"""
        names: list[str] = []
        index = 0
        while len(names) < count:
            surname = SURNAMES[index % len(SURNAMES)]
            given = given_pool[(index // len(SURNAMES) + index) % len(given_pool)]
            index += 1
            candidate = surname + given
            if candidate in RESERVED_NAMES or candidate in names:
                continue
            names.append(candidate)
        return names
