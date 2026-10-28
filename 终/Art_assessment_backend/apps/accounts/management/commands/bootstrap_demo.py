"""一条命令完成本地演示环境初始化：建表 + 角色菜单 + 组织 + 演示数据 + 题库。

适合新电脑第一次部署：装完依赖后执行
    python manage.py bootstrap_demo

已初始化的环境可重复执行，各 seed 命令本身幂等（不重复插入）。
只想快速看界面、不需要 3600 道题时可加 --skip-bank。
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

DEMO_PASSWORD = "Demo@123456"

# 顺序不可随意调整：
# seed_all_portals 会自动组卷（含音频/图片上传题），必须先把题库补齐，
# 否则新库里会报「题库题目不足：audio_upload 需要 1 道」。
SEED_STEPS = [
    ("seed_menus", "角色与菜单"),
    ("seed_organizations", "省/市/区县/学校"),
    ("seed_demo_accounts", "七类角色演示账号"),
    ("seed_demo", "课程、班级、试卷、测评、成绩"),
    ("seed_question_bank", "音乐/美术题库（3600 道）与章节知识讲解"),
    ("seed_rich_demo", "分类题库、组卷、学情报告、证书"),
    ("seed_all_portals", "全部学生/教师的功能页面数据"),
    ("seed_classes", "中学 4 个班（每班约 20 名学生）"),
    ("seed_primary_classes", "小学部 2 个班"),
    # 最后把演示组织、账号、试题换成真实信息（保留业务记录，不改用户名与密码）。
    ("realify_demo_data", "替换为真实学校/姓名/题目"),
]


class Command(BaseCommand):
    help = "初始化本地演示环境（建表 + 全部演示数据，可重复执行）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-bank",
            action="store_true",
            help="快速模式：跳过 3600 道题库、章节知识讲解与全端口演示数据（初始化更快，页面数据较少）",
        )

    def handle(self, *args, **options):
        # 快速模式下 seed_all_portals 也一并跳过：它自动组卷需要上传类题目。
        skipped = {"seed_question_bank", "seed_all_portals"} if options["skip_bank"] else set()
        steps = [
            (name, label, {})
            for name, label in SEED_STEPS
            if name not in skipped
        ]
        total = len(steps) + 1

        self.stdout.write(self.style.MIGRATE_HEADING(f"[1/{total}] migrate 建表"))
        call_command("migrate", interactive=False, stdout=self.stdout)

        for index, (name, label, kwargs) in enumerate(steps, start=2):
            self.stdout.write(
                self.style.MIGRATE_HEADING(f"[{index}/{total}] {name} · {label}")
            )
            try:
                call_command(name, stdout=self.stdout, **kwargs)
            except CommandError as exc:
                raise CommandError(f"{name} 执行失败：{exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "本地演示环境初始化完成。"
                f"演示账号密码统一为 {DEMO_PASSWORD}，"
                "可用 python manage.py runserver 启动后端。"
            )
        )
