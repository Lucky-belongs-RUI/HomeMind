<template>
  <div class="page device-view">
    <div class="stat-row">
      <div class="stat-block">
        <span class="stat-icon bg-blue-500/10 text-blue-500"><Cpu :size="18" /></span>
        <div>
          <div class="stat-value">{{ devices.length }}</div>
          <div class="stat-label">设备总数</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-emerald-500/10 text-emerald-500"><Wifi :size="18" /></span>
        <div>
          <div class="stat-value">{{ deviceStore.onlineCount }}</div>
          <div class="stat-label">在线设备</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-amber-500/10 text-amber-500"><Sparkles :size="18" /></span>
        <div>
          <div class="stat-value">{{ deviceStore.cleaningCount }}</div>
          <div class="stat-label">清扫中</div>
        </div>
      </div>
      <div class="stat-block">
        <span class="stat-icon bg-violet-500/10 text-violet-500"><Home :size="18" /></span>
        <div>
          <div class="stat-value">{{ roomStore.rooms.length }}</div>
          <div class="stat-label">房间数</div>
        </div>
      </div>
    </div>

    <ScenePanel @executed="loadAll" />

    <div class="filter-bar">
      <el-select v-model="filterRoom" placeholder="按房间筛选" clearable style="width: 160px">
        <el-option v-for="room in roomStore.rooms" :key="room.id" :label="room.name" :value="room.id" />
      </el-select>
      <el-select v-model="filterType" placeholder="按类型筛选" clearable style="width: 160px">
        <el-option label="空调" value="air_conditioner" />
        <el-option label="灯" value="light" />
        <el-option label="扫地机器人" value="robot_vacuum" />
        <el-option label="窗帘" value="curtain" />
        <el-option label="音箱/马桶" value="speaker" />
        <el-option label="电视" value="tv" />
        <el-option label="空气净化器" value="air_purifier" />
        <el-option label="加湿器" value="humidifier" />
        <el-option label="热水器" value="water_heater" />
        <el-option label="洗衣机" value="washer" />
        <el-option label="冰箱" value="fridge" />
        <el-option label="智能门锁" value="door_lock" />
        <el-option label="空气质量检测仪" value="air_monitor" />
        <el-option label="温湿度传感器" value="temp_humidity_sensor" />
        <el-option label="室外温湿度传感器" value="outdoor_sensor" />
        <el-option label="室外气象站" value="weather_station" />
        <el-option label="智能电表" value="electricity_meter" />
        <el-option label="智能插座" value="smart_plug" />
        <el-option label="智能水表" value="water_meter" />
        <el-option label="智能燃气表" value="gas_meter" />
        <el-option label="门窗传感器" value="door_window_sensor" />
        <el-option label="人体存在传感器" value="presence_sensor" />
        <el-option label="水浸传感器" value="leak_sensor" />
        <el-option label="燃气传感器" value="gas_sensor" />
        <el-option label="烟雾传感器" value="smoke_sensor" />
        <el-option label="智能路由器" value="router" />
        <el-option label="摄像头" value="camera" />
      </el-select>
      <el-input
        v-model="keyword"
        placeholder="搜索设备名称或品牌"
        clearable
        style="width: 240px"
        class="filter-search"
      >
        <template #prefix><Search :size="15" class="text-gray-400" /></template>
      </el-input>
      <el-button v-if="canManageDevices" type="primary" class="ml-auto" @click="openAdd">
        <Plus :size="14" class="mr-1" />
        添加设备
      </el-button>
    </div>

    <div v-loading="deviceStore.loading" class="device-grid" v-if="filteredDevices.length">
      <DeviceCardFactory
        v-for="device in filteredDevices"
        :key="device.id"
        :device="device"
        @control="onControl"
        @edit="openEdit"
        @delete="requestDelete"
        @saved="loadAll"
      />
    </div>
    <div
      v-else-if="!deviceStore.loading"
      class="section-panel flex flex-col items-center justify-center py-14 text-gray-400"
    >
      <PackageOpen :size="34" class="mb-3 text-gray-300" />
      <p class="text-sm">当前家庭暂无匹配的设备</p>
    </div>

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
import { Plus, Cpu, Wifi, Sparkles, Home, Search, PackageOpen } from 'lucide-vue-next'
import { useDeviceStore } from '@/stores/device'
import { useRoomStore } from '@/stores/room'
import { useUserStore } from '@/stores/user'
import { usePermission } from '@/composables/usePermission'
import { deleteDevice } from '@/api/device'
import DeviceCardFactory from '@/components/device/DeviceCardFactory.vue'
import AddDeviceDialog from '@/components/device/AddDeviceDialog.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import ScenePanel from '@/components/device/ScenePanel.vue'

const deviceStore = useDeviceStore()
const roomStore = useRoomStore()
const userStore = useUserStore()
const { canManageDevices } = usePermission()


const filterRoom = ref(null)
const filterType = ref(null)
const keyword = ref('')
const showDialog = ref(false)
const editingDevice = ref(null)
const showDelete = ref(false)
const deleteTarget = ref(null)

const devices = computed(() =>
  deviceStore.devices.map((device) => ({
    ...device,
    room_name: roomStore.rooms.find((room) => room.id === device.room_id)?.name || '未分配房间',
  })),
)

const filteredDevices = computed(() =>
  devices.value.filter((device) => {
    if (filterRoom.value && device.room_id !== filterRoom.value) return false
    if (filterType.value && device.type !== filterType.value) return false
    if (keyword.value) {
      const text = `${device.name}${device.brand || ''}${device.model || ''}`.toLowerCase()
      if (!text.includes(keyword.value.toLowerCase())) return false
    }
    return true
  }),
)

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
    filterRoom.value = null
    filterType.value = null
    keyword.value = ''
    loadAll()
  },
)
</script>

<style scoped>
.filter-search :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.6);
}
</style>
