<template>
  <div v-if="steps.length" class="agent-stream-panel">
    <div class="stream-head">
      <span class="stream-title">执行链路</span>
      <span v-if="current" class="stream-current">
        <Loader2 :size="12" class="spin inline mr-1" />
        {{ current }} 节点正在执行...
      </span>
    </div>

    <!-- 按链路分组展示节点步骤（支持多链路并发） -->
    <div class="stream-chains">
      <div v-for="group in groups" :key="group.name" class="stream-chain">
        <span class="chain-name">{{ group.name }}</span>
        <div class="stream-steps">
          <template v-for="(step, index) in group.steps" :key="step.node">
            <span
              class="stream-step"
              :class="{ active: step.status === 'running', done: step.status === 'completed' }"
            >
              <Check v-if="step.status === 'completed'" :size="11" />
              <Loader2 v-else :size="11" class="spin" />
              {{ step.label }}
            </span>
            <ArrowRight v-if="index < group.steps.length - 1" :size="11" class="step-arrow" />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check, Loader2, ArrowRight } from 'lucide-vue-next'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  current: { type: String, default: '' },
})

// 按链路（chain）分组，保持节点出现顺序；无 chain 字段的归入"执行链路"
const groups = computed(() => {
  const map = new Map()
  for (const step of props.steps) {
    const name = step.chain || '执行链路'
    if (!map.has(name)) map.set(name, [])
    map.get(name).push(step)
  }
  return Array.from(map.entries()).map(([name, steps]) => ({ name, steps }))
})
</script>

<style scoped>
.agent-stream-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(239, 246, 255, 0.72);
  border: 1px solid rgba(59, 130, 246, 0.18);
}

.stream-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.stream-title {
  font-size: 12px;
  font-weight: 600;
  color: #4b5563;
  white-space: nowrap;
}

.stream-current {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  font-size: 12px;
  color: #2563eb;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stream-chains {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stream-chain {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chain-name {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 6px;
  padding: 2px 7px;
}

.stream-steps {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.stream-step {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: #6b7280;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.24);
  white-space: nowrap;
}

.stream-step.active {
  color: #1d4ed8;
  border-color: rgba(59, 130, 246, 0.42);
  background: rgba(219, 234, 254, 0.72);
}

.stream-step.done {
  color: #15803d;
  border-color: rgba(22, 163, 74, 0.24);
  background: rgba(240, 253, 244, 0.72);
}

.step-arrow {
  flex: none;
  color: #94a3b8;
}

.spin {
  animation: stream-spin 1s linear infinite;
}

@keyframes stream-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
