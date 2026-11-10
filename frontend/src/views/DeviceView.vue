<template>
  <div class="page device-view">
    <h1 class="sr-only">设备总览</h1>

    <div class="stat-row">
      <div class="stat-block">
        <span class="stat-icon bg-blue-500/10 text-blue-500"><Cpu :size="19" /></span>
        <div>
          <div class="stat-value">{{ devices.length }}</div>
          <div class="stat-label">设备总数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-emerald-500/10 text-emerald-500"><Wifi :size="19" /></span>
        <div>
          <div class="stat-value">{{ deviceStore.onlineCount }}</div>
          <div class="stat-label">在线设备</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-amber-500/10 text-amber-500"><Sparkles :size="19" /></span>
        <div>
          <div class="stat-value">{{ deviceStore.cleaningCount }}</div>
          <div class="stat-label">清扫中</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-violet-500/10 text-violet-500"><Home :size="19" /></span>
        <div>
          <div class="stat-value">{{ roomStore.rooms.length }}</div>
          <div class="stat-label">房间数</div>
        </div>
      </div>
    </div>

    <ScenePanel @executed="loadAll" />

    <section class="section-panel filter-panel">
      <div class="filter-main">
        <div class="room-tabs" role="group" aria-label="按房间筛选">
          <button
            type="button"
            class="room-tab"
            :class="{ active: filterRoom === null }"
            :aria-pressed="filterRoom === null"
            @click="filterRoom = null"
          >
            全部房间
            <span class="room-count">{{ devices.length }}</span>
          </button>
          <button
            v-for="room in roomStore.rooms"
            :key="room.id"
            type="button"
            class="room-tab"
            :class="{ active: filterRoom === room.id }"
            :aria-pressed="filterRoom === room.id"
            @click="filterRoom = filterRoom === room.id ? null : room.id"
          >
            {{ room.name }}
            <span class="room-count">{{ roomDeviceCount(room.id) }}</span>
          </button>
        </div>

        <div class="filter-tools">
          <el-input v-model="keyword" placeholder="搜索名称 / 品牌 / 型号" clearable class="filter-search">
            <template #prefix><Search :size="15" class="text-gray-400" /></template>
          </el-input>
          <el-select v-model="filterType" placeholder="全部类型" clearable filterable class="filter-type">
            <el-option
              v-for="option in typeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-button v-if="canManageDevices" type="primary" class="filter-add" @click="openAdd">
            <Plus :size="15" class="mr-1.5" />
            添加设备
          </el-button>
        </div>
      </div>

      <div v-if="hasFilters" class="filter-result">
        <span>筛选结果 <strong>{{ filteredDevices.length }}</strong> 台</span>
        <button type="button" class="clear-filter" @click="clearFilters">
          <X :size="12" />
          清除筛选
        </button>
      </div>
    </section>

    <div v-if="deviceStore.loading && !devices.length" class="device-grid" aria-hidden="true">
      <div v-for="n in 8" :key="n" class="device-skeleton">
        <div class="skeleton sk-media"></div>
        <div class="sk-body">
          <div class="skeleton sk-line sk-line-lg"></div>
          <div class="skeleton sk-line sk-line-sm"></div>
          <div class="skeleton sk-line sk-line-foot"></div>
        </div>
      </div>
    </div>

    <div v-else-if="filteredDevices.length" class="device-grid">
      <DeviceCard
        v-for="device in filteredDevices"
        :key="device.id"
        :device="device"
        @open="openControl"
        @control="onControl"
      />
    </div>

    <section v-else class="section-panel empty-state">
      <span class="empty-icon">
        <PackageOpen :size="26" />
      </span>
      <p class="text-sm font-medium text-gray-600">
        {{ hasFilters ? '没有找到匹配的设备' : '当前家庭还没有设备' }}
      </p>
      <p class="mt-1 text-xs text-gray-400">
        {{ hasFilters ? '试试更换房间或类型筛选' : '添加设备后即可在此统一控制' }}
      </p>
      <div class="mt-4 flex items-center gap-2">
        <el-button v-if="hasFilters" @click="clearFilters">清除筛选</el-button>
        <el-button v-else-if="canManageDevices" type="primary" @click="openAdd">
          <Plus :size="14" class="mr-1" />
          添加设备
        </el-button>
      </div>
    </section>

    <DeviceControlDialog
      v-model="showControl"
      :device="controlDevice"
      @control="onControl"
      @edit="openEdit"
      @delete="requestDelete"
      @saved="loadAll"
    />

    <AddDeviceDialog
      v-model="showDialog"
      :rooms="roomStore.rooms"
      :device="editingDevice"
      @saved="loadAll"
    />

    <ConfirmDialog
      v-model="showDelete"
      title="删除设备"
      :message="`确定删除设备「${deleteTarget?.name || ''}」吗？该操作仅作软删除，不影响家庭数据隔离。`"
      type="danger"
      confirm-text="删除"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Cpu, Wifi, Sparkles, Home, Search, PackageOpen, X } from 'lucide-vue-next'
