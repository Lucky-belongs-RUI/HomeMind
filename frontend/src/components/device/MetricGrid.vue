<template>
  <div class="grid grid-cols-3 gap-2">
    <div
      v-for="item in items"
      :key="item.label"
      class="rounded-lg bg-white/60 border border-white/40 px-2.5 py-2"
    >
      <div class="text-[10px] text-gray-400 leading-none truncate">{{ item.label }}</div>
      <div class="mt-1 text-sm font-bold text-gray-800 leading-none truncate">
        {{ item.value ?? '--' }}<span v-if="item.unit" class="ml-0.5 text-[10px] font-medium text-gray-400">{{ item.unit }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
})
</script>