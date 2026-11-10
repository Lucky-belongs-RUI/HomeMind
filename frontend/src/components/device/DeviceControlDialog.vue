<template>
  <el-dialog
    :model-value="modelValue"
    width="min(820px, 94vw)"
    align-center
    append-to-body
    class="device-control-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="dd-header">
        <div class="dd-head-main">
          <span class="dd-type">
            <component :is="typeIcon" :size="13" />
            {{ typeLabel }}
          </span>
          <h2 class="dd-title">{{ device?.name || '设备设置' }}</h2>
          <p class="dd-sub">{{ subtitle }}</p>
        </div>
        <div v-if="device" class="dd-head-side">
          <span class="dd-state" :class="online ? 'online' : 'offline'">
            <i></i>
            {{ online ? '在线' : '离线' }}
          </span>
          <el-switch
            v-if="hasPowerControl"
            v-model="powerOn"
            :disabled="!canControlDevice"
            :aria-label="powerOn ? '关闭设备' : '开启设备'"
          />
        </div>
      </div>
    </template>

    <div v-if="device" class="dd-body">
      <div class="dd-art" :class="toneClass">
        <DeviceImage
          :type="device.type"
          :is-on="isDeviceOn(status)"
          :locked="status.locked"
          :recording="status.recording"
        />
      </div>

      <div class="dd-panel">
        <div class="dd-panel-head">
          <h3>{{ isEnvironment ? '数据设置' : '设备设置' }}</h3>
          <span>{{ isEnvironment ? '修改后点击保存生效' : '调整后立即同步到设备' }}</span>
        </div>

        <template v-if="isEnvironment">
          <div v-if="envFields.length" class="dd-fields">
            <div v-for="field in envFields" :key="field.key" class="dd-field">
              <label>{{ fieldLabelOf(field) }}</label>
              <el-input-number
                v-if="field.type === 'number'"
                v-model="envForm[field.key]"
                :min="field.min ?? 0"
                :max="field.max ?? 999999"
                :step="field.step ?? 1"
                :disabled="!canControlDevice"
                controls-position="right"
                class="w-full"
              />
              <el-input
                v-else-if="field.type === 'text'"
                v-model="envForm[field.key]"
                maxlength="40"
                :disabled="!canControlDevice"
              />
              <el-select
                v-else-if="field.type === 'select'"
                v-model="envForm[field.key]"
                :disabled="!canControlDevice"
                class="w-full"
              >
                <el-option
                  v-for="option in field.options || []"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-switch
                v-else-if="field.type === 'switch'"
                v-model="envForm[field.key]"
                :disabled="!canControlDevice"
              />
            </div>
          </div>
          <p v-else class="dd-empty">该设备暂无可编辑的数据字段</p>
        </template>

        <!-- 空调 -->
        <template v-else-if="device.type === 'air_conditioner'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.temperature }}</span>
            <span class="dd-unit">℃</span>
            <el-tag size="small" effect="light" :type="powerOn ? 'success' : 'info'">
              {{ powerOn ? '运行中' : '已关闭' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-radio-group
              v-model="state.mode"
              size="small"
              class="dd-radio"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-radio-button value="cool">制冷</el-radio-button>
              <el-radio-button value="heat">制热</el-radio-button>
              <el-radio-button value="fan">送风</el-radio-button>
              <el-radio-button value="auto">自动</el-radio-button>
            </el-radio-group>
          </div>
          <div class="dd-row">
            <span class="dd-label">温度</span>
            <div class="dd-control">
              <el-button circle size="small" :disabled="!canControlDevice" @click="adjustTemp(-1)">
                <Minus :size="14" />
              </el-button>
              <el-slider
                v-model="state.temperature"
                class="flex-1"
                :min="16"
                :max="30"
                :disabled="!canControlDevice"
                @change="(value) => update('temperature', value)"
              />
              <el-button circle size="small" :disabled="!canControlDevice" @click="adjustTemp(1)">
                <Plus :size="14" />
              </el-button>
            </div>
          </div>
          <div class="dd-row">
            <span class="dd-label">风量</span>
            <el-select
              v-model="state.fan_speed"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('fan_speed', value)"
            >
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
              <el-option label="自动" value="auto" />
            </el-select>
          </div>
          <div class="dd-row">
            <span class="dd-label">摆风</span>
            <el-switch
              v-model="state.swing"
              :disabled="!canControlDevice"
              @change="(value) => update('swing', value)"
            />
          </div>
        </template>

        <!-- 灯光 -->
        <template v-else-if="device.type === 'light'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.brightness }}</span>
            <span class="dd-unit">% 亮度</span>
            <el-tag size="small" effect="light" :type="powerOn ? 'warning' : 'info'">
              {{ powerOn ? '已开启' : '已关闭' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-radio-group
              v-model="state.mode"
              size="small"
              class="dd-radio"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-radio-button value="normal">正常</el-radio-button>
              <el-radio-button value="reading">阅读</el-radio-button>
              <el-radio-button value="night">夜灯</el-radio-button>
            </el-radio-group>
          </div>
          <div class="dd-row">
            <span class="dd-label">亮度</span>
            <el-slider
              v-model="state.brightness"
              class="flex-1"
              :min="0"
              :max="100"
              :disabled="!canControlDevice"
              @change="(value) => update('brightness', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">颜色</span>
            <div class="dd-control">
              <input
                v-model="state.color"
                type="color"
                class="dd-color"
                :disabled="!canControlDevice"
                @change="update('color', state.color)"
              />
              <span class="dd-color-value">{{ state.color }}</span>
            </div>
          </div>
        </template>

        <!-- 扫地机器人 -->
        <template v-else-if="device.type === 'robot_vacuum'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.battery }}</span>
            <span class="dd-unit">% 电量</span>
            <el-tag size="small" effect="light" :type="vacuumRunning ? 'success' : 'info'">
              {{ vacuumRunning ? '清扫中' : '待命' }}
            </el-tag>
          </div>
          <el-progress :percentage="state.battery" :stroke-width="8" :color="batteryColor" />
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-select
              v-model="state.cleaning_mode"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('cleaning_mode', value)"
            >
              <el-option label="智能" value="auto" />
              <el-option label="定点" value="spot" />
              <el-option label="沿边" value="edge" />
            </el-select>
          </div>
          <div class="dd-row">
            <span class="dd-label">清扫</span>
            <div class="dd-control">
              <el-button
                type="primary"
                plain
                size="small"
                :disabled="!canControlDevice"
                @click="toggleVacuum"
              >
                {{ vacuumRunning ? '暂停清扫' : '开始清扫' }}
              </el-button>
              <span class="dd-note">尘盒 {{ state.dust_bin }}%</span>
            </div>
          </div>
        </template>

        <!-- 窗帘 -->
        <template v-else-if="device.type === 'curtain'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.position }}</span>
            <span class="dd-unit">% 开合</span>
          </div>
          <div class="dd-row">
            <span class="dd-label">开合</span>
            <el-slider
              v-model="state.position"
              class="flex-1"
              :min="0"
              :max="100"
              :disabled="!canControlDevice"
              @change="(value) => update('position', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-select
              v-model="state.mode"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-option label="手动" value="manual" />
              <el-option label="定时" value="timed" />
              <el-option label="智能" value="smart" />
            </el-select>
          </div>
          <div class="dd-row">
            <span class="dd-label">快捷</span>
            <div class="dd-control">
              <el-button size="small" :disabled="!canControlDevice" @click="setPosition(0)">全关</el-button>
              <el-button size="small" type="primary" plain :disabled="!canControlDevice" @click="setPosition(100)">
                全开
              </el-button>
            </div>
          </div>
        </template>

        <!-- 智能音箱 -->
        <template v-else-if="device.type === 'speaker'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.volume }}</span>
            <span class="dd-unit">% 音量</span>
            <el-tag size="small" effect="light" :type="state.playing ? 'success' : 'info'">
              {{ state.playing ? '播放中' : '已暂停' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">音量</span>
            <el-slider
              v-model="state.volume"
              class="flex-1"
              :min="0"
              :max="100"
              :disabled="!canControlDevice"
              @change="(value) => update('volume', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">播放</span>
            <el-switch
              v-model="state.playing"
              :disabled="!canControlDevice"
              @change="(value) => update('playing', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">音源</span>
            <el-select
              v-model="state.source"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('source', value)"
            >
              <el-option label="本地" value="local" />
              <el-option label="蓝牙" value="bluetooth" />
              <el-option label="线路输入" value="line_in" />
            </el-select>
          </div>
        </template>

        <!-- 电视 -->
        <template v-else-if="device.type === 'tv'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.volume }}</span>
            <span class="dd-unit">% 音量</span>
            <el-tag size="small" effect="light" :type="powerOn ? 'success' : 'info'">
              {{ powerOn ? '播放中' : '已关机' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">音量</span>
            <el-slider
              v-model="state.volume"
              class="flex-1"
              :min="0"
              :max="100"
              :disabled="!canControlDevice"
              @change="(value) => update('volume', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">频道</span>
            <el-input-number
              v-model="state.channel"
              :min="1"
              :max="200"
              size="small"
              controls-position="right"
              :disabled="!canControlDevice"
              @change="(value) => update('channel', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">信号源</span>
            <el-select
              v-model="state.input_source"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('input_source', value)"
            >
              <el-option label="HDMI 1" value="hdmi1" />
              <el-option label="HDMI 2" value="hdmi2" />
              <el-option label="有线电视" value="cable" />
              <el-option label="网络视频" value="network" />
            </el-select>
          </div>
        </template>

        <!-- 空气净化器 -->
        <template v-else-if="device.type === 'air_purifier'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.pm25 }}</span>
            <span class="dd-unit">μg/m³</span>
            <el-tag size="small" effect="light" :type="state.pm25 <= 50 ? 'success' : 'warning'">
              {{ state.pm25 <= 50 ? '空气良好' : '建议净化' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">滤芯</span>
            <div class="dd-control">
              <el-progress :percentage="state.filter_life" :stroke-width="8" class="flex-1" :color="filterColor" />
              <span class="dd-note">{{ state.filter_life }}%</span>
            </div>
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-radio-group
              v-model="state.mode"
              size="small"
              class="dd-radio"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-radio-button value="auto">智能</el-radio-button>
              <el-radio-button value="manual">手动</el-radio-button>
              <el-radio-button value="sleep">睡眠</el-radio-button>
            </el-radio-group>
          </div>
          <div class="dd-row">
            <span class="dd-label">风量</span>
            <el-select
              v-model="state.fan_speed"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('fan_speed', value)"
            >
              <el-option label="低" value="low" />
              <el-option label="中" value="medium" />
              <el-option label="高" value="high" />
              <el-option label="自动" value="auto" />
            </el-select>
          </div>
        </template>

        <!-- 加湿器 -->
        <template v-else-if="device.type === 'humidifier'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.target_humidity }}</span>
            <span class="dd-unit">% 目标湿度</span>
          </div>
          <div class="dd-row">
            <span class="dd-label">水位</span>
            <div class="dd-control">
              <el-progress :percentage="state.water_level" :stroke-width="8" class="flex-1" color="#38bdf8" />
              <span class="dd-note">{{ state.water_level }}%</span>
            </div>
          </div>
          <div class="dd-row">
            <span class="dd-label">湿度</span>
            <el-slider
              v-model="state.target_humidity"
              class="flex-1"
              :min="30"
              :max="80"
              :disabled="!canControlDevice"
              @change="(value) => update('target_humidity', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-select
              v-model="state.mode"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-option label="智能" value="auto" />
              <el-option label="手动" value="manual" />
              <el-option label="睡眠" value="sleep" />
            </el-select>
          </div>
        </template>

        <!-- 热水器 -->
        <template v-else-if="device.type === 'water_heater'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.temperature }}</span>
            <span class="dd-unit">℃</span>
            <el-tag size="small" effect="light" :type="powerOn ? 'warning' : 'info'">
              {{ powerOn ? '加热中' : '已关闭' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">水温</span>
            <el-slider
              v-model="state.temperature"
              class="flex-1"
              :min="30"
              :max="75"
              :disabled="!canControlDevice"
              @change="(value) => update('temperature', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-radio-group
              v-model="state.mode"
              size="small"
              class="dd-radio"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-radio-button value="standard">标准</el-radio-button>
              <el-radio-button value="eco">节能</el-radio-button>
              <el-radio-button value="turbo">速热</el-radio-button>
            </el-radio-group>
          </div>
        </template>

        <!-- 洗衣机 -->
        <template v-else-if="device.type === 'washer'">
          <div class="dd-headline">
            <span class="dd-big">{{ washerModeText }}</span>
            <el-tag size="small" effect="light" :type="washerTagType">{{ washerStatusText }}</el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-select
              v-model="state.mode"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-option label="标准洗" value="standard" />
              <el-option label="快速洗" value="quick" />
              <el-option label="轻柔洗" value="delicate" />
              <el-option label="强力洗" value="heavy" />
            </el-select>
          </div>
          <div class="dd-row">
            <span class="dd-label">水温</span>
            <el-select
              v-model="state.water_temp"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('water_temp', value)"
            >
              <el-option label="冷水" value="cold" />
              <el-option label="温水" value="warm" />
              <el-option label="热水" value="hot" />
            </el-select>
          </div>
          <div class="dd-row">
            <span class="dd-label">运行</span>
            <el-button
              type="primary"
              plain
              size="small"
              :disabled="!canControlDevice"
              @click="toggleWasher"
            >
              {{ washerRunning ? '暂停洗涤' : '开始洗涤' }}
            </el-button>
          </div>
        </template>

        <!-- 冰箱 -->
        <template v-else-if="device.type === 'fridge'">
          <div class="dd-readouts">
            <div class="dd-readout">
              <span>冷藏</span>
              <strong>{{ state.temperature }}℃</strong>
            </div>
            <div class="dd-readout">
              <span>冷冻</span>
              <strong>{{ state.freezer_temperature }}℃</strong>
            </div>
          </div>
          <div class="dd-row">
            <span class="dd-label">冷藏</span>
            <el-slider
              v-model="state.temperature"
              class="flex-1"
              :min="1"
              :max="10"
              :disabled="!canControlDevice"
              @change="(value) => update('temperature', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">冷冻</span>
            <el-input-number
              v-model="state.freezer_temperature"
              :min="-24"
              :max="-10"
              size="small"
              controls-position="right"
              :disabled="!canControlDevice"
              @change="(value) => update('freezer_temperature', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">模式</span>
            <el-select
              v-model="state.mode"
              size="small"
              :disabled="!canControlDevice"
              @change="(value) => update('mode', value)"
            >
              <el-option label="智能" value="smart" />
              <el-option label="速冷" value="turbo" />
              <el-option label="假日" value="vacation" />
            </el-select>
          </div>
        </template>

        <!-- 智能门锁 -->
        <template v-else-if="device.type === 'door_lock'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.locked ? '已上锁' : '未上锁' }}</span>
            <el-tag size="small" effect="light" :type="state.locked ? 'success' : 'warning'">
              {{ state.locked ? '安全' : '请注意' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">电量</span>
            <div class="dd-control">
              <el-progress :percentage="state.battery" :stroke-width="8" class="flex-1" :color="batteryColor" />
              <span class="dd-note">{{ state.battery }}%</span>
            </div>
          </div>
          <div class="dd-row">
            <span class="dd-label">门锁</span>
            <div class="dd-control">
              <span class="dd-note">{{ state.locked ? '上锁' : '解锁' }}</span>
              <el-switch
                v-model="state.locked"
                :disabled="!canControlDevice"
                @change="(value) => update('locked', value)"
              />
            </div>
          </div>
          <div class="dd-row">
            <span class="dd-label">自动上锁</span>
            <el-switch
              v-model="state.auto_lock"
              :disabled="!canControlDevice"
              @change="(value) => update('auto_lock', value)"
            />
          </div>
        </template>

        <!-- 摄像头 -->
        <template v-else-if="device.type === 'camera'">
          <div class="dd-headline">
            <span class="dd-big">{{ state.recording ? '录制中' : '待机' }}</span>
            <el-tag size="small" effect="light" :type="state.recording ? 'danger' : 'success'">
              {{ state.recording ? '正在录像' : '监控中' }}
            </el-tag>
          </div>
          <div class="dd-row">
            <span class="dd-label">录制</span>
            <el-switch
              v-model="state.recording"
              :disabled="!canControlDevice"
              @change="(value) => update('recording', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">移动侦测</span>
            <el-switch
              v-model="state.motion_detection"
              :disabled="!canControlDevice"
              @change="(value) => update('motion_detection', value)"
            />
          </div>
          <div class="dd-row">
            <span class="dd-label">夜视</span>
            <el-switch
              v-model="state.night_vision"
              :disabled="!canControlDevice"
              @change="(value) => update('night_vision', value)"
            />
          </div>
        </template>

        <p v-else class="dd-empty">该设备暂无可调参数</p>
      </div>
    </div>

    <template #footer>
      <div class="dd-footer">
        <div class="dd-footer-manage">
          <el-button v-if="canManageDevices" @click="onEdit">
            <Pencil :size="13" class="mr-1" />
            编辑信息
          </el-button>
          <el-button v-if="canManageDevices" type="danger" plain @click="onDelete">
            <Trash2 :size="13" class="mr-1" />
            删除设备
          </el-button>
        </div>
        <div class="dd-footer-actions">
          <span v-if="!canControlDevice" class="dd-readonly">访客仅可查看</span>
          <el-button
            v-if="isEnvironment"
            type="primary"
            :loading="saving"
            :disabled="!canControlDevice || !envFields.length"
            @click="saveEnvironment"
          >
            保存数据
          </el-button>
          <el-button v-else @click="close">完成</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Minus, Plus, Pencil, Trash2 } from 'lucide-vue-next'
import { updateDeviceStatus } from '@/api/device'
import { usePermission } from '@/composables/usePermission'
import DeviceImage from './DeviceImage.vue'
import {
  typeLabelOf,
  typeIconOf,
  toneOf,
  isOnline,
  hasPower,
  isDeviceOn,
  modelLabelOf,
} from './deviceMeta'
import { ENVIRONMENT_FIELDS, fieldLabelOf, defaultValueOf } from './environmentFields'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  device: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'control', 'edit', 'delete', 'saved'])

const { canControlDevice, canManageDevices } = usePermission()

const CONTROLLABLE_TYPES = new Set([
  'air_conditioner',
  'light',
  'robot_vacuum',
  'curtain',
  'speaker',
  'tv',
  'air_purifier',
  'humidifier',
  'water_heater',
  'washer',
  'fridge',
  'door_lock',
  'camera',
])

const status = computed(() => props.device?.status || {})
const online = computed(() => isOnline(status.value))
const hasPowerControl = computed(() => hasPower(status.value))
const typeLabel = computed(() => typeLabelOf(props.device?.type))
const typeIcon = computed(() => typeIconOf(props.device?.type))
const toneClass = computed(() => toneOf(props.device?.type))
const isEnvironment = computed(() => Boolean(props.device) && !CONTROLLABLE_TYPES.has(props.device.type))
const subtitle = computed(() => {
  if (!props.device) return ''
  const model = modelLabelOf(props.device)
  return [props.device.room_name || '未分配房间', model].filter(Boolean).join(' · ')
})

const state = reactive({ power: 'off' })
const envForm = reactive({})
const saving = ref(false)

const MODE_FALLBACK = {
  air_conditioner: 'cool',
  light: 'normal',
  water_heater: 'standard',
  washer: 'standard',
  fridge: 'smart',
}

const initState = () => {
  const s = status.value
  Object.keys(state).forEach((key) => delete state[key])
  Object.assign(state, {
    power: s.power === 'on' ? 'on' : 'off',
    temperature: s.temperature ?? 26,
    mode: s.mode || MODE_FALLBACK[props.device?.type] || 'auto',
    fan_speed: s.fan_speed || 'auto',
    swing: Boolean(s.swing),
    brightness: s.brightness ?? 80,
    color: s.color || '#FFFFFF',
    volume: s.volume ?? 20,
    channel: s.channel ?? 1,
    input_source: s.input_source || 'hdmi1',
    playing: Boolean(s.playing),
    source: s.source || 'local',
    position: s.position ?? 0,
    cleaning_mode: s.cleaning_mode || 'auto',
    cleaning_status: s.status || 'idle',
    battery: s.battery ?? 100,
    dust_bin: s.dust_bin ?? 0,
    pm25: s.pm25 ?? 35,
    filter_life: s.filter_life ?? 80,
    target_humidity: s.target_humidity ?? 55,
    water_level: s.water_level ?? 80,
    freezer_temperature: s.freezer_temperature ?? -18,
    water_temp: s.water_temp || 'cold',
    washer_status: s.status || 'idle',
    locked: Boolean(s.locked),
    auto_lock: Boolean(s.auto_lock),
    recording: Boolean(s.recording),
    motion_detection: Boolean(s.motion_detection),
    night_vision: Boolean(s.night_vision),
  })
  initEnvForm()
}

const envFields = computed(() =>
  (ENVIRONMENT_FIELDS[props.device?.type] || []).filter((field) => field.key in status.value),
)

const initEnvForm = () => {
  const s = status.value
  Object.keys(envForm).forEach((key) => delete envForm[key])
  envFields.value.forEach((field) => {
    const value = s[field.key]
    envForm[field.key] = value === undefined || value === null ? defaultValueOf(field) : value
  })
}

watch(
  () => [props.modelValue, props.device?.id, props.device?.status],
  ([visible]) => {
    if (visible) initState()
  },
  { deep: true, immediate: true },
)

const powerOn = computed({
  get: () => state.power === 'on',
  set: (value) => {
    if (!canControlDevice.value) return
    state.power = value ? 'on' : 'off'
    update('power', state.power)
  },
})

const vacuumRunning = computed(() => state.cleaning_status === 'cleaning')
const washerRunning = computed(() => state.washer_status === 'running')
const washerModeText = computed(() => {
  const labels = { standard: '标准洗', quick: '快速洗', delicate: '轻柔洗', heavy: '强力洗' }
  return labels[state.mode] || '标准洗'
})
const washerStatusText = computed(() => {
  if (state.washer_status === 'running') return '洗涤中'
  if (state.washer_status === 'finished') return '已完成'
  if (state.washer_status === 'paused') return '已暂停'
  return '待机'
})
const washerTagType = computed(() => {
  if (state.washer_status === 'running') return 'warning'
  if (state.washer_status === 'finished') return 'success'
  return 'info'
})
const batteryColor = computed(() => {
  if (state.battery <= 20) return '#ef4444'
  if (state.battery <= 50) return '#f59e0b'
  return '#10b981'
})
const filterColor = computed(() => {
  if (state.filter_life <= 20) return '#ef4444'
  if (state.filter_life <= 50) return '#f59e0b'
  return '#10b981'
})

const update = (key, value) => {
  if (!canControlDevice.value || !props.device) return
  emit('control', props.device.id, { [key]: value })
}

const updateMany = (attributes) => {
  if (!canControlDevice.value || !props.device) return
  emit('control', props.device.id, attributes)
}

const adjustTemp = (delta) => {
  const next = state.temperature + delta
  if (next < 16 || next > 30) return
  state.temperature = next
  update('temperature', next)
}

const setPosition = (value) => {
  state.position = value
  update('position', value)
}

const toggleVacuum = () => {
  const next = vacuumRunning.value ? 'idle' : 'cleaning'
  state.cleaning_status = next
  if (next === 'cleaning') {
    state.power = 'on'
    updateMany({ status: next, power: 'on' })
  } else {
    update('status', next)
  }
}

const toggleWasher = () => {
  const next = washerRunning.value ? 'paused' : 'running'
  state.washer_status = next
  state.power = 'on'
  updateMany({ status: next, power: 'on' })
}

const saveEnvironment = async () => {
  if (!props.device || !canControlDevice.value) return
  saving.value = true
  try {
    const attributes = {}
    envFields.value.forEach((field) => {
      attributes[field.key] = envForm[field.key]
    })
    await updateDeviceStatus(props.device.id, attributes)
    ElMessage.success('设备数据已保存')
    emit('saved')
    close()
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    saving.value = false
  }
}

const close = () => emit('update:modelValue', false)

const onEdit = () => {
  const device = props.device
  close()
  emit('edit', device)
}

const onDelete = () => {
  const device = props.device
  close()
  emit('delete', device)
}
</script>

<style scoped>
.dd-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-right: 24px;
}

.dd-head-main {
  min-width: 0;
}

.dd-type {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 650;
  color: var(--ink-500);
  background: rgba(23, 28, 43, 0.05);
}

.dd-title {
  margin: 7px 0 0;
  font-size: 20px;
  font-weight: 750;
  line-height: 1.2;
  color: var(--ink-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dd-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dd-head-side {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
  padding-top: 4px;
}

.dd-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-400);
}

.dd-state i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.14);
}

.dd-state.offline i {
  background: #d99a4e;
  box-shadow: 0 0 0 3px rgba(217, 154, 78, 0.16);
}

.dd-body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
  max-height: min(62vh, 620px);
  overflow-y: auto;
  padding-right: 4px;
}

.dd-art {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  padding: 22px 18px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.6);
}

.tone-climate {
  background: radial-gradient(120% 120% at 20% 0%, rgba(79, 107, 237, 0.2), rgba(255, 255, 255, 0.42) 66%);
}

.tone-warm {
  background: radial-gradient(120% 120% at 20% 0%, rgba(217, 154, 78, 0.22), rgba(255, 255, 255, 0.44) 66%);
}

.tone-sage {
  background: radial-gradient(120% 120% at 20% 0%, rgba(111, 155, 131, 0.22), rgba(255, 255, 255, 0.44) 66%);
}

.tone-amber {
  background: radial-gradient(120% 120% at 20% 0%, rgba(217, 154, 78, 0.26), rgba(255, 255, 255, 0.42) 66%);
}

.tone-slate {
  background: radial-gradient(120% 120% at 20% 0%, rgba(95, 103, 122, 0.18), rgba(255, 255, 255, 0.44) 66%);
}

.tone-sky {
  background: radial-gradient(120% 120% at 20% 0%, rgba(56, 189, 248, 0.2), rgba(255, 255, 255, 0.44) 66%);
}

.tone-sand {
  background: radial-gradient(120% 120% at 20% 0%, rgba(180, 160, 130, 0.22), rgba(255, 255, 255, 0.44) 66%);
}

.dd-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.dd-panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(23, 28, 43, 0.06);
}

.dd-panel-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink-900);
}

.dd-panel-head span {
  font-size: 11px;
  color: var(--ink-400);
}

.dd-headline {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.dd-headline .el-tag {
  margin-left: 4px;
}

.dd-big {
  font-size: 30px;
  font-weight: 750;
  line-height: 1;
  color: var(--ink-900);
  font-variant-numeric: tabular-nums;
}

.dd-unit {
  font-size: 12px;
  color: var(--ink-400);
}

.dd-row {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.dd-label {
  font-size: 12px;
  color: var(--ink-500);
}

.dd-control {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.dd-radio {
  flex-wrap: wrap;
}

.dd-note {
  font-size: 11px;
  color: var(--ink-400);
  white-space: nowrap;
}

.dd-readouts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.dd-readout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.75);
}

.dd-readout span {
  font-size: 11px;
  color: var(--ink-400);
}

.dd-readout strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--ink-900);
  font-variant-numeric: tabular-nums;
}

.dd-fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(156px, 1fr));
  gap: 12px;
}

.dd-field label {
  display: block;
  margin-bottom: 5px;
  font-size: 11px;
  color: var(--ink-400);
}

.dd-color {
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 9px;
  background: transparent;
  cursor: pointer;
}

.dd-color-value {
  font-size: 11px;
  color: var(--ink-400);
  font-variant-numeric: tabular-nums;
}

.dd-empty {
  margin: 0;
  padding: 28px 0;
  text-align: center;
  font-size: 12px;
  color: var(--ink-400);
}

.dd-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dd-footer-manage,
.dd-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dd-readonly {
  font-size: 11px;
  color: var(--ink-400);
}

@media (max-width: 720px) {
  .dd-body {
    grid-template-columns: 1fr;
    max-height: min(64vh, 560px);
  }

  .dd-art {
    min-height: 132px;
    padding: 12px;
  }

  .dd-art :deep(svg) {
    max-height: 120px;
  }

  .dd-header {
    flex-direction: column;
    gap: 10px;
  }

  .dd-head-side {
    padding-top: 0;
  }

  .dd-footer {
    flex-direction: column-reverse;
    align-items: stretch;
  }

  .dd-footer-manage,
  .dd-footer-actions {
    justify-content: flex-end;
  }
}
</style>
