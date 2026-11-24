"""成绩发布后的联动：刷新学情报告，并为正式测评自动发放证书。

学习报告：正式测评与随机练习出分后都会重建；
证书：只有教师/管理员发布的正式测评、得分率达到 90% 才自动生成，
随机练习不生成证书。
"""
import logging

from common.enums import GradingStatus, PaperType
from apps.exams.services.certificate import issue_certificate_for_score
from apps.exams.services.growth import _build_learning_report

logger = logging.getLogger(__name__)


def after_score_released(score):
    """成绩落库后调用：刷新报告、按条件发证书。"""
    if score is None or score.status != GradingStatus.GRADED:
        return

    try:
        _build_learning_report(score.student, score.subject)
    except Exception:  # 报告失败不应影响成绩发布
        logger.exception("生成学情报告失败：score=%s", score.pk)

    if score.assessment.paper_type != PaperType.FORMAL:
        return
    try:
        issue_certificate_for_score(score)
    except Exception:  # 证书失败不应影响成绩发布
        logger.exception("自动生成证书失败：score=%s", score.pk)
