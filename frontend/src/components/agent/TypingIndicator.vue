<template>
  <div class="flex items-center gap-1 px-4 py-3">
    <div class="flex items-center gap-1.5 bg-blue-500/10 border border-blue-500/20 rounded-2xl px-4 py-3">
      <span
        v-for="i in 3"
        :key="i"
        class="w-2 h-2 rounded-full bg-blue-400 animate-bounce"
        :style="{ animationDelay: `${(i - 1) * 0.15}s`, animationDuration: '0.8s' }"
      ></span>
      <span class="text-xs text-blue-400 ml-1.5">AI 思考中...</span>
    </div>
  </div>
</template>