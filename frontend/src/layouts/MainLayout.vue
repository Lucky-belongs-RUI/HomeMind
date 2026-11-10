<template>
  <div class="app-shell h-dvh w-full flex flex-col overflow-hidden">
    <TopBar />
    <main class="flex-1 overflow-y-auto overflow-x-hidden">
      <div class="mx-auto w-full max-w-[1680px] px-3 py-4 sm:px-4 lg:px-6 lg:py-5">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import TopBar from '@/components/layout/TopBar.vue'
import { useWebSocket } from '@/composables/useWebSocket'

useWebSocket()
</script>

<style scoped>
.app-shell {
  background: transparent;
}
</style>
