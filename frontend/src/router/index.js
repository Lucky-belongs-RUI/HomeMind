import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  // 登录/注册页（无需认证，独立布局）
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { public: true },
  },
  // 主布局（需认证）
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: '/devices' },
      { path: 'devices', name: 'devices', component: () => import('@/views/DeviceView.vue') },
      { path: 'rooms', name: 'rooms', component: () => import('@/views/RoomView.vue') },
      { path: 'agent', name: 'agent', component: () => import('@/views/AgentView.vue') },
      { path: 'users', name: 'users', component: () => import('@/views/UserView.vue') },
      { path: 'upload', name: 'upload', component: () => import('@/views/FileUploadView.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：未登录跳转登录页，已登录访问登录/注册页跳回首页
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  const isPublic = Boolean(to.meta.public)
  const isLoggedIn = userStore.isLoggedIn

  if (isPublic && isLoggedIn) {
    next('/devices')
  } else if (!isPublic && !isLoggedIn) {
    next('/login')
  } else {
    next()
  }
})

export default router