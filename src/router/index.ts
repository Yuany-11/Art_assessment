import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true }
    },
    {
      path: '/',
      component: () => import('@/layouts/AppShell.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '项目概览', roles: ['teacher', 'school_admin', 'district_admin', 'city_admin', 'province_admin', 'question_admin'] }
        },
        {
          path: 'school/accounts/teachers',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'teachers' },
          meta: { title: '教师账号', roles: ['school_admin'] }
        },
        {
          path: 'teacher/classes',
          component: () => import('@/views/ClassesView.vue'),
          meta: { title: '班级管理', roles: ['teacher', 'school_admin'] }
        },
        {
          path: 'teacher/students',
          component: () => import('@/views/TeacherStudentsView.vue'),
          meta: { title: '学生管理', roles: ['teacher'] }
        },
        {
          path: 'teacher/questions',
          component: () => import('@/views/TeacherQuestionBankView.vue'),
          meta: { title: '题库查询', roles: ['teacher'] }
        },
        {
          path: 'teacher/grading',
          component: () => import('@/views/GradingView.vue'),
          meta: { title: '学生评分', roles: ['teacher'] }
        },
        {
          path: 'teacher/certificates',
          component: () => import('@/views/CertificatesView.vue'),
          meta: { title: '证书管理', roles: ['teacher'] }
        },
        {
          path: 'school/accounts/students',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'students' },
          meta: { title: '学生账号', roles: ['school_admin'] }
        },
        {
          path: 'district/accounts/schools',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'schools' },
          meta: { title: '学校账号', roles: ['district_admin', 'province_admin'] }
        },
        {
          path: 'city/accounts/districts',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'districts' },
          meta: { title: '区县账号', roles: ['city_admin', 'province_admin'] }
        },
        {
          path: 'city/accounts/schools',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'schools' },
          meta: { title: '市直属学校', roles: ['city_admin'] }
        },
        {
          path: 'province/accounts/cities',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'cities' },
          meta: { title: '市州账号', roles: ['province_admin'] }
        },
        {
          path: 'province/accounts/students',
          component: () => import('@/views/AccountsView.vue'),
          props: { kind: 'students' },
          meta: { title: '省级学生账号', roles: ['province_admin'] }
        },
        {
          path: 'papers',
          name: 'papers',
          component: () => import('@/views/PapersView.vue'),
          meta: { title: '组卷管理', roles: ['teacher', 'school_admin', 'district_admin', 'city_admin', 'province_admin'] }
        },
        {
          path: 'paper-review',
          component: () => import('@/views/PaperReviewView.vue'),
          meta: { title: '试卷审核', roles: ['school_admin', 'district_admin', 'city_admin', 'province_admin', 'question_admin'] }
        },
        {
          path: 'assessments',
          name: 'assessments',
          component: () => import('@/views/AssessmentsView.vue'),
          meta: { title: '测评发布', roles: ['teacher', 'school_admin', 'district_admin', 'city_admin', 'province_admin'] }
        },
        {
          path: 'scores',
          name: 'scores',
          component: () => import('@/views/ScoresView.vue'),
          meta: { title: '成绩管理', roles: ['teacher', 'school_admin', 'district_admin', 'city_admin', 'province_admin'] }
        },
        {
          path: 'statistics',
          name: 'statistics',
          component: () => import('@/views/StatisticsView.vue'),
          meta: { title: '数据统计', roles: ['teacher', 'school_admin', 'district_admin', 'city_admin', 'province_admin'] }
        },
        {
          path: 'qbank/questions',
          name: 'questions',
          component: () => import('@/views/QuestionsView.vue'),
          meta: { title: '试题管理', roles: ['question_admin'] }
        },
        {
          path: 'qbank/courses',
          name: 'courses',
          component: () => import('@/views/CoursesView.vue'),
          meta: { title: '课程章节', roles: ['question_admin'] }
        },
        {
          path: 'logs',
          name: 'logs',
          component: () => import('@/views/LogsView.vue'),
          meta: { title: '操作日志', roles: ['province_admin', 'question_admin'] }
        },
        {
          path: 'student/home',
          name: 'student-home',
          component: () => import('@/views/student/StudentHomeView.vue'),
          meta: { title: '我的学习', roles: ['student'] }
        },
        {
          path: 'student/assessments',
          name: 'student-assessments',
          component: () => import('@/views/student/StudentAssessmentsView.vue'),
          meta: { title: '我的测评', roles: ['student'] }
        },
        {
          path: 'student/knowledge',
          component: () => import('@/views/student/StudentKnowledgeView.vue'),
          meta: { title: '趣味课堂', roles: ['student'] }
        },
        {
          path: 'student/attempt/:attemptId',
          name: 'student-attempt',
          component: () => import('@/views/student/StudentAttemptView.vue'),
          meta: { title: '在线答题', roles: ['student'], fullscreen: true }
        },
        {
          path: 'student/results',
          name: 'student-results',
          component: () => import('@/views/student/StudentResultsView.vue'),
          meta: { title: '我的成绩', roles: ['student'] }
        },
        {
          path: 'student/wrong-questions',
          component: () => import('@/views/student/WrongQuestionsView.vue'),
          meta: { title: '我的错题', roles: ['student'] }
        },
        {
          path: 'student/certificates',
          name: 'student-certificates',
          component: () => import('@/views/student/StudentCertificatesView.vue'),
          meta: { title: '我的证书', roles: ['student'] }
        },
        {
          path: 'student/report',
          component: () => import('@/views/student/StudentReportView.vue'),
          meta: { title: '学习报告', roles: ['student'] }
        },
        {
          path: 'student/artworks',
          component: () => import('@/views/student/StudentArtworkView.vue'),
          meta: { title: '课外作品', roles: ['student'] }
        },
        {
          path: 'profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { title: '个人信息', roles: ['student', 'teacher'] }
        }
      ]
    },
    {
      path: '/403',
      component: () => import('@/views/ForbiddenView.vue'),
      meta: { public: true }
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    return true
  }
  if (!auth.isAuthed) return { path: '/login', query: { redirect: to.fullPath } }
  const allowed = to.meta.roles as string[] | undefined
  if (allowed && auth.role && !allowed.includes(auth.role)) return '/403'
  return true
})

export default router
