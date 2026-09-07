<template>
  <div class="min-h-screen flex items-center justify-center px-4 py-10 relative overflow-hidden auth-bg">
    <div class="w-full max-w-md relative z-10">
      <div class="text-center mb-6">
        <div class="w-16 h-16 rounded-2xl glass-strong flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-500/10">
          <Home :size="30" class="text-blue-500" />
        </div>
        <h1 class="text-2xl font-semibold text-gray-800 tracking-tight">注册新家庭</h1>
        <p class="text-sm text-gray-500 mt-1.5">创建家庭后您将成为房主，可邀请住户和访客加入</p>
      </div>

      <div class="glass-strong rounded-2xl p-7 shadow-xl shadow-black/5">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="家庭名称" prop="family_name">
            <el-input v-model="form.family_name" placeholder="如：张三的家" size="large" />
          </el-form-item>
          <el-form-item label="家庭描述">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              placeholder="可选，描述您的家庭环境"
            />
          </el-form-item>

          <div class="flex items-center gap-3 my-4">
            <span class="flex-1 h-px bg-white/50"></span>
            <span class="text-xs text-gray-400 font-medium">房主账户</span>
            <span class="flex-1 h-px bg-white/50"></span>
          </div>

          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="登录用户名" size="large" />
          </el-form-item>
          <el-form-item label="昵称" prop="nickname">
            <el-input v-model="form.nickname" placeholder="前端展示昵称" size="large" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" placeholder="至少 6 位" size="large" show-password />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm">
            <el-input v-model="form.confirm" type="password" placeholder="再次输入密码" size="large" show-password />
          </el-form-item>

          <el-button class="w-full" type="primary" size="large" :loading="loading" @click="onRegister">
            注册并创建家庭
          </el-button>

          <p class="text-center text-sm text-gray-500 mt-5">
            已有家庭？
            <router-link class="text-blue-500 hover:text-blue-600 transition-colors font-medium" to="/login">
              返回登录
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
import { register } from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const uiStore = useUiStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({
  family_name: '',
  description: '',
  username: '',
  nickname: '',
  password: '',
  confirm: '',
})

const validatePass = (rule, value, callback) => {
  if (value !== form.password) {
    callback(new Error('两次输入密码不一致'))
  } else {
    callback()
  }
}

const rules = {
  family_name: [{ required: true, message: '请输入家庭名称', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validatePass, trigger: 'blur' },
  ],
}

const onRegister = async () => {
  await formRef.value.validate()
  loading.value = true
  try {
    const data = await register(form)
    userStore.setLoginInfo(data)
    uiStore.addToast('success', '家庭创建成功，您已成为房主')
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