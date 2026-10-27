"""学情报告规则生成（非训练模型）。"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

REPORT_VERSION = "art-report-rules-v0.1.0"


def _trend_slope(scores: List[float]) -> float:
    if len(scores) < 2:
        return 0.0
    x = np.arange(len(scores), dtype=np.float64)
    y = np.asarray(scores, dtype=np.float64)
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope, 2)


def _trend_label(slope: float) -> str:
    if slope >= 1.0:
        return "上升"
    if slope <= -1.0:
        return "下降"
    return "平稳"


def build_report(
    student_id: int,
    subject: str = "art",
    records: List[Dict] | None = None,
    time_range: Dict | None = None,
    focus: str | None = None,
    language: str = "zh",
) -> Dict:
    records = records or []
    if not records:
        return {
            "studentId": student_id,
            "subject": subject,
            "modelVersion": REPORT_VERSION,
            "summary": "暂无测评记录，无法生成学情分析。",
            "strengths": [],
            "weaknesses": [],
            "suggestions": ["完成一次测评后即可生成学情报告"],
            "scoreTrend": [],
            "rawText": "",
        }

    scored = [r for r in records if isinstance(r.get("score"), (int, float))]
    scores = [float(r["score"]) for r in scored]
    avg = round(float(np.mean(scores)), 2) if scores else 0.0
    slope = _trend_slope(scores)
    trend = _trend_label(slope)

    points: Dict[str, List[float]] = {}
    for record in records:
        kp = record.get("knowledgePoints") or {}
        if isinstance(kp, dict):
            for name, value in kp.items():
                if isinstance(value, (int, float)):
                    points.setdefault(str(name), []).append(float(value))
    ranked = sorted(((k, float(np.mean(v))) for k, v in points.items()), key=lambda kv: kv[1], reverse=True)

    strengths = [f"{k}掌握较好（平均{n:.1f}）" for k, n in ranked[:3]]
    weaknesses = [f"{k}相对薄弱（平均{n:.1f}）" for k, n in reversed(ranked[-2:])] if len(ranked) > 3 else \
        [f"{k}相对薄弱（平均{n:.1f}）" for k, n in reversed(ranked[-1:])]
    if not strengths:
        strengths = [f"平均分 {avg:.1f}，已完成 {len(records)} 次测评"]

    suggestions = []
    if trend == "下降":
        suggestions.append("近期成绩呈下降趋势，建议复盘最近作品的问题并针对性练习")
    elif trend == "上升":
        suggestions.append("成绩稳步上升，建议保持当前练习节奏")
    if ranked:
        suggestions.append(f"重点加强 {ranked[-1][0]} 的专项训练")
    suggestions.append("建议多观察优秀作品，提升构图与色彩的整体把握")

    score_trend = [
        {"index": i + 1, "date": r.get("date"), "score": float(r["score"])}
        for i, r in enumerate(scored)
    ]
    raw_text = "；".join(
        f"第{i + 1}次：{r.get('score')}分" + (f"（{r.get('date')}）" if r.get("date") else "")
        for i, r in enumerate(scored)
    )

    summary = (
        f"{subject}学科共 {len(records)} 次测评，平均分 {avg:.1f}，"
        f"整体趋势{trend}（每次变化 {slope:+.2f} 分）。"
    )
    if ranked:
        summary += f"优势项为 {ranked[0][0]}，薄弱项为 {ranked[-1][0]}。"

    return {
        "studentId": student_id,
        "subject": subject,
        "timeRange": time_range or {},
        "focus": focus or "",
        "avgScore": avg,
        "trend": trend,
        "trendSlope": slope,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
        "scoreTrend": score_trend,
        "summary": summary,
        "rawText": raw_text,
        "modelVersion": REPORT_VERSION,
        "generatedBy": "rules",
    }
