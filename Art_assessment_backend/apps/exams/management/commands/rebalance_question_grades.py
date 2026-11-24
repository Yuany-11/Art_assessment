"""把题库按难度大致平均分配到一~九年级。

背景：`seed_question_bank` 只为七年级建了 3500 道题，`seed_grade_question_bank`
给其他年级各补 50 道，导致七年级题量远高于其他年级。本命令把七年级多余的题
按「难度从低到高」切分，分给其他年级，并把题目挂到目标年级的课程与章节上，
使每个年级的题量接近（默认每个年级约 500 道，音乐 + 美术）。

说明：分到低年级的题目内容仍来自七年级教材（例如作品《命运交响曲》），
这是为了让每个年级都有足够题量、难度按年级递增，属于演示数据层面的均衡，
不是按教材重新命题。

可重复执行：年级题量已均衡时不会有任何改动。
"""
import re
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.qbank.models import Course, Question
from common.enums import QuestionStatus, Subject

GRADES = list(range(1, 10))
GRADE_NAMES = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}
# 与 seed_grade_question_bank 保持一致：每个年级对应的难度层级。
GRADE_DIFFICULTY = {
    1: 1,
    2: 1,
    3: 2,
    4: 2,
    5: 3,
    6: 3,
    7: 3,
    8: 4,
    9: 5,
}
SUBJECT_LABEL = {Subject.MUSIC: "音乐", Subject.ART: "美术"}
TYPE_ORDER = [
    "single_choice",
    "multiple_choice",
    "true_false",
    "fill_blank",
    "listening",
    "image_upload",
    "audio_upload",
]
PREFIX_RE = re.compile(r"^【(音乐|美术)·[一二三四五六七八九]年级】")
FIXED_COMMENT = "按年级分层补充"
MOVED_MARK = "按难度均衡分配"


def _allocate(total, weights, rotation=0):
    """按权重把 total 个名额分给各年级，余数用最大余数法补齐。

    rotation 用于轮换余数相同时的优先顺序，避免每个题型都偏向低年级，
    使各年级最终题量更接近。
    """
    result = {grade: 0 for grade in weights}
    if total <= 0 or not weights:
        return result
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        return result
    raw = {grade: Decimal(total) * Decimal(weight) / Decimal(weight_sum)
           for grade, weight in weights.items()}
    for grade, value in raw.items():
        result[grade] = int(value)
    remainder = total - sum(result.values())
    grades = sorted(weights)
    position = {grade: index for index, grade in enumerate(grades)}
    order = sorted(
        weights,
        key=lambda grade: (
            -(raw[grade] - result[grade]),
            (position[grade] - rotation) % len(grades),
        ),
    )
    for grade in order[:remainder]:
        result[grade] += 1
    return result


def _mark(comment, grade):
    """在审核意见里标注题目被均衡到哪个年级。"""
    base = (comment or "").split("；按难度均衡分配")[0]
    marked = f"{base}；{MOVED_MARK}至{GRADE_NAMES[grade]}年级"
    return marked[:500]


