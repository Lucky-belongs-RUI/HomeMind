<template>
  <header class="app-header glass relative z-40 shrink-0">
    <div class="h-16 px-3 sm:px-4 lg:px-6 flex items-center justify-between gap-3">
      <div class="flex items-center gap-2.5 min-w-0">
        <button
          class="lg:hidden w-9 h-9 rounded-xl bg-white/60 border border-white/70 text-gray-600 grid place-items-center hover:bg-white/85 transition-colors"
          type="button"
          :aria-label="mobileOpen ? '关闭导航' : '打开导航'"
          :aria-expanded="mobileOpen"
          @click="mobileOpen = !mobileOpen"
        >
          <X v-if="mobileOpen" :size="18" />
          <Menu v-else :size="18" />
        </button>

        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 text-white flex items-center justify-center shrink-0 shadow-lg shadow-blue-500/20">
          <Home :size="18" />
        </div>
        <div class="min-w-0 hidden sm:block">
          <p class="text-[13px] leading-tight font-semibold text-gray-800 truncate">智能家居大模型体验平台</p>
          <p class="text-[10px] leading-tight text-gray-400 tracking-wide mt-0.5">HOMEMIND STUDIO</p>
        </div>
      </div>

      <nav class="hidden lg:flex items-center gap-1 p-1 rounded-2xl bg-white/45 border border-white/60 shadow-sm" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          type="button"
          :aria-current="isActive(item.path) ? 'page' : undefined"
          @click="router.push(item.path)"
        >
          <component :is="item.icon" :size="15" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="flex items-center gap-2 min-w-0">
        <span class="hidden md:inline-flex items-center gap-1.5 text-[11px] text-gray-500 shrink-0">
          <span class="w-2 h-2 rounded-full" :class="isConnected ? 'bg-emerald-400' : 'bg-amber-400'"></span>
          {{ isConnected ? '实时连接' : '连接中' }}
        </span>

        <span
          v-if="userStore.familyName"
          class="hidden xl:inline-flex text-[11px] text-gray-600 bg-white/55 border border-white/65 rounded-full px-2.5 py-1 truncate max-w-36 shrink-0"
        >
          {{ userStore.familyName }}
        </span>

        <span class="role-badge" :class="roleBadgeClass">{{ roleLabel }}</span>

        <div class="flex items-center gap-2 pl-2 ml-0.5 border-l border-white/60 shrink-0">
          <div class="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-sm">
            <User :size="15" class="text-white" />
          </div>
          <div class="hidden md:block leading-tight max-w-28">
            <p class="text-[12px] font-semibold text-gray-700 truncate">{{ userStore.nickname || '用户' }}</p>
            <p class="text-[10px] text-gray-400 truncate">{{ userStore.familyName || '我的家庭' }}</p>
          </div>
          <button class="header-icon-btn hidden md:grid" type="button" title="退出登录" aria-label="退出登录" @click="logout">
            <LogOut :size="15" />
          </button>
        </div>
      </div>
    </div>

    <Transition name="sheet">
      <div v-if="mobileOpen" class="lg:hidden absolute top-full inset-x-2 mt-2 z-50 mobile-sheet glass-strong rounded-2xl p-3">
        <nav class="grid grid-cols-2 gap-1.5" aria-label="移动端导航">
          <button
            v-for="item in navItems"
            :key="item.path"
            class="nav-item justify-start"
            :class="{ active: isActive(item.path) }"
            type="button"
            @click="go(item.path)"
          >
            <component :is="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </button>
        </nav>

        <div class="mt-3 pt-3 border-t border-white/60 flex items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-gray-800 truncate">{{ userStore.nickname || '用户' }}</p>
            <p class="text-[11px] text-gray-400 truncate">
              {{ userStore.familyName || '我的家庭' }} · {{ roleLabel }}
            </p>
          </div>
          <el-button size="small" plain type="danger" @click="logout">
            <LogOut :size="13" class="mr-1" />
            退出登录
          </el-button>
        </div>
      </div>
    </Transition>

    <div v-if="mobileOpen" class="lg:hidden fixed inset-0 top-16 z-40" @click="mobileOpen = false"></div>
  </header>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Home, LayoutDashboard, Bot, Users, UploadCloud, User, LogOut, Menu, X } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { useWebSocket } from '@/composables/useWebSocket'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const { isConnected, closeWs } = useWebSocket()
const mobileOpen = ref(false)

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
    owner: 'bg-blue-500/10 text-blue-700 border-blue-200/80',
    resident: 'bg-emerald-500/10 text-emerald-700 border-emerald-200/80',
    guest: 'bg-gray-500/10 text-gray-600 border-gray-200/80',
  }
  return map[userStore.userRole] || 'bg-gray-500/10 text-gray-600 border-gray-200/80'
})

const go = (path) => {
  mobileOpen.value = false
  router.push(path)
}

const logout = () => {
  mobileOpen.value = false
  closeWs()
  userStore.logout()
  router.push('/login')
}

watch(
  () => route.path,
  () => {
    mobileOpen.value = false
  },
)
</script>

<style scoped>
.app-header {
  border-top: none;
  border-left: none;
  border-right: none;
  border-radius: 0;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.7), 0 8px 28px rgba(23, 28, 43, 0.05);
}

.nav-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 12px;
  border: 1px solid transparent;
  color: #5f677a;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.7);
  color: #171c2b;
}

.nav-item.active {
  background: rgba(255, 255, 255, 0.94);
  border-color: rgba(255, 255, 255, 0.9);
  color: #3f57d6;
  box-shadow: 0 4px 14px rgba(23, 28, 43, 0.06);
}

.role-badge {
  display: none;
  padding: 2px 9px;
  border-radius: 999px;
  border-width: 1px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.header-icon-btn {
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 10px;
  color: #737a8c;
  transition: background 0.18s ease, color 0.18s ease;
}

.header-icon-btn:hover {
  background: rgba(255, 255, 255, 0.7);
  color: #d8695a;
}

.mobile-sheet {
  transform-origin: top center;
}

.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.99);
}

@media (min-width: 640px) {
  .role-badge {
    display: inline-block;
  }
}
</style>
