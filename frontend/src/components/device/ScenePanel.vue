<template>
  <section class="section-panel scene-panel">
    <div class="panel-head">
      <div class="flex items-center gap-2.5">
        <span class="scene-badge">
          <Zap :size="16" />
        </span>
        <div>
          <h3 class="panel-title">场景快捷控制</h3>
          <p class="text-[11px] text-gray-400 mt-0.5">一键联动当前家庭的多个设备</p>
        </div>
      </div>
      <el-button v-if="canManageScenes" size="small" type="primary" plain @click="openCreate">
        <Plus :size="13" class="mr-1" />
        新增场景
      </el-button>
    </div>

    <div v-if="scenes.length" class="scene-grid">
      <article v-for="scene in scenes" :key="scene.id" class="scene-card">
        <span class="scene-icon"><Zap :size="15" /></span>
        <div class="scene-main">
          <h4 class="scene-name" :title="scene.name">{{ scene.name }}</h4>
          <p class="scene-desc" :title="scene.description || ''">
            {{ scene.description || '一键执行家庭设备联动' }}
          </p>
          <span v-if="actionCount(scene)" class="scene-meta">
            <Layers :size="11" />
            {{ actionCount(scene) }} 个动作
          </span>
        </div>
        <div class="scene-actions">
          <el-button size="small" type="primary" :loading="executingId === scene.id" @click="runScene(scene)">
            执行
          </el-button>
          <button
            v-if="canManageScenes"
            type="button"
            class="scene-delete"
            title="删除场景"
            aria-label="删除场景"
            @click="removeScene(scene)"
          >
            <Trash2 :size="14" />
          </button>
        </div>
      </article>
    </div>
    <div v-else class="scene-empty">
      <Zap :size="20" class="text-gray-300" />
      <p>当前家庭暂无场景，创建后即可一键联动设备</p>
    </div>

    <el-dialog v-model="showCreate" title="新增场景" width="680px" align-center append-to-body class="scene-dialog">
      <el-form :model="form" label-position="top">
        <el-form-item label="场景名称" required>
          <el-input v-model="form.name" placeholder="如：回家模式" maxlength="64" />
        </el-form-item>
        <el-form-item label="场景描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="120" />
        </el-form-item>
        <el-form-item label="场景动作">
          <div class="w-full space-y-2">
            <div v-for="(action, index) in form.actions" :key="index" class="action-row">
              <div class="action-selects">
                <el-select
                  v-model="action.room_id"
                  size="small"
                  placeholder="房间"
                  class="action-select room-select"
                  @change="onRoomChange(action)"
                >
                  <el-option v-for="room in rooms" :key="room.id" :label="room.name" :value="room.id" />
                </el-select>
                <el-select
                  v-model="action.device_id"
                  size="small"
                  placeholder="设备"
                  class="action-select type-select"
                  :disabled="!action.room_id"
                  @change="onDeviceChange(action)"
                >
                  <el-option v-for="device in devicesFor(action)" :key="device.id" :label="device.name" :value="device.id" />
                </el-select>
                <el-select
                  v-model="action.operation"
                  size="small"
                  placeholder="操作"
                  class="action-select operation-select"
                  :disabled="!action.device_type"
                >
                  <el-option v-for="option in operationsFor(action.device_type)" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
              </div>
              <div class="action-tail">
                <div v-if="paramMeta(action)" class="action-param">
                  <span class="param-label">{{ paramMeta(action).label }}</span>
                  <el-input-number
                    v-model="action[paramMeta(action).key]"
                    :min="paramMeta(action).min"
                    :max="paramMeta(action).max"
                    size="small"
                    controls-position="right"
                    class="param-input"
                  />
                </div>
                <button
                  class="action-remove"
                  type="button"
                  title="删除动作"
                  aria-label="删除动作"
                  @click="removeAction(index)"
                >
                  <X :size="14" />
                </button>
              </div>
            </div>

            <el-button size="small" class="w-full add-action-btn" @click="addAction">
              <Plus :size="13" class="mr-1" />
              添加动作
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Trash2, Zap, Layers, X } from 'lucide-vue-next'
import { listScenes, createScene, executeScene, deleteScene } from '@/api/scene'
import { getRoomDetail } from '@/api/room'
import { usePermission } from '@/composables/usePermission'
import { useRoomStore } from '@/stores/room'

const emit = defineEmits(['executed'])

const { canManageScenes } = usePermission()
const roomStore = useRoomStore()
const rooms = roomStore.rooms

const scenes = ref([])
const executingId = ref(null)
const creating = ref(false)
const showCreate = ref(false)
const form = ref(emptyForm())

const deviceOptions = [
  { label: '空调', value: 'air_conditioner' },
  { label: '灯光', value: 'light' },
  { label: '扫地机器人', value: 'robot_vacuum' },
  { label: '窗帘', value: 'curtain' },
  { label: '智能音箱', value: 'speaker' },
  { label: '电视', value: 'tv' },
  { label: '空气净化器', value: 'air_purifier' },
  { label: '加湿器', value: 'humidifier' },
  { label: '热水器', value: 'water_heater' },
  { label: '洗衣机', value: 'washer' },
  { label: '冰箱', value: 'fridge' },
  { label: '智能门锁', value: 'door_lock' },
  { label: '摄像头', value: 'camera' },
]

