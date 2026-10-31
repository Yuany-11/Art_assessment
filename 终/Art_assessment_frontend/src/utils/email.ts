export const EMAIL_PATTERN = /^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)*\.[^\s@.]{2,}$/
export const EMAIL_MESSAGE = '邮箱格式不正确'

export function isEmail(value: string | null | undefined): boolean {
  const email = (value ?? '').trim()
  if (!email) return true
  return email.length <= 254 && EMAIL_PATTERN.test(email)
}
