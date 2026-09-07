<template>
  <el-dialog
    :model-value="modelValue"
    :title="`编辑数据 - ${device?.name || '设备'}`"
    width="560px"
    align-center
    append-to-body
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form :model="form" label-position="top">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
        <el-form-item v-for="field in fields" :key="field.key" :label="fieldLabel(field)">
          <el-input-number
            v-if="field.type === 'number'"
            v-model="form[field.key]"
            :min="field.min ?? 0"
            :max="field.max ?? 999999"
            :step="field.step ?? 1"
            controls-position="right"
            class="w-full"
          />
          <el-input v-else-if="field.type === 'text'" v-model="form[field.key]" maxlength="40" />
          <el-select v-else-if="field.type === 'select'" v-model="form[field.key]" class="w-full">
            <el-option
              v-for="option in field.options || []"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-switch v-else-if="field.type === 'switch'" v-model="form[field.key]" />
        </el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { updateDeviceStatus } from '@/api/device'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  device: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'saved'])

const submitting = ref(false)
const form = reactive({})

const airQualityOptions = [
  { label: '优', value: '优' },
  { label: '良', value: '良' },
  { label: '轻度污染', value: '轻度污染' },
  { label: '中度污染', value: '中度污染' },
  { label: '重度污染', value: '重度污染' },
]

const weatherOptions = [
  { label: '晴', value: '晴' },
  { label: '多云', value: '多云' },
  { label: '阴', value: '阴' },
  { label: '小雨', value: '小雨' },
  { label: '中雨', value: '中雨' },
  { label: '大雨', value: '大雨' },
  { label: '雷阵雨', value: '雷阵雨' },
  { label: '雪', value: '雪' },
  { label: '雾', value: '雾' },
  { label: '霾', value: '霾' },
]

