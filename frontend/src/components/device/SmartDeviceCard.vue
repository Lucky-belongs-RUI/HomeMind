<template>
  <DeviceCard
    :device="device"
    @control="(id, attrs) => $emit('control', id, attrs)"
    @edit="$emit('edit', $event)"
    @delete="$emit('delete', $event)"
  >
    <div class="space-y-3">
      <!-- 电视 -->
      <template v-if="type === 'tv'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ volume }}</span>
            <span class="text-sm text-gray-400">% 音量</span>
          </div>
          <el-tag size="small" effect="light" :type="power ? 'success' : 'info'">
            {{ power ? '播放中' : '已关机' }}
          </el-tag>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-500 shrink-0">音量</span>
          <el-slider
            v-model="volume"
            class="flex-1"
            :min="0"
            :max="100"
            :disabled="!power || !canControlDevice"
            @change="onAttr('volume', $event)"
          />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">频道</span>
          <el-input-number
            v-model="channel"
            class="flex-1"
            :min="1"
            :max="200"
            size="small"
            controls-position="right"
            :disabled="!power || !canControlDevice"
            @change="onAttr('channel', $event)"
          />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">信号源</span>
          <el-select
            v-model="inputSource"
            size="small"
            class="flex-1"
            :disabled="!power || !canControlDevice"
            @change="onAttr('input_source', $event)"
          >
            <el-option label="HDMI 1" value="hdmi1" />
            <el-option label="HDMI 2" value="hdmi2" />
            <el-option label="有线电视" value="cable" />
            <el-option label="网络视频" value="network" />
          </el-select>
        </div>
      </template>

      <!-- 空气净化器 -->
      <template v-else-if="type === 'air_purifier'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ pm25 }}</span>
            <span class="text-sm text-gray-400">μg/m³</span>
          </div>
          <el-tag size="small" effect="light" :type="power ? (pm25 <= 50 ? 'success' : 'warning') : 'info'">
            {{ power ? (pm25 <= 50 ? '空气良好' : '建议净化') : '已关闭' }}
          </el-tag>
        </div>
        <div class="flex items-center gap-2 text-xs">
          <span class="text-gray-500 shrink-0">滤芯寿命</span>
          <el-progress :percentage="filterLife" :stroke-width="8" class="flex-1" :color="filterColor" />
        </div>
        <el-radio-group
          v-model="mode"
          size="small"
          :disabled="!power || !canControlDevice"
          @change="onAttr('mode', $event)"
        >
          <el-radio-button value="auto">智能</el-radio-button>
          <el-radio-button value="manual">手动</el-radio-button>
          <el-radio-button value="sleep">睡眠</el-radio-button>
        </el-radio-group>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">风量</span>
          <el-select
            v-model="fanSpeed"
            size="small"
            class="flex-1"
            :disabled="!power || !canControlDevice"
            @change="onAttr('fan_speed', $event)"
          >
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="自动" value="auto" />
          </el-select>
        </div>
      </template>

      <!-- 加湿器 -->
      <template v-else-if="type === 'humidifier'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ targetHumidity }}</span>
            <span class="text-sm text-gray-400">% 目标湿度</span>
          </div>
          <div class="flex items-center gap-1.5 text-xs text-gray-500">
            水位
            <el-progress :percentage="waterLevel" :stroke-width="6" class="w-20" color="#38bdf8" />
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-500 shrink-0">湿度</span>
          <el-slider
            v-model="targetHumidity"
            class="flex-1"
            :min="30"
            :max="80"
            :disabled="!power || !canControlDevice"
            @change="onAttr('target_humidity', $event)"
          />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">模式</span>
          <el-select
            v-model="mode"
            size="small"
            class="flex-1"
            :disabled="!power || !canControlDevice"
            @change="onAttr('mode', $event)"
          >
            <el-option label="智能" value="auto" />
            <el-option label="手动" value="manual" />
            <el-option label="睡眠" value="sleep" />
          </el-select>
        </div>
      </template>

      <!-- 热水器 -->
      <template v-else-if="type === 'water_heater'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold text-gray-800 leading-none">{{ temperature }}</span>
            <span class="text-sm text-gray-400">℃</span>
          </div>
          <el-tag size="small" effect="light" :type="power ? 'warning' : 'info'">
            {{ power ? '加热中' : '已关闭' }}
          </el-tag>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-500 shrink-0">水温</span>
          <el-slider
            v-model="temperature"
            class="flex-1"
            :min="30"
            :max="75"
            :disabled="!power || !canControlDevice"
            @change="onAttr('temperature', $event)"
          />
        </div>
        <el-radio-group
          v-model="mode"
          size="small"
          :disabled="!power || !canControlDevice"
          @change="onAttr('mode', $event)"
        >
          <el-radio-button value="standard">标准</el-radio-button>
          <el-radio-button value="eco">节能</el-radio-button>
          <el-radio-button value="turbo">速热</el-radio-button>
        </el-radio-group>
      </template>

      <!-- 洗衣机 -->
      <template v-else-if="type === 'washer'">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1">
            <span class="text-lg font-bold text-gray-800 leading-none">{{ washerModeText }}</span>
          </div>
          <el-tag size="small" effect="light" :type="washerTagType">
            {{ washerStatusText }}
          </el-tag>
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">模式</span>
          <el-select
            v-model="mode"
            size="small"
            class="flex-1"
            :disabled="!power || !canControlDevice"
            @change="onAttr('mode', $event)"
          >
            <el-option label="标准洗" value="standard" />
            <el-option label="快速洗" value="quick" />
            <el-option label="轻柔洗" value="delicate" />
            <el-option label="强力洗" value="heavy" />
          </el-select>
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">水温</span>
          <el-select
            v-model="waterTemp"
            size="small"
            class="flex-1"
            :disabled="!power || !canControlDevice"
            @change="onAttr('water_temp', $event)"
          >
            <el-option label="冷水" value="cold" />
            <el-option label="温水" value="warm" />
            <el-option label="热水" value="hot" />
          </el-select>
          <el-button
            type="primary"
            plain
            size="small"
            :disabled="!power || !canControlDevice"
            @click="toggleWash"
          >
            {{ washerRunning ? '暂停' : '开始' }}
          </el-button>
        </div>
      </template>

      <!-- 冰箱 -->
      <template v-else-if="type === 'fridge'">
        <div class="grid grid-cols-2 gap-2">
          <div class="rounded-lg bg-sky-50/80 px-3 py-2">
            <div class="text-[11px] text-gray-500">冷藏</div>
            <div class="flex items-baseline gap-0.5">
              <span class="text-2xl font-bold text-gray-800 leading-none">{{ temperature }}</span>
              <span class="text-xs text-gray-400">℃</span>
            </div>
          </div>
          <div class="rounded-lg bg-indigo-50/80 px-3 py-2">
            <div class="text-[11px] text-gray-500">冷冻</div>
            <div class="flex items-baseline gap-0.5">
              <span class="text-2xl font-bold text-gray-800 leading-none">{{ freezerTemperature }}</span>
              <span class="text-xs text-gray-400">℃</span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-500 shrink-0">冷藏</span>
          <el-slider
            v-model="temperature"
            class="flex-1"
            :min="1"
            :max="10"
            :disabled="!power || !canControlDevice"
            @change="onAttr('temperature', $event)"
          />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">模式</span>
          <el-select
            v-model="mode"
            size="small"
            class="flex-1"
            :disabled="!power || !canControlDevice"
            @change="onAttr('mode', $event)"
          >
            <el-option label="智能" value="smart" />
            <el-option label="速冷" value="turbo" />
            <el-option label="假日" value="vacation" />
          </el-select>
        </div>
      </template>

      <!-- 智能门锁 -->
      <template v-else-if="type === 'door_lock'">
        <div class="flex items-center gap-2 text-xs">
          <span class="text-gray-500 shrink-0">电量</span>
          <el-progress :percentage="battery" :stroke-width="8" class="flex-1" :color="batteryColor" />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">门锁状态</span>
          <span class="flex items-center gap-1.5">
            {{ locked ? '已上锁' : '未上锁' }}
            <el-switch v-model="locked" size="small" :disabled="!canControlDevice" @change="onAttr('locked', $event)" />
          </span>
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">自动上锁</span>
          <el-switch v-model="autoLock" size="small" :disabled="!canControlDevice" @change="onAttr('auto_lock', $event)" />
        </div>
      </template>

      <!-- 摄像头 -->
      <template v-else-if="type === 'camera'">
        <div class="flex items-center justify-between gap-2">
          <el-tag size="small" effect="light" :type="recording ? 'danger' : (power ? 'success' : 'info')">
            {{ recording ? '录制中' : (power ? '待机' : '已关闭') }}
          </el-tag>
          <span class="text-[11px] text-gray-400">{{ motionDetection ? '移动侦测已开启' : '移动侦测已关闭' }}</span>
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">录制</span>
          <el-switch v-model="recording" size="small" :disabled="!power || !canControlDevice" @change="onAttr('recording', $event)" />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">移动侦测</span>
          <el-switch v-model="motionDetection" size="small" :disabled="!power || !canControlDevice" @change="onAttr('motion_detection', $event)" />
        </div>
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="text-gray-500 shrink-0">夜视</span>
          <el-switch v-model="nightVision" size="small" :disabled="!power || !canControlDevice" @change="onAttr('night_vision', $event)" />
        </div>
      </template>
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

