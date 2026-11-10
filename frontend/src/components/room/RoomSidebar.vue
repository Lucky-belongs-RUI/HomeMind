<template>
  <aside class="room-panel section-panel">
    <div class="room-head">
      <h3 class="panel-title">房间列表</h3>
      <span class="room-total">{{ rooms.length }}</span>
    </div>

    <nav class="room-list" aria-label="房间列表">
      <button
        v-for="room in rooms"
        :key="room.id"
        type="button"
        class="room-item"
        :class="{ active: room.id === selectedRoomId }"
        :aria-current="room.id === selectedRoomId ? 'true' : undefined"
        @click="$emit('select', room.id)"
      >
        <span class="room-icon">
          <component :is="roomIcon(room.icon)" :size="16" />
        </span>
        <span class="room-label">
          <span class="room-name">{{ room.name }}</span>
          <span class="room-desc">{{ room.description || '智能空间' }}</span>
        </span>
        <span class="room-count">{{ room.device_count || 0 }}</span>
        <ChevronRight :size="14" class="room-arrow" />
      </button>

      <div v-if="!rooms.length" class="room-empty">当前家庭暂无房间</div>
    </nav>
  </aside>
</template>

<script setup>
import { Home, BedDouble, Utensils, BookOpen, ShowerHead, Sun, ChevronRight } from 'lucide-vue-next'

defineProps({
  rooms: { type: Array, default: () => [] },
  selectedRoomId: { type: Number, default: null },
})

defineEmits(['select'])

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
.room-panel {
  display: flex;
  flex-direction: column;
  width: 252px;
  flex: none;
  min-height: 0;
  padding: 16px 12px;
}

.room-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 6px 10px;
  flex: none;
}

.room-total {
  min-width: 20px;
  padding: 1px 6px;
  border-radius: 999px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-400);
  background: rgba(23, 28, 43, 0.06);
}

.room-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
  scrollbar-width: thin;
}

.room-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border-radius: 12px;
  border: 1px solid transparent;
  text-align: left;
  transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.room-item:hover {
  background: rgba(255, 255, 255, 0.66);
}

.room-item.active {
  background: #fff;
  border-color: rgba(79, 107, 237, 0.2);
  box-shadow: 0 6px 18px rgba(79, 107, 237, 0.1);
}

.room-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: 10px;
  color: var(--ink-400);
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.8);
  transition: color 0.18s ease, background 0.18s ease;
}

.room-item.active .room-icon {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
  border-color: rgba(79, 107, 237, 0.14);
}

.room-label {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.room-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-700);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-item.active .room-name {
  color: var(--ink-900);
}

.room-desc {
  margin-top: 1px;
  font-size: 10px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-count {
  min-width: 20px;
  padding: 1px 6px;
  border-radius: 999px;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-400);
  background: rgba(23, 28, 43, 0.05);
}

.room-item.active .room-count {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.12);
}

.room-arrow {
  color: #b6bbc8;
  flex: none;
  transition: transform 0.18s ease;
}

.room-item.active .room-arrow {
  color: var(--accent);
  transform: translateX(1px);
}

.room-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--ink-400);
}

@media (max-width: 820px) {
  .room-panel {
    width: 100%;
    padding: 10px;
    flex: none;
  }

  .room-head {
    display: none;
  }

  .room-list {
    flex-direction: row;
    gap: 6px;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 2px;
    scrollbar-width: none;
  }

  .room-list::-webkit-scrollbar {
    display: none;
  }

  .room-item {
    width: auto;
    flex: none;
    padding: 7px 10px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.6);
    border-color: rgba(255, 255, 255, 0.72);
  }

  .room-item.active {
    border-radius: 999px;
  }

  .room-icon {
    width: 24px;
    height: 24px;
    border-radius: 8px;
    background: transparent;
    border: none;
  }

  .room-label {
    flex-direction: row;
    align-items: center;
  }

  .room-name {
    font-size: 12px;
  }

  .room-desc,
  .room-arrow {
    display: none;
  }

  .room-count {
    background: transparent;
    padding: 0;
    min-width: 0;
  }

  .room-empty {
    width: 100%;
    padding: 10px;
  }
}
</style>
