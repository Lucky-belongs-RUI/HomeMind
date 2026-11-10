import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 用户状态：JWT token 与用户信息持久化到 localStorage，
 * 刷新页面后从本地恢复登录态。
 */
export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userId = ref(Number(localStorage.getItem('userId')) || 0)
  const userRole = ref(localStorage.getItem('userRole') || '')
  const nickname = ref(localStorage.getItem('nickname') || '')
  const familyId = ref(Number(localStorage.getItem('familyId')) || 0)
  const familyName = ref(localStorage.getItem('familyName') || '')

  const isLoggedIn = computed(() => Boolean(token.value))
  const isOwner = computed(() => userRole.value === 'owner')
  const isGuest = computed(() => userRole.value === 'guest')

  // 登录/注册成功后设置用户信息并持久化
  const setLoginInfo = (data) => {
    token.value = data.token
    userId.value = data.user.id
    userRole.value = data.user.role
    nickname.value = data.user.nickname
    familyId.value = data.user.family_id
    familyName.value = data.family?.name || ''

    localStorage.setItem('token', data.token)
    localStorage.setItem('userId', String(data.user.id))
    localStorage.setItem('userRole', data.user.role)
    localStorage.setItem('nickname', data.user.nickname)
    localStorage.setItem('familyId', String(data.user.family_id))
    localStorage.setItem('familyName', data.family?.name || '')
  }

  const logout = () => {
    token.value = ''
    userId.value = 0
    userRole.value = ''
    nickname.value = ''
    familyId.value = 0
    familyName.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userId')
    localStorage.removeItem('userRole')
    localStorage.removeItem('nickname')
    localStorage.removeItem('familyId')
    localStorage.removeItem('familyName')
  }

  return {
    token,
    userId,
    userRole,
    nickname,
    familyId,
    familyName,
    isLoggedIn,
    isOwner,
    isGuest,
    setLoginInfo,
    logout,
  }
})