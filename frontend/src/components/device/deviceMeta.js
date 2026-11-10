import {
  AirVent,
  Lamp,
  Bot,
  Blinds,
  Tv,
  Refrigerator,
  Lock,
  Camera,
  Activity,
  Droplets,
  Wind,
  Thermometer,
  Zap,
  Plug,
  Router,
  ShieldCheck,
  CloudSun,
  Home,
  Cpu,
  Waves,
} from 'lucide-vue-next'

export const TYPE_LABELS = {
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
  outdoor_sensor: '室外传感器',
  weather_station: '气象站',
  electricity_meter: '智能电表',
  smart_plug: '智能插座',
  water_meter: '智能水表',
  gas_meter: '智能燃气表',
  door_window_sensor: '门窗传感器',
  presence_sensor: '人体传感器',
  leak_sensor: '水浸传感器',
  gas_sensor: '燃气传感器',
  smoke_sensor: '烟雾传感器',
  router: '智能路由器',
}

export const TYPE_ICONS = {
  air_conditioner: AirVent,
  light: Lamp,
  robot_vacuum: Bot,
  curtain: Blinds,
  speaker: Waves,
  tv: Tv,
  air_purifier: Wind,
  humidifier: Droplets,
  water_heater: Waves,
  washer: Waves,
  fridge: Refrigerator,
  door_lock: Lock,
  camera: Camera,
  air_monitor: Activity,
  temp_humidity_sensor: Thermometer,
  outdoor_sensor: Thermometer,
  weather_station: CloudSun,
  electricity_meter: Zap,
  smart_plug: Plug,
  water_meter: Droplets,
  gas_meter: Zap,
  door_window_sensor: Home,
  presence_sensor: Activity,
  leak_sensor: Droplets,
  gas_sensor: Zap,
  smoke_sensor: ShieldCheck,
  router: Router,
}

export const TONE_MAP = {
  air_conditioner: 'tone-climate',
  air_purifier: 'tone-climate',
  humidifier: 'tone-climate',
  fridge: 'tone-climate',
  washer: 'tone-climate',
  light: 'tone-warm',
  water_heater: 'tone-warm',
  curtain: 'tone-sand',
  door_lock: 'tone-sage',
  camera: 'tone-sage',
  door_window_sensor: 'tone-sage',
  presence_sensor: 'tone-sage',
  leak_sensor: 'tone-sage',
  gas_sensor: 'tone-sage',
  smoke_sensor: 'tone-sage',
  electricity_meter: 'tone-amber',
  smart_plug: 'tone-amber',
  water_meter: 'tone-amber',
  gas_meter: 'tone-amber',
  tv: 'tone-slate',
  speaker: 'tone-slate',
  robot_vacuum: 'tone-slate',
  router: 'tone-slate',
  air_monitor: 'tone-sky',
  temp_humidity_sensor: 'tone-sky',
  outdoor_sensor: 'tone-sky',
  weather_station: 'tone-sky',
}

export const typeLabelOf = (type) => TYPE_LABELS[type] || '智能设备'
export const typeIconOf = (type) => TYPE_ICONS[type] || Cpu
export const toneOf = (type) => TONE_MAP[type] || 'tone-slate'

export const isOnline = (status) => status?.online !== false
export const hasPower = (status) => 'power' in (status || {})
export const isPoweredOn = (status) => status?.power === 'on'
export const isDeviceOn = (status) => isPoweredOn(status) || status?.online === true

export const statusTextOf = (status) => {
  if (!isOnline(status)) return '离线'
  if (!hasPower(status)) return '在线'
  return isPoweredOn(status) ? '运行中' : '待机'
}

export const modelLabelOf = (device) =>
  [device?.brand, device?.model].filter(Boolean).join(' ')

export const metricTextOf = (type, status = {}) => {
  if (type === 'air_conditioner') return `${status.temperature ?? 26}°C`
  if (type === 'light') return `${status.brightness ?? 0}% 亮度`
  if (type === 'curtain') return `${status.position ?? 0}% 开合`
  if (type === 'robot_vacuum') return `${status.battery ?? 0}% 电量`
  if (type === 'speaker') return status.volume ? `${status.volume}% 音量` : ''
  if (type === 'tv') return status.volume ? `${status.volume}% 音量` : ''
  if (type === 'air_purifier') return status.pm25 ? `${status.pm25} μg/m³` : ''
  if (type === 'humidifier') return `${status.target_humidity ?? 55}% 湿度`
  if (type === 'water_heater') return `${status.temperature ?? 45}°C`
  if (type === 'washer') return status.status === 'running' ? '洗涤中' : '待机'
  if (type === 'fridge') return `${status.temperature ?? 4}°C`
  if (type === 'door_lock') return status.locked ? '已上锁' : '未上锁'
  if (type === 'camera') return status.recording ? '录制中' : '待机'
  if (type === 'air_monitor') return `${status.pm25 ?? '--'} μg/m³ · ${status.air_quality ?? '--'}`
  if (type === 'temp_humidity_sensor' || type === 'outdoor_sensor') {
    return `${status.temperature ?? '--'}°C · ${status.humidity ?? '--'}%`
  }
  if (type === 'weather_station') return `${status.weather || '--'} · ${status.temperature ?? '--'}°C`
  if (type === 'electricity_meter') return `${status.power_w ?? 0}W · 余额${status.balance ?? '--'}元`
  if (type === 'smart_plug') return `${status.power_w ?? 0}W`
  if (type === 'water_meter') return `${status.monthly_usage ?? '--'}m³ · 余额${status.balance ?? '--'}元`
  if (type === 'gas_meter') return `${status.monthly_usage ?? '--'}m³ · 余额${status.balance ?? '--'}元`
  if (type === 'door_window_sensor') return status.status === 'open' ? '门窗开启' : '门窗关闭'
  if (type === 'presence_sensor') return status.presence ? '有人' : '无人'
  if (type === 'leak_sensor') return status.leak ? '漏水告警' : '正常'
  if (type === 'gas_sensor') return status.gas_leak ? '燃气泄漏' : '正常'
  if (type === 'smoke_sensor') return status.smoke || status.alarm ? '烟雾告警' : '正常'
  if (type === 'router') return status.internet_status === 'online' ? '网络在线' : '网络离线'
  return ''
}
