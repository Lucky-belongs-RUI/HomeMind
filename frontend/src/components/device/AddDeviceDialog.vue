<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    :title="editing ? '编辑设备' : '添加设备'"
    width="460px"
    align-center
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form :model="form" label-width="76px">
      <el-form-item label="设备名称" required>
        <el-input v-model="form.name" placeholder="如：卧室空调" maxlength="30" />
      </el-form-item>
      <el-form-item label="设备类型" required>
        <el-select v-model="form.type" placeholder="选择类型" style="width: 100%">
          <el-option label="空调" value="air_conditioner" />
          <el-option label="灯" value="light" />
          <el-option label="扫地机器人" value="robot_vacuum" />
          <el-option label="窗帘" value="curtain" />
          <el-option label="音箱/马桶" value="speaker" />
          <el-option label="电视" value="tv" />
          <el-option label="空气净化器" value="air_purifier" />
          <el-option label="加湿器" value="humidifier" />
          <el-option label="热水器" value="water_heater" />
          <el-option label="洗衣机" value="washer" />
          <el-option label="冰箱" value="fridge" />
          <el-option label="智能门锁" value="door_lock" />
          <el-option label="空气质量检测仪" value="air_monitor" />
          <el-option label="温湿度传感器" value="temp_humidity_sensor" />
          <el-option label="室外温湿度传感器" value="outdoor_sensor" />
          <el-option label="室外气象站" value="weather_station" />
          <el-option label="智能电表" value="electricity_meter" />
          <el-option label="智能插座" value="smart_plug" />
          <el-option label="智能水表" value="water_meter" />
          <el-option label="智能燃气表" value="gas_meter" />
          <el-option label="门窗传感器" value="door_window_sensor" />
          <el-option label="人体存在传感器" value="presence_sensor" />
          <el-option label="水浸传感器" value="leak_sensor" />
          <el-option label="燃气传感器" value="gas_sensor" />
          <el-option label="烟雾传感器" value="smoke_sensor" />
          <el-option label="智能路由器" value="router" />
          <el-option label="摄像头" value="camera" />
        </el-select>
      </el-form-item>
      <el-form-item label="所属房间" required>
        <el-select v-model="form.room_id" placeholder="选择房间" style="width: 100%">
          <el-option v-for="room in rooms" :key="room.id" :label="room.name" :value="room.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="品牌">
        <el-input v-model="form.brand" placeholder="如：格力" maxlength="20" />
      </el-form-item>
      <el-form-item label="型号">
        <el-input v-model="form.model" placeholder="如：KFR-26" maxlength="30" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">
        {{ editing ? '保存' : '添加' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createDevice, updateDevice } from '@/api/device'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  rooms: { type: Array, default: () => [] },
  device: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'saved'])

const submitting = ref(false)
const form = reactive({
  name: '',
  type: '',
  room_id: null,
  brand: '',
  model: '',
})

const editing = computed(() => Boolean(props.device?.id))

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      Object.assign(form, {
        name: props.device?.name || '',
        type: props.device?.type || '',
        room_id: props.device?.room_id || null,
        brand: props.device?.brand || '',
        model: props.device?.model || '',
      })
    }
  },
)

const onSubmit = async () => {
  if (!form.name.trim() || !form.type || !form.room_id) {
    ElMessage.warning('请填写设备名称、类型和所属房间')
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: form.name.trim(),
      type: form.type,
      room_id: form.room_id,
      brand: form.brand.trim(),
      model: form.model.trim(),
    }
    if (editing.value) {
      await updateDevice(props.device.id, payload)
      ElMessage.success('设备信息已保存')
    } else {
      await createDevice(payload)
      ElMessage.success('设备添加成功')
    }
    emit('update:modelValue', false)
    emit('saved')
  } catch (error) {
    // 错误提示已在请求层统一处理
  } finally {
    submitting.value = false
  }
}
</script>