import { useDeviceStore } from '@/stores/device'
import { useRoomStore } from '@/stores/room'
import { useUserStore } from '@/stores/user'
import { usePermission } from '@/composables/usePermission'
import { deleteDevice } from '@/api/device'
import DeviceCard from '@/components/device/DeviceCard.vue'
import DeviceControlDialog from '@/components/device/DeviceControlDialog.vue'
import AddDeviceDialog from '@/components/device/AddDeviceDialog.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import ScenePanel from '@/components/device/ScenePanel.vue'

const deviceStore = useDeviceStore()
const roomStore = useRoomStore()
const userStore = useUserStore()
const { canManageDevices } = usePermission()

const typeOptions = [
  { label: '空调', value: 'air_conditioner' },
  { label: '灯', value: 'light' },
  { label: '扫地机器人', value: 'robot_vacuum' },
  { label: '窗帘', value: 'curtain' },
  { label: '音箱/马桶', value: 'speaker' },
  { label: '电视', value: 'tv' },
  { label: '空气净化器', value: 'air_purifier' },
  { label: '加湿器', value: 'humidifier' },
  { label: '热水器', value: 'water_heater' },
  { label: '洗衣机', value: 'washer' },
  { label: '冰箱', value: 'fridge' },
  { label: '智能门锁', value: 'door_lock' },
  { label: '空气质量检测仪', value: 'air_monitor' },
  { label: '温湿度传感器', value: 'temp_humidity_sensor' },
  { label: '室外温湿度传感器', value: 'outdoor_sensor' },
  { label: '室外气象站', value: 'weather_station' },
  { label: '智能电表', value: 'electricity_meter' },
  { label: '智能插座', value: 'smart_plug' },
  { label: '智能水表', value: 'water_meter' },
  { label: '智能燃气表', value: 'gas_meter' },
  { label: '门窗传感器', value: 'door_window_sensor' },
  { label: '人体存在传感器', value: 'presence_sensor' },
  { label: '水浸传感器', value: 'leak_sensor' },
  { label: '燃气传感器', value: 'gas_sensor' },
  { label: '烟雾传感器', value: 'smoke_sensor' },
  { label: '智能路由器', value: 'router' },
  { label: '摄像头', value: 'camera' },
]

const filterRoom = ref(null)
const filterType = ref(null)
const keyword = ref('')
const showDialog = ref(false)
const editingDevice = ref(null)
const showControl = ref(false)
const controlDeviceId = ref(null)
const showDelete = ref(false)
const deleteTarget = ref(null)

const devices = computed(() =>
  deviceStore.devices.map((device) => ({
    ...device,
    room_name: roomStore.rooms.find((room) => room.id === device.room_id)?.name || '未分配房间',
  })),
)

const controlDevice = computed(
  () => devices.value.find((device) => device.id === controlDeviceId.value) || null,
)

