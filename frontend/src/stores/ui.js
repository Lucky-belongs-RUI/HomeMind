import { defineStore } from 'pinia'
import { ref } from 'vue'

let toastSeq = 0

/**
 * UI 状态：全局 Toast 消息。
 */
export const useUiStore = defineStore('ui', () => {
  const toasts = ref([])

  const addToast = (type, message) => {
    toastSeq += 1
    const toast = { id: toastSeq, type, message }
    toasts.value.push(toast)
    setTimeout(() => removeToast(toast.id), 3400)
  }

  const removeToast = (id) => {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  return {
    toasts,
    addToast,
    removeToast,
  }
})