from django.core.cache import cache
from rest_framework.test import APIClient

from common.jwt import issue_access_token
from common.enums import AccountStatus
from apps.exams.tests.base import ApiTestBase


class AuthTests(ApiTestBase):
    def test_missing_token_returns_401_envelope(self):
        client = APIClient()
        response = client.get("/api/v1/papers")
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(body["code"], 401)
        self.assertIn("message", body)

    def test_invalid_token(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        response = client.get("/api/v1/papers")
        self.assertEqual(response.status_code, 401)

    def test_valid_token(self):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION="Bearer " + issue_access_token(self.teacher)
        )
        response = client.get("/api/v1/papers")
        self.assertEqual(response.status_code, 200)

    def test_blacklisted_token_rejected(self):
        import jwt
        from django.conf import settings

        token = issue_access_token(self.teacher)
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        cache.set(f"jwt:blacklist:{payload['jti']}", True, 60)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(client.get("/api/v1/papers").status_code, 401)

    def test_token_version_mismatch(self):
        token = issue_access_token(self.teacher)
        self.teacher.token_version += 1
        self.teacher.save(update_fields=["token_version"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(client.get("/api/v1/papers").status_code, 401)

    def test_disabled_account_rejected(self):
        token = issue_access_token(self.student)
        self.student.status = AccountStatus.DISABLED
        self.student.save(update_fields=["status"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(client.get("/api/v1/assessments").status_code, 401)

    def test_question_admin_can_view_papers_but_cannot_create(self):
        response = self.api(self.question_admin).get("/api/v1/papers")
        self.assertEqual(response.status_code, 200)
        response = self.api(self.question_admin).post(
            "/api/v1/papers/manual", {}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_unknown_paper_404_envelope(self):
        response = self.api(self.teacher).get("/api/v1/papers/999999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 404)
