"""把非单元练习题按内容归入相关教材单元，其余归入“拓展类”。

题库中原先除单元练习外，其余题目统一放在“综合复习”章节。本命令读取每个
教材单元章节的知识讲解，提取重点作品、核心概念和章节名称作为关键词，再把
题干、选项或解析中命中这些关键词的题目移入对应单元；没有命中任何单元关键词
的题目统一放入该课程的“拓展类”章节。

命令幂等：重复执行只调整章节归属，不会创建、删除题目。
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.qbank.models import Chapter, Course, Question

EXTENSION_CHAPTER = "拓展类"
LEGACY_CHAPTER = "综合复习"


def chapter_keywords(chapter: Chapter) -> set[str]:
    """从章节知识讲解中提取可用于题目归类的关键词。"""
    content = chapter.content or ""
    keywords = {chapter.name}
    keywords.update(re.findall(r"《([^》]+)》", content))

    in_core = False
    for raw in content.splitlines():
        line = raw.strip()
        if line == "【核心概念】":
            in_core = True
            continue
        if in_core and line.startswith("【"):
            break
        if in_core:
            matched = re.match(r"[·•]\s*([^（(：:]+)", line)
            if matched:
                keywords.add(matched.group(1).strip())
    return {item for item in keywords if len(item) >= 2}


def question_text(question: Question) -> str:
    options = " ".join(option.text for option in question.options.all())
    return " ".join([question.stem, question.analysis or "", options])


def ensure_extension_chapter(course: Course) -> Chapter:
    extension = Chapter.objects.filter(
        course=course, name=EXTENSION_CHAPTER, deleted_at__isnull=True
    ).first()
    legacy = Chapter.objects.filter(
        course=course, name=LEGACY_CHAPTER, deleted_at__isnull=True
    ).first()
    if extension is None and legacy is not None:
        legacy.name = EXTENSION_CHAPTER
        legacy.description = "与教材单元无直接对应关系的拓展题。"
        legacy.content = "【拓展说明】\n本类题目用于拓展练习，不绑定具体教材单元。"
        legacy.sort_order = 99
        legacy.save(
            update_fields=["name", "description", "content", "sort_order", "updated_at"]
        )
        return legacy
    if extension is not None and legacy is not None:
        Question.objects.filter(chapter=legacy).update(chapter=extension)
        legacy.delete()
        return extension
    if extension is not None:
        return extension
    return Chapter.objects.create(
        course=course,
        name=EXTENSION_CHAPTER,
        description="与教材单元无直接对应关系的拓展题。",
        content="【拓展说明】\n本类题目用于拓展练习，不绑定具体教材单元。",
        sort_order=99,
    )


def classify_course(course: Course, dry_run: bool = False) -> dict[str, int]:
    """把一门课程的非单元练习题归入单元章节或拓展类。"""
    unit_chapters = list(
        Chapter.objects.filter(course=course, deleted_at__isnull=True)
        .exclude(name__in=[EXTENSION_CHAPTER, LEGACY_CHAPTER])
        .order_by("sort_order", "id")
    )
    keyword_map = {
        chapter.id: chapter_keywords(chapter) for chapter in unit_chapters
    }
    extension = None
    if not dry_run:
        extension = ensure_extension_chapter(course)

    questions = list(
        Question.objects.filter(course=course, deleted_at__isnull=True)
        .exclude(review_comment="课程单元同步练习，自动审核通过")
        .prefetch_related("options")
    )
    stats = {"unit": 0, "extension": 0, "moved": 0}
    for question in questions:
        text = question_text(question)
        best_chapter = None
        best_score = 0
        for chapter in unit_chapters:
            score = sum(
                len(keyword)
                for keyword in keyword_map[chapter.id]
                if keyword and keyword in text
            )
            if score > best_score:
                best_score = score
                best_chapter = chapter
        if best_score > 0:
            target = best_chapter
            stats["unit"] += 1
        else:
            target = extension
            stats["extension"] += 1
        if target is None:
            continue
        if question.chapter_id != target.id:
            if not dry_run:
                question.chapter = target
                question.save(update_fields=["chapter", "updated_at"])
            stats["moved"] += 1
    return stats


class Command(BaseCommand):
    help = "把非单元练习题按内容归入教材单元，其余归入拓展类"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="只统计分类结果，不修改数据库"
        )
        parser.add_argument("--subject", choices=["music", "art"], help="只处理指定学科")
        parser.add_argument("--grade", type=int, help="只处理指定年级")

    @transaction.atomic
    def handle(self, *args, **options):
        courses = Course.objects.filter(deleted_at__isnull=True).order_by(
            "subject", "grade", "id"
        )
        if options.get("subject"):
            courses = courses.filter(subject=options["subject"])
        if options.get("grade"):
            courses = courses.filter(grade=options["grade"])
        if not courses.exists():
            self.stdout.write(self.style.WARNING("没有需要处理的课程"))
            return

        total = {"unit": 0, "extension": 0, "moved": 0}
        for course in courses:
            stats = classify_course(course, dry_run=options["dry_run"])
            for key in total:
                total[key] += stats[key]
            self.stdout.write(
                f"{course.subject} {course.grade} 年级《{course.name}》："
                f"单元题 {stats['unit']} 道，拓展题 {stats['extension']} 道，"
                f"本次调整 {stats['moved']} 道"
            )

        prefix = "预演完成" if options["dry_run"] else "分类完成"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}：单元题 {total['unit']} 道，"
                f"拓展题 {total['extension']} 道，"
                f"本次调整 {total['moved']} 道"
            )
        )
