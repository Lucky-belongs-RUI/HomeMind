<template>
  <DeviceCard
    :device="device"
    @control="(id, attrs) => $emit('control', id, attrs)"
    @edit="$emit('edit', $event)"
    @delete="$emit('delete', $event)"
  >
    <div class="space-y-3">
      <!-- 空气质量检测仪 -->
      <template v-if="type === 'air_monitor'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.pm25 ?? '--' }}</span>
            <span class="text-sm text-gray-400">μg/m³ PM2.5</span>
          </div>
          <el-tag size="small" effect="light" :type="qualityTagType">{{ status.air_quality || '--' }}</el-tag>
        </div>
        <MetricGrid :items="airMetrics" />
      </template>

      <!-- 温湿度传感器 / 室外温湿度传感器 -->
      <template v-else-if="type === 'temp_humidity_sensor' || type === 'outdoor_sensor'">
        <MetricGrid :items="tempHumidityMetrics" />
        <div v-if="status.battery != null" class="flex items-center justify-between text-xs">
          <span class="text-gray-500">电池电量</span>
          <el-progress :percentage="status.battery" :stroke-width="7" class="w-28" :color="batteryColor" />
        </div>
      </template>

      <!-- 室外气象站 -->
      <template v-else-if="type === 'weather_station'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.weather || '--' }}</span>
            <span class="text-sm text-gray-400">当前天气</span>
          </div>
          <el-tag size="small" effect="light" :type="qualityTagType">{{ status.air_quality || '--' }}</el-tag>
        </div>
        <MetricGrid :items="weatherMetrics" />
      </template>

      <!-- 智能电表 -->
      <template v-else-if="type === 'electricity_meter'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.power_w ?? 0 }}</span>
            <span class="text-sm text-gray-400">W 当前功率</span>
          </div>
          <span class="text-xs text-amber-500 font-semibold">余额 {{ status.balance ?? '--' }} 元</span>
        </div>
        <MetricGrid :items="electricityMetrics" />
      </template>

      <!-- 智能插座 -->
      <template v-else-if="type === 'smart_plug'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.power_w ?? 0 }}</span>
            <span class="text-sm text-gray-400">W 负载功率</span>
          </div>
          <el-tag size="small" effect="light" :type="status.power === 'on' ? 'success' : 'info'">
            {{ status.power === 'on' ? '通电中' : '已断电' }}
          </el-tag>
        </div>
        <MetricGrid :items="plugMetrics" />
      </template>

      <!-- 智能水表 -->
      <template v-else-if="type === 'water_meter'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.monthly_usage ?? '--' }}</span>
            <span class="text-sm text-gray-400">m³ 本月用水</span>
          </div>
          <span class="text-xs text-cyan-500 font-semibold">余额 {{ status.balance ?? '--' }} 元</span>
        </div>
        <MetricGrid :items="waterMetrics" />
      </template>

      <!-- 智能燃气表 -->
      <template v-else-if="type === 'gas_meter'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.monthly_usage ?? '--' }}</span>
            <span class="text-sm text-gray-400">m³ 本月用气</span>
          </div>
          <span class="text-xs text-orange-500 font-semibold">余额 {{ status.balance ?? '--' }} 元</span>
        </div>
        <MetricGrid :items="gasMetrics" />
      </template>

      <!-- 智能路由器 -->
      <template v-else-if="type === 'router'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ status.internet_status === 'online' ? '在线' : '离线' }}</span>
            <span class="text-sm text-gray-400">外网状态</span>
          </div>
          <span class="text-xs text-gray-500">{{ status.wifi_ssid || '--' }}</span>
        </div>
        <MetricGrid :items="routerMetrics" />
      </template>

      <!-- 门窗 / 人体 / 水浸 / 燃气 / 烟雾传感器 -->
      <template v-else-if="securitySensorTypes.includes(type)">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold leading-none" :class="sensorAlert ? 'text-red-500' : 'text-gray-800'">
              {{ sensorStatusText }}
            </span>
            <span class="text-sm text-gray-400">{{ sensorStatusLabel }}</span>
          </div>
          <el-tag size="small" effect="light" :type="sensorAlert ? 'danger' : 'success'">
            {{ sensorAlert ? '告警' : '正常' }}
          </el-tag>
        </div>
        <div v-if="status.battery != null" class="flex items-center justify-between text-xs">
          <span class="text-gray-500">电池电量</span>
          <el-progress :percentage="status.battery" :stroke-width="7" class="w-28" :color="batteryColor" />
        </div>
      </template>
      <div class="pt-2 border-t border-white/40 flex items-center justify-end">
        <el-button size="small" :icon="Pencil" :disabled="!canControlDevice" @click="showEdit = true">
          编辑数据
        </el-button>
      </div>

      <EnvironmentEditDialog v-model="showEdit" :device="device" @saved="$emit('saved', $event)" />
    </div>
  </DeviceCard>
</template>

<script setup>
import { ref, computed } from 'vue'
import DeviceCard from './DeviceCard.vue'
import MetricGrid from './MetricGrid.vue'
import EnvironmentEditDialog from './EnvironmentEditDialog.vue'
import { Pencil } from 'lucide-vue-next'
import { usePermission } from '@/composables/usePermission'