const FIELD_CONFIGS = {
  air_monitor: [
    { key: 'pm25', label: 'PM2.5', type: 'number', unit: 'μg/m³', min: 0, max: 1000 },
    { key: 'pm10', label: 'PM10', type: 'number', unit: 'μg/m³', min: 0, max: 2000 },
    { key: 'co2', label: 'CO₂ 浓度', type: 'number', unit: 'ppm', min: 0, max: 5000 },
    { key: 'hcho', label: '甲醛 HCHO', type: 'number', unit: 'mg/m³', min: 0, max: 5, step: 0.01 },
    { key: 'tvoc', label: 'TVOC', type: 'number', unit: 'mg/m³', min: 0, max: 10, step: 0.01 },
    { key: 'co', label: 'CO 浓度', type: 'number', unit: 'ppm', min: 0, max: 100, step: 0.1 },
    { key: 'air_quality', label: '空气质量', type: 'select', options: airQualityOptions },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  temp_humidity_sensor: [
    { key: 'temperature', label: '温度', type: 'number', unit: '°C', min: -40, max: 60, step: 0.5 },
    { key: 'humidity', label: '湿度', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  outdoor_sensor: [
    { key: 'temperature', label: '室外温度', type: 'number', unit: '°C', min: -40, max: 60, step: 0.5 },
    { key: 'humidity', label: '室外湿度', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  weather_station: [
    { key: 'weather', label: '当前天气', type: 'select', options: weatherOptions },
    { key: 'temperature', label: '室外温度', type: 'number', unit: '°C', min: -40, max: 60, step: 0.5 },
    { key: 'humidity', label: '室外湿度', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'uv_index', label: 'UV 指数', type: 'number', min: 0, max: 11 },
    { key: 'pressure', label: '气压', type: 'number', unit: 'hPa', min: 900, max: 1100 },
    { key: 'pm25', label: 'PM2.5', type: 'number', unit: 'μg/m³', min: 0, max: 1000 },
    { key: 'air_quality', label: '空气质量', type: 'select', options: airQualityOptions },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  electricity_meter: [
    { key: 'power_w', label: '当前功率', type: 'number', unit: 'W', min: 0, max: 20000 },
    { key: 'voltage', label: '电压', type: 'number', unit: 'V', min: 0, max: 300, step: 0.1 },
    { key: 'current', label: '电流', type: 'number', unit: 'A', min: 0, max: 100, step: 0.1 },
    { key: 'daily_energy_kwh', label: '今日用电', type: 'number', unit: 'kWh', min: 0, max: 1000, step: 0.1 },
    { key: 'monthly_energy_kwh', label: '本月用电', type: 'number', unit: 'kWh', min: 0, max: 100000, step: 0.1 },
    { key: 'balance', label: '电费余额', type: 'number', unit: '元', min: 0, max: 100000, step: 0.1 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  smart_plug: [
    { key: 'power', label: '通断状态', type: 'select', options: [{ label: '通电', value: 'on' }, { label: '断电', value: 'off' }] },
    { key: 'power_w', label: '负载功率', type: 'number', unit: 'W', min: 0, max: 5000 },
    { key: 'energy_kwh', label: '累计电量', type: 'number', unit: 'kWh', min: 0, max: 100000, step: 0.1 },
    { key: 'voltage', label: '电压', type: 'number', unit: 'V', min: 0, max: 300, step: 0.1 },
    { key: 'current', label: '电流', type: 'number', unit: 'A', min: 0, max: 50, step: 0.1 },
  ],
  water_meter: [
    { key: 'flow_rate', label: '实时流量', type: 'number', unit: 'm³/h', min: 0, max: 100, step: 0.1 },
    { key: 'daily_usage', label: '今日用水', type: 'number', unit: 'm³', min: 0, max: 100, step: 0.1 },
    { key: 'monthly_usage', label: '本月用水', type: 'number', unit: 'm³', min: 0, max: 1000, step: 0.1 },
    { key: 'balance', label: '水费余额', type: 'number', unit: '元', min: 0, max: 100000, step: 0.1 },
    { key: 'leak_alarm', label: '漏水告警', type: 'switch' },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  gas_meter: [
    { key: 'flow_rate', label: '燃气流量', type: 'number', unit: 'm³/h', min: 0, max: 100, step: 0.1 },
    { key: 'monthly_usage', label: '本月用气', type: 'number', unit: 'm³', min: 0, max: 1000, step: 0.1 },
    { key: 'balance', label: '燃气费余额', type: 'number', unit: '元', min: 0, max: 100000, step: 0.1 },
    { key: 'gas_alarm', label: '燃气泄漏告警', type: 'switch' },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  router: [
    { key: 'internet_status', label: '外网状态', type: 'select', options: [{ label: '在线', value: 'online' }, { label: '离线', value: 'offline' }] },
    { key: 'wifi_ssid', label: 'WiFi 名称', type: 'text' },
    { key: 'signal_strength', label: '信号强度', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'device_count', label: '在线设备', type: 'number', unit: '台', min: 0, max: 200 },
    { key: 'bandwidth_mbps', label: '带宽', type: 'number', unit: 'Mbps', min: 0, max: 10000 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  door_window_sensor: [
    { key: 'status', label: '门窗状态', type: 'select', options: [{ label: '关闭', value: 'closed' }, { label: '开启', value: 'open' }] },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  presence_sensor: [
    { key: 'presence', label: '人体存在', type: 'switch' },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  leak_sensor: [
    { key: 'leak', label: '漏水状态', type: 'switch' },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  gas_sensor: [
    { key: 'gas_leak', label: '燃气泄漏', type: 'switch' },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
  smoke_sensor: [
    { key: 'smoke', label: '烟雾状态', type: 'switch' },
    { key: 'alarm', label: '火灾告警', type: 'switch' },
    { key: 'battery', label: '电量', type: 'number', unit: '%', min: 0, max: 100 },
    { key: 'online', label: '在线状态', type: 'switch' },
  ],
}

const fields = computed(() => FIELD_CONFIGS[props.device?.type] || [])

const fieldLabel = (field) => (field.unit ? `${field.label}（${field.unit}）` : field.label)

const defaultFor = (field) => {
  if (field.type === 'number') return 0
  if (field.type === 'select') return field.options?.[0]?.value ?? ''
  if (field.type === 'switch') return false
  return ''
}

const initForm = () => {
  const status = props.device?.status || {}
  for (const key of Object.keys(form)) delete form[key]
  fields.value.forEach((field) => {
    const value = status[field.key]
    form[field.key] = value === undefined || value === null ? defaultFor(field) : value
  })
}

watch(
  () => [props.modelValue, props.device],
  () => {
    if (props.modelValue && props.device) initForm()
  },
  { immediate: true },
)

const onSubmit = async () => {
  if (!props.device) return
  submitting.value = true
  try {
    const attributes = {}
    fields.value.forEach((field) => {
      attributes[field.key] = form[field.key]
    })
    await updateDeviceStatus(props.device.id, attributes)
    ElMessage.success('设备数据已保存')
    emit('update:modelValue', false)
    emit('saved')
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    submitting.value = false
  }
}
</script>
