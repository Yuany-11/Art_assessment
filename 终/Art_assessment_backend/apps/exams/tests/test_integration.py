"""跨模块集成：题库快照、发布可见性、成绩数据范围。"""
from apps.exams.models import PaperQuestion
from apps.exams.tests.base import ApiTestBase
from apps.files.models import FileObject
from apps.qbank.models import QuestionResource
from common.enums import FileCategory, ResourceType


class ExamsIntegrationTests(ApiTestBase):
    def test_question_snapshot_contains_resource_and_rubric(self):
        file_obj = FileObject.objects.create(
            uploader=self.teacher,
            category=FileCategory.QUESTION_IMAGE,
            original_name="demo.png",
            object_key="question_image/demo.png",
            mime_type="image/png",
            size=4,
            storage_backend="local",
        )
        QuestionResource.objects.create(
            question=self.questions["single"], file=file_obj, type=ResourceType.IMAGE
        )

        paper = self.make_paper(with_subjective=False)
        row = PaperQuestion.objects.get(
            paper=paper, question_id=self.questions["single"].id
        )
        self.assertEqual(row.resources[0]["fileId"], file_obj.id)
        self.assertTrue(row.resources[0]["url"].endswith("question_image/demo.png"))
        self.assertEqual(row.rubric, "测试评分细则")

    def test_published_assessment_visible_only_to_target_class(self):
        assessment = self.make_assessment()

        visible = self.api(self.student).get("/api/v1/assessments")
        self.assertEqual(visible.status_code, 200)
        ids = [item["id"] for item in visible.json()["data"]["list"]]
        self.assertIn(assessment.id, ids)

        hidden = self.api(self.outsider).get("/api/v1/assessments")
        hidden_ids = [item["id"] for item in hidden.json()["data"]["list"]]
        self.assertNotIn(assessment.id, hidden_ids)

    def test_score_list_respects_teaching_class_scope(self):
        assessment = self.make_assessment()
        attempt_id = self.start_attempt(assessment=assessment)
        self.submit_all_correct(attempt_id)
        response = self.api(self.teacher).patch(
            f"/api/v1/grading/attempts/{attempt_id}/scores",
            {"items": [{"questionId": self.questions["short"].id, "score": 18}],
             "finalize": True, "version": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content.decode())

        own = self.api(self.teacher).get("/api/v1/scores")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["data"]["total"], 1)

        other = self.api(self.other_teacher).get("/api/v1/scores")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.json()["data"]["total"], 0)
