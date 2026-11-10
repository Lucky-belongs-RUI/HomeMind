<template>
  <article
    class="device-card group"
    :class="{ 'is-offline': !online }"
    role="button"
    tabindex="0"
    :aria-label="`${device.name}，${typeLabel}，${statusText}。打开设备设置`"
    @click="$emit('open', device)"
    @keydown.enter.prevent="$emit('open', device)"
    @keydown.space.prevent="$emit('open', device)"
  >
    <div class="device-media" :class="toneClass">
      <div class="device-art">
        <DeviceImage
          :type="device.type"
          :is-on="isOn"
          :locked="device.status?.locked"
          :recording="device.status?.recording"
        />
      </div>
    </div>

    <div class="device-body">
      <div class="device-title-row">
        <h3 class="device-name">{{ device.name }}</h3>
        <span v-if="metricText" class="device-metric" :title="metricText">{{ metricText }}</span>
      </div>
      <p class="device-room">{{ device.room_name || '未分配房间' }}</p>
    </div>

    <div class="device-foot">
      <span class="device-online" :class="online ? 'online' : 'offline'">
        <i></i>
        {{ online ? '在线' : '离线' }}
      </span>
      <span v-if="hasPowerControl" class="power-wrap" @click.stop @keydown.stop>
        <el-switch
          class="device-power"
          :model-value="powerOn"
          :disabled="!canControlDevice"
          size="small"
          :aria-label="powerOn ? '关闭设备' : '开启设备'"
          @update:model-value="togglePower"
        />
      </span>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { usePermission } from '@/composables/usePermission'
import DeviceImage from './DeviceImage.vue'
import {
  typeLabelOf,
  toneOf,
  isOnline,
  hasPower,
  isPoweredOn,
  isDeviceOn,
  statusTextOf,
  metricTextOf,
} from './deviceMeta'

const props = defineProps({
  device: { type: Object, required: true },
})

const emit = defineEmits(['open', 'control'])
const { canControlDevice } = usePermission()

const online = computed(() => isOnline(props.device.status))
const isOn = computed(() => isDeviceOn(props.device.status))
const powerOn = computed(() => isPoweredOn(props.device.status))
const hasPowerControl = computed(() => hasPower(props.device.status))
const typeLabel = computed(() => typeLabelOf(props.device.type))
const toneClass = computed(() => toneOf(props.device.type))
const statusText = computed(() => statusTextOf(props.device.status))
const metricText = computed(() => metricTextOf(props.device.type, props.device.status))

const togglePower = (value) => {
  if (!canControlDevice.value) return
  emit('control', props.device.id, { power: value ? 'on' : 'off' })
}
</script>

<style scoped>
.device-card {
  display: flex;
  flex-direction: column;
  align-self: start;
  overflow: hidden;
  border-radius: 18px;
  background: var(--surface-1);
  border: 1px solid var(--stroke);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75), var(--shadow-1);
  cursor: pointer;
  user-select: none;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.device-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.9);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8), var(--shadow-2);
}

.device-card:focus-visible {
  outline: 2px solid rgba(79, 107, 237, 0.72);
  outline-offset: 2px;
}

.device-card.is-offline .device-art {
  opacity: 0.72;
}

.device-media {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 16 / 10;
  padding: 14px 20px;
  overflow: hidden;
}

.device-art {
  width: 100%;
  height: 100%;
  transition: transform 0.25s ease;
}

.device-card:hover .device-art {
  transform: scale(1.02);
}

.tone-climate {
  background: radial-gradient(120% 120% at 20% 0%, rgba(79, 107, 237, 0.18), rgba(255, 255, 255, 0.4) 62%);
}

.tone-warm {
  background: radial-gradient(120% 120% at 20% 0%, rgba(217, 154, 78, 0.2), rgba(255, 255, 255, 0.42) 62%);
}

.tone-sage {
  background: radial-gradient(120% 120% at 20% 0%, rgba(111, 155, 131, 0.2), rgba(255, 255, 255, 0.42) 62%);
}

.tone-amber {
  background: radial-gradient(120% 120% at 20% 0%, rgba(217, 154, 78, 0.24), rgba(255, 255, 255, 0.4) 62%);
}

.tone-slate {
  background: radial-gradient(120% 120% at 20% 0%, rgba(95, 103, 122, 0.16), rgba(255, 255, 255, 0.42) 62%);
}

.tone-sky {
  background: radial-gradient(120% 120% at 20% 0%, rgba(56, 189, 248, 0.17), rgba(255, 255, 255, 0.42) 62%);
}

.tone-sand {
  background: radial-gradient(120% 120% at 20% 0%, rgba(180, 160, 130, 0.2), rgba(255, 255, 255, 0.42) 62%);
}

.device-body {
  padding: 11px 14px 10px;
}

.device-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.device-name {
  margin: 0;
  min-width: 0;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.3;
  color: var(--ink-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-metric {
  flex: none;
  max-width: 46%;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-700);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.device-room {
  margin: 3px 0 0;
  font-size: 11px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 14px;
  padding: 9px 0 11px;
  border-top: 1px solid rgba(23, 28, 43, 0.06);
}

.device-online {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--ink-400);
}

.device-online i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.14);
}

.device-online.offline i {
  background: #d99a4e;
  box-shadow: 0 0 0 3px rgba(217, 154, 78, 0.16);
}

.power-wrap {
  display: inline-flex;
  align-items: center;
  cursor: default;
}

.device-power {
  --el-switch-on-color: #4f6bed;
}
</style>
