<template>
  <div v-if="message.role === 'system'" class="flex justify-center py-2">
    <span class="text-[10px] text-gray-400 bg-white/70 px-3 py-1 rounded-full border border-white/30">
      {{ message.content }}
    </span>
  </div>

  <div v-else class="flex gap-2 px-4 py-2" :class="isUser ? 'justify-end' : 'justify-start'">
    <div
      v-if="!isUser"
      class="w-7 h-7 rounded-lg bg-blue-50 border border-blue-200/50 flex items-center justify-center flex-shrink-0 mt-1"
    >
      <Bot :size="14" class="text-blue-600" />
    </div>

    <div
      class="max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed break-words"
      :class="
        isUser
          ? 'bg-blue-600 text-white rounded-tr-md shadow-sm shadow-blue-600/20'
          : 'glass text-gray-700 border border-white/30 rounded-tl-md'
      "
    >
      <p class="whitespace-pre-wrap break-words">{{ message.content }}</p>
    </div>

    <div
      v-if="isUser"
      class="w-7 h-7 rounded-lg bg-white/80 border border-white/30 flex items-center justify-center flex-shrink-0 mt-1"
    >
      <User :size="14" class="text-gray-500" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bot, User } from 'lucide-vue-next'

const props = defineProps({
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
</script>