// 房间 -> 该房间实际存在的可控设备（缓存，避免重复请求）
const roomDevicesCache = ref({})

const loadRoomDevices = async (roomId) => {
  if (!roomId || roomDevicesCache.value[roomId]) return
  try {
    const detail = await getRoomDetail(roomId)
    const devices = (detail?.devices || [])
      .filter((device) => deviceOptions.some((option) => option.value === device.type))
      .map((device) => ({ id: device.id, name: device.name, type: device.type }))
    roomDevicesCache.value = { ...roomDevicesCache.value, [roomId]: devices }
  } catch (error) {
    // 拉取失败时设备列表保持为空，不阻断场景配置
  }
}

const onRoomChange = (action) => {
  // 房间变更后旧设备可能不存在于新房间，清空并联动拉取该房间设备
  action.device_id = null
  action.device_type = ''
  action.operation = ''
  loadRoomDevices(action.room_id)
}

const devicesFor = (action) => roomDevicesCache.value[action.room_id] || []

const onDeviceChange = (action) => {
  // 由选中的具体设备推导设备类型，再决定可用操作
  const device = devicesFor(action).find((item) => item.id === action.device_id)
  action.device_type = device?.type || ''
  action.operation = ''
}

const operationOptions = {
  air_conditioner: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
    { label: '设定温度', value: 'set_temperature' },
  ],
  light: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
    { label: '调节亮度', value: 'set_brightness' },
  ],
  robot_vacuum: [
    { label: '开始清扫', value: 'start_clean' },
    { label: '停止清扫', value: 'stop_clean' },
  ],
  curtain: [
    { label: '全部打开', value: 'open_curtain' },
    { label: '全部关闭', value: 'close_curtain' },
    { label: '调节开合', value: 'set_position' },
  ],
  speaker: [
    { label: '播放', value: 'play_speaker' },
    { label: '停止播放', value: 'stop_speaker' },
  ],
  tv: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
    { label: '调节音量', value: 'set_volume' },
  ],
  air_purifier: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
  ],
  humidifier: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
    { label: '设定湿度', value: 'set_humidity' },
  ],
  water_heater: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
    { label: '设定水温', value: 'set_temperature' },
  ],
  washer: [
    { label: '开始洗涤', value: 'start_wash' },
    { label: '停止洗涤', value: 'stop_wash' },
  ],
  fridge: [
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
  ],
  door_lock: [
    { label: '上锁', value: 'lock_door' },
    { label: '开锁', value: 'unlock_door' },
  ],
  camera: [
    { label: '开始录制', value: 'start_record' },
    { label: '停止录制', value: 'stop_record' },
    { label: '开启', value: 'on' },
    { label: '关闭', value: 'off' },
  ],
}

const paramMetaMap = {
  set_temperature: { key: 'temperature', label: '温度', min: 16, max: 30 },
  set_brightness: { key: 'brightness', label: '亮度', min: 0, max: 100 },
  set_position: { key: 'position', label: '开合', min: 0, max: 100 },
  set_volume: { key: 'volume', label: '音量', min: 0, max: 100 },
  set_humidity: { key: 'targetHumidity', label: '湿度', min: 30, max: 80 },
}

const specialAttributes = {
  start_clean: { power: 'on', status: 'cleaning' },
  stop_clean: { power: 'off', status: 'idle' },
  open_curtain: { power: 'on', position: 100 },
  close_curtain: { power: 'off' },
  play_speaker: { power: 'on', playing: true },
  stop_speaker: { playing: false },
  start_wash: { power: 'on', status: 'running' },
  stop_wash: { power: 'off', status: 'idle' },
  lock_door: { locked: true },
  unlock_door: { locked: false },
  start_record: { power: 'on', recording: true },
  stop_record: { recording: false },
}

function emptyForm() {
  return {
    name: '',
    description: '',
    actions: [emptyAction()],
  }
}

function emptyAction() {
  return {
    room_id: null,
    device_id: null,
    device_type: '',
    operation: '',
    temperature: 26,
    brightness: 80,
    position: 50,
    volume: 30,
    targetHumidity: 55,
  }
}

