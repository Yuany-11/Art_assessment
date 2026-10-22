from django.urls import path

from exams.views import assessments, attempts, certificates, grading, growth, papers, scores

urlpatterns = [
    # 试卷（静态路径必须在 <int:paper_id> 之前）
    path("papers", papers.PaperListView.as_view()),
    path("papers/manual", papers.PaperManualCreateView.as_view()),
    path("papers/auto", papers.PaperAutoCreateView.as_view()),
    path("papers/practice/random", papers.PracticeRandomView.as_view()),
    path("papers/<int:paper_id>", papers.PaperDetailView.as_view()),
    path("papers/<int:paper_id>/draft", papers.PaperDraftView.as_view()),
    path("papers/<int:paper_id>/materials/download", papers.PaperMaterialsDownloadView.as_view()),
    path("papers/<int:paper_id>/answers/download", papers.PaperAnswersDownloadView.as_view()),

    # 测评
    path("assessments", assessments.AssessmentListCreateView.as_view()),
    path("assessments/<int:assessment_id>", assessments.AssessmentDetailView.as_view()),
    path("assessments/<int:assessment_id>/withdraw", assessments.AssessmentWithdrawView.as_view()),
    path("assessments/<int:assessment_id>/attempts", assessments.AttemptStartView.as_view()),

    # 答卷
    path("attempts/<int:attempt_id>", attempts.AttemptDetailView.as_view()),
    path("attempts/<int:attempt_id>/answers", attempts.AttemptAnswersView.as_view()),
    path("attempts/<int:attempt_id>/submit", attempts.AttemptSubmitView.as_view()),

    # 成绩（静态路径必须在 <int:score_id> 之前）
    path("scores/me", scores.MyScoresView.as_view()),
    path("scores/statistics", scores.StatisticsOverviewView.as_view()),
    path("scores/statistics/list", scores.StatisticsListView.as_view()),
    path("scores/statistics/export", scores.StatisticsExportView.as_view()),
    path("scores/manual", scores.ManualScoreView.as_view()),
    path("scores/import", scores.ScoreImportView.as_view()),
    path("scores", scores.ScoreListView.as_view()),
    path("scores/<int:score_id>", scores.ScoreDetailView.as_view()),
    path("scores/<int:score_id>/regrade", scores.RegradeView.as_view()),

    # 人工评分
    path("grading/tasks", grading.GradingTaskListView.as_view()),
    path("grading/attempts/<int:attempt_id>", grading.GradingAttemptDetailView.as_view()),
    path("grading/attempts/<int:attempt_id>/scores", grading.GradingAttemptScoreView.as_view()),

    # 证书
    path("certificates/generate", certificates.CertificateGenerateView.as_view()),
    path("certificates", certificates.CertificateListView.as_view()),
    path("certificates/<int:certificate_id>", certificates.CertificateDetailView.as_view()),
    path("certificates/<int:certificate_id>/download", certificates.CertificateDownloadView.as_view()),

    # 成长曲线与学情报告
    path("students/<int:student_id>/growth-curve", growth.GrowthCurveView.as_view()),
    path("students/<int:student_id>/learning-report", growth.LearningReportView.as_view()),
]