const props = defineProps({
  device: { type: Object, required: true },
})

defineEmits(['control', 'edit', 'delete', 'saved'])

const type = computed(() => props.device.type)
const status = computed(() => props.device.status || {})
const securitySensorTypes = ['door_window_sensor', 'presence_sensor', 'leak_sensor', 'gas_sensor', 'smoke_sensor']
const { canControlDevice } = usePermission()
const showEdit = ref(false)

const qualityTagType = computed(() => {
  const label = status.value.air_quality || ''
  if (label.includes('优')) return 'success'
  if (label.includes('良')) return 'warning'
  return 'danger'
})

const tempHumidityMetrics = computed(() => [
  { label: '温度', value: status.value.temperature, unit: '°C' },
  { label: '湿度', value: status.value.humidity, unit: '%' },
])

const airMetrics = computed(() => [
  { label: 'PM10', value: status.value.pm10, unit: 'μg/m³' },
  { label: 'CO₂', value: status.value.co2, unit: 'ppm' },
  { label: '甲醛 HCHO', value: status.value.hcho, unit: 'mg/m³' },
  { label: 'TVOC', value: status.value.tvoc, unit: 'mg/m³' },
  { label: 'CO', value: status.value.co, unit: 'ppm' },
  { label: '电量', value: status.value.battery, unit: '%' },
])

const weatherMetrics = computed(() => [
  { label: '温度', value: status.value.temperature, unit: '°C' },
  { label: '湿度', value: status.value.humidity, unit: '%' },
  { label: 'UV 指数', value: status.value.uv_index, unit: '' },
  { label: '气压', value: status.value.pressure, unit: 'hPa' },
  { label: 'PM2.5', value: status.value.pm25, unit: 'μg/m³' },
  { label: '空气质量', value: status.value.air_quality, unit: '' },
])

const electricityMetrics = computed(() => [
  { label: '电压', value: status.value.voltage, unit: 'V' },
  { label: '电流', value: status.value.current, unit: 'A' },
  { label: '今日用电', value: status.value.daily_energy_kwh, unit: 'kWh' },
  { label: '本月用电', value: status.value.monthly_energy_kwh, unit: 'kWh' },
  { label: '电费余额', value: status.value.balance, unit: '元' },
])

const plugMetrics = computed(() => [
  { label: '累计电量', value: status.value.energy_kwh, unit: 'kWh' },
  { label: '电压', value: status.value.voltage, unit: 'V' },
  { label: '电流', value: status.value.current, unit: 'A' },
])

const waterMetrics = computed(() => [
  { label: '流量', value: status.value.flow_rate, unit: 'm³/h' },
  { label: '今日用水', value: status.value.daily_usage, unit: 'm³' },
  { label: '水费余额', value: status.value.balance, unit: '元' },
  { label: '漏水告警', value: status.value.leak_alarm ? '有' : '无', unit: '' },
])

const gasMetrics = computed(() => [
  { label: '流量', value: status.value.flow_rate, unit: 'm³/h' },
  { label: '燃气余额', value: status.value.balance, unit: '元' },
  { label: '泄漏告警', value: status.value.gas_alarm ? '有' : '无', unit: '' },
])

const routerMetrics = computed(() => [
  { label: '信号强度', value: status.value.signal_strength, unit: '%' },
  { label: '在线设备', value: status.value.device_count, unit: '台' },
  { label: '带宽', value: status.value.bandwidth_mbps, unit: 'Mbps' },
])

const sensorAlert = computed(() => {
  if (type.value === 'door_window_sensor') return status.value.status === 'open'
  if (type.value === 'leak_sensor') return Boolean(status.value.leak)
  if (type.value === 'gas_sensor') return Boolean(status.value.gas_leak)
  if (type.value === 'smoke_sensor') return Boolean(status.value.smoke || status.value.alarm)
  return false
})

const sensorStatusText = computed(() => {
  if (type.value === 'door_window_sensor') return status.value.status === 'open' ? '开启' : '关闭'
  if (type.value === 'presence_sensor') return status.value.presence ? '有人' : '无人'
  if (type.value === 'leak_sensor') return status.value.leak ? '漏水' : '正常'
  if (type.value === 'gas_sensor') return status.value.gas_leak ? '泄漏' : '正常'
  if (type.value === 'smoke_sensor') return status.value.smoke || status.value.alarm ? '告警' : '正常'
  return '--'
})

const sensorStatusLabel = computed(() => {
  const labels = {
    door_window_sensor: '门窗状态',
    presence_sensor: '人体存在',
    leak_sensor: '水浸状态',
    gas_sensor: '燃气状态',
    smoke_sensor: '烟雾状态',
  }
  return labels[type.value] || '状态'
})

const batteryColor = computed(() => {
  const battery = status.value.battery ?? 100
  if (battery <= 20) return '#ef4444'
  if (battery <= 50) return '#f59e0b'
  return '#10b981'
})
</script>