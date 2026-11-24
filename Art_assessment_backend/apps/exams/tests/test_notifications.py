from apps.exams.models import Notification
from apps.exams.tests.base import ApiTestBase


class NotificationApiTests(ApiTestBase):
    def test_notification_list_read_and_read_all(self):
        for index in range(2):
            Notification.objects.create(
                user=self.teacher,
                type="system",
                title=f"通知{index}",
                content="内容",
            )
        client = self.api(self.teacher)
        listing = client.get("/api/v1/notifications")
        self.assertEqual(listing.status_code, 200)
        data = listing.json()["data"]
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["unreadCount"], 2)

        notification_id = data["list"][0]["id"]
        read = client.patch(f"/api/v1/notifications/{notification_id}/read")
        self.assertEqual(read.status_code, 200)
        self.assertTrue(read.json()["data"]["read"])
        self.assertEqual(client.get("/api/v1/notifications").json()["data"]["unreadCount"], 1)

        # 重复标记幂等
        again = client.patch(f"/api/v1/notifications/{notification_id}/read")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["data"]["read"])

        all_read = client.patch("/api/v1/notifications/read-all")
        self.assertEqual(all_read.status_code, 200)
        self.assertEqual(all_read.json()["data"]["updatedCount"], 1)
        self.assertEqual(client.get("/api/v1/notifications").json()["data"]["unreadCount"], 0)

    def test_student_cannot_read_other_users_notification(self):
        notification = Notification.objects.create(
            user=self.teacher, type="system", title="私有通知", content="内容"
        )
        response = self.api(self.student).patch(f"/api/v1/notifications/{notification.id}/read")
        self.assertEqual(response.status_code, 404)
