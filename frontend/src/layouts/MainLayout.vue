<template>
  <div class="h-screen w-screen flex flex-col overflow-hidden app-shell">
    <TopBar />
    <main class="flex-1 overflow-auto p-4 lg:p-5">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import TopBar from '@/components/layout/TopBar.vue'
import { useWebSocket } from '@/composables/useWebSocket'

useWebSocket()
</script>