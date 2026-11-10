<template>
  <div class="auth-page min-h-dvh relative overflow-hidden">
    <div class="auth-orb auth-orb-a" aria-hidden="true"></div>
    <div class="auth-orb auth-orb-b" aria-hidden="true"></div>

    <div class="relative z-10 mx-auto flex min-h-dvh w-full max-w-[1180px] items-center px-4 py-8 lg:px-6">
      <div class="grid w-full items-center gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14">
        <!-- 品牌区 -->
        <section class="hidden lg:flex flex-col justify-center pr-6">
          <div class="flex items-center gap-3 mb-9">
            <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 text-white grid place-items-center shadow-xl shadow-blue-500/25">
              <Home :size="22" />
            </div>
            <div>
              <p class="text-[15px] font-semibold text-gray-800 leading-tight">智能家居大模型体验平台</p>
              <p class="text-[11px] text-gray-400 tracking-[0.18em] mt-0.5">HOMEMIND STUDIO</p>
            </div>
          </div>

          <h1 class="text-[42px] leading-[1.12] font-bold tracking-[-0.03em] text-gray-900 max-w-[520px]">
            让家，听懂你的<br />
            <span class="text-blue-600">每一句话</span>
          </h1>
          <p class="mt-5 max-w-[460px] text-[15px] leading-relaxed text-gray-500">
            把大模型 Agent 接入真实家居场景。设备控制、场景联动、知识问答与全屋报告，一句话完成。
          </p>

          <div class="mt-9 grid grid-cols-1 gap-3 max-w-[470px]">
            <div v-for="feature in features" :key="feature.title" class="feature-row">
              <span class="feature-icon">
                <component :is="feature.icon" :size="17" />
              </span>
              <div>
                <p class="text-[13px] font-semibold text-gray-800">{{ feature.title }}</p>
                <p class="text-[12px] text-gray-400 mt-0.5">{{ feature.desc }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- 表单区 -->
        <section class="w-full max-w-[430px] mx-auto lg:mx-0 lg:ml-auto">
          <div class="lg:hidden text-center mb-6">
            <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 text-white grid place-items-center mx-auto mb-4 shadow-xl shadow-blue-500/25">
              <Home :size="26" />
            </div>
            <h1 class="text-2xl font-bold text-gray-900 tracking-tight">智能家居大模型体验平台</h1>
            <p class="text-sm text-gray-400 mt-1.5">登录以管理您的智能设备</p>
          </div>

          <div class="auth-card glass-strong rounded-[26px] p-7 sm:p-8">
            <div class="mb-6">
              <h2 class="text-[22px] font-bold text-gray-900 tracking-tight">欢迎回来</h2>
              <p class="text-[13px] text-gray-400 mt-1">登录后继续管理您的智能家庭</p>
            </div>

            <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onLogin">
              <el-form-item label="用户名" prop="username">
                <el-input
                  v-model="form.username"
                  placeholder="请输入用户名"
                  size="large"
                  autocomplete="username"
                  @keyup.enter="onLogin"
                />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="form.password"
                  type="password"
                  placeholder="请输入密码"
                  size="large"
                  autocomplete="current-password"
                  show-password
                  @keyup.enter="onLogin"
                />
              </el-form-item>

              <el-button class="w-full mt-1" type="primary" size="large" :loading="loading" @click="onLogin">
                登录
              </el-button>
            </el-form>

            <p class="text-center text-[13px] text-gray-500 mt-6">
              还没有账号？
              <router-link class="text-blue-600 hover:text-blue-700 transition-colors font-semibold" to="/register">
                立即注册
              </router-link>
            </p>
          </div>

          <p class="text-center text-[11px] text-gray-400 mt-4">仅用于本地学习与体验，请勿存放真实敏感数据</p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Home, Sparkles, ShieldCheck, Users } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { login } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const uiStore = useUiStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const features = [
  { icon: Sparkles, title: '多意图并发 Agent', desc: '意图识别后并发执行聊天、问答、设备控制与全屋报告' },
  { icon: ShieldCheck, title: '分级权限与审批', desc: '房主、住户、访客三级权限，高风险操作先审批再执行' },
  { icon: Users, title: '家庭共享与记忆', desc: '家庭数据隔离、偏好画像与长期记忆，越用越懂你' },
]

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const onLogin = async () => {
  await formRef.value.validate()
  loading.value = true
  try {
    const data = await login(form)
    userStore.setLoginInfo(data)
    uiStore.addToast('success', `欢迎回来，${data.user.nickname}`)
    router.push('/devices')
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    loading.value = false
  }
}
</script>
