import type { FormItemRule } from 'element-plus'

export const GRADE_MIN = 1
export const GRADE_MAX = 9
export const GRADE_OPTIONS = Array.from(
  { length: GRADE_MAX - GRADE_MIN + 1 },
  (_, index) => GRADE_MIN + index
)

export const PASSWORD_REQUIREMENT = '密码需为 8~32 位，且至少包含字母和数字'
export const USERNAME_REQUIREMENT = '登录账号需为 4~32 位字母、数字或下划线'
export const STUDENT_NO_LENGTH = 9
export const STUDENT_NO_REQUIREMENT = `学籍号需为 ${STUDENT_NO_LENGTH} 位数字`
export const DEFAULT_INITIAL_PASSWORD = 'Art@2026'

export const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{8,32}$/
export const USERNAME_PATTERN = /^[A-Za-z0-9_]{4,32}$/
export const STUDENT_NO_PATTERN = /^\d{9}$/

export function isStrongPassword(value: string): boolean {
  return PASSWORD_PATTERN.test(value)
}

export const passwordRule: FormItemRule = {
  validator: (_rule, value, callback) => {
    if (value && !isStrongPassword(String(value))) {
      callback(new Error(PASSWORD_REQUIREMENT))
      return
    }
    callback()
  },
  trigger: ['blur', 'change']
}

export const usernameRule: FormItemRule = {
  validator: (_rule, value, callback) => {
    if (value && !USERNAME_PATTERN.test(String(value))) {
      callback(new Error(USERNAME_REQUIREMENT))
      return
    }
    callback()
  },
  trigger: 'blur'
}

export const studentNoRule: FormItemRule = {
  validator: (_rule, value, callback) => {
    if (value && !STUDENT_NO_PATTERN.test(String(value))) {
      callback(new Error(STUDENT_NO_REQUIREMENT))
      return
    }
    callback()
  },
  trigger: 'blur'
}
