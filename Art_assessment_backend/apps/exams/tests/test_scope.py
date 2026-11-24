"""数据范围单元测试：覆盖六种角色的组织/班级收敛。"""
from apps.exams.scope import DataScope
from apps.exams.tests.base import ApiTestBase


class DataScopeTests(ApiTestBase):
    def test_student_scope_is_own_class(self):
        scope = DataScope(self.student)
        self.assertEqual(scope.class_ids, {self.classroom.id})
        self.assertEqual(scope.school_id, self.school.id)

    def test_teacher_scope_is_teaching_class(self):
        scope = DataScope(self.teacher)
        self.assertEqual(scope.class_ids, {self.classroom.id})
        self.assertEqual(
            DataScope(self.other_teacher).class_ids, {self.classroom2.id}
        )

    def test_head_teacher_without_class_teacher_row_is_in_scope(self):
        from apps.classes.models import Class

        headed = Class.objects.create(
            school=self.school,
            name="七年级（3）班",
            grade=7,
            class_code="T-7-3",
            head_teacher=self.teacher,
        )
        scope = DataScope(self.teacher)
        self.assertIn(headed.id, scope.class_ids)
        self.assertIn(self.school.id, scope.school_ids)

    def test_school_admin_sees_school_classes(self):
        scope = DataScope(self.school_admin)
        self.assertEqual(scope.class_ids, {self.classroom.id, self.classroom2.id})
        self.assertEqual(scope.school_ids, {self.school.id})

    def test_district_admin_sees_district_schools(self):
        scope = DataScope(self.district_admin)
        self.assertEqual(scope.school_ids, {self.school.id})
        self.assertEqual(scope.district_id, self.district.id)

    def test_city_admin_sees_city_and_districts(self):
        scope = DataScope(self.city_admin)
        self.assertEqual(scope.city_id, self.city.id)
        self.assertIn(self.district.id, scope.district_ids)
        self.assertIn(self.school.id, scope.school_ids)

    def test_province_admin_sees_all_classes(self):
        scope = DataScope(self.province_admin)
        self.assertEqual(scope.class_ids, {self.classroom.id, self.classroom2.id})
        self.assertEqual(scope.school_ids, {self.school.id})
