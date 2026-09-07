<template>
  <div class="page user-view">
    <div class="stat-row">
      <div class="stat-block">
        <span class="stat-icon bg-blue-500/10 text-blue-500"><Users :size="18" /></span>
        <div>
          <div class="stat-value">{{ family.users_count ?? 0 }}</div>
          <div class="stat-label">用户数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-emerald-500/10 text-emerald-500"><Home :size="18" /></span>
        <div>
          <div class="stat-value">{{ family.rooms_count ?? 0 }}</div>
          <div class="stat-label">房间数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-amber-500/10 text-amber-500"><Cpu :size="18" /></span>
        <div>
          <div class="stat-value">{{ family.devices_count ?? 0 }}</div>
          <div class="stat-label">设备数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-violet-500/10 text-violet-500"><Wand2 :size="18" /></span>
        <div>
          <div class="stat-value">{{ family.scenes_count ?? 0 }}</div>
          <div class="stat-label">场景数</div>
        </div>
      </div>
    </div>

    <div class="user-grid grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_330px] gap-4 items-stretch flex-1 min-h-0">
      <section class="section-panel h-full flex flex-col">
        <div class="panel-head">
          <div class="flex items-center gap-2">
            <span class="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-500 flex items-center justify-center">
              <Users :size="16" />
            </span>
            <div>
              <h3 class="panel-title">家庭成员</h3>
              <p class="text-[11px] text-gray-400 mt-0.5">{{ userStore.familyName }}</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <el-tag effect="plain" round>{{ roleLabel(userStore.userRole) }}</el-tag>
            <el-button v-if="canManageUsers" size="small" type="primary" @click="openAddMember">
              <UserPlus :size="13" class="mr-1" />
              创建子账户
            </el-button>
          </div>
        </div>

        <div class="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto pr-0.5">
          <div
            v-for="user in users"
            :key="user.id"
            class="flex items-center gap-3 px-3.5 py-3 rounded-xl bg-white/50 border border-white/40 hover:border-blue-200/70 transition-all"
          >
            <span
              class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
              :class="avatarClass(user.role)"
            >
              {{ (user.nickname || '?').slice(0, 1) }}
            </span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold text-gray-800 truncate">{{ user.nickname }}</span>
                <el-tag :type="roleTagType(user.role)" size="small" effect="light">
                  {{ roleLabel(user.role) }}
                </el-tag>
              </div>
              <p class="text-xs text-gray-400 mt-0.5 truncate">@{{ user.username }}</p>
            </div>
            <el-button
              v-if="canManageUsers && user.role !== 'owner'"
              size="small"
              text
              type="danger"
              @click="requestDelete(user)"
            >
              <Trash2 :size="14" class="mr-1" />
              删除
            </el-button>
          </div>

          <div v-if="!users.length" class="text-center text-sm text-gray-400 py-10">
            当前家庭暂无成员
          </div>
        </div>
      </section>

      <div class="flex flex-col gap-4 h-full min-h-0">
        <section class="section-panel flex-1 min-h-0">
          <div class="panel-head">
            <h3 class="panel-title">我的偏好画像</h3>
            <el-button size="small" :loading="analyzing" @click="analyzePreferences">
              <RefreshCw :size="13" class="mr-1" />
              重新分析
            </el-button>
          </div>

          <template v-if="hasPreferences">
            <div class="pref-row">
              <span class="pref-label">夏季温度</span>
              <span class="pref-value">{{ preferences.preferred_temperature?.summer ?? '—' }} ℃</span>
            </div>
            <div class="pref-row">
              <span class="pref-label">作息</span>
              <span class="pref-value">
                {{ preferences.sleep_schedule?.bedtime || '—' }} 睡 · {{ preferences.sleep_schedule?.wakeup || '—' }} 起
              </span>
            </div>
            <div class="pref-row">
              <span class="pref-label">兴趣</span>
              <span class="pref-value">{{ (preferences.interests || []).join('、') || '—' }}</span>
            </div>
            <div class="pref-row">
              <span class="pref-label">常用设备</span>
              <span class="pref-value">
                {{ (preferences.frequent_devices || []).map(deviceLabel).join('、') || '—' }}
              </span>
            </div>
          </template>
          <div v-else class="flex flex-col items-center py-8 text-center text-gray-400">
            <Brain :size="30" class="mb-2 text-gray-300" />
            <p class="text-sm">暂未生成偏好画像</p>
            <p class="text-xs mt-1">对话积累后可由 LLM 自动分析</p>
          </div>
        </section>

        <section class="section-panel">
          <h3 class="panel-title mb-3">角色权限说明</h3>
          <ul class="flex flex-col gap-2.5 text-xs text-gray-500 leading-relaxed">
            <li class="flex gap-2"><span class="shrink-0 w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5"></span><span><strong class="text-gray-800">房主</strong>：管理全部房间、设备、场景与家庭成员</span></li>
            <li class="flex gap-2"><span class="shrink-0 w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5"></span><span><strong class="text-gray-800">住户</strong>：共享家庭数据，可控制设备、触发场景，不可增删</span></li>
            <li class="flex gap-2"><span class="shrink-0 w-1.5 h-1.5 rounded-full bg-gray-400 mt-1.5"></span><span><strong class="text-gray-800">访客</strong>：仅可查看，不可操作任何设备</span></li>
          </ul>
        </section>
      </div>
    </div>

    <el-dialog v-model="showAddMember" title="创建子账户（住户/访客）" width="440px" align-center append-to-body>
      <el-alert type="info" :closable="false" class="mb-4">
        子账户创建后可用用户名密码登录，自动绑定到您的家庭，共享家庭数据
      </el-alert>
      <el-form :model="newMember" label-width="72px">
        <el-form-item label="用户名" required>
          <el-input v-model="newMember.username" placeholder="登录用户名" maxlength="30" />
        </el-form-item>
        <el-form-item label="昵称" required>
          <el-input v-model="newMember.nickname" placeholder="前端展示昵称" maxlength="20" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="newMember.password" type="password" placeholder="至少 6 位" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="newMember.role">
            <el-radio value="resident">住户（可控制设备，不能创建用户）</el-radio>
            <el-radio value="guest">访客（仅可查看）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddMember = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="addMember">创建子账户</el-button>
      </template>
    </el-dialog>

    <ConfirmDialog
      v-model="showDelete"
      title="删除用户"
      :message="`确定删除用户「${deleteTarget?.nickname || ''}」吗？`"
      type="danger"
      confirm-text="删除"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UserPlus, Users, Home, Cpu, Wand2, Trash2, RefreshCw, Brain } from 'lucide-vue-next'