const type = computed(() => props.device.type)
const power = ref(props.device.status?.power === 'on')

// 电视
const volume = ref(props.device.status?.volume ?? 20)
const channel = ref(props.device.status?.channel ?? 1)
const inputSource = ref(props.device.status?.input_source || 'hdmi1')

// 空气净化器
const pm25 = ref(props.device.status?.pm25 ?? 35)
const filterLife = ref(props.device.status?.filter_life ?? 80)
const mode = ref(props.device.status?.mode || 'auto')
const fanSpeed = ref(props.device.status?.fan_speed || 'auto')

// 加湿器
const targetHumidity = ref(props.device.status?.target_humidity ?? 55)
const waterLevel = ref(props.device.status?.water_level ?? 80)

// 热水器
const temperature = ref(props.device.status?.temperature ?? 45)

// 洗衣机
const washerStatus = ref(props.device.status?.status || 'idle')
const washerStatusMode = ref(props.device.status?.mode || 'standard')
const waterTemp = ref(props.device.status?.water_temp || 'cold')

// 冰箱
const freezerTemperature = ref(props.device.status?.freezer_temperature ?? -18)

// 智能门锁
const locked = ref(Boolean(props.device.status?.locked))
const autoLock = ref(Boolean(props.device.status?.auto_lock))
const battery = ref(props.device.status?.battery ?? 100)

