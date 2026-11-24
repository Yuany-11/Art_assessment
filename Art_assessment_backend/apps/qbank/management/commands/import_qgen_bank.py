"""导入 Model B（美术出题模型）交付题库，全部以 pending 状态入库。

只做离线转换与去重，不调用 8002 模型服务，也不修改题库之外的数据。
默认只导入单选、判断题；填空题与简答题按现有产品规则丢弃。
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.qbank.qgen import default_bank_path, import_cards
from common.enums import AccountStatus, Role
from common.exceptions import BusinessError


class Command(BaseCommand):
    help = "导入 Model B 美术题卡为待审题目（默认只导入单选、判断）"

    def add_arguments(self, parser):
        parser.add_argument("--path", default="", help="题卡 jsonl 路径，默认取 QGEN_BANK_PATH")
        parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
        parser.add_argument("--limit", type=int, default=None, help="最多读取多少行")
        parser.add_argument("--grade", type=int, default=None, help="只处理指定年级")
        parser.add_argument(
            "--allow-fill-blank",
            action="store_true",
            help="同时导入填空题（默认关闭，与现有产品规则一致）",
        )
        parser.add_argument("--actor", default="", help="创建人用户名，默认取第一位题库管理员")
        parser.add_argument(
            "--near-threshold", type=float, default=0.9, help="近似重复 Jaccard 阈值"
        )

    def handle(self, *args, **options):
        path = Path(options["path"]) if options["path"] else default_bank_path()
        if not path.exists():
            raise CommandError(f"题卡文件不存在：{path}")

        actor = None
        if not options["dry_run"]:
            actor = self._resolve_actor(options["actor"])

        try:
            report = import_cards(
                path,
                actor,
                dry_run=options["dry_run"],
                limit=options["limit"],
                grade=options["grade"],
                allow_fill_blank=options["allow_fill_blank"],
                near_duplicate_threshold=options["near_threshold"],
            )
        except BusinessError as exc:
            raise CommandError(exc.message) from exc

        prefix = "[dry-run] " if report["dryRun"] else ""
        self.stdout.write(f"{prefix}读取 {report['read']} 行，新增 {report['created']} 道待审题")
        if report["skipped"]:
            self.stdout.write("跳过统计：")
            for reason, count in sorted(report["skipped"].items(), key=lambda item: -item[1]):
                self.stdout.write(f"  {reason}: {count}")
        if report["createdIds"]:
            self.stdout.write(
                "新增题目 ID：" + ", ".join(str(item) for item in report["createdIds"][:30])
            )
        self.stdout.write(f"题卡文件：{report['path']}")

    def _resolve_actor(self, username: str) -> User:
        queryset = User.objects.filter(
            role=Role.QUESTION_ADMIN,
            status=AccountStatus.ACTIVE,
            deleted_at__isnull=True,
        )
        if username:
            user = queryset.filter(username=username).first()
            if user is None:
                raise CommandError(f"题库管理员账号不存在：{username}")
            return user
        user = queryset.order_by("id").first()
        if user is None:
            raise CommandError("未找到题库管理员账号，请用 --actor 指定创建人")
        return user
