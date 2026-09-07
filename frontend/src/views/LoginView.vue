<template>
  <div class="min-h-screen flex items-center justify-center px-4 relative overflow-hidden auth-bg">
    <div class="w-full max-w-sm relative z-10">
      <div class="text-center mb-8">
        <div class="w-16 h-16 rounded-2xl glass-strong flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-500/10">
          <Home :size="30" class="text-blue-500" />
        </div>
        <h1 class="text-2xl font-semibold text-gray-800 tracking-tight">智能家居大模型体验平台</h1>
        <p class="text-sm text-gray-500 mt-1.5">登录以管理您的智能设备</p>
      </div>

      <div class="glass-strong rounded-2xl p-7 shadow-xl shadow-black/5">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onLogin">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="请输入用户名" size="large" @keyup.enter="onLogin" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              show-password
              @keyup.enter="onLogin"
            />
          </el-form-item>

          <el-button class="w-full mt-1" type="primary" size="large" :loading="loading" @click="onLogin">
            登录
          </el-button>

          <p class="text-center text-sm text-gray-500 mt-5">
            还没有账号？
            <router-link class="text-blue-500 hover:text-blue-600 transition-colors font-medium" to="/register">
              立即注册
            </router-link>
          </p>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Home } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { login } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const uiStore = useUiStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

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

<style scoped>
.auth-bg {
  background:
    radial-gradient(600px 360px at 15% 20%, rgba(59, 130, 246, 0.14), transparent 60%),
    radial-gradient(560px 340px at 85% 80%, rgba(16, 185, 129, 0.1), transparent 60%),
    linear-gradient(135deg, #f0f2f5 0%, #e8ecf1 50%, #f5f0eb 100%);
}
</style>