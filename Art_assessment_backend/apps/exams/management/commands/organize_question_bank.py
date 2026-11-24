"""整理题库：去重，并把“拓展类”里能对应到章节知识点的题归入对应章节。

处理步骤：
0. 填空题整体下线：全部逻辑删除，不再出现在题库与组卷候选里；
1. 按清洗后的题干去重：同题干只保留一条，优先保留已被试卷引用、位于章节内、
   状态为已通过的题；
2. 扫描“拓展类”章节（以及未绑定章节）的试题，用章节知识里的作品名、核心概念、
   章节名做关键词匹配，命中即归入同一学科下得分最高的章节；题目原本分的年级
   与知识点不符时，按知识点所在章节一并修正年级与课程；
3. 匹配不到任何知识点的题保留在“拓展类”，作为拓展题。

命令默认直接写库；加 --dry-run 只统计不修改，便于核对影响范围。
"""
from __future__ import annotations

import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.exams.models import PaperQuestion
from apps.qbank.models import Chapter, Course, Question
from apps.qbank.stem_cleaner import clean_stem
from common.enums import QuestionStatus, QuestionType

REVIEW_CHAPTER = "拓展类"
# 关键词匹配的最低得分：命中一个核心概念（权重 2）即可归入。
MIN_MATCH_SCORE = 2


def _normalize_stem(stem: str | None) -> str:
    return " ".join(clean_stem(stem).split())


def _chapter_keywords(chapter: Chapter) -> dict[str, int]:
    """从章节知识中提取关键词：作品名权重最高，其次是核心概念和章节名。"""
    content = chapter.content or ""
    keywords: dict[str, int] = {}
    for title in re.findall(r"《([^》]+)》", content):
        title = title.strip()
        # 单字作品名（如《虾》《春》）同样是有效知识点，不能按长度过滤。
        if title:
            keywords[title] = 3
    in_concepts = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("【"):
            in_concepts = stripped == "【核心概念】"
            continue
        if in_concepts and stripped.startswith("· "):
            term = stripped[2:].split("（")[0].split("：")[0].strip()
            if len(term) >= 2:
                keywords[term] = max(keywords.get(term, 0), 2)
    name = (chapter.name or "").strip()
    if len(name) >= 2:
        keywords[name] = max(keywords.get(name, 0), 2)
    return keywords


class Command(BaseCommand):
    help = "题库去重，并按章节知识点把拓展题归入对应章节"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="只统计，不修改数据库"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("预览模式：不会修改数据库"))
        with transaction.atomic():
            fills = self._retire_fill_blank(dry_run)
            deleted = self._dedupe(dry_run)
            moved, remaining = self._redistribute(dry_run)
        self.stdout.write(
            self.style.SUCCESS(
                f"题库整理完成：删除填空题 {fills} 道，删除重复题 {deleted} 道，"
                f"归入章节 {moved} 道，保留为拓展题 {remaining} 道"
            )
        )

    def _retire_fill_blank(self, dry_run: bool) -> int:
        """填空题整体下线：直接从题库移除（试卷快照不受影响）。"""
        qs = Question.objects.filter(
            deleted_at__isnull=True, type=QuestionType.FILL_BLANK
        )
        count = qs.count()
        if count and not dry_run:
            qs.update(deleted_at=timezone.now())
        return count

    def _dedupe(self, dry_run: bool) -> int:
        referenced = set(
            PaperQuestion.objects.filter(
                paper__deleted_at__isnull=True
            ).values_list("question_id", flat=True)
        )
        groups: dict[str, list[Question]] = defaultdict(list)
        rows = (
            Question.objects.filter(deleted_at__isnull=True)
            .select_related("chapter")
            .order_by("id")
        )
        for question in rows:
            key = _normalize_stem(question.stem)
            if key:
                groups[key].append(question)

        removed = 0
        for items in groups.values():
            if len(items) < 2:
                continue
            items.sort(
                key=lambda q: (
                    0 if q.id in referenced else 1,
                    0 if q.chapter and q.chapter.name != REVIEW_CHAPTER else 1,
                    0 if q.status == QuestionStatus.APPROVED else 1,
                    q.id,
                )
            )
            duplicates = [q.id for q in items[1:]]
            if duplicates:
                removed += len(duplicates)
                if not dry_run:
                    Question.objects.filter(id__in=duplicates).update(
                        deleted_at=timezone.now()
                    )
        return removed

    def _redistribute(self, dry_run: bool) -> tuple[int, int]:
        now = timezone.now()
        units_by_subject: dict[str, list[tuple[Chapter, dict[str, int]]]] = defaultdict(list)
        for chapter in (
            Chapter.objects.filter(deleted_at__isnull=True)
            .exclude(name=REVIEW_CHAPTER)
            .select_related("course")
        ):
            keywords = _chapter_keywords(chapter)
            if keywords:
                units_by_subject[chapter.course.subject].append((chapter, keywords))

        moved = 0
        remaining = 0
        pending = Question.objects.filter(
            deleted_at__isnull=True, status=QuestionStatus.APPROVED
        ).filter(
            Q(chapter__isnull=True) | Q(chapter__name=REVIEW_CHAPTER)
        ).select_related("chapter")
        for question in pending.iterator():
            text = f"{question.stem or ''} {question.analysis or ''}"
            best_chapter = None
            best_key: tuple[int, int, int, int] | None = None
            for chapter, keywords in units_by_subject.get(question.subject, []):
                score = 0
                for keyword, weight in keywords.items():
                    if keyword in text:
                        # 关键词越长越具体，命中后额外加分，减少短词误判。
                        score += weight + min(len(keyword), 6)
                if not score:
                    continue
                grade_gap = abs(chapter.course.grade - question.grade)
                # 得分相同时优先本年级、其次年级最接近、再次章节顺序靠前。
                key = (
                    score,
                    1 if grade_gap == 0 else 0,
                    -grade_gap,
                    -chapter.sort_order,
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best_chapter = chapter
            if best_chapter is None or best_key is None or best_key[0] < MIN_MATCH_SCORE:
                remaining += 1
                if not dry_run and question.chapter_id is None:
                    self._ensure_review_chapter(question, now)
                continue
            moved += 1
            if not dry_run:
                Question.objects.filter(id=question.id).update(
                    chapter=best_chapter,
                    course=best_chapter.course,
                    grade=best_chapter.course.grade,
                    updated_at=now,
                )
        return moved, remaining

    def _ensure_review_chapter(self, question: Question, now) -> None:
        """没有匹配到知识点的题统一挂在所属课程的“拓展类”下。"""
        course = Course.objects.filter(pk=question.course_id).first()
        if course is None:
            return
        review, _ = Chapter.objects.get_or_create(
            course=course,
            name=REVIEW_CHAPTER,
            defaults={
                "sort_order": 99,
                "description": "与教材单元无直接对应关系的拓展题。",
                "content": "【拓展说明】\n本类题目用于拓展练习，不绑定具体教材单元。",
            },
        )
        Question.objects.filter(id=question.id).update(
            chapter=review, updated_at=now
        )
