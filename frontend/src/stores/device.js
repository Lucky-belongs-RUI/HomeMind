import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getDevices, updateDeviceStatus } from '@/api/device'

export const useDeviceStore = defineStore('device', () => {
  const devices = ref([])
  const loading = ref(false)

  const onlineCount = computed(
    () => devices.value.filter((d) => d.status?.power === 'on' || d.status?.online === true).length,
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