class Command(BaseCommand):
    help = "把题库按难度大致平均分配到一~九年级（默认每个年级约 500 道）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-per-grade",
            type=int,
            default=500,
            help="每个年级的目标总题量（音乐 + 美术），默认 500",
        )
        parser.add_argument(
            "--subject",
            choices=[Subject.MUSIC, Subject.ART],
            default=None,
            help="只调整某个学科，默认音乐、美术都调整",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只打印分配方案，不写入数据库",
        )

    def handle(self, *args, **options):
        target_total = options["target_per_grade"]
        if target_total < 18:
            raise CommandError("--target-per-grade 至少为 18（每个年级每科 9 道）")
        target_per_subject = max(1, int((Decimal(target_total) / 2).quantize(
            Decimal("1"), ROUND_HALF_UP
        )))
        subjects = [options["subject"]] if options["subject"] else [
            Subject.MUSIC, Subject.ART
        ]
        dry_run = options["dry_run"]

        with transaction.atomic():
            for subject in subjects:
                self._rebalance(subject, target_per_subject, dry_run)

    def _course_maps(self, subject):
        courses = {
            course.grade: course
            for course in Course.objects.filter(subject=subject)
        }
        missing = [grade for grade in GRADES if grade not in courses]
        if missing:
            names = "、".join(f"{GRADE_NAMES[grade]}年级" for grade in missing)
            raise CommandError(
                f"{SUBJECT_LABEL[subject]}缺少 {names} 课程，"
                "请先执行 python manage.py seed_grade_question_bank"
            )
        chapters = {}
        for grade, course in courses.items():
            by_name = {chapter.name: chapter for chapter in course.chapters.all()}
            chapters[grade] = (by_name, course.chapters.order_by("sort_order", "id").first())
        return courses, chapters

    def _rebalance(self, subject, target, dry_run):
        label = SUBJECT_LABEL[subject]
        courses, chapters = self._course_maps(subject)
        approved = Question.objects.filter(
            subject=subject, status=QuestionStatus.APPROVED, deleted_at__isnull=True
        )
        counts = Counter(approved.values_list("grade", flat=True))

        fixed = list(
            approved.filter(
                grade=7, review_comment__contains=FIXED_COMMENT
            ).select_related("chapter")
        )
        fixed_ids = {question.id for question in fixed}
        donor_filter = approved.filter(grade=7).exclude(id__in=fixed_ids)
        donor_count = donor_filter.count()

        deficits = {
            grade: max(0, target - counts.get(grade, 0))
            for grade in GRADES if grade != 7
        }
        total_deficit = sum(deficits.values())
        keep_at_seven = max(0, target - len(fixed))
        available = donor_count - keep_at_seven
        surplus = counts.get(7, 0) - target
        if surplus <= 0 or total_deficit <= 0 or available <= 0:
            self.stdout.write(f"{label}：各年级题量已接近目标，无需调整。")
            return

        donors = list(donor_filter.select_related("chapter"))
        by_type = defaultdict(list)
        for question in donors:
            by_type[question.type].append(question)
        type_keys = sorted(
            by_type,
            key=lambda item: TYPE_ORDER.index(item)
            if item in TYPE_ORDER else len(TYPE_ORDER),
        )

        move_total = min(total_deficit, available)
        type_quotas = _allocate(
            move_total, {qtype: len(by_type[qtype]) for qtype in type_keys}
        )

        moves = defaultdict(list)  # grade -> [(question, old_chapter_name)]
        active_grades = [grade for grade in GRADES if grade != 7 and deficits[grade] > 0]
        grade_weights = {grade: deficits[grade] for grade in active_grades}
        for type_index, qtype in enumerate(type_keys):
            items = sorted(by_type[qtype], key=lambda q: (q.difficulty, q.id))
            quota = min(type_quotas.get(qtype, 0), len(items))
            if quota <= 0:
                continue
            # 在难度序列上均匀抽取，七年级留下的也是各难度都有。
            moved_items = [
                items[int((index + 0.5) * len(items) / quota)]
                for index in range(quota)
            ]
            allocation = _allocate(quota, grade_weights, rotation=type_index)
            index = 0
            for grade in active_grades:
                take = allocation.get(grade, 0)
                for question in moved_items[index:index + take]:
                    moves[grade].append(
                        (question, question.chapter.name if question.chapter else None)
                    )
                index += take

        moved_away = sum(len(moves[grade]) for grade in active_grades)
        if dry_run:
            self.stdout.write(f"\n{label}（预览，不写入）：")
            for grade in GRADES:
                after = (
                    counts.get(grade, 0) - moved_away
                    if grade == 7
                    else counts.get(grade, 0) + len(moves[grade])
                )
                take = 0 if grade == 7 else len(moves[grade])
                self.stdout.write(
                    f"  {GRADE_NAMES[grade]}年级：{counts.get(grade, 0)} → {after} 道"
                    f"（接收 {take} 道，难度 {GRADE_DIFFICULTY[grade]}）"
                )
            self.stdout.write(f"  共调配 {moved_away} 道（原七年级）\n")
            return

        updates = []
        moved_ids = set()
        for grade in GRADES:
            if grade == 7:
                continue
            course = courses[grade]
            chapter_by_name, first_chapter = chapters[grade]
            for question, old_chapter_name in moves[grade]:
                moved_ids.add(question.id)
                question.grade = grade
                question.difficulty = GRADE_DIFFICULTY[grade]
                question.course = course
                question.chapter = chapter_by_name.get(old_chapter_name) or first_chapter
                question.stem = PREFIX_RE.sub(
                    f"【{label}·{GRADE_NAMES[grade]}年级】", question.stem, count=1
                )
                question.review_comment = _mark(question.review_comment, grade)
                updates.append(question)

        # 七年级保留的题目统一到本年级难度层级，不再改年级与课程。
        for question in donors:
            if question.id not in moved_ids:
                question.difficulty = GRADE_DIFFICULTY[7]
                updates.append(question)

        Question.objects.bulk_update(
            updates,
            ["grade", "difficulty", "course", "chapter", "stem", "review_comment"],
            batch_size=200,
        )

        self.stdout.write(f"\n{label}：")
        for grade in GRADES:
            after = (
                counts.get(grade, 0) - moved_away
                if grade == 7
                else counts.get(grade, 0) + len(moves[grade])
            )
            take = 0 if grade == 7 else len(moves[grade])
            self.stdout.write(
                f"  {GRADE_NAMES[grade]}年级：{counts.get(grade, 0)} → {after} 道"
                f"（接收 {take} 道，难度 {GRADE_DIFFICULTY[grade]}）"
            )
        self.stdout.write(f"  共调配 {moved_away} 道（原七年级）\n")
