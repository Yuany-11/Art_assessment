import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'
import type { ApiResponse } from '@/types'

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0'))
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

interface RetryConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

let refreshPromise: Promise<string> | null = null

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 60_000
})

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  config.headers['X-Request-Id'] = generateUUID()
  const method = (config.method ?? 'get').toUpperCase()
  if (['POST', 'PATCH', 'DELETE'].includes(method) && !config.url?.includes('/auth/login')) {
    config.headers['Idempotency-Key'] = generateUUID()
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    const config = error.config as RetryConfig | undefined
    const isAuthRequest = Boolean(config?.url?.includes('/auth/login') || config?.url?.includes('/auth/refresh'))
    if (error.response?.status !== 401 || !config || config._retried || isAuthRequest) {
      const data = error.response?.data
      const message = (data && !(data instanceof Blob) && data.message) || error.message || '请求失败'
      return Promise.reject(new Error(message))
    }
    config._retried = true
    const auth = useAuthStore()
    if (!auth.refreshToken) {
      auth.logout()
      window.location.assign('/login')
      return Promise.reject(error)
    }
    try {
      refreshPromise ??= axios.post<ApiResponse<{ token: string; refreshToken: string }>>(
        `${http.defaults.baseURL}/auth/refresh`,
        { refreshToken: auth.refreshToken }
      ).then((response) => {
        auth.setTokens(response.data.data.token, response.data.data.refreshToken)
        return response.data.data.token
      }).finally(() => {
        refreshPromise = null
      })
      const nextToken = await refreshPromise
      config.headers.Authorization = `Bearer ${nextToken}`
      return http(config)
    } catch {
      auth.logout()
      window.location.assign('/login')
      return Promise.reject(error)
    }
  }
)

export async function request<T>(config: Parameters<typeof http.request>[0]): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config)
  if (response.data.code !== 200) {
    throw new Error(response.data.message)
  }
  return response.data.data
}

export async function download(path: string, params?: Record<string, string | number | undefined>): Promise<Blob> {
  const response = await http.get(path, { params, responseType: 'blob' })
  return response.data as Blob
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
