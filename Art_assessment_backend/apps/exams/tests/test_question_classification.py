"""非单元练习题按章节关键词归类。"""
import pytest

from apps.exams.management.commands.classify_question_chapters import (
    EXTENSION_CHAPTER,
    classify_course,
)
from apps.qbank.models import Chapter, Course, Question
from common.enums import QuestionStatus, QuestionType, Subject


@pytest.mark.django_db
def test_classify_non_unit_questions(question_admin):
    course = Course.objects.create(
        name="七年级音乐测试课程", subject=Subject.MUSIC, grade=7
    )
    unit = Chapter.objects.create(
        course=course,
        name="歌唱祖国",
        content=(
            "【重点作品】\n"
            "· 《义勇军进行曲》，聂耳，中国，近代，进行曲，常以齐唱形式呈现。\n"
            "【核心概念】\n"
            "· 进行曲（体裁）：用步伐节奏写成的乐曲。\n"
        ),
    )
    extension = Chapter.objects.create(
        course=course,
        name=EXTENSION_CHAPTER,
        description="与教材单元无直接对应关系的拓展题。",
    )

    related = Question.objects.create(
        subject=Subject.MUSIC,
        grade=7,
        course=course,
        chapter=extension,
        type=QuestionType.SINGLE_CHOICE,
        stem="《义勇军进行曲》的曲作者是谁？",
        score=2,
        answer={"value": "A"},
        status=QuestionStatus.APPROVED,
        creator=question_admin,
    )
    unrelated = Question.objects.create(
        subject=Subject.MUSIC,
        grade=7,
        course=course,
        chapter=extension,
        type=QuestionType.SINGLE_CHOICE,
        stem="下列哪种颜色属于暖色？",
        score=2,
        answer={"value": "A"},
        status=QuestionStatus.APPROVED,
        creator=question_admin,
    )

    stats = classify_course(course)
    assert stats == {"unit": 1, "extension": 1, "moved": 1}

    related.refresh_from_db()
    unrelated.refresh_from_db()
    assert related.chapter_id == unit.id
    assert unrelated.chapter_id == extension.id

    # 重复执行不会再把题目搬来搬去。
    second = classify_course(course)
    assert second == {"unit": 1, "extension": 1, "moved": 0}
