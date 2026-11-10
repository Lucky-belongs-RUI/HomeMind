<template>
  <div class="chat-window">
    <div ref="scrollRef" class="chat-scroll">
      <template v-if="messages.length">
        <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
        <TypingIndicator v-if="thinking" />
      </template>

      <div v-else class="chat-welcome">
        <div class="welcome-orb">
          <Bot :size="24" />
        </div>
        <h3>你好，我是你的智能家居助手</h3>
        <p>可以指挥我调节设备、触发场景，也可以询问家庭环境与能耗情况</p>
        <div class="welcome-chips">
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            class="welcome-chip"
            type="button"
            @click="$emit('send', suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { Bot } from 'lucide-vue-next'
import MessageBubble from './MessageBubble.vue'
import TypingIndicator from './TypingIndicator.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  thinking: { type: Boolean, default: false },
})

defineEmits(['send'])

const suggestions = [
  '将卧室空调调整到 27 度',
  '我要回家了',
  '打开客厅灯',
  '开启睡眠模式',
]

const scrollRef = ref(null)

watch(
  () => [props.messages.length, props.thinking],
  () => {
    nextTick(() => {
      if (scrollRef.value) {
        scrollRef.value.scrollTop = scrollRef.value.scrollHeight
      }
    })
  },
)
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.36);
  border: 1px solid rgba(255, 255, 255, 0.56);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
}

.chat-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 2px;
}

.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 260px;
  padding: 28px 20px;
  text-align: center;
}

.welcome-orb {
  display: grid;
  place-items: center;
  width: 54px;
  height: 54px;
  margin-bottom: 12px;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #7f92f6, #4f6bed 58%, #3f57d6);
  box-shadow: 0 12px 28px rgba(79, 107, 237, 0.24);
}

.chat-welcome h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
  color: var(--ink-900);
}

.chat-welcome p {
  max-width: 300px;
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--ink-400);
}

.welcome-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  margin-top: 16px;
}

.welcome-chip {
  padding: 6px 11px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-strong);
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(79, 107, 237, 0.16);
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

.welcome-chip:hover {
  background: #fff;
  border-color: rgba(79, 107, 237, 0.34);
  transform: translateY(-1px);
}
</style>
