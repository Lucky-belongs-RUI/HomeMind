<template>
  <div class="chat-window glass rounded-xl overflow-hidden min-h-[320px] flex flex-col">
    <div ref="scrollRef" class="flex-1 overflow-y-auto py-2 min-h-0">
      <template v-if="messages.length">
        <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
        <TypingIndicator v-if="thinking" />
      </template>

      <div v-else class="flex flex-col items-center justify-center h-full min-h-[320px] text-center px-6 py-8">
        <div class="w-14 h-14 rounded-2xl bg-blue-50 border border-blue-200/50 flex items-center justify-center mb-3">
          <Bot :size="26" class="text-blue-500" />
        </div>
        <h3 class="text-sm text-gray-700 font-medium mb-1">你好，我是您的智能家居助手</h3>
        <p class="text-xs text-gray-400 max-w-[260px] leading-relaxed">
          可以指挥我调节设备、触发场景，也可以问我关于家庭的问题
        </p>
        <div class="flex flex-wrap justify-center gap-2 mt-4">
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            class="px-2.5 py-1.5 rounded-full text-[11px] text-blue-600 bg-blue-50 border border-blue-200/60 hover:bg-blue-100 transition-colors"
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