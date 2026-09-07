<template>
  <section class="section-panel scene-panel">
    <div class="panel-head">
      <div class="flex items-center gap-2">
        <span class="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-500 flex items-center justify-center shrink-0">
          <Zap :size="16" />
        </span>
        <div>
          <h3 class="panel-title">场景快捷控制</h3>
          <p class="text-[11px] text-gray-400 mt-0.5">一键批量控制当前家庭设备</p>
        </div>
      </div>
      <el-button v-if="canManageScenes" size="small" type="primary" plain @click="openCreate">
        <Plus :size="13" class="mr-1" />
        新增场景
      </el-button>
    </div>

    <div v-if="scenes.length" class="scene-list">
      <div v-for="scene in scenes" :key="scene.id" class="scene-item">
        <div class="flex-1 min-w-0">
          <div class="text-sm font-semibold text-gray-800 truncate">{{ scene.name }}</div>
          <p class="text-xs text-gray-400 truncate">{{ scene.description || '暂无描述' }}</p>
        </div>
        <el-button size="small" type="primary" :loading="executingId === scene.id" @click="runScene(scene)">
          执行
        </el-button>
        <el-button
          v-if="canManageScenes"
          size="small"
          text
          type="danger"
          aria-label="删除场景"
          @click="removeScene(scene)"
        >
          <Trash2 :size="14" />
        </el-button>
      </div>
    </div>
    <div v-else class="text-center text-sm text-gray-400 py-6">当前家庭暂无场景</div>

    <el-dialog v-model="showCreate" title="新增场景" width="680px" align-center append-to-body>
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
              <el-select
                v-model="action.room_id"
                size="small"
                placeholder="房间"
                class="action-select room-select"
              >
                <el-option v-for="room in rooms" :key="room.id" :label="room.name" :value="room.id" />
              </el-select>
              <el-select
                v-model="action.device_type"
                size="small"
                placeholder="设备类型"
                class="action-select type-select"
                @change="onDeviceChange(action)"
              >
                <el-option v-for="option in deviceOptions" :key="option.value" :label="option.label" :value="option.value" />
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
              <el-button
                class="action-remove"
                size="small"
                text
                type="danger"
                aria-label="删除动作"
                @click="removeAction(index)"
              >
                <Trash2 :size="14" />
              </el-button>
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
import { Plus, Trash2, Zap } from 'lucide-vue-next'
import { listScenes, createScene, executeScene, deleteScene } from '@/api/scene'
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

const runScene = async (scene) => {
  executingId.value = scene.id
  try {
    const result = await executeScene(scene.name)
    if (result?.success === false) {
      ElMessage.error(result.error || '场景执行失败')
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

const onDeviceChange = (action) => {
  action.operation = ''
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
    .filter((action) => action.room_id && action.device_type && action.operation)
    .map((action) => {
      const room = rooms.find((item) => item.id === action.room_id)
      return {
        device_type: action.device_type,
        room_name: room?.name || '',
        attributes: buildAttributes(action),
      }
    })
  if (!actions.length) {
    ElMessage.warning('请至少添加一条完整的场景动作')
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
  margin-bottom: 16px;
}
.scene-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}
.scene-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 220px;
  max-width: 100%;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.55);
}
.action-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.5);
}
.action-select {
  flex: 1;
  min-width: 0;
}
.room-select {
  max-width: 130px;
}
.type-select {
  max-width: 140px;
}
.operation-select {
  max-width: 130px;
}
.action-param {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.param-label {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}
.param-input {
  width: 110px;
}
.action-remove {
  flex: none;
}
.add-action-btn {
  border-style: dashed;
}
</style>