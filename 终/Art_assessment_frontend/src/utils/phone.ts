export const PHONE_PATTERN = /^\d{11}$/
export const PHONE_MESSAGE = '手机号需为 11 位数字'

export function isPhone(value: string | null | undefined): boolean {
  return !value || PHONE_PATTERN.test(value.trim())
}
