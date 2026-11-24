"""批量调用音频标签服务，为题库音频和学生作品补齐标签。"""
from django.core.management.base import BaseCommand

from common.enums import AudioAnalysisStatus, FileCategory
from common.exceptions import BusinessError

from apps.files.audio_tags import analyze_audio, is_audio_file
from apps.files.models import AudioAnalysis, FileObject


class Command(BaseCommand):
    help = "批量生成音频标签与规则参考分析（需要先启动 arteval-v4 推理服务）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            choices=[
                FileCategory.QUESTION_AUDIO,
                FileCategory.STUDENT_WORK,
                FileCategory.OTHER,
            ],
            help="只处理指定文件分类；默认处理题库音频与学生作品",
        )
        parser.add_argument("--file-id", type=int, action="append", help="只处理指定文件 ID")
        parser.add_argument("--limit", type=int, default=0, help="最多处理多少个文件，0 表示不限")
        parser.add_argument("--force", action="store_true", help="已完成的分析也重新跑一遍")
        parser.add_argument("--dry-run", action="store_true", help="只统计，不调用分析服务")

    def handle(self, *args, **options):
        categories = [options["category"]] if options["category"] else [
            FileCategory.QUESTION_AUDIO,
            FileCategory.STUDENT_WORK,
        ]
        queryset = FileObject.objects.filter(
            category__in=categories, deleted_at__isnull=True
        ).order_by("id")
        if options["file_id"]:
            queryset = queryset.filter(pk__in=options["file_id"])

        files = [item for item in queryset if is_audio_file(item)]
        if not options["force"]:
            completed = set(
                AudioAnalysis.objects.filter(
                    file__in=files, status=AudioAnalysisStatus.COMPLETED
                ).values_list("file_id", flat=True)
            )
            files = [item for item in files if item.id not in completed]
        if options["limit"]:
            files = files[: options["limit"]]

        if options["dry_run"]:
            self.stdout.write(f"待分析音频 {len(files)} 个")
            for item in files:
                self.stdout.write(f"  #{item.id} {item.original_name}")
            return

        ok = failed = 0
        for item in files:
            try:
                analyze_audio(item, force=options["force"])
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"#{item.id} {item.original_name}"))
            except BusinessError as exc:
                failed += 1
                self.stderr.write(f"#{item.id} {item.original_name} 失败：{exc.message}")
        self.stdout.write(
            self.style.SUCCESS(f"完成：成功 {ok} 个，失败 {failed} 个")
        )
