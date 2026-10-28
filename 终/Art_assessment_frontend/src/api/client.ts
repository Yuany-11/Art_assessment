import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/stores/auth'
import type { ApiResponse } from '@/types'

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
  if (auth.token && !auth.token.startsWith('mock-')) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  config.headers['X-Request-Id'] = crypto.randomUUID()
  const method = (config.method ?? 'get').toUpperCase()
  if (['POST', 'PATCH', 'DELETE'].includes(method) && !config.url?.includes('/auth/login')) {
    config.headers['Idempotency-Key'] = crypto.randomUUID()
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    const config = error.config as RetryConfig | undefined
    const message = error.response?.data?.message || error.message || '请求失败'
    const isLoginRequest = Boolean(config?.url?.includes('/auth/login'))
    if (isLoginRequest || error.response?.status !== 401 || !config || config._retried) {
      return Promise.reject(new Error(message))
    }
    config._retried = true
    const auth = useAuthStore()
    if (!auth.refreshToken || auth.refreshToken.startsWith('mock-')) {
      auth.logout()
      window.location.assign('/login')
      return Promise.reject(new Error(message))
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
      return Promise.reject(new Error('登录状态已失效，请重新登录'))
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
