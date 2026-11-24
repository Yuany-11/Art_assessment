from django.core.management.base import BaseCommand
from django.utils import timezone

from common.enums import AssessmentStatus, PaperType
from apps.exams.models import Assessment
from apps.exams.services.certificate import generate_for_assessment


class Command(BaseCommand):
    help = "为已结束的正式测评批量生成证书"

    def add_arguments(self, parser):
        parser.add_argument("--assessment-id", type=int, default=None)
        parser.add_argument("--force", action="store_true", help="覆盖已生成的证书")

    def handle(self, *args, **options):
        qs = Assessment.objects.filter(
            paper_type=PaperType.FORMAL,
            status=AssessmentStatus.FINISHED,
        )
        if options["assessment_id"]:
            qs = qs.filter(pk=options["assessment_id"])
        total = 0
        for assessment in qs.iterator():
            total += generate_for_assessment(assessment, force=options["force"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{timezone.localdate()} 证书生成完成：{total} 份"
            )
        )
