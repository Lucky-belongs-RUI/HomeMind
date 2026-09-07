<template>
  <section class="section-panel flex-1 min-w-0 h-full flex flex-col min-h-[400px]">
    <template v-if="room">
      <div class="flex items-start justify-between gap-4 mb-4 shrink-0">
        <div class="min-w-0">
          <div class="flex items-center gap-2.5">
            <span class="w-9 h-9 rounded-lg bg-blue-500/10 text-blue-500 flex items-center justify-center shrink-0">
              <Home :size="18" />
            </span>
            <div class="min-w-0">
              <h2 class="text-lg font-bold text-gray-800 leading-tight truncate">{{ room.name }}</h2>
              <p class="text-xs text-gray-400 mt-0.5 truncate">{{ room.description || '暂无描述' }}</p>
            </div>
          </div>
        </div>
        <el-button
          v-if="canManage"
          type="danger"
          plain
          size="small"
          class="shrink-0"
          @click="$emit('delete', room)"
        >
          <Trash2 :size="13" class="mr-1" />
          删除房间
        </el-button>
      </div>

      <div class="flex gap-2 mb-4 shrink-0">
        <span class="px-3 py-1.5 rounded-full bg-white/60 border border-white/40 text-xs text-gray-500">
          {{ devices.length }} 个设备
        </span>
        <span class="px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-200/60 text-xs text-emerald-600">
          {{ onlineCount }} 在线
        </span>
      </div>

      <div v-if="devices.length" class="flex-1 min-h-0 overflow-y-auto pr-0.5">
        <div class="device-grid content-start">
          <DeviceCardFactory
            v-for="device in devices"
            :key="device.id"
            :device="device"
            @control="(id, attrs) => $emit('control', id, attrs)"
          />
        </div>
      </div>
      <div v-else class="flex-1 flex flex-col items-center justify-center text-center text-gray-400">
        <Home :size="42" class="mb-3 text-gray-300" />
        <p class="text-sm">该房间暂无设备</p>
      </div>
    </template>

    <div v-else class="flex-1 flex flex-col items-center justify-center text-center text-gray-400">
      <Home :size="42" class="mb-3 text-gray-300" />
      <p class="text-sm">请从左侧选择一个房间</p>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Home, Trash2 } from 'lucide-vue-next'
import DeviceCardFactory from '@/components/device/DeviceCardFactory.vue'

const props = defineProps({
  room: { type: Object, default: null },
  devices: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: false },
})

defineEmits(['control', 'delete'])

const onlineCount = computed(
  () => props.devices.filter((device) => device.status?.power === 'on').length,
)
</script>
<style scoped>
@media (max-width: 820px) {
  section {
    height: auto;
    flex: 1;
  }
}
</style>
