<template>
  <el-dialog
    append-to-body
    :model-value="modelValue"
    :title="config ? '编辑模型配置' : '新增模型配置'"
    width="480px"
    align-center
    :close-on-click-modal="!loading"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form label-position="top" class="model-form" @submit.prevent>
      <el-form-item label="配置名称" required>
        <el-input v-model="form.name" maxlength="64" placeholder="例如：我的 DeepSeek" />
      </el-form-item>

      <el-form-item label="模型厂商" required>
        <el-select v-model="form.provider" class="w-full" @change="onProviderChange">
          <el-option
            v-for="provider in PROVIDERS"
            :key="provider.value"
            :label="provider.label"
            :value="provider.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="模型名称" required>
        <el-input v-model="form.model" maxlength="128" :placeholder="currentProvider.model" />
      </el-form-item>

      <el-form-item :label="form.provider === 'ollama' ? 'API Key（本地模型可留空）' : 'API Key'" :required="form.provider !== 'ollama' && (!config || providerChanged)">
        <el-input
          v-model="form.api_key"
          type="password"
          show-password
          autocomplete="new-password"
          :placeholder="apiKeyPlaceholder"
        />
      </el-form-item>

      <el-form-item label="Base URL">
        <el-input v-model="form.base_url" maxlength="255" :placeholder="currentProvider.base_url" />
      </el-form-item>

      <p class="form-tip">
        API Key 只保存在服务端加密字段中，接口不会返回明文。本地 Ollama 默认地址为
        <code>http://127.0.0.1:11434/v1</code>。
        <template v-if="config">编辑时 API Key 留空表示保持原 Key 不变。</template>
      </p>
    </el-form>

    <template #footer>
      <el-button :disabled="loading" @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">
        {{ config ? '保存修改' : '保存并使用' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  config: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'submit'])

const PROVIDERS = [
  {
    value: 'qwen',
    label: '阿里云通义千问',
    model: 'qwen-plus',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    model: 'deepseek-chat',
    base_url: 'https://api.deepseek.com/v1',
  },
  {
    value: 'zhipu',
    label: '智谱 GLM',
    model: 'glm-4',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
  },
  {
    value: 'ollama',
    label: '本地 Ollama',
    model: 'qwen2.5:7b',
    base_url: 'http://127.0.0.1:11434/v1',
  },
]

const form = reactive({
  name: '',
  provider: 'qwen',
  model: 'qwen-plus',
  api_key: '',
  base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
})

const currentProvider = computed(
  () => PROVIDERS.find((item) => item.value === form.provider) || PROVIDERS[0],
)

const providerChanged = computed(
  () => Boolean(props.config) && props.config.provider !== form.provider,
)

const reset = () => {
  const provider = PROVIDERS[0]
  form.name = ''
  form.provider = provider.value
  form.model = provider.model
  form.api_key = ''
  form.base_url = provider.base_url
}

const applyConfig = (config) => {
  const provider = PROVIDERS.find((item) => item.value === config.provider) || PROVIDERS[0]
  form.name = config.name || ''
  form.provider = provider.value
  form.model = config.model || provider.model
  form.api_key = ''
  form.base_url = config.base_url || provider.base_url
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      if (props.config) applyConfig(props.config)
      else reset()
    }
  },
)

const apiKeyPlaceholder = computed(() => {
  if (props.config) return '留空则保持原 API Key'
  return form.provider === 'ollama' ? '本地 Ollama 可留空' : '请输入 API Key'
})

const onProviderChange = (value) => {
  const provider = PROVIDERS.find((item) => item.value === value) || PROVIDERS[0]
  form.model = provider.model
  form.base_url = provider.base_url
  if (value === 'ollama') form.api_key = ''
}

const submit = () => {
  const name = form.name.trim()
  const model = form.model.trim()
  const apiKey = form.api_key.trim()
  if (!name) {
    ElMessage.warning('请填写配置名称')
    return
  }
  if (!model) {
    ElMessage.warning('请填写模型名称')
    return
  }
  if (form.provider !== 'ollama' && !apiKey && (!props.config || providerChanged.value)) {
    ElMessage.warning(providerChanged.value ? '切换供应商后请重新填写 API Key' : '请填写 API Key')
    return
  }
  emit('submit', {
    name,
    provider: form.provider,
    model,
    api_key: apiKey || null,
    base_url: form.base_url.trim() || null,
  })
}
</script>

<style scoped>
.model-form {
  display: flex;
  flex-direction: column;
}

.model-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.w-full {
  width: 100%;
}

.form-tip {
  margin: 0;
  font-size: 11px;
  line-height: 1.6;
  color: var(--ink-400);
}

.form-tip code {
  padding: 1px 4px;
  border-radius: 4px;
  background: rgba(79, 107, 237, 0.08);
  color: var(--accent-strong);
}
</style>
