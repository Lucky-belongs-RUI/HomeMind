<template>
  <div v-if="message.role === 'system'" class="system-row">
    <span class="system-pill">{{ message.content }}</span>
  </div>

  <div v-else class="message-row" :class="isUser ? 'is-user' : 'is-assistant'">
    <span v-if="!isUser" class="avatar avatar-assistant">
      <Bot :size="14" />
    </span>

    <div class="bubble" :class="isUser ? 'bubble-user' : 'bubble-assistant'">
      <p class="bubble-text">{{ message.content }}</p>
      <div v-if="!isUser && message.warning" class="bubble-warning">
        <AlertTriangle :size="13" />
        <span>{{ message.warning }}，当前回复由内置规则生成，能力受限</span>
      </div>
    </div>

    <span v-if="isUser" class="avatar avatar-user">
      <User :size="14" />
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bot, User, AlertTriangle } from 'lucide-vue-next'

const props = defineProps({
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
</script>

<style scoped>
.system-row {
  display: flex;
  justify-content: center;
  padding: 6px 12px;
}

.system-pill {
  padding: 4px 11px;
  border-radius: 999px;
  font-size: 10px;
  color: var(--ink-400);
  background: rgba(255, 255, 255, 0.66);
  border: 1px solid rgba(255, 255, 255, 0.75);
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 5px 12px;
}

.message-row.is-user {
  justify-content: flex-end;
}

.avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: none;
  margin-top: 2px;
  border-radius: 9px;
}

.avatar-assistant {
  color: #fff;
  background: linear-gradient(135deg, #7f92f6, #4f6bed 60%, #3f57d6);
  box-shadow: 0 4px 12px rgba(79, 107, 237, 0.2);
}

.avatar-user {
  color: var(--ink-500);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.9);
}

.bubble {
  max-width: 78%;
  padding: 10px 13px;
  border-radius: 16px;
  font-size: 13px;
  line-height: 1.65;
  word-break: break-word;
}

.bubble-user {
  color: #fff;
  background: linear-gradient(135deg, #5c76ee, #4f6bed 64%, #3f57d6);
  border-top-right-radius: 6px;
  box-shadow: 0 6px 16px rgba(79, 107, 237, 0.18);
}

.bubble-assistant {
  color: var(--ink-700);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.86);
  border-top-left-radius: 6px;
  box-shadow: 0 4px 14px rgba(23, 28, 43, 0.04);
}

.bubble-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-warning {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 7px 9px;
  border-radius: 10px;
  font-size: 11px;
  line-height: 1.5;
  color: #94601f;
  background: rgba(255, 251, 235, 0.92);
  border: 1px solid rgba(217, 154, 78, 0.24);
}

.bubble-warning svg {
  flex: none;
  margin-top: 1px;
  color: #b0742e;
}

@media (max-width: 520px) {
  .message-row {
    padding: 4px 8px;
  }

  .bubble {
    max-width: 84%;
  }
}
</style>
