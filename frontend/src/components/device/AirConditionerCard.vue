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
          <span class="text-2xl font-bold text-gray-800 leading-none">{{ temperature }}</span>
          <span class="text-sm text-gray-400">℃</span>
        </div>
        <el-radio-group
          v-model="mode"
          size="small"
          :disabled="!power || !canControlDevice"
          @change="onModeChange"
        >
          <el-radio-button value="cool">制冷</el-radio-button>
          <el-radio-button value="heat">制热</el-radio-button>
          <el-radio-button value="fan">送风</el-radio-button>
          <el-radio-button value="auto">自动</el-radio-button>
        </el-radio-group>
      </div>

      <div class="flex items-center gap-2">
        <el-button
          circle
          size="small"
          :disabled="!power || !canControlDevice"
          @click="adjustTemp(-1)"
        >
          <Minus :size="14" />
        </el-button>
        <el-slider
          v-model="temperature"
          class="flex-1"
          :min="16"
          :max="30"
          :disabled="!power || !canControlDevice"
          @change="onTempChange"
        />
        <el-button
          circle
          size="small"
          :disabled="!power || !canControlDevice"
          @click="adjustTemp(1)"
        >
          <Plus :size="14" />
        </el-button>
      </div>

      <div class="flex items-center justify-between gap-2 text-xs">
        <span class="text-gray-500 shrink-0">风量</span>
        <el-select
          v-model="fanSpeed"
          size="small"
          class="flex-1"
          :disabled="!power || !canControlDevice"
          @change="onFanChange"
        >
          <el-option label="低" value="low" />
          <el-option label="中" value="medium" />
          <el-option label="高" value="high" />
          <el-option label="自动" value="auto" />
        </el-select>
        <span class="flex items-center gap-1.5 text-gray-500 shrink-0">
          摆风
          <el-switch v-model="swing" size="small" :disabled="!power || !canControlDevice" @change="onSwingChange" />
        </span>
      </div>
    </div>
  </DeviceCard>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Minus, Plus } from 'lucide-vue-next'
import { usePermission } from '@/composables/usePermission'
import DeviceCard from './DeviceCard.vue'

const props = defineProps({
  device: { type: Object, required: true },
})

const emit = defineEmits(['control', 'edit', 'delete'])
const { canControlDevice } = usePermission()

const power = ref(props.device.status?.power === 'on')
const temperature = ref(props.device.status?.temperature ?? 26)
const mode = ref(props.device.status?.mode || 'cool')
const fanSpeed = ref(props.device.status?.fan_speed || 'auto')
const swing = ref(Boolean(props.device.status?.swing))

watch(
  () => props.device.status,
  (status) => {
    if (!status) return
    power.value = status.power === 'on'
    temperature.value = status.temperature ?? temperature.value
    mode.value = status.mode || 'cool'
    fanSpeed.value = status.fan_speed || 'auto'
    swing.value = Boolean(status.swing)
  },
  { deep: true },
)

const adjustTemp = (delta) => {
  const next = temperature.value + delta
  if (next < 16 || next > 30) return
  temperature.value = next
  emit('control', props.device.id, { temperature: next })
}

const onTempChange = (value) => emit('control', props.device.id, { temperature: value })
const onModeChange = (value) => emit('control', props.device.id, { mode: value })
const onFanChange = (value) => emit('control', props.device.id, { fan_speed: value })
const onSwingChange = (value) => emit('control', props.device.id, { swing: value })
</script>