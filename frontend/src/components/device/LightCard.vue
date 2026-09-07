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
          <span class="text-2xl font-bold text-gray-800 leading-none">{{ brightness }}</span>
          <span class="text-sm text-gray-400">% 亮度</span>
        </div>
        <el-radio-group
          v-model="mode"
          size="small"
          :disabled="!power || !canControlDevice"
          @change="onModeChange"
        >
          <el-radio-button value="normal">正常</el-radio-button>
          <el-radio-button value="reading">阅读</el-radio-button>
          <el-radio-button value="night">夜灯</el-radio-button>
        </el-radio-group>
      </div>

      <div class="flex items-center gap-3">
        <span class="text-xs text-gray-500 shrink-0">亮度</span>
        <el-slider
          v-model="brightness"
          class="flex-1"
          :min="0"
          :max="100"
          :disabled="!power || !canControlDevice"
          @change="onBrightnessChange"
        />
      </div>

      <div class="flex items-center justify-between gap-2">
        <span class="text-xs text-gray-500 shrink-0">颜色</span>
        <div class="flex items-center gap-2">
          <input
            v-model="color"
            type="color"
            class="w-8 h-8 rounded-lg cursor-pointer"
            :disabled="!power || !canControlDevice"
            @change="onColorChange"
          />
          <span class="text-xs text-gray-400">{{ color }}</span>
        </div>
      </div>
    </div>
  </DeviceCard>
</template>

<script setup>
import { ref, watch } from 'vue'
import { usePermission } from '@/composables/usePermission'
import DeviceCard from './DeviceCard.vue'

const props = defineProps({
  device: { type: Object, required: true },
})

const emit = defineEmits(['control', 'edit', 'delete'])
const { canControlDevice } = usePermission()

const power = ref(props.device.status?.power === 'on')
const brightness = ref(props.device.status?.brightness ?? 80)
const color = ref(props.device.status?.color || '#FFFFFF')
const mode = ref(props.device.status?.mode || 'normal')

watch(
  () => props.device.status,
  (status) => {
    if (!status) return
    power.value = status.power === 'on'
    brightness.value = status.brightness ?? brightness.value
    color.value = status.color || color.value
    mode.value = status.mode || 'normal'
  },
  { deep: true },
)

const onBrightnessChange = (value) => emit('control', props.device.id, { brightness: value })
const onColorChange = (event) => emit('control', props.device.id, { color: event.target.value })
const onModeChange = (value) => emit('control', props.device.id, { mode: value })
</script>