const loadScenes = async () => {
  try {
    scenes.value = (await listScenes()) || []
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

const actionCount = (scene) => {
  const actions = scene.actions
  if (Array.isArray(actions)) return actions.length
  if (Array.isArray(actions?.actions)) return actions.actions.length
  return 0
}

const runScene = async (scene) => {
  executingId.value = scene.id
  try {
    const result = await executeScene(scene.name)
    if (result?.success === false) {
      ElMessage.error(result.error || '场景执行失败')
    } else if (result?.failed_count > 0) {
      // 部分动作失败：成功的动作已生效，需明确提示用户失败明细
      ElMessage.warning(result.message || `场景部分动作执行失败（${result.failed_count} 个）`)
      emit('executed')
    } else {
      ElMessage.success(`场景「${scene.name}」执行完成`)
      emit('executed')
    }
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    executingId.value = null
  }
}

const operationsFor = (deviceType) => operationOptions[deviceType] || []

const paramMeta = (action) => {
  const meta = paramMetaMap[action.operation]
  if (!meta) return null
  if (action.device_type === 'water_heater' && action.operation === 'set_temperature') {
    return { ...meta, min: 30, max: 75 }
  }
  return meta
}

const addAction = () => {
  form.value.actions.push(emptyAction())
}

const removeAction = (index) => {
  form.value.actions.splice(index, 1)
  if (!form.value.actions.length) form.value.actions.push(emptyAction())
}

const buildAttributes = (action) => {
  if (specialAttributes[action.operation]) return { ...specialAttributes[action.operation] }
  if (action.operation === 'on') return { power: 'on' }
  if (action.operation === 'off') return { power: 'off' }
  const attrs = { power: 'on' }
  if (action.operation === 'set_temperature') attrs.temperature = action.temperature
  if (action.operation === 'set_brightness') attrs.brightness = action.brightness
  if (action.operation === 'set_position') attrs.position = action.position
  if (action.operation === 'set_volume') attrs.volume = action.volume
  if (action.operation === 'set_humidity') attrs.target_humidity = action.targetHumidity
  return attrs
}

const openCreate = () => {
  form.value = emptyForm()
  if (!rooms.length) roomStore.fetchRooms().catch(() => {})
  showCreate.value = true
}

const submitCreate = async () => {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入场景名称')
    return
  }
  const actions = form.value.actions
    .filter((action) => action.room_id && action.device_id && action.operation)
    .map((action) => {
      const room = rooms.find((item) => item.id === action.room_id)
      return {
        device_id: action.device_id,
        device_type: action.device_type,
        room_name: room?.name || '',
        attributes: buildAttributes(action),
      }
    })
  if (!actions.length) {
    ElMessage.warning('请至少添加一条完整的场景动作（房间 + 设备 + 操作）')
    return
  }

  creating.value = true
  try {
    await createScene({
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
      actions: { actions },
    })
    ElMessage.success('场景创建成功')
    showCreate.value = false
    await loadScenes()
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    creating.value = false
  }
}

const removeScene = async (scene) => {
  try {
    await deleteScene(scene.id)
    ElMessage.success(`场景「${scene.name}」已删除`)
    await loadScenes()
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

onMounted(() => {
  loadScenes()
  if (!rooms.length) roomStore.fetchRooms().catch(() => {})
})
</script>

<style scoped>
.scene-panel {
  padding: 16px 18px;
}

.scene-badge {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: 11px;
  color: #b0742e;
  background: linear-gradient(135deg, rgba(217, 154, 78, 0.2), rgba(217, 154, 78, 0.08));
  border: 1px solid rgba(217, 154, 78, 0.18);
}

.scene-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.scene-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.72);
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.scene-card:hover {
  background: rgba(255, 255, 255, 0.82);
  border-color: rgba(255, 255, 255, 0.92);
  transform: translateY(-1px);
}

.scene-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 10px;
  color: #b0742e;
  background: rgba(217, 154, 78, 0.14);
}

.scene-main {
  flex: 1;
  min-width: 0;
}

.scene-name {
  margin: 1px 0 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--ink-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scene-desc {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scene-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 10px;
  color: var(--ink-400);
}

.scene-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.scene-delete {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  color: #a3a8b6;
  transition: color 0.16s ease, background 0.16s ease;
}

.scene-delete:hover {
  color: #c45a4c;
  background: rgba(216, 105, 90, 0.1);
}

.scene-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px 12px;
  border-radius: 14px;
  border: 1px dashed rgba(23, 28, 43, 0.1);
  background: rgba(255, 255, 255, 0.32);
  font-size: 12px;
  color: var(--ink-400);
  text-align: center;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.7);
}

.action-selects {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.action-tail {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.action-select {
  flex: 1;
  min-width: 0;
  max-width: none;
}

.action-param {
  display: flex;
  align-items: center;
  gap: 6px;
}

.param-label {
  font-size: 12px;
  color: var(--ink-500);
  white-space: nowrap;
}

.param-input {
  width: 104px;
}

.action-remove {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 8px;
  color: #a3a8b6;
  transition: color 0.16s ease, background 0.16s ease;
}

.action-remove:hover {
  color: #c45a4c;
  background: rgba(216, 105, 90, 0.1);
}

.add-action-btn {
  border-style: dashed;
}

@media (max-width: 640px) {
  .scene-grid {
    grid-template-columns: 1fr;
  }

  .action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .action-selects {
    flex-wrap: wrap;
  }

  .action-select {
    flex: 1 1 44%;
  }

  .action-tail {
    justify-content: space-between;
  }

  .action-param {
    flex: 1;
  }

  .param-input {
    flex: 1;
    width: auto;
  }
}
</style>
