<template>
  <div class="page user-view">
    <h1 class="sr-only">家庭成员</h1>

    <div class="stat-row">
      <div class="stat-block">
        <span class="stat-icon bg-blue-500/10 text-blue-500"><Users :size="19" /></span>
        <div>
          <div class="stat-value">{{ family.users_count ?? 0 }}</div>
          <div class="stat-label">用户数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-emerald-500/10 text-emerald-500"><Home :size="19" /></span>
        <div>
          <div class="stat-value">{{ family.rooms_count ?? 0 }}</div>
          <div class="stat-label">房间数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-amber-500/10 text-amber-500"><Cpu :size="19" /></span>
        <div>
          <div class="stat-value">{{ family.devices_count ?? 0 }}</div>
          <div class="stat-label">设备数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-violet-500/10 text-violet-500"><Wand2 :size="19" /></span>
        <div>
          <div class="stat-value">{{ family.scenes_count ?? 0 }}</div>
          <div class="stat-label">场景数</div>
        </div>
      </div>
    </div>

    <div class="user-grid">
      <section class="section-panel member-panel">
        <div class="panel-head">
          <div class="flex items-center gap-2.5">
            <span class="panel-icon"><Users :size="15" /></span>
            <div>
              <h3 class="panel-title">成员列表</h3>
              <p class="text-[11px] text-gray-400 mt-0.5">共 {{ users.length }} 位成员共享家庭数据</p>
            </div>
          </div>
          <div class="member-head-actions">
            <span class="role-chip" :class="userStore.userRole">{{ roleLabel(userStore.userRole) }}</span>
            <el-button v-if="canManageUsers" type="primary" size="small" @click="openAddMember">
              <UserPlus :size="13" class="mr-1" />
              创建子账户
            </el-button>
          </div>
        </div>

        <div class="member-list">
          <article
            v-for="user in users"
            :key="user.id"
            class="member-row"
            :class="{ self: user.id === userStore.userId }"
          >
            <span class="member-avatar" :class="avatarClass(user.role)">
              {{ (user.nickname || '?').slice(0, 1) }}
            </span>
            <div class="member-main">
              <div class="member-name-line">
                <span class="member-name">{{ user.nickname }}</span>
                <span class="role-pill" :class="user.role">{{ roleLabel(user.role) }}</span>
                <span v-if="user.id === userStore.userId" class="self-tag">我</span>
              </div>
              <span class="member-handle">@{{ user.username }}</span>
            </div>
            <button
              v-if="canManageUsers && user.role !== 'owner'"
              type="button"
              class="member-remove"
              title="删除成员"
              aria-label="删除成员"
              @click="requestDelete(user)"
            >
              <Trash2 :size="14" />
            </button>
          </article>

          <div v-if="!users.length" class="empty-state member-empty">
            <span class="empty-icon"><Users :size="22" /></span>
            <p class="text-sm">当前家庭暂无成员</p>
          </div>
        </div>
      </section>

      <div class="user-aside">
        <section class="section-panel pref-panel">
          <div class="panel-head">
            <div class="flex items-center gap-2.5">
              <span class="panel-icon amber"><Brain :size="15" /></span>
              <h3 class="panel-title">我的偏好画像</h3>
            </div>
            <el-button size="small" :loading="analyzing" @click="analyzePreferences">
              <RefreshCw :size="13" class="mr-1" />
              重新分析
            </el-button>
          </div>

          <template v-if="hasPreferences">
            <div class="pref-list">
              <div v-for="row in prefRows" :key="row.label" class="pref-row">
                <span class="pref-label">{{ row.label }}</span>
                <span class="pref-value">{{ row.value }}</span>
              </div>
            </div>
          </template>
          <div v-else class="empty-state pref-empty">
            <span class="empty-icon"><Brain :size="22" /></span>
            <p class="text-sm">暂未生成偏好画像</p>
            <p class="mt-1 text-xs text-gray-400">对话积累后可由大模型自动分析</p>
          </div>
        </section>

        <section class="section-panel perm-panel">
          <h3 class="panel-title mb-3">角色权限说明</h3>
          <div class="perm-list">
            <div class="perm-item">
              <span class="perm-icon owner"><ShieldCheck :size="15" /></span>
              <div>
                <strong>房主</strong>
                <p>管理全部房间、设备、场景与家庭成员</p>
              </div>
            </div>
            <div class="perm-item">
              <span class="perm-icon resident"><UserCheck :size="15" /></span>
              <div>
                <strong>住户</strong>
                <p>共享家庭数据，可控制设备与触发场景</p>
              </div>
            </div>
            <div class="perm-item">
              <span class="perm-icon guest"><Eye :size="15" /></span>
              <div>
                <strong>访客</strong>
                <p>仅可查看，不可操作任何设备</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <el-dialog v-model="showAddMember" title="创建子账户（住户/访客）" width="460px" align-center append-to-body>
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
import {
  UserPlus,
  Users,
  Home,
  Cpu,
  Wand2,
  Trash2,
  RefreshCw,
  Brain,
  ShieldCheck,
  UserCheck,
  Eye,
} from 'lucide-vue-next'
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

