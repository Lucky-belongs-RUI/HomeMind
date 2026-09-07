<template>
  <el-dialog
    :model-value="true"
    :title="isApproval ? '操作审批' : '需要您补充说明'"
    width="560px"
    append-to-body
    :close-on-click-modal="false"
    class="agent-interrupt-dialog"
    @close="$emit('close')"
  >
    <div v-if="interrupt" class="interrupt-body">
      <!-- 中断询问：问题 + 选项 + 文本输入 -->
      <template v-if="!isApproval">
        <div class="question-box">
          <HelpCircle :size="17" class="text-blue-500 shrink-0 mt-0.5" />
          <p class="text-sm text-gray-700 leading-relaxed">{{ interrupt.question || '请补充说明您的需求。' }}</p>
        </div>

        <div v-if="interrupt.options && interrupt.options.length" class="flex flex-wrap gap-2 mt-3">
          <button
            v-for="option in interrupt.options"
            :key="option"
            type="button"
            class="px-3 py-1.5 rounded-lg text-xs border transition-colors"
            :class="answer === option
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white/70 text-gray-600 border-white/40 hover:border-blue-300 hover:text-blue-600'"
            @click="answer = option"
          >
            {{ option }}
          </button>
        </div>

        <el-input
          v-model="answer"
          type="textarea"
          :rows="3"
          resize="none"
          class="mt-3"
          placeholder="直接输入您的回答，例如：卧室空调，调到 26 度"
        />
      </template>

      <!-- 中断审批：任务列表 + 勾选 -->
      <template v-else>
        <div class="flex items-center justify-between mb-3">
          <span class="text-xs text-gray-500">
            共 {{ approvalTasks.length }} 个待执行任务
            <el-tag :type="riskTagType" size="small" class="ml-2" effect="plain">
              风险：{{ riskLabel }}
            </el-tag>
          </span>
          <div class="flex gap-2">
            <el-button size="small" @click="selectAll(true)">全选</el-button>
            <el-button size="small" @click="selectAll(false)">反选</el-button>
          </div>
        </div>

        <div class="approval-list">
          <div
            v-for="task in approvalTasks"
            :key="task.task_id"
            class="approval-item"
            :class="{ checked: selectedIds.includes(task.task_id) }"
          >
            <el-checkbox
              :model-value="selectedIds.includes(task.task_id)"
              @change="(value) => toggleTask(task.task_id, value)"
            />
            <div class="flex-1 min-w-0">
              <p class="text-sm text-gray-800 font-medium truncate">{{ task.description }}</p>
              <p class="text-xs text-gray-500 mt-0.5 line-clamp-2">{{ task.expected_effect }}</p>
            </div>
            <el-tag :type="taskRiskType(task.risk_level)" size="small" effect="plain">
              {{ taskRiskLabel(task.risk_level) }}
            </el-tag>
          </div>
          <div v-if="!approvalTasks.length" class="py-8 text-center text-sm text-gray-400">
            暂无可审批任务
          </div>
        </div>
      </template>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <el-button @click="handleCancel">取消</el-button>
        <el-button type="primary" :disabled="!canSubmit" @click="handleSubmit">
          {{ isApproval ? '确认执行' : '提交回答' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { HelpCircle } from 'lucide-vue-next'

const props = defineProps({
  interrupt: { type: Object, default: null },
})

const emit = defineEmits(['submit', 'close'])

const answer = ref('')
const selectedIds = ref([])

const isApproval = computed(() => props.interrupt?.type === 'approval')
const approvalTasks = computed(() => props.interrupt?.tasks || [])
const riskLevel = computed(() => props.interrupt?.risk_level || 'low')
const canSubmit = computed(() => {
  if (isApproval.value) return selectedIds.value.length > 0
  return Boolean(answer.value.trim())
})

const riskTagType = computed(() => ({ low: 'success', medium: 'warning', high: 'danger' }[riskLevel.value] || 'info'))
const riskLabel = computed(() => ({ low: '低', medium: '中', high: '高' }[riskLevel.value] || '未知'))

const taskRiskType = (level) => ({ low: 'success', medium: 'warning', high: 'danger' }[level] || 'info')
const taskRiskLabel = (level) => ({ low: '低', medium: '中', high: '高' }[level] || '未知')

// 弹窗每次打开时重置选择状态
if (props.interrupt?.type === 'approval') {
  selectedIds.value = (props.interrupt.tasks || []).map((task) => task.task_id)
}

const selectAll = (checked) => {
  selectedIds.value = checked
    ? approvalTasks.value.map((task) => task.task_id)
    : []
}

const toggleTask = (taskId, checked) => {
  if (checked) {
    if (!selectedIds.value.includes(taskId)) selectedIds.value.push(taskId)
  } else {
    selectedIds.value = selectedIds.value.filter((id) => id !== taskId)
  }
}

const handleSubmit = () => {
  if (isApproval.value) {
    emit('submit', { approved: true, task_ids: selectedIds.value })
  } else {
    emit('submit', { answer: answer.value.trim() })
  }
}

const handleCancel = () => {
  if (isApproval.value) {
    emit('submit', { approved: false, task_ids: [] })
  } else {
    emit('close')
  }
}
</script>

<style scoped>
.interrupt-body {
  padding: 2px 0 4px;
}

.question-box {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(239, 246, 255, 0.72);
  border: 1px solid rgba(59, 130, 246, 0.18);
}

.approval-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 2px;
}

.approval-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: rgba(255, 255, 255, 0.62);
  transition: border-color 0.2s ease, background 0.2s ease;
}

.approval-item.checked {
  border-color: rgba(59, 130, 246, 0.4);
  background: rgba(239, 246, 255, 0.62);
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>