import { useUserStore } from '@/stores/user'
import { usePermission } from '@/composables/usePermission'
import { getFamilyOverview } from '@/api/family'
import { createSubAccount } from '@/api/auth'
import { getUsers, deleteUser, getUserPreferences, analyzeUserPreferences } from '@/api/user'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const userStore = useUserStore()
const { canManageUsers } = usePermission()

const family = ref({})
const users = ref([])
const preferences = ref({})
const analyzing = ref(false)
const submitting = ref(false)
const showAddMember = ref(false)
const showDelete = ref(false)
const deleteTarget = ref(null)
const newMember = ref({ username: '', nickname: '', role: 'resident', password: '' })

const hasPreferences = computed(() => Object.keys(preferences.value || {}).length > 0)

const roleLabel = (role) => ({ owner: '房主', resident: '住户', guest: '访客' }[role] || role)
const roleTagType = (role) => ({ owner: 'danger', resident: 'warning', guest: 'info' }[role] || 'info')
const deviceLabel = (type) =>
  ({ air_conditioner: '空调', light: '灯', robot_vacuum: '扫地机器人', curtain: '窗帘' }[type] || type)

const avatarClass = (role) => {
  const map = {
    owner: 'bg-blue-500/15 text-blue-600',
    resident: 'bg-emerald-500/15 text-emerald-600',
    guest: 'bg-gray-500/15 text-gray-500',
  }
  return map[role] || 'bg-blue-500/15 text-blue-600'
}

const loadData = async () => {
  try {
    const [familyDetail, memberList, preferenceData] = await Promise.all([
      getFamilyOverview(userStore.familyId),
      getUsers(),
      getUserPreferences(userStore.userId),
    ])
    family.value = familyDetail || {}
    users.value = memberList || []
    preferences.value = preferenceData?.preferences || {}
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

const openAddMember = () => {
  newMember.value = { username: '', nickname: '', role: 'resident', password: '' }
  showAddMember.value = true
}

const addMember = async () => {
  const member = newMember.value
  if (!member.username.trim() || !member.nickname.trim()) {
    ElMessage.warning('请填写用户名和昵称')
    return
  }
  if (!member.password || member.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  submitting.value = true
  try {
    await createSubAccount({
      username: member.username.trim(),
      password: member.password,
      nickname: member.nickname.trim(),
      role: member.role,
    })
    ElMessage.success(`子账户创建成功，${member.nickname} 可用此账号登录`)
    showAddMember.value = false
    await loadData()
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    submitting.value = false
  }
}

const analyzePreferences = async () => {
  analyzing.value = true
  try {
    preferences.value = await analyzeUserPreferences(userStore.userId)
    ElMessage.success('偏好画像分析完成')
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    analyzing.value = false
  }
}

const requestDelete = (user) => {
  deleteTarget.value = user
  showDelete.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  try {
    await deleteUser(deleteTarget.value.id)
    ElMessage.success('用户已删除')
    await loadData()
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

onMounted(loadData)
watch(
  () => [userStore.familyId, userStore.userId],
  loadData,
)
</script>

<style scoped>
.pref-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 9px 0;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

.pref-row:last-child {
  border-bottom: none;
}

.pref-label {
  flex: none;
  color: #5a5a7a;
}

.pref-value {
  text-align: right;
  word-break: break-all;
  color: #1a1a2e;
}

@media (max-width: 1023px) {
  .user-grid {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
  .user-grid > * {
    height: auto;
  }
}
</style>
