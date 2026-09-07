<template>
  <component
    :is="cardComponent"
    :device="device"
    @control="(id, attrs) => $emit('control', id, attrs)"
    @edit="$emit('edit', $event)"
    @delete="$emit('delete', $event)"
    @saved="$emit('saved', $event)"
  />
</template>

<script setup>
import { computed } from 'vue'
import DeviceCard from './DeviceCard.vue'
import AirConditionerCard from './AirConditionerCard.vue'
import LightCard from './LightCard.vue'
import VacuumCard from './VacuumCard.vue'
import CurtainCard from './CurtainCard.vue'
import SmartDeviceCard from './SmartDeviceCard.vue'
import EnvironmentDeviceCard from './EnvironmentDeviceCard.vue'

const props = defineProps({
  device: { type: Object, required: true },
})

defineEmits(['control', 'edit', 'delete', 'saved'])

const TYPE_COMPONENTS = {
  air_conditioner: AirConditionerCard,
  light: LightCard,
  robot_vacuum: VacuumCard,
  curtain: CurtainCard,
  speaker: DeviceCard,
  tv: SmartDeviceCard,
  air_purifier: SmartDeviceCard,
  humidifier: SmartDeviceCard,
  water_heater: SmartDeviceCard,
  washer: SmartDeviceCard,
  fridge: SmartDeviceCard,
  door_lock: SmartDeviceCard,
  camera: SmartDeviceCard,
  // 环境感知 / 计量 / 安防 / 网络设备
  air_monitor: EnvironmentDeviceCard,
  temp_humidity_sensor: EnvironmentDeviceCard,
  outdoor_sensor: EnvironmentDeviceCard,
  weather_station: EnvironmentDeviceCard,
  electricity_meter: EnvironmentDeviceCard,
  smart_plug: EnvironmentDeviceCard,
  water_meter: EnvironmentDeviceCard,
  gas_meter: EnvironmentDeviceCard,
  door_window_sensor: EnvironmentDeviceCard,
  presence_sensor: EnvironmentDeviceCard,
  leak_sensor: EnvironmentDeviceCard,
  gas_sensor: EnvironmentDeviceCard,
  smoke_sensor: EnvironmentDeviceCard,
  router: EnvironmentDeviceCard,
}

const cardComponent = computed(() => TYPE_COMPONENTS[props.device.type] || DeviceCard)
</script>
