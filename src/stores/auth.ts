import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { Role, UserProfile } from '@/types'

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

  return { token, refreshToken, role, user, isAuthed, setSession, setTokens, updateProfile, logout, hasPermission }
})
