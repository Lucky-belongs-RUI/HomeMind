<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    :title="title"
    width="420px"
    align-center
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="confirm-body">
      <div class="confirm-icon" :class="type">
        <AlertTriangle v-if="type === 'danger'" :size="22" />
        <HelpCircle v-else :size="22" />
      </div>
      <div class="confirm-message">{{ message }}</div>
    </div>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button :type="type === 'danger' ? 'danger' : 'primary'" @click="onConfirm">
        {{ confirmText || '确定' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { AlertTriangle, HelpCircle } from 'lucide-vue-next'

defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '' },
  type: { type: String, default: 'primary' },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const onConfirm = () => {
  emit('confirm')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.confirm-body {
  display: flex;
  align-items: center;
  gap: 14px;
}

.confirm-icon {
  display: grid;
  width: 44px;
  height: 44px;
  flex: none;
  place-items: center;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.confirm-icon.danger {
  background: #fdeee8;
  color: #ef4444;
}

.confirm-message {
  color: #1a1a2e;
  line-height: 1.6;
}
</style>