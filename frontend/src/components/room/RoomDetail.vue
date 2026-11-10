<template>
  <section class="room-detail section-panel">
    <template v-if="room">
      <div class="room-detail-head">
        <div class="room-title-wrap">
          <span class="room-detail-icon">
            <component :is="roomIcon" :size="18" />
          </span>
          <div class="min-w-0">
            <h2 class="room-title">{{ room.name }}</h2>
            <p class="room-subtitle">{{ room.description || '当前房间的设备与控制入口' }}</p>
          </div>
        </div>
        <div v-if="canManage" class="room-actions">
          <el-button type="primary" size="small" @click="$emit('add')">
            <Plus :size="13" class="mr-1" />
            添加房间
          </el-button>
          <el-button type="danger" plain size="small" @click="$emit('delete', room)">
            <Trash2 :size="13" class="mr-1" />
            删除房间
          </el-button>
        </div>
      </div>

      <div class="room-stat-row">
        <span class="chip">设备 {{ devices.length }}</span>
        <span class="chip chip-online">在线 {{ onlineCount }}</span>
        <span v-if="runningCount" class="chip chip-running">运行中 {{ runningCount }}</span>
        <span v-if="offlineCount" class="chip chip-offline">离线 {{ offlineCount }}</span>
      </div>

      <div v-if="devices.length" class="room-device-scroll">
        <div class="device-grid content-start">
          <DeviceCard
            v-for="device in devices"
            :key="device.id"
            :device="device"
            @open="$emit('open', $event)"
            @control="(id, attrs) => $emit('control', id, attrs)"
          />
        </div>
      </div>

      <div v-else class="empty-state room-empty">
        <span class="empty-icon">
          <Home :size="24" />
        </span>
        <p class="text-sm font-medium text-gray-600">该房间暂无设备</p>
        <p class="mt-1 text-xs text-gray-400">前往设备页添加后，会自动归入当前房间</p>
      </div>
    </template>

    <div v-else class="empty-state room-empty">
      <span class="empty-icon">
        <Home :size="24" />
      </span>
      <p class="text-sm font-medium text-gray-600">请选择一个房间</p>
      <p class="mt-1 text-xs text-gray-400">从左侧列表或上方胶囊切换空间</p>
      <el-button v-if="canManage" type="primary" size="small" class="mt-4" @click="$emit('add')">
        <Plus :size="13" class="mr-1" />
        添加房间
      </el-button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Home, Plus, Trash2, BedDouble, Utensils, BookOpen, ShowerHead, Sun } from 'lucide-vue-next'
import DeviceCard from '@/components/device/DeviceCard.vue'

const props = defineProps({
  room: { type: Object, default: null },
  devices: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: false },
})

defineEmits(['control', 'open', 'add', 'delete'])

const ICONS = {
  home: Home,
  bed: BedDouble,
  kitchen: Utensils,
  book: BookOpen,
  bath: ShowerHead,
  balcony: Sun,
}

const roomIcon = computed(() => ICONS[props.room?.icon] || Home)
const onlineCount = computed(
  // 可控制设备默认没有 online 字段（视为在线），只有明确离线才不计入
  () => props.devices.filter((device) => device.status?.online !== false).length,
)
const offlineCount = computed(() => props.devices.length - onlineCount.value)
const runningCount = computed(
  () =>
    props.devices.filter((device) => {
      const status = device.status || {}
      return (
        status.power === 'on' ||
        status.status === 'cleaning' ||
        status.status === 'running' ||
        status.recording === true
      )
    }).length,
)
</script>

<style scoped>
.room-detail {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  padding: 18px;
}

.room-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  flex: none;
}

.room-title-wrap {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.room-actions {
  display: flex;
  flex: none;
  flex-direction: column;
  gap: 8px;
  width: 104px;
}

.room-actions :deep(.el-button) {
  width: 100%;
  margin-left: 0;
}

.room-detail-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 12px;
  color: var(--accent-strong);
  background: linear-gradient(135deg, rgba(79, 107, 237, 0.16), rgba(79, 107, 237, 0.06));
  border: 1px solid rgba(79, 107, 237, 0.13);
}

.room-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ink-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-subtitle {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 14px 0;
  flex: none;
}

.chip {
  padding: 5px 10px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.66);
}

.chip-online {
  color: #2c7a5f;
  background: rgba(236, 253, 245, 0.86);
  border-color: rgba(16, 185, 129, 0.18);
}

.chip-running {
  color: #3f57d6;
  background: rgba(79, 107, 237, 0.08);
  border-color: rgba(79, 107, 237, 0.16);
}

.chip-offline {
  color: #9a6b2f;
  background: rgba(255, 251, 235, 0.9);
  border-color: rgba(217, 154, 78, 0.22);
}

.room-device-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.room-empty {
  flex: 1;
}

@media (max-width: 820px) {
  .room-detail {
    height: auto;
    min-height: 320px;
    padding: 16px;
  }

  .room-device-scroll {
    overflow: visible;
  }
}

@media (max-width: 520px) {
  .room-title {
    font-size: 16px;
  }

  .room-detail-head {
    flex-direction: column;
    align-items: stretch;
  }

  .room-actions {
    width: 100%;
  }
}
</style>
