import axios from 'axios'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

// 支持通过 VITE_API_BASE_URL 直连后端；未配置时走 Vite /api 代理
const baseURL = import.meta.env?.VITE_API_BASE_URL || '/api'

const instance = axios.create({
  baseURL,
  timeout: 30000,
})

/**
 * 统一请求封装：
 * 1. 自动注入 Authorization: Bearer <token>（JWT 认证）；
 * 2. 401 时清空登录态并跳转登录页；
 * 3. 403/404/其他错误统一 Toast 提示。
 */
function send(config) {
  const userStore = useUserStore()
  const headers = { ...(config.headers || {}) }
  if (userStore.token) {
    headers.Authorization = `Bearer ${userStore.token}`
  }
  const finalConfig = { ...config, headers }

  return instance
    .request(finalConfig)
    .then((res) => res.data)
    .catch((error) => {
      const status = error.status || error.response?.status
      const message = error.response?.data?.detail || error.message || '请求失败'
      const uiStore = useUiStore()

      if (status === 401) {
        uiStore.addToast('error', '登录已过期，请重新登录')
        userStore.logout()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      } else if (status === 403) {
        uiStore.addToast('error', '无权限执行此操作（房主专属功能或访客受限）')
      } else if (status === 404) {
        uiStore.addToast('error', '资源不存在（可能不属于当前家庭）')
      } else if (message) {
        uiStore.addToast('error', message)
      }
      return Promise.reject(error)
    })
}

export default {
  get: (url, config = {}) => send({ method: 'get', url, ...config }),
  post: (url, data, config = {}) => send({ method: 'post', url, data, ...config }),
  put: (url, data, config = {}) => send({ method: 'put', url, data, ...config }),
  patch: (url, data, config = {}) => send({ method: 'patch', url, data, ...config }),
  delete: (url, config = {}) => send({ method: 'delete', url, ...config }),
}
