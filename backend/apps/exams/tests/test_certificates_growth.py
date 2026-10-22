import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import override_settings
from django.utils import timezone

from apps.exams.models import Certificate, LearningReport, Score
from apps.exams.tests.base import ApiTestBase


class CertificateApiTests(ApiTestBase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="art-cert-"))
        self.override = override_settings(
            MEDIA_ROOT=self.tmpdir,
            CERTIFICATE_ROOT=self.tmpdir / "certificates",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.assessment = self.make_assessment()
        self.attempt_id = self.start_attempt()
        self.submit_all_correct(self.attempt_id)
        self.api(self.teacher).patch(
            f"/api/v1/grading/attempts/{self.attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 18}],
             "finalize": True, "version": 0},
            format="json",
        )
        self.score = Score.objects.get(attempt_id=self.attempt_id)

    def test_generate_list_download(self):
        teacher = self.api(self.teacher)
        response = teacher.post("/api/v1/certificates/generate", {
            "assessmentId": self.assessment.id, "subject": "music",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(data["generatedCount"], 1)
        self.assertEqual(data["status"], "ready")

        cert = Certificate.objects.get(assessment=self.assessment)
        from apps.files.models import FileObject

        file_obj = FileObject.objects.filter(object_key=cert.file_path).first()
        self.assertIsNotNone(file_obj)
        self.assertTrue((self.tmpdir / file_obj.object_key).exists())
        self.assertRegex(cert.certificate_no, r"^YS\d{4}-MUSIC-\d{6}$")

        listing = self.api(self.student).get("/api/v1/certificates")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["data"]["total"], 1)
        item = listing.json()["data"]["list"][0]
        self.assertEqual(item["certificateNo"], cert.certificate_no)

        detail = self.api(self.student).get(f"/api/v1/certificates/{cert.id}")
        self.assertEqual(detail.json()["data"]["level"], "excellent")

        download = self.api(self.student).get(
            f"/api/v1/certificates/{cert.id}/download"
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertTrue(download.content.startswith(b"%PDF"))

    def test_duplicate_generate_skips_unless_forced(self):
        teacher = self.api(self.teacher)
        payload = {"assessmentId": self.assessment.id, "subject": "music"}
        teacher.post("/api/v1/certificates/generate", payload, format="json")
        second = teacher.post("/api/v1/certificates/generate", payload, format="json")
        self.assertEqual(second.json()["data"]["generatedCount"], 0)
        self.assertEqual(second.json()["data"]["skippedCount"], 1)

        forced = teacher.post("/api/v1/certificates/generate", {
            **payload, "forceRegenerate": True,
        }, format="json")
        self.assertEqual(forced.json()["data"]["generatedCount"], 1)

    def test_student_cannot_generate(self):
        response = self.api(self.student).post("/api/v1/certificates/generate", {
            "assessmentId": self.assessment.id, "subject": "music",
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_other_student_cannot_view_or_download(self):
        self.api(self.teacher).post("/api/v1/certificates/generate", {
            "assessmentId": self.assessment.id, "subject": "music",
        }, format="json")
        cert = Certificate.objects.get(assessment=self.assessment)
        client = self.api(self.student2)
        self.assertEqual(
            client.get(f"/api/v1/certificates/{cert.id}").status_code, 403
        )
        self.assertEqual(
            client.get(f"/api/v1/certificates/{cert.id}/download").status_code, 403
        )

    def test_subject_mismatch_unprocessable(self):
        response = self.api(self.teacher).post("/api/v1/certificates/generate", {
            "assessmentId": self.assessment.id, "subject": "art",
        }, format="json")
        self.assertEqual(response.status_code, 422)

    def test_certificate_list_scope_for_outsider_student(self):
        self.api(self.teacher).post("/api/v1/certificates/generate", {
            "assessmentId": self.assessment.id, "subject": "music",
        }, format="json")
        response = self.api(self.student2).get("/api/v1/certificates")
        self.assertEqual(response.json()["data"]["total"], 0)


class GrowthApiTests(ApiTestBase):
    def test_growth_curve_and_report(self):
        assessment1 = self.make_assessment(
            title="上学期测评",
            start_offset=timedelta(days=-60),
            end_offset=timedelta(days=-59),
        )
        assessment2 = self.make_assessment(
            title="本学期测评",
            start_offset=timedelta(days=-2),
            end_offset=timedelta(days=-1),
        )
        teacher = self.api(self.teacher)
        for assessment, total in ((assessment1, 30), (assessment2, 54)):
            response = teacher.post("/api/v1/scores/manual", {
                "studentId": self.student.id,
                "assessmentId": assessment.id,
                "subject": "music",
                "scoreItems": [{"name": "总分", "score": total, "maxScore": 60}],
                "reason": "成长曲线测试",
            }, format="json")
            self.assertEqual(response.status_code, 200, response.content.decode())

        client = self.api(self.student)
        response = client.get(
            f"/api/v1/students/{self.student.id}/growth-curve?subject=music"
        )
        self.assertEqual(response.status_code, 200, response.content.decode())
        data = response.json()["data"]
        self.assertEqual(len(data["points"]), 2)
        self.assertEqual([p["score"] for p in data["points"]], [30, 54])
        self.assertEqual(data["summary"]["latestScore"], 54)
        self.assertEqual(data["summary"]["bestScore"], 54)
        self.assertEqual(data["summary"]["trend"], "up")
        self.assertEqual(data["summary"]["avgScore"], 42)
        self.assertEqual(data["range"]["startDate"], data["points"][0]["date"])
        self.assertEqual(data["range"]["endDate"], data["points"][-1]["date"])

        LearningReport.objects.create(
            report_id="RPT-001",
            student=self.student,
            subject="music",
            summary="节奏感较好，识谱需加强。",
            strengths=["节奏感"],
            weaknesses=["识谱"],
            suggestions=["每日视唱 10 分钟"],
            score_trend=[{"assessmentId": assessment2.id, "score": 54}],
            model_version="demo-v1",
        )
        report = client.get(
            f"/api/v1/students/{self.student.id}/learning-report?subject=music"
        )
        self.assertEqual(report.status_code, 200, report.content.decode())
        self.assertEqual(report.json()["data"]["reportId"], "RPT-001")
        self.assertEqual(report.json()["data"]["strengths"], ["节奏感"])

    def test_student_cannot_view_other_growth(self):
        response = self.api(self.student2).get(
            f"/api/v1/students/{self.student.id}/growth-curve?subject=music"
        )
        self.assertEqual(response.status_code, 403)

    def test_growth_requires_subject(self):
        response = self.api(self.student).get(
            f"/api/v1/students/{self.student.id}/growth-curve"
        )
        self.assertEqual(response.status_code, 400)

    def test_learning_report_missing_404(self):
        response = self.api(self.student).get(
            f"/api/v1/students/{self.student.id}/learning-report"
        )
        self.assertEqual(response.status_code, 404)
