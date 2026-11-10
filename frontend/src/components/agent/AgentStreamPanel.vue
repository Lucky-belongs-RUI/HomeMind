<template>
  <div v-if="steps.length" class="agent-stream-panel" :class="{ collapsed }">
    <div
      class="stream-head"
      role="button"
      tabindex="0"
      aria-expanded="!collapsed"
      @click="toggle"
      @keydown.enter="toggle"
    >
      <span class="stream-toggle">
        <ChevronDown :size="13" class="toggle-icon" :class="{ flipped: !collapsed }" />
      </span>
      <span class="stream-title">执行链路</span>
      <span v-if="current" class="stream-current">
        <Loader2 :size="12" class="spin inline mr-1" />
        {{ current }}
      </span>
      <span v-else-if="allDone" class="stream-done-text">
        <Check :size="11" class="inline mr-1" />
        执行完成
      </span>
      <span v-else class="stream-idle-text">{{ steps.length }} 个节点</span>
      <span class="stream-hint">{{ collapsed ? '展开' : '收起' }}</span>
    </div>

    <!-- 按链路分组展示节点步骤（支持多链路并发，横向滚动） -->
    <div v-show="!collapsed" class="stream-chains">
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
import { ref, computed, watch } from 'vue'
import { Check, Loader2, ArrowRight, ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  current: { type: String, default: '' },
})

// 默认折叠（只占一行）；执行中自动展开，用户手动操作后不再自动干预
const collapsed = ref(true)
let userCollapsed = false

const toggle = () => {
  collapsed.value = !collapsed.value
  userCollapsed = true
}

const allDone = computed(
  () => props.steps.length > 0 && props.steps.every((step) => step.status === 'completed'),
)

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

// 节点进入 running 时自动展开；用户手动折叠/展开后不再自动干预
watch(
  () => props.steps.map((step) => `${step.node}:${step.status}`).join(','),
  () => {
    if (!userCollapsed && props.steps.some((step) => step.status === 'running')) {
      collapsed.value = false
    }
  },
)
</script>

<style scoped>
.agent-stream-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(239, 246, 255, 0.72);
  border: 1px solid rgba(59, 130, 246, 0.18);
}

.agent-stream-panel.collapsed {
  gap: 0;
  padding-bottom: 6px;
}

.stream-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 30px;
  cursor: pointer;
  user-select: none;
  border-radius: 6px;
}

.stream-head:hover {
  background: rgba(59, 130, 246, 0.06);
}

.stream-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 22px;
  height: 22px;
  color: #6b7280;
}

.toggle-icon {
  transition: transform 0.18s ease;
}

.toggle-icon.flipped {
  transform: rotate(180deg);
}

.stream-title {
  flex: none;
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

.stream-done-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #15803d;
  white-space: nowrap;
}

.stream-idle-text {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.stream-hint {
  margin-left: auto;
  flex: none;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

.stream-chains {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
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
  white-space: nowrap;
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
