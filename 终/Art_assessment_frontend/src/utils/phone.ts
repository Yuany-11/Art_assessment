export const PHONE_PATTERN = /^1[3-9]\d{9}$/
export const PHONE_MESSAGE = '手机号格式不正确，需为 11 位手机号'

export function isPhone(value: string | null | undefined): boolean {
  return !value || PHONE_PATTERN.test(value.trim())
}
