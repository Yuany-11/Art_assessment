import type { Role } from '@/types'

export function defaultPathForRole(role: Role | null | undefined) {
  return role === 'student' ? '/student/home' : '/dashboard'
}
