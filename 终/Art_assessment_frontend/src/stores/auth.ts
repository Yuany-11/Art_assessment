import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { Role, UserProfile } from '@/types'

const roleNames: Record<Role, string> = {
  student: '学生',
  teacher: '教师',
  school_admin: '学校管理员',
  district_admin: '区县管理员',
  city_admin: '市州管理员',
  province_admin: '省级管理员',
  question_admin: '题库管理员'
}

const profileByRole: Record<Role, Omit<UserProfile, 'role' | 'roleName'>> = {
  student: {
    id: 1001,
    username: 'student2026001',
    realName: '王小明',
    schoolId: 301,
    schoolName: '示范中学',
    districtId: 22,
    districtName: '示例区',
    cityId: 3,
    cityName: '示例市',
    avatarUrl: null,
    permissions: ['assessment.attempt', 'score.self.view', 'certificate.self.view'],
    grade: 7,
    classId: 5001,
    className: '七年级（1）班'
  },
  teacher: {
    id: 2001,
    username: 'teacher1001',
    realName: '李老师',
    schoolId: 301,
    schoolName: '示范中学',
    districtId: 22,
    districtName: '示例区',
    cityId: 3,
    cityName: '示例市',
    avatarUrl: null,
    permissions: ['paper.create', 'assessment.publish', 'score.view', 'grading.submit']
  },
  school_admin: {
    id: 3001,
    username: 'school301',
    realName: '孙校长',
    schoolId: 301,
    schoolName: '示范中学',
    districtId: 22,
    districtName: '示例区',
    cityId: 3,
    cityName: '示例市',
    avatarUrl: null,
    permissions: ['account.manage', 'paper.create', 'assessment.publish', 'score.export']
  },
  district_admin: {
    id: 2201,
    username: 'district22',
    realName: '刘主任',
    schoolId: null,
    schoolName: null,
    districtId: 22,
    districtName: '示例区',
    cityId: 3,
    cityName: '示例市',
    avatarUrl: null,
    permissions: ['account.manage', 'paper.create', 'assessment.publish', 'score.export']
  },
  city_admin: {
    id: 3011,
    username: 'city03',
    realName: '周局长',
    schoolId: null,
    schoolName: null,
    districtId: null,
    districtName: null,
    cityId: 3,
    cityName: '示例市',
    avatarUrl: null,
    permissions: ['account.manage', 'paper.create', 'assessment.publish', 'score.export']
  },
  province_admin: {
    id: 4001,
    username: 'province01',
    realName: '许处长',
    schoolId: null,
    schoolName: null,
    districtId: null,
    districtName: null,
    cityId: null,
    cityName: null,
    avatarUrl: null,
    permissions: ['account.manage', 'paper.create', 'assessment.publish', 'score.export', 'log.view']
  },
  question_admin: {
    id: 7001,
    username: 'qbank01',
    realName: '题库管理员',
    schoolId: null,
    schoolName: null,
    districtId: null,
    districtName: null,
    cityId: null,
    cityName: null,
    avatarUrl: null,
    permissions: ['question.manage', 'question.review', 'course.manage', 'log.view']
  }
}

const stored = sessionStorage.getItem('art-assessment-session')
const initial = stored
  ? (JSON.parse(stored) as { role: Role; token: string; refreshToken?: string; user: UserProfile })
  : null

export const useAuthStore = defineStore('auth', () => {
  const token = ref(initial?.token ?? '')
  const refreshToken = ref(initial?.refreshToken ?? '')
  const role = ref<Role | null>(initial?.role ?? null)
  const user = ref<UserProfile | null>(initial?.user ?? null)
  const isAuthed = computed(() => Boolean(token.value && user.value))

  function login(nextRole: Role) {
    const base = profileByRole[nextRole]
    const nextUser: UserProfile = {
      ...base,
      role: nextRole,
      roleName: roleNames[nextRole]
    }
    role.value = nextRole
    user.value = nextUser
    token.value = `mock-token-${nextRole}-${Date.now()}`
    refreshToken.value = `mock-refresh-${nextRole}-${Date.now()}`
    sessionStorage.setItem(
      'art-assessment-session',
      JSON.stringify({ role: nextRole, token: token.value, refreshToken: refreshToken.value, user: nextUser })
    )
  }

  function setSession(nextRole: Role, nextUser: UserProfile, nextToken: string, nextRefreshToken: string) {
    role.value = nextRole
    user.value = nextUser
    token.value = nextToken
    refreshToken.value = nextRefreshToken
    sessionStorage.setItem(
      'art-assessment-session',
      JSON.stringify({ role: nextRole, token: nextToken, refreshToken: nextRefreshToken, user: nextUser })
    )
  }

  function setTokens(nextToken: string, nextRefreshToken: string) {
    token.value = nextToken
    refreshToken.value = nextRefreshToken
    if (role.value && user.value) {
      sessionStorage.setItem(
        'art-assessment-session',
        JSON.stringify({ role: role.value, token: nextToken, refreshToken: nextRefreshToken, user: user.value })
      )
    }
  }

  function updateProfile(values: Partial<UserProfile>) {
    if (!user.value || !role.value) return
    user.value = { ...user.value, ...values }
    sessionStorage.setItem(
      'art-assessment-session',
      JSON.stringify({ role: role.value, token: token.value, refreshToken: refreshToken.value, user: user.value })
    )
  }

  function logout() {
    token.value = ''
    refreshToken.value = ''
    role.value = null
    user.value = null
    sessionStorage.removeItem('art-assessment-session')
  }

  function hasPermission(permission: string) {
    return user.value?.permissions.includes(permission) ?? false
  }

  return { token, refreshToken, role, user, isAuthed, login, setSession, setTokens, updateProfile, logout, hasPermission }
})
