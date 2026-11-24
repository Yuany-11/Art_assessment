"""调用 Model B 服务批量生成美术待审题。

需要先启动 http://127.0.0.1:8002 并在配置中打开 QGEN_ENABLED。
生成结果全部以 pending 入库；重复题会被跳过，服务不可用时立即停止。
"""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.qbank.qgen import allowed_types, generate_question, load_unit_map, qgen_enabled
from common.enums import AccountStatus, Role
from common.exceptions import BusinessError


class Command(BaseCommand):
    help = "调用美术出题服务批量生成待审题（需要 8002 服务与 QGEN_ENABLED=true）"

    def add_arguments(self, parser):
        parser.add_argument("--unit", required=True, help="目录单元 ID，如 g7-u2")
        parser.add_argument("--knowledge-point", required=True, help="单元内的知识点")
        parser.add_argument(
            "--type", default="single_choice", choices=["single_choice", "true_false"]
        )
        parser.add_argument("--difficulty", type=int, default=1, choices=[1, 2, 3])
        parser.add_argument("--count", type=int, default=1, help="希望新增的题目数量")
        parser.add_argument("--actor", default="", help="创建人用户名，默认取第一位题库管理员")
        parser.add_argument("--dry-run", action="store_true", help="只调用不落库")

    def handle(self, *args, **options):
        if not qgen_enabled():
            raise CommandError("QGEN_ENABLED=false，请先在 .env 或 settings 中打开")
        entry = load_unit_map().get(options["unit"])
        if entry is None:
            raise CommandError(f"单元不存在：{options['unit']}")
        if options["knowledge_point"] not in entry.get("knowledgePoints", []):
            raise CommandError("知识点不在该单元的目录中")
        if options["type"] not in allowed_types():
            raise CommandError(f"不支持的题型：{options['type']}")

        actor = self._resolve_actor(options["actor"])
        created = 0
        attempts = 0
        max_attempts = max(options["count"] * 3, options["count"])
        errors: list[str] = []
        while created < options["count"] and attempts < max_attempts:
            attempts += 1
            try:
                question, _warnings, _model = generate_question(
                    actor,
                    {
                        "unitId": options["unit"],
                        "knowledgePoint": options["knowledge_point"],
                        "type": options["type"],
                        "difficulty": options["difficulty"],
                    },
                    dry_run=options["dry_run"],
                )
            except BusinessError as exc:
                if exc.status_code in {502, 503}:
                    raise CommandError(exc.message) from exc
                errors.append(exc.message)
                continue
            created += 1
            if options["dry_run"]:
                self.stdout.write(f"[dry-run] 生成成功：{question.stem[:40]}")
            else:
                self.stdout.write(f"已创建待审题 Q{question.id}：{question.stem[:40]}")

        if created < options["count"]:
            self.stdout.write(
                self.style.WARNING(
                    f"目标 {options['count']} 道，实际 {created} 道；"
                    f"尝试 {attempts} 次，跳过原因：{errors[-5:]}"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"完成：新增 {created} 道待审题"))

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
