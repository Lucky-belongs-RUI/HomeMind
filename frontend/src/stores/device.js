import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getDevices, updateDeviceStatus } from '@/api/device'

export const useDeviceStore = defineStore('device', () => {
  const devices = ref([])
  const loading = ref(false)

  // “在线设备”统计的是连接状态，不能把 power=on 的设备算进来：
  // 可控制设备默认没有 online 字段（视为在线），传感器离线时 online=false。
  const onlineCount = computed(
    () => devices.value.filter((d) => d.status?.online !== false).length,
  )
  const cleaningCount = computed(
    () =>
      devices.value.filter(
        (d) => d.type === 'robot_vacuum' && d.status?.status === 'cleaning',
      ).length,
  )

  const fetchDevices = async () => {
    loading.value = true
    try {
      devices.value = await getDevices()
    } finally {
      loading.value = false
    }
  }

  // WebSocket 推送设备状态变更时调用
  const updateDeviceFromWS = (data) => {
    const device = devices.value.find((d) => d.id === data.device_id)
    if (device) {
      device.status = data.status
    }
  }

  // 手动控制设备：优先本地更新，WebSocket 到达后再同步
  const controlDevice = async (deviceId, attributes) => {
    const updated = await updateDeviceStatus(deviceId, attributes)
    const device = devices.value.find((d) => d.id === deviceId)
    if (device) device.status = updated.status
    return updated
  }

  return {
    devices,
    loading,
    onlineCount,
    cleaningCount,
    fetchDevices,
    updateDeviceFromWS,
    controlDevice,
  }
})
