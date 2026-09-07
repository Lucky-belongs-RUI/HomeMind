<template>
  <div class="page room-view">
    <div class="flex flex-1 min-h-0 gap-4 room-layout">
      <RoomSidebar
        :rooms="roomStore.rooms"
        :selected-room-id="roomStore.selectedRoomId"
        :can-manage="canManageRooms"
        @select="roomStore.selectRoom"
        @add="openAdd"
      />

      <RoomDetail
        :room="selectedRoom"
        :devices="selectedRoomDevices"
        :can-manage="canManageRooms"
        @control="onControl"
        @delete="requestDelete"
      />
    </div>

    <el-dialog v-model="showDialog" title="添加房间" width="440px" align-center append-to-body>
      <el-form :model="form" label-width="72px">
        <el-form-item label="房间名称" required>
          <el-input v-model="form.name" placeholder="如：影音室" maxlength="20" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="80" />
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="form.icon" style="width: 100%">
            <el-option label="客厅" value="home" />
            <el-option label="卧室" value="bed" />
            <el-option label="厨房" value="kitchen" />
            <el-option label="书房" value="book" />
            <el-option label="卫生间" value="bath" />
            <el-option label="阳台" value="balcony" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAdd">添加</el-button>
      </template>
    </el-dialog>

    <ConfirmDialog
      v-model="showDelete"
      title="删除房间"
      :message="`确定删除房间「${deleteTarget?.name || ''}」吗？`"
      type="danger"
      confirm-text="删除"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoomStore } from '@/stores/room'
import { useDeviceStore } from '@/stores/device'
import { useUserStore } from '@/stores/user'
import { usePermission } from '@/composables/usePermission'
import { createRoom, deleteRoom } from '@/api/room'
import RoomSidebar from '@/components/room/RoomSidebar.vue'
import RoomDetail from '@/components/room/RoomDetail.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const roomStore = useRoomStore()
const deviceStore = useDeviceStore()
const userStore = useUserStore()
const { canManageRooms } = usePermission()

const showDialog = ref(false)
const submitting = ref(false)
const showDelete = ref(false)
const deleteTarget = ref(null)
const form = reactive({ name: '', description: '', icon: 'home' })

const selectedRoom = computed(() => roomStore.selectedRoom)

const selectedRoomDevices = computed(() => {
  if (!selectedRoom.value) return []
  return deviceStore.devices
    .filter((device) => device.room_id === selectedRoom.value.id)
    .map((device) => ({
      ...device,
      room_name: selectedRoom.value.name,
    }))
})

const loadAll = async () => {
  await Promise.all([roomStore.fetchRooms(), deviceStore.fetchDevices()])
  if (!roomStore.selectedRoomId && roomStore.rooms.length) {
    roomStore.selectRoom(roomStore.rooms[0].id)
  }
}

const openAdd = () => {
  Object.assign(form, { name: '', description: '', icon: 'home' })
  showDialog.value = true
}

const submitAdd = async () => {
  if (!form.name.trim()) {
    ElMessage.warning('请输入房间名称')
    return
  }
  submitting.value = true
  try {
    const room = await createRoom({ ...form, name: form.name.trim() })
    ElMessage.success('房间添加成功')
    showDialog.value = false
    await roomStore.fetchRooms()
    roomStore.selectRoom(room.id)
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    submitting.value = false
  }
}

const onControl = async (deviceId, attributes) => {
  try {
    await deviceStore.controlDevice(deviceId, attributes)
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

const requestDelete = (room) => {
  deleteTarget.value = room
  showDelete.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  try {
    await deleteRoom(deleteTarget.value.id)
    ElMessage.success('房间已删除')
    roomStore.selectedRoomId = null
    await loadAll()
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

onMounted(loadAll)
watch(
  () => userStore.familyId,
  () => {
    roomStore.selectedRoomId = null
    loadAll()
  },
)
</script>

<style scoped>
@media (max-width: 820px) {
  .room-layout {
    flex-direction: column;
    min-height: 0;
  }
}
</style>
