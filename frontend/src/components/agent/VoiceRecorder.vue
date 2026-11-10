<template>
  <el-tooltip :content="isRecording ? '点击停止录音' : '语音输入'" placement="top">
    <button
      class="w-9 h-9 rounded-lg flex items-center justify-center transition-all"
      :class="
        isRecording
          ? 'bg-red-500 text-white shadow-sm shadow-red-500/30 animate-pulse'
          : 'bg-white/60 border border-white/40 text-gray-500 hover:text-blue-600 hover:border-blue-300'
      "
      type="button"
      @click="toggleRecording"
    >
      <Mic v-if="!isRecording" :size="17" />
      <Square v-else :size="13" />
    </button>
  </el-tooltip>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { Mic, Square } from 'lucide-vue-next'
import { useVoice } from '@/composables/useVoice'

const emit = defineEmits(['recorded'])
const { isRecording, startRecording, stopRecording } = useVoice()

const toggleRecording = async () => {
  if (isRecording.value) {
    const blob = await stopRecording()
    if (blob) emit('recorded', blob)
  } else {
    await startRecording()
  }
}

onUnmounted(() => {
  if (isRecording.value) stopRecording()
})
</script>