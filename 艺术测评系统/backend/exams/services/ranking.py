"""成绩排名与等级计算。"""
from collections import defaultdict

from common.utils import level_for
from exams.models import Score


def assign_ranks(sorted_items):
    """竞赛排名：同分同名次，下一名次跳过（1,1,3）。返回 {id: rank}。"""
    ranks = {}
    last_score = None
    last_rank = 0
    for index, item in enumerate(sorted_items, start=1):
        score = item.total_score
        if last_score is None or score != last_score:
            last_rank = index
            last_score = score
        ranks[item.id] = last_rank
    return ranks


def recompute_ranks(assessment):
    scores = list(
        Score.objects.filter(
            assessment=assessment, status="graded"
        ).order_by("-total_score", "created_at", "id")
    )
    class_groups = defaultdict(list)
    grade_groups = defaultdict(list)
    for score in scores:
        score.level = level_for(score.total_score, score.max_score or assessment.max_score)
        if score.classroom_id:
            class_groups[score.classroom_id].append(score)
        grade_groups[(score.school_id, score.grade)].append(score)

    for items in class_groups.values():
        items.sort(key=lambda s: (-s.total_score, s.created_at, s.id))
        for sid, rank in assign_ranks(items).items():
            Score.objects.filter(pk=sid).update(class_rank=rank)
    for items in grade_groups.values():
        items.sort(key=lambda s: (-s.total_score, s.created_at, s.id))
        for sid, rank in assign_ranks(items).items():
            Score.objects.filter(pk=sid).update(grade_rank=rank)

    for score in scores:
        Score.objects.filter(pk=score.id).update(level=score.level)


def clear_ranks_for_attempt(attempt):
    if not attempt.classroom_id:
        return
    Score.objects.filter(attempt=attempt).update(class_rank=None, grade_rank=None)
