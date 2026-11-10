<template>
  <div class="auth-page min-h-dvh relative overflow-hidden">
    <div class="auth-orb auth-orb-a" aria-hidden="true"></div>
    <div class="auth-orb auth-orb-b" aria-hidden="true"></div>

    <div class="relative z-10 mx-auto flex min-h-dvh w-full max-w-[1180px] items-center px-4 py-8 lg:px-6">
      <div class="grid w-full items-center gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14">
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
            创建你的<br />
            <span class="text-blue-600">智能家庭</span>
          </h1>
          <p class="mt-5 max-w-[460px] text-[15px] leading-relaxed text-gray-500">
            注册即成为房主，邀请家人加入同一家庭。设备、场景、知识库与偏好画像按家庭隔离。
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

        <section class="w-full max-w-[520px] mx-auto lg:mx-0 lg:ml-auto">
          <div class="lg:hidden text-center mb-6">
            <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 text-white grid place-items-center mx-auto mb-4 shadow-xl shadow-blue-500/25">
              <Home :size="26" />
            </div>
            <h1 class="text-2xl font-bold text-gray-900 tracking-tight">注册新家庭</h1>
            <p class="text-sm text-gray-400 mt-1.5">创建家庭后您将成为房主</p>
          </div>

          <div class="auth-card glass-strong rounded-[26px] p-6 sm:p-7">
            <div class="mb-5">
              <h2 class="text-[22px] font-bold text-gray-900 tracking-tight">注册新家庭</h2>
              <p class="text-[13px] text-gray-400 mt-1">创建家庭后您将成为房主，可邀请住户和访客</p>
            </div>

            <el-form
              ref="formRef"
              class="register-form"
              :model="form"
              :rules="rules"
              label-position="top"
            >
              <section class="form-section">
                <div class="form-section-title">
                  <span class="form-section-icon"><Home :size="13" /></span>
                  <span>家庭信息</span>
                </div>
                <el-form-item label="家庭名称" prop="family_name">
                  <el-input v-model="form.family_name" placeholder="如：张三的家" size="large" />
                </el-form-item>
                <el-form-item label="家庭描述（可选）">
                  <el-input
                    v-model="form.description"
                    placeholder="一句话描述您的家庭环境"
                    size="large"
                  />
                </el-form-item>
              </section>

              <section class="form-section">
                <div class="form-section-title">
                  <span class="form-section-icon"><Users :size="13" /></span>
                  <span>房主账户</span>
                </div>
                <div class="form-grid">
                  <el-form-item label="用户名" prop="username">
                    <el-input
                      v-model="form.username"
                      placeholder="登录用户名"
                      size="large"
                      autocomplete="username"
                    />
                  </el-form-item>
                  <el-form-item label="昵称" prop="nickname">
                    <el-input v-model="form.nickname" placeholder="前端展示昵称" size="large" />
                  </el-form-item>
                  <el-form-item label="密码" prop="password">
                    <el-input
                      v-model="form.password"
                      type="password"
                      placeholder="至少 6 位"
                      size="large"
                      autocomplete="new-password"
                      show-password
                    />
                  </el-form-item>
                  <el-form-item label="确认密码" prop="confirm">
                    <el-input
                      v-model="form.confirm"
                      type="password"
                      placeholder="再次输入密码"
                      size="large"
                      autocomplete="new-password"
                      show-password
                    />
                  </el-form-item>
                </div>
              </section>

              <el-button class="w-full mt-2" type="primary" size="large" :loading="loading" @click="onRegister">
                注册并创建家庭
              </el-button>
            </el-form>

            <p class="text-center text-[13px] text-gray-500 mt-5">
              已有家庭？
              <router-link class="text-blue-600 hover:text-blue-700 transition-colors font-semibold" to="/login">
                返回登录
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
import { Home, ShieldCheck, Database, Users } from 'lucide-vue-next'
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

const features = [
  { icon: Users, title: '家庭多角色', desc: '房主、住户、访客三级权限，数据按家庭隔离' },
  { icon: ShieldCheck, title: '安全审批', desc: '门锁与场景等高风险操作，先确认再执行' },
  { icon: Database, title: '私有知识库', desc: '上传家庭规章与私人文档，问答时按权限检索' },
]

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
.register-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.form-section + .form-section {
  margin-top: 2px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.72);
}

.form-section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-600, #4c5468);
}

.form-section-icon {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 8px;
  color: var(--accent-strong, #3f57d6);
  background: rgba(79, 107, 237, 0.1);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 14px;
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
