<template>
  <div class="fixed top-4 right-4 z-[999] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]">
    <TransitionGroup name="toast">
      <div
        v-for="toast in uiStore.toasts"
        :key="toast.id"
        class="glass-strong rounded-xl px-4 py-3 shadow-lg shadow-black/5 flex items-start gap-3 animate-slide-in-right"
      >
        <span class="mt-0.5 shrink-0">
          <CheckCircle2 v-if="toast.type === 'success'" :size="17" class="text-emerald-500" />
          <AlertCircle v-else-if="toast.type === 'warning'" :size="17" class="text-amber-500" />
          <XCircle v-else :size="17" class="text-red-500" />
        </span>
        <p class="flex-1 text-sm text-gray-700 leading-relaxed break-words min-w-0">{{ toast.message }}</p>
        <button
          class="shrink-0 p-0.5 text-gray-400 hover:text-gray-600 transition-colors"
          type="button"
          title="关闭"
          @click="uiStore.removeToast(toast.id)"
        >
          <X :size="14" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { CheckCircle2, AlertCircle, XCircle, X } from 'lucide-vue-next'
import { useUiStore } from '@/stores/ui'

const uiStore = useUiStore()
</script>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.25s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(24px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(24px);
}
</style>