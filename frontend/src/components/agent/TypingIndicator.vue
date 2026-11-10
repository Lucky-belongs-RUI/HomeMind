<template>
  <div class="typing-row">
    <span class="typing-avatar"><Bot :size="14" /></span>
    <div class="typing-bubble">
      <span v-for="i in 3" :key="i" class="typing-dot" :style="{ animationDelay: `${(i - 1) * 0.15}s` }"></span>
      <span class="typing-text">正在思考</span>
    </div>
  </div>
</template>

<script setup>
import { Bot } from 'lucide-vue-next'
</script>

<style scoped>
.typing-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 12px 10px;
}

.typing-avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: 9px;
  color: #fff;
  background: linear-gradient(135deg, #7f92f6, #4f6bed 60%, #3f57d6);
  box-shadow: 0 4px 12px rgba(79, 107, 237, 0.2);
}

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 13px;
  border-radius: 16px;
  border-top-left-radius: 6px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.86);
}

.typing-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  animation: typing-bounce 0.9s ease-in-out infinite;
}

.typing-text {
  margin-left: 6px;
  font-size: 11px;
  color: var(--ink-400);
}

@keyframes typing-bounce {
  0%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-3px);
  }
}
</style>
