<template>
  <DeviceCard
    :device="device"
    @control="(id, attrs) => $emit('control', id, attrs)"
    @edit="$emit('edit', $event)"
    @delete="$emit('delete', $event)"
  >
    <div class="space-y-3">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-baseline gap-1">
          <span class="text-2xl font-bold text-gray-800 leading-none">{{ battery }}</span>
          <span class="text-sm text-gray-400">% 电量</span>
        </div>
        <el-tag :type="cleaning ? 'success' : 'info'" size="small" effect="light">
          {{ cleaning ? '清扫中' : '待命' }}
        </el-tag>
      </div>

      <el-progress :percentage="battery" :stroke-width="8" :color="batteryColor" />

      <div class="flex items-center justify-between gap-2 text-xs">
        <span class="text-gray-500 shrink-0">模式</span>
        <el-select
          v-model="cleaningMode"
          size="small"
          class="flex-1"
          :disabled="!power || !canControlDevice"
          @change="onModeChange"
        >
          <el-option label="智能" value="auto" />
          <el-option label="定点" value="spot" />
          <el-option label="沿边" value="edge" />
        </el-select>
        <el-button
          type="primary"
          plain
          size="small"
          :disabled="!power || !canControlDevice"
          @click="toggleCleaning"
        >
          {{ cleaning ? '暂停' : '开始清扫' }}
        </el-button>
      </div>

      <div class="flex items-center justify-between text-xs text-gray-400">
        <span>尘盒 {{ dustBin }}%</span>
        <span class="font-mono">x {{ position.x.toFixed(2) }} · y {{ position.y.toFixed(2) }}</span>
      </div>
    </div>
  </DeviceCard>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { usePermission } from '@/composables/usePermission'
import DeviceCard from './DeviceCard.vue'

const props = defineProps({
  device: { type: Object, required: true },
})

const emit = defineEmits(['control', 'edit', 'delete'])
const { canControlDevice } = usePermission()

const power = ref(props.device.status?.power === 'on')
const battery = ref(props.device.status?.battery ?? 100)
const cleaning = ref(props.device.status?.status === 'cleaning')
const cleaningMode = ref(props.device.status?.cleaning_mode || 'auto')
const dustBin = ref(props.device.status?.dust_bin ?? 0)
const position = ref({ ...(props.device.status?.position || { x: 0, y: 0 }) })

const batteryColor = computed(() => {
  if (battery.value <= 20) return '#ef4444'
  if (battery.value <= 50) return '#f59e0b'
  return '#10b981'
})

watch(
  () => props.device.status,
  (status) => {
    if (!status) return
    power.value = status.power === 'on'
    battery.value = status.battery ?? battery.value
    cleaning.value = status.status === 'cleaning'
    cleaningMode.value = status.cleaning_mode || 'auto'
    dustBin.value = status.dust_bin ?? dustBin.value
    position.value = { ...(status.position || position.value) }
  },
  { deep: true },
)

const onModeChange = (value) => emit('control', props.device.id, { cleaning_mode: value })

const toggleCleaning = () => {
  const attributes = cleaning.value
    ? { status: 'idle' }
    : { status: 'cleaning', power: 'on' }
  emit('control', props.device.id, attributes)
}
</script>