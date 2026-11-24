"""教材单元练习的题型构成。"""
from apps.exams.management.commands.seed_curriculum_units import UNITS, _build_specs
from apps.exams.management.commands.seed_grade_question_bank import (
    ART_GRADES,
    MUSIC_GRADES,
)
from common.enums import Subject


def test_unit_specs_focus_on_objective_questions():
    """单元练习以判断题为重点，不再生成填空题。"""
    for subject, data_by_grade in (
        (Subject.MUSIC, MUSIC_GRADES),
        (Subject.ART, ART_GRADES),
    ):
        data = data_by_grade[1]
        unit_name, focus = UNITS[subject][1][0]
        # 与 seed_curriculum_units 的分配一致：每个单元只聚焦一个作品、一个核心概念。
        specs, *_ = _build_specs(
            1,
            subject,
            unit_name,
            focus,
            data["works"][:1],
            data["terms"][:1],
            data,
        )
        types = [spec["type"] for spec in specs]
        assert 23 <= len(specs) <= 25
        assert 7 <= types.count("single_choice") <= 9
        assert types.count("multiple_choice") == 3
        assert types.count("true_false") == 12
        assert types.count("audio_upload") + types.count("image_upload") == 1
        assert "fill_blank" not in types
        assert "short_answer" not in types

        for spec in specs:
            if spec["type"] == "true_false":
                assert isinstance(spec["answer"]["value"], bool)
