<template>
  <div class="glass rounded-xl overflow-hidden shadow-sm ring-1 ring-white/40 hover:shadow-md hover:ring-blue-200/60 transition-all self-start">
    <div class="relative group cursor-pointer bg-white" @click="expanded = !expanded">
      <div class="w-full aspect-[3/2]">
        <DeviceImage :type="device.type" :is-on="isOn" :locked="device.status?.locked" :recording="device.status?.recording" />
      </div>

      <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/65 via-black/30 to-transparent px-3 pb-3 pt-8 pointer-events-none">
        <h3 class="text-sm font-semibold text-white drop-shadow-sm leading-tight truncate">{{ device.name }}</h3>
        <div class="flex items-center gap-1.5 mt-0.5">
          <span class="text-[11px] text-white/80 truncate">{{ modelLabel || typeLabel }}</span>
          <template v-if="attrText">
            <span class="text-white/40">·</span>
            <span class="text-[11px] text-white/70 truncate">{{ attrText }}</span>
          </template>
        </div>
      </div>

      <div class="absolute top-2 right-2 pointer-events-none">
        <span
          class="px-2 py-0.5 rounded-full text-[10px] font-medium"
          :class="isOn ? 'bg-white/90 text-emerald-600' : 'bg-black/35 text-white/80'"
        >
          {{ isOn ? '运行中' : '已关闭' }}
        </span>
      </div>

      <div
        class="absolute inset-x-0 bottom-0 p-2 translate-y-full group-hover:translate-y-0 transition-transform duration-200"
      >
        <button
          class="w-full py-1.5 rounded-lg text-xs font-medium transition-all flex items-center justify-center gap-1.5"
          :class="
            isOn
              ? 'bg-white/95 text-blue-700 hover:bg-white shadow-sm'
              : 'bg-white/85 text-gray-500 hover:bg-white hover:text-gray-700'
          "
          v-if="hasPowerControl"
          type="button"
          :disabled="!canControlDevice"
          :title="canControlDevice ? (isOn ? '关闭' : '开启') : '访客仅可查看'"
          @click.stop="togglePower"
        >
          <Power :size="12" />
          {{ isOn ? '关闭' : '开启' }}
        </button>
        <span
          v-else
          class="w-full py-1.5 rounded-lg text-xs font-medium text-white/90 bg-black/25 flex items-center justify-center gap-1.5"
        >
          {{ isOn ? '在线' : '离线' }}
        </span>
      </div>

      <div
        v-if="canManageDevices"
        class="absolute top-2 left-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <button
          class="p-1.5 rounded-lg bg-black/35 text-white hover:bg-black/60 transition-colors"
          type="button"
          title="编辑"
          @click.stop="$emit('edit', device)"
        >
          <Pencil :size="12" />
        </button>
        <button
          class="p-1.5 rounded-lg bg-black/35 text-white hover:bg-red-500/80 transition-colors"
          type="button"
          title="删除"
          @click.stop="$emit('delete', device)"
        >
          <Trash2 :size="12" />
        </button>
      </div>

      <div class="absolute top-2 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <span class="text-[10px] text-white/85 bg-black/30 rounded-full px-2 py-0.5 whitespace-nowrap">
          {{ expanded ? '点击收起控制' : '点击展开控制' }}
        </span>
      </div>
    </div>

    <div v-if="expanded" class="border-t border-white/40 bg-white/70 p-3">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Power, Pencil, Trash2 } from 'lucide-vue-next'
import { usePermission } from '@/composables/usePermission'
import DeviceImage from './DeviceImage.vue'

const props = defineProps({
  device: { type: Object, required: true },
})

const emit = defineEmits(['control', 'edit', 'delete'])

const { canControlDevice, canManageDevices } = usePermission()
const expanded = ref(false)

