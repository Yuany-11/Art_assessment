import type { Role } from '@/types'

export interface MenuItem {
  title: string
  path: string
  icon: string
  roles: Role[]
}

export interface MenuGroup {
  title: string
  items: MenuItem[]
}

const allAdminRoles: Role[] = [
  'teacher',
  'school_admin',
  'district_admin',
  'city_admin',
  'province_admin'
]

export const menuGroups: MenuGroup[] = [
  {
    title: '工作台',
    items: [
      { title: '项目概览', path: '/dashboard', icon: 'DataBoard', roles: [...allAdminRoles, 'question_admin'] },
      { title: '我的学习', path: '/student/home', icon: 'HomeFilled', roles: ['student'] }
    ]
  },
  {
    title: '账号与组织',
    items: [
      { title: '教师账号', path: '/school/accounts/teachers', icon: 'User', roles: ['school_admin'] },
      { title: '学生账号', path: '/school/accounts/students', icon: 'Avatar', roles: ['school_admin'] },
      { title: '班级管理', path: '/teacher/classes', icon: 'School', roles: ['teacher', 'school_admin'] },
      { title: '学校账号', path: '/district/accounts/schools', icon: 'OfficeBuilding', roles: ['district_admin', 'province_admin'] },
      { title: '市直属学校', path: '/city/accounts/schools', icon: 'OfficeBuilding', roles: ['city_admin'] },
      { title: '区县账号', path: '/city/accounts/districts', icon: 'MapLocation', roles: ['city_admin', 'province_admin'] },
      { title: '市州账号', path: '/province/accounts/cities', icon: 'Location', roles: ['province_admin'] },
      { title: '省级学生账号', path: '/province/accounts/students', icon: 'Avatar', roles: ['province_admin'] },
      { title: '个人信息', path: '/profile', icon: 'Setting', roles: ['school_admin', 'district_admin', 'city_admin', 'province_admin', 'question_admin'] }
    ]
  },
  {
    title: '教师工作',
    items: [
      { title: '学生管理', path: '/teacher/students', icon: 'UserFilled', roles: ['teacher'] },
      { title: '试题管理', path: '/teacher/questions', icon: 'Search', roles: ['teacher'] },
      { title: '学生评分', path: '/teacher/grading', icon: 'EditPen', roles: ['teacher'] },
      { title: '学生评分', path: '/teacher/grading', icon: 'EditPen', roles: ['school_admin'] }
    ]
  },
  {
    title: '测评管理',
    items: [
      { title: '组卷管理', path: '/papers', icon: 'Document', roles: [...allAdminRoles] },
      { title: '测评发布', path: '/assessments', icon: 'Paperclip', roles: [...allAdminRoles] },
      { title: '成绩管理', path: '/scores', icon: 'Tickets', roles: [...allAdminRoles] },
      { title: '数据统计', path: '/statistics', icon: 'TrendCharts', roles: [...allAdminRoles] },
      { title: '证书管理', path: '/teacher/certificates', icon: 'Postcard', roles: [...allAdminRoles] }
    ]
  },
  {
    title: '题库管理',
    items: [
      { title: '试题管理', path: '/qbank/questions', icon: 'Collection', roles: ['question_admin'] },
      { title: '试卷审核', path: '/paper-review', icon: 'DocumentChecked', roles: ['question_admin'] },
      { title: '课程章节', path: '/qbank/courses', icon: 'Reading', roles: ['question_admin'] },
      { title: '操作日志', path: '/logs', icon: 'DocumentCopy', roles: ['province_admin', 'question_admin'] }
    ]
  },
  {
    title: '学生端',
    items: [
      { title: '我的测评', path: '/student/assessments', icon: 'Edit', roles: ['student'] },
      { title: '趣味课堂', path: '/student/knowledge', icon: 'Reading', roles: ['student'] },
      { title: '我的成绩', path: '/student/results', icon: 'Medal', roles: ['student'] },
      { title: '我的错题', path: '/student/wrong-questions', icon: 'Tickets', roles: ['student'] },
      { title: '学习报告', path: '/student/report', icon: 'TrendCharts', roles: ['student'] },
      { title: '课外作品', path: '/student/artworks', icon: 'Picture', roles: ['student'] },
      { title: '我的证书', path: '/student/certificates', icon: 'Postcard', roles: ['student'] },
      { title: '个人信息', path: '/profile', icon: 'Setting', roles: ['student', 'teacher'] }
    ]
  }
]

export function menusForRole(role: Role | null): MenuGroup[] {
  if (!role) return []
  return menuGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => item.roles.includes(role))
    }))
    .filter((group) => group.items.length > 0)
}
