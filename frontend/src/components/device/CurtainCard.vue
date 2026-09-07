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
          <span class="text-2xl font-bold text-gray-800 leading-none">{{ position }}</span>
          <span class="text-sm text-gray-400">% 开合</span>
        </div>
        <el-select
          v-model="mode"
          size="small"
          :disabled="!power || !canControlDevice"
          @change="onModeChange"
        >
          <el-option label="手动" value="manual" />
          <el-option label="定时" value="timed" />
          <el-option label="智能" value="smart" />
        </el-select>
      </div>

      <div class="flex items-center gap-3">
        <span class="text-xs text-gray-500 shrink-0">开合</span>
        <el-slider
          v-model="position"
          class="flex-1"
          :min="0"
          :max="100"
          :disabled="!power || !canControlDevice"
          @change="onPositionChange"
        />
      </div>

      <div class="flex gap-2">
        <el-button
          size="small"
          class="flex-1"
          :disabled="!power || !canControlDevice"
          @click="setPosition(0)"
        >
          全关
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          class="flex-1"
          :disabled="!power || !canControlDevice"
          @click="setPosition(100)"
        >
          全开
        </el-button>
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
const position = ref(props.device.status?.position ?? 0)
const mode = ref(props.device.status?.mode || 'manual')

watch(
  () => props.device.status,
  (status) => {
    if (!status) return
    power.value = status.power === 'on'
    position.value = status.position ?? position.value
    mode.value = status.mode || 'manual'
  },
  { deep: true },
)

const onPositionChange = (value) => emit('control', props.device.id, { position: value })
const onModeChange = (value) => emit('control', props.device.id, { mode: value })
const setPosition = (value) => emit('control', props.device.id, { position: value })
</script>