// 画像展示：直接把模型输出的 JSON 对象动态渲染为「标签 + 值」行，
// 兼容旧版固定字段结构（preferred_temperature / sleep_schedule 等）。
const DEVICE_LABEL_MAP = {
  air_conditioner: '空调', light: '灯', robot_vacuum: '扫地机器人', curtain: '窗帘',
  speaker: '音箱', tv: '电视', air_purifier: '空气净化器', humidifier: '加湿器',
  water_heater: '热水器', washer: '洗衣机', fridge: '冰箱', door_lock: '智能门锁',
  camera: '摄像头',
}
const toDisplay = (value) => {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.filter((v) => v !== null && v !== '' && v !== undefined).join('、') || '—'
  if (typeof value === 'object') {
    const parts = Object.entries(value)
      .filter(([, v]) => v !== null && v !== '' && v !== undefined)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('、') : v}`)
    return parts.join('；') || '—'
  }
  return String(value)
}
const prefRows = computed(() => {
  const pref = preferences.value || {}
  const rows = []
  // 旧版固定字段兼容
  if (pref.preferred_temperature && typeof pref.preferred_temperature === 'object') {
    const t = pref.preferred_temperature
    if (t.summer !== undefined && t.summer !== null && t.summer !== '') rows.push({ label: '夏季温度', value: `${t.summer} ℃` })
    if (t.winter !== undefined && t.winter !== null && t.winter !== '') rows.push({ label: '冬季温度', value: `${t.winter} ℃` })
  }
  if (pref.sleep_schedule && typeof pref.sleep_schedule === 'object') {
    const s = pref.sleep_schedule
    rows.push({
      label: '作息',
      value: `${s.bedtime || '—'} 睡 · ${s.wakeup || '—'} 起`,
    })
  }
  if (pref.interests) rows.push({ label: '兴趣', value: toDisplay(pref.interests) })
  if (pref.frequent_devices) {
    rows.push({
      label: '常用设备',
      value: (Array.isArray(pref.frequent_devices) ? pref.frequent_devices : [pref.frequent_devices])
        .map((d) => DEVICE_LABEL_MAP[d] || d)
        .join('、') || '—',
    })
  }
  if (pref.interaction_style) rows.push({ label: '交互风格', value: toDisplay(pref.interaction_style) })
  if (pref.remarks) rows.push({ label: '备注/特殊要求', value: toDisplay(pref.remarks) })
  // 新版自由 JSON：模型输出的任意中文键直接展示（跳过已处理的旧键）
  const handled = new Set(['preferred_temperature', 'sleep_schedule', 'interests', 'frequent_devices', 'interaction_style', 'remarks'])
  for (const [key, value] of Object.entries(pref)) {
    if (handled.has(key)) continue
    rows.push({ label: key, value: toDisplay(value) })
  }
  return rows
})

const roleLabel = (role) => ({ owner: '房主', resident: '住户', guest: '访客' }[role] || role)

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
.user-view {
  height: calc(100dvh - 104px);
}

.user-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 14px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.member-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
}

.panel-icon.amber {
  color: #b0742e;
  background: rgba(217, 154, 78, 0.14);
}

.member-head-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex: none;
}

@media (max-width: 520px) {
  .member-head-actions {
    flex-wrap: wrap;
  }
}

.role-chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-500);
  background: rgba(255, 255, 255, 0.68);
  border: 1px solid rgba(255, 255, 255, 0.8);
}

.role-chip.owner {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.09);
  border-color: rgba(79, 107, 237, 0.16);
}

.role-chip.resident {
  color: #2c7a5f;
  background: rgba(236, 253, 245, 0.86);
  border-color: rgba(16, 185, 129, 0.18);
}

.member-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.member-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.62);
  transition: background 0.18s ease, border-color 0.18s ease;
}

.member-row:hover {
  background: rgba(255, 255, 255, 0.78);
  border-color: rgba(255, 255, 255, 0.88);
}

.member-row.self {
  background: rgba(79, 107, 237, 0.055);
  border-color: rgba(79, 107, 237, 0.14);
}

.member-avatar {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 700;
}

.member-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.member-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.member-name {
  font-size: 13px;
  font-weight: 650;
  color: var(--ink-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-handle {
  margin-top: 2px;
  font-size: 11px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-pill {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  color: var(--ink-500);
  background: rgba(23, 28, 43, 0.05);
}

.role-pill.owner {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
}

.role-pill.resident {
  color: #2c7a5f;
  background: rgba(16, 185, 129, 0.1);
}

.role-pill.guest {
  color: var(--ink-500);
  background: rgba(95, 103, 122, 0.09);
}

.self-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  color: var(--accent-strong);
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(79, 107, 237, 0.2);
}

.member-remove {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: 9px;
  color: #a3a8b6;
  transition: color 0.16s ease, background 0.16s ease;
}

.member-remove:hover {
  color: #c45a4c;
  background: rgba(216, 105, 90, 0.1);
}

.member-empty {
  flex: 1;
}

.user-aside {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.pref-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.pref-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  min-height: 0;
}

.pref-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 9px 10px;
  border-radius: 9px;
  font-size: 12px;
  transition: background 0.16s ease;
}

.pref-row:hover {
  background: rgba(255, 255, 255, 0.52);
}

.pref-label {
  flex: none;
  max-width: 42%;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pref-value {
  text-align: right;
  word-break: break-word;
  color: var(--ink-700);
  font-weight: 500;
}

.pref-empty {
  flex: 1;
  padding: 28px 12px;
}

.perm-panel {
  flex: none;
}

.perm-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.perm-item {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.44);
  border: 1px solid rgba(255, 255, 255, 0.56);
}

.perm-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 8px;
}

.perm-icon.owner {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
}

.perm-icon.resident {
  color: #2c7a5f;
  background: rgba(16, 185, 129, 0.1);
}

.perm-icon.guest {
  color: var(--ink-500);
  background: rgba(95, 103, 122, 0.09);
}

.perm-item strong {
  font-size: 12px;
  color: var(--ink-900);
}

.perm-item p {
  margin: 1px 0 0;
  font-size: 10px;
  line-height: 1.5;
  color: var(--ink-400);
}

@media (max-width: 1023px) {
  .user-grid {
    grid-template-columns: 1fr;
    flex: none;
  }

  .user-view {
    height: auto;
    min-height: 100%;
  }

  .member-panel {
    min-height: 320px;
  }

  .user-aside {
    overflow: visible;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }
}

@media (max-width: 720px) {
  .user-aside {
    grid-template-columns: 1fr;
  }
}
</style>
