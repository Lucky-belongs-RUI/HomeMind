<template>
  <aside class="glass rounded-xl p-4 w-64 shrink-0 h-full flex flex-col min-h-[240px]">
    <div class="flex items-center justify-between gap-2 mb-3 shrink-0">
      <h3 class="text-sm font-bold text-gray-800">房间列表</h3>
      <el-button v-if="canManage" type="primary" size="small" @click="$emit('add')">
        <Plus :size="13" class="mr-1" />
        添加
      </el-button>
    </div>

    <div class="flex flex-col gap-1.5 flex-1 min-h-0 overflow-y-auto pr-0.5">
      <button
        v-for="room in rooms"
        :key="room.id"
        class="flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all w-full text-left"
        :class="
          room.id === selectedRoomId
            ? 'bg-blue-500/10 text-blue-600 border border-blue-200/60 shadow-sm'
            : 'text-gray-500 hover:bg-black/5 hover:text-gray-900 border border-transparent'
        "
        type="button"
        @click="$emit('select', room.id)"
      >
        <span
          class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          :class="room.id === selectedRoomId ? 'bg-white text-blue-500' : 'bg-white/60 text-gray-400'"
        >
          <component :is="roomIcon(room.icon)" :size="16" />
        </span>
        <span class="flex-1 min-w-0 truncate font-medium">{{ room.name }}</span>
        <span
          class="min-w-[22px] px-1.5 py-0.5 rounded-full text-[11px] text-center"
          :class="room.id === selectedRoomId ? 'bg-blue-100 text-blue-600' : 'bg-white/70 text-gray-400'"
        >
          {{ room.device_count || 0 }}
        </span>
      </button>

      <div v-if="!rooms.length" class="text-center text-xs text-gray-400 py-8">
        当前家庭暂无房间
      </div>
    </div>
  </aside>
</template>

<script setup>
import { Home, BedDouble, Utensils, BookOpen, ShowerHead, Sun, Plus } from 'lucide-vue-next'

defineProps({
  rooms: { type: Array, default: () => [] },
  selectedRoomId: { type: Number, default: null },
  canManage: { type: Boolean, default: false },
})

defineEmits(['select', 'add'])

const ICONS = {
  home: Home,
  bed: BedDouble,
  kitchen: Utensils,
  book: BookOpen,
  bath: ShowerHead,
  balcony: Sun,
}

const roomIcon = (icon) => ICONS[icon] || Home
</script>

<style scoped>
@media (max-width: 820px) {
  aside {
    width: 100%;
    height: auto;
    min-height: 220px;
    max-height: 44vh;
  }
}
</style>