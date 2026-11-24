"""清理题库、试卷快照、答卷快照和错题本中的题干标签。"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.exams.models import Attempt, PaperQuestion, WrongQuestion
from apps.qbank.models import Question
from apps.qbank.stem_cleaner import clean_stem


class Command(BaseCommand):
    help = "去掉题干中的【单元练习】、[七年级音乐·…]、（变式 N）等标签，只保留纯题干"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只预览，不写数据库")
        parser.add_argument("--subject", choices=["music", "art"], help="只处理指定学科")
        parser.add_argument("--grade", type=int, help="只处理指定年级")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        qs = Question.objects.all().order_by("id")
        if options["subject"]:
            qs = qs.filter(subject=options["subject"])
        if options["grade"]:
            qs = qs.filter(grade=options["grade"])

        questions = list(qs)
        changed: dict[int, str] = {}
        for question in questions:
            cleaned = clean_stem(question.stem)
            if cleaned != question.stem:
                changed[question.id] = cleaned
                if not dry_run:
                    question.stem = cleaned

        paper_rows = []
        wrong_rows = []
        attempt_rows = []
        if dry_run:
            paper_count = sum(
                1
                for stem in PaperQuestion.objects.values_list("stem", flat=True)
                if clean_stem(stem) != stem
            )
            wrong_count = sum(
                1
                for stem in WrongQuestion.objects.values_list("stem", flat=True)
                if clean_stem(stem) != stem
            )
            attempt_count = 0
            for snapshot in Attempt.objects.exclude(
                questions_snapshot=None
            ).values_list("questions_snapshot", flat=True):
                if any(
                    clean_stem(item.get("stem")) != (item.get("stem") or "").strip()
                    for item in (snapshot or [])
                ):
                    attempt_count += 1
            self.stdout.write(
                self.style.WARNING(
                    f"[预览] 题目 {len(changed)} 道、试卷快照 {paper_count} 条、"
                    f"错题快照 {wrong_count} 条、答卷快照 {attempt_count} 份"
                )
            )
            return

        with transaction.atomic():
            Question.objects.bulk_update(
                [q for q in questions if q.id in changed], ["stem"], batch_size=500
            )

            for row in PaperQuestion.objects.iterator(chunk_size=500):
                cleaned = clean_stem(row.stem)
                if cleaned != row.stem:
                    row.stem = cleaned
                    paper_rows.append(row)
            if paper_rows:
                PaperQuestion.objects.bulk_update(paper_rows, ["stem"], batch_size=500)

            for row in WrongQuestion.objects.iterator(chunk_size=500):
                cleaned = clean_stem(row.stem)
                if cleaned != row.stem:
                    row.stem = cleaned
                    wrong_rows.append(row)
            if wrong_rows:
                WrongQuestion.objects.bulk_update(wrong_rows, ["stem"], batch_size=500)

            for attempt in Attempt.objects.exclude(questions_snapshot=None).iterator():
                changed_snapshot = False
                snapshot = attempt.questions_snapshot or []
                for item in snapshot:
                    cleaned = clean_stem(item.get("stem"))
                    if cleaned != item.get("stem"):
                        item["stem"] = cleaned
                        changed_snapshot = True
                if changed_snapshot:
                    attempt.questions_snapshot = snapshot
                    attempt.save(update_fields=["questions_snapshot", "updated_at"])
                    attempt_rows.append(attempt)

        self.stdout.write(
            self.style.SUCCESS(
                f"题干清理完成：题目 {len(changed)} 道、试卷快照 {len(paper_rows)} 条、"
                f"错题快照 {len(wrong_rows)} 条、答卷快照 {len(attempt_rows)} 份"
            )
        )
