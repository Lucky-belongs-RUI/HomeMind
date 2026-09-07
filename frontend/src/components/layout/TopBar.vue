<template>
  <header
    class="h-14 glass border-b border-white/30 flex items-center justify-between gap-3 px-4 shrink-0 shadow-sm z-30"
  >
    <div class="flex items-center gap-2.5 min-w-0">
      <div class="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-200/60 flex items-center justify-center shrink-0">
        <Home :size="17" class="text-blue-500" />
      </div>
      <span class="text-sm font-semibold text-gray-800 truncate hidden sm:block">智能家居大模型体验平台</span>
    </div>

    <nav class="flex items-center gap-1 overflow-x-auto min-w-0 py-1 nav-scroll">
      <button
        v-for="item in navItems"
        :key="item.path"
        class="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-all whitespace-nowrap shrink-0"
        :class="
          isActive(item.path)
            ? 'bg-blue-500/10 text-blue-600 border border-blue-200/60 shadow-sm'
            : 'text-gray-500 hover:bg-black/5 hover:text-gray-900 border border-transparent'
        "
        type="button"
        @click="router.push(item.path)"
      >
        <component :is="item.icon" :size="15" />
        <span class="font-medium">{{ item.label }}</span>
      </button>
    </nav>

    <div class="flex items-center gap-2 min-w-0">
      <span class="hidden xl:flex items-center gap-1.5 text-xs text-gray-400 shrink-0">
        <span class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-emerald-400' : 'bg-amber-400'"></span>
        {{ isConnected ? '实时连接' : '连接中' }}
      </span>
      <span
        v-if="userStore.familyName"
        class="hidden lg:block text-xs text-gray-500 bg-white/60 border border-white/40 rounded-full px-2.5 py-1 truncate max-w-32 shrink-0"
      >
        {{ userStore.familyName }}
      </span>
      <span class="text-[11px] px-2 py-0.5 rounded-full font-medium shrink-0" :class="roleBadgeClass">
        {{ roleLabel }}
      </span>
      <div class="w-7 h-7 rounded-full bg-blue-500 flex items-center justify-center shrink-0">
        <User :size="15" class="text-white" />
      </div>
      <span class="hidden md:block text-sm text-gray-700 truncate max-w-24 shrink-0">
        {{ userStore.nickname || '用户' }}
      </span>
      <button
        class="p-1 text-gray-400 hover:text-red-500 transition-colors shrink-0"
        type="button"
        title="退出登录"
        @click="logout"
      >
        <LogOut :size="15" />
      </button>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Home, LayoutDashboard, Bot, Users, UploadCloud, User, LogOut } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { useWebSocket } from '@/composables/useWebSocket'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const { isConnected, closeWs } = useWebSocket()

const navItems = [
  { path: '/devices', label: '设备管理', icon: LayoutDashboard },
  { path: '/rooms', label: '房间管理', icon: Home },
  { path: '/agent', label: 'AI 助理', icon: Bot },
  { path: '/users', label: '家庭管理', icon: Users },
  { path: '/upload', label: '数据上传', icon: UploadCloud },
]

const isActive = (path) => route.path === path || route.path.startsWith(`${path}/`)

const roleLabel = computed(
  () => ({ owner: '房主', resident: '住户', guest: '访客' }[userStore.userRole] || userStore.userRole),
)

const roleBadgeClass = computed(() => {
  const map = {
    owner: 'bg-blue-500/10 text-blue-600 border border-blue-200/70',
    resident: 'bg-emerald-500/10 text-emerald-600 border border-emerald-200/70',
    guest: 'bg-gray-500/10 text-gray-500 border border-gray-200/70',
  }
  return map[userStore.userRole] || 'bg-gray-500/10 text-gray-500 border border-gray-200/70'
})

const logout = () => {
  closeWs() // 登出时主动关闭并重置 WebSocket，避免下次登录无法重连
  userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.nav-scroll {
  scrollbar-width: none;
}

.nav-scroll::-webkit-scrollbar {
  display: none;
}
</style>