const TYPE_LABELS = {
  air_conditioner: '空调',
  light: '灯光',
  robot_vacuum: '扫地机器人',
  curtain: '窗帘',
  speaker: '智能音箱',
  tv: '电视',
  air_purifier: '空气净化器',
  humidifier: '加湿器',
  water_heater: '热水器',
  washer: '洗衣机',
  fridge: '冰箱',
  door_lock: '智能门锁',
  camera: '摄像头',
  air_monitor: '空气检测仪',
  temp_humidity_sensor: '温湿度传感器',
  outdoor_sensor: '室外温湿度传感器',
  weather_station: '室外气象站',
  electricity_meter: '智能电表',
  smart_plug: '智能插座',
  water_meter: '智能水表',
  gas_meter: '智能燃气表',
  door_window_sensor: '门窗传感器',
  presence_sensor: '人体存在传感器',
  leak_sensor: '水浸传感器',
  gas_sensor: '燃气传感器',
  smoke_sensor: '烟雾传感器',
  router: '智能路由器',
}

const isOn = computed(() => props.device.status?.power === 'on' || props.device.status?.online === true)
const hasPowerControl = computed(() => 'power' in (props.device.status || {}))
const typeLabel = computed(() => TYPE_LABELS[props.device.type] || '智能设备')
const modelLabel = computed(() =>
  [props.device.brand, props.device.model].filter(Boolean).join(' '),
)

const attrText = computed(() => {
  const status = props.device.status || {}
  if (props.device.type === 'air_conditioner') return `${status.temperature ?? 26}°C`
  if (props.device.type === 'light') return `${status.brightness ?? 0}% 亮度`
  if (props.device.type === 'curtain') return `${status.position ?? 0}% 开合`
  if (props.device.type === 'robot_vacuum') return `${status.battery ?? 0}% 电量`
  if (props.device.type === 'speaker') return status.volume ? `${status.volume}% 音量` : ''
  if (props.device.type === 'tv') return status.volume ? `${status.volume}% 音量` : ''
  if (props.device.type === 'air_purifier') return status.pm25 ? `${status.pm25} μg/m³` : ''
  if (props.device.type === 'humidifier') return `${status.target_humidity ?? 55}% 湿度`
  if (props.device.type === 'water_heater') return `${status.temperature ?? 45}°C`
  if (props.device.type === 'washer') return status.status || ''
  if (props.device.type === 'fridge') return `${status.temperature ?? 4}°C`
  if (props.device.type === 'door_lock') return status.locked ? '已上锁' : '未上锁'
  if (props.device.type === 'camera') return status.recording ? '录制中' : '待机'
  if (props.device.type === 'air_monitor') return `${status.pm25 ?? '--'} μg/m³ · ${status.air_quality ?? '--'}`
  if (props.device.type === 'temp_humidity_sensor' || props.device.type === 'outdoor_sensor') return `${status.temperature ?? '--'}°C · ${status.humidity ?? '--'}%`
  if (props.device.type === 'weather_station') return `${status.weather || '--'} · ${status.temperature ?? '--'}°C`
  if (props.device.type === 'electricity_meter') return `${status.power_w ?? 0}W · 余额${status.balance ?? '--'}元`
  if (props.device.type === 'smart_plug') return `${status.power_w ?? 0}W`
  if (props.device.type === 'water_meter') return `${status.monthly_usage ?? '--'}m³ · 余额${status.balance ?? '--'}元`
  if (props.device.type === 'gas_meter') return `${status.monthly_usage ?? '--'}m³ · 余额${status.balance ?? '--'}元`
  if (props.device.type === 'door_window_sensor') return status.status === 'open' ? '门窗开启' : '门窗关闭'
  if (props.device.type === 'presence_sensor') return status.presence ? '有人' : '无人'
  if (props.device.type === 'leak_sensor') return status.leak ? '漏水告警' : '正常'
  if (props.device.type === 'gas_sensor') return status.gas_leak ? '燃气泄漏' : '正常'
  if (props.device.type === 'smoke_sensor') return status.smoke || status.alarm ? '烟雾告警' : '正常'
  if (props.device.type === 'router') return status.internet_status === 'online' ? '网络在线' : '网络离线'
  return ''
})

const togglePower = () => {
  if (!canControlDevice.value) return
  emit('control', props.device.id, { power: isOn.value ? 'off' : 'on' })
}
</script>