const filteredDevices = computed(() =>
  devices.value.filter((device) => {
    if (filterRoom.value && device.room_id !== filterRoom.value) return false
    if (filterType.value && device.type !== filterType.value) return false
    if (keyword.value) {
      const text = `${device.name}${device.brand || ''}${device.model || ''}`.toLowerCase()
      if (!text.includes(keyword.value.trim().toLowerCase())) return false
    }
    return true
  }),
)

const hasFilters = computed(() => Boolean(filterRoom.value || filterType.value || keyword.value.trim()))

const roomDeviceCount = (roomId) => devices.value.filter((device) => device.room_id === roomId).length

const clearFilters = () => {
  filterRoom.value = null
  filterType.value = null
  keyword.value = ''
}

const loadAll = async () => {
  await Promise.all([deviceStore.fetchDevices(), roomStore.fetchRooms()])
}

const onControl = async (deviceId, attributes) => {
  try {
    await deviceStore.controlDevice(deviceId, attributes)
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

const openControl = (device) => {
  controlDeviceId.value = device.id
  showControl.value = true
}

const openAdd = () => {
  editingDevice.value = null
  showDialog.value = true
}

const openEdit = (device) => {
  editingDevice.value = device
  showDialog.value = true
}

const requestDelete = (device) => {
  deleteTarget.value = device
  showDelete.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  try {
    await deleteDevice(deleteTarget.value.id)
    ElMessage.success('设备已删除')
    await loadAll()
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

onMounted(loadAll)

watch(
  () => userStore.familyId,
  () => {
    showControl.value = false
    clearFilters()
    loadAll()
  },
)
</script>

<style scoped>
.filter-panel {
  position: sticky;
  top: 0;
  z-index: 20;
  padding: 12px 14px;
  border-radius: 16px;
}

.filter-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.room-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  max-width: 100%;
  padding-bottom: 2px;
  scrollbar-width: none;
}

.room-tabs::-webkit-scrollbar {
  display: none;
}

.room-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  padding: 7px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-500);
  border: 1px solid transparent;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.room-tab:hover {
  background: rgba(255, 255, 255, 0.7);
  color: var(--ink-900);
}

.room-tab.active {
  background: #fff;
  color: var(--accent-strong);
  border-color: rgba(79, 107, 237, 0.22);
  box-shadow: 0 4px 12px rgba(79, 107, 237, 0.1);
}

.room-count {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.4;
  text-align: center;
  color: var(--ink-400);
  background: rgba(23, 28, 43, 0.06);
}

.room-tab.active .room-count {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.12);
}

.filter-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.filter-search {
  width: 220px;
}

.filter-type {
  width: 150px;
}

.filter-add {
  flex: none;
}

.filter-search :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.72);
}

.filter-result {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(23, 28, 43, 0.06);
  font-size: 12px;
  color: var(--ink-400);
}

.filter-result strong {
  color: var(--ink-700);
}

.clear-filter {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-strong);
}

.clear-filter:hover {
  text-decoration: underline;
}

.device-skeleton {
  overflow: hidden;
  border-radius: 18px;
  background: var(--surface-1);
  border: 1px solid var(--stroke);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75), var(--shadow-1);
}

.sk-media {
  aspect-ratio: 16 / 10;
  border-radius: 0;
  opacity: 0.7;
}

.sk-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
}

.sk-line {
  height: 10px;
}

.sk-line-lg {
  width: 62%;
}

.sk-line-sm {
  width: 42%;
  height: 9px;
}

.sk-line-foot {
  width: 100%;
  height: 22px;
  margin-top: 4px;
}

@media (max-width: 760px) {
  .filter-main {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-tools {
    margin-left: 0;
  }

  .filter-search {
    flex: 1;
    width: auto;
  }

  .filter-type {
    width: 132px;
  }
}

@media (max-width: 520px) {
  .filter-panel {
    padding: 10px;
  }

  .filter-tools {
    flex-wrap: wrap;
  }

  .filter-search {
    width: 100%;
    flex: none;
  }

  .filter-type {
    flex: 1;
    width: auto;
    min-width: 0;
  }
}
</style>