// 摄像头
const recording = ref(Boolean(props.device.status?.recording))
const motionDetection = ref(Boolean(props.device.status?.motion_detection))
const nightVision = ref(Boolean(props.device.status?.night_vision))

const washerRunning = computed(() => washerStatus.value === 'running')
const washerModeText = computed(() => {
  const labels = { standard: '标准洗', quick: '快速洗', delicate: '轻柔洗', heavy: '强力洗' }
  return labels[washerStatusMode.value] || washerStatusMode.value
})
const washerStatusText = computed(() => {
  if (washerStatus.value === 'running') return '洗涤中'
  if (washerStatus.value === 'finished') return '已完成'
  if (washerStatus.value === 'paused') return '已暂停'
  return '待机'
})
const washerTagType = computed(() => {
  if (washerStatus.value === 'running') return 'warning'
  if (washerStatus.value === 'finished') return 'success'
  return 'info'
})
const filterColor = computed(() => {
  if (filterLife.value <= 20) return '#ef4444'
  if (filterLife.value <= 50) return '#f59e0b'
  return '#10b981'
})
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
    volume.value = status.volume ?? volume.value
    channel.value = status.channel ?? channel.value
    inputSource.value = status.input_source || inputSource.value
    pm25.value = status.pm25 ?? pm25.value
    filterLife.value = status.filter_life ?? filterLife.value
    mode.value = status.mode || mode.value
    fanSpeed.value = status.fan_speed || fanSpeed.value
    targetHumidity.value = status.target_humidity ?? targetHumidity.value
    waterLevel.value = status.water_level ?? waterLevel.value
    temperature.value = status.temperature ?? temperature.value
    washerStatus.value = status.status || washerStatus.value
    washerStatusMode.value = status.mode || washerStatusMode.value
    waterTemp.value = status.water_temp || waterTemp.value
    freezerTemperature.value = status.freezer_temperature ?? freezerTemperature.value
    locked.value = Boolean(status.locked)
    autoLock.value = Boolean(status.auto_lock)
    battery.value = status.battery ?? battery.value
    recording.value = Boolean(status.recording)
    motionDetection.value = Boolean(status.motion_detection)
    nightVision.value = Boolean(status.night_vision)
  },
  { deep: true },
)

const onAttr = (key, value) => emit('control', props.device.id, { [key]: value })

const toggleWash = () => {
  const next = washerRunning.value ? 'paused' : 'running'
  washerStatus.value = next
  emit('control', props.device.id, { status: next, power: 'on' })
}
</script>