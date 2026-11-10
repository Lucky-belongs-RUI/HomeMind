<template>
  <div class="page agent-view">
    <h1 class="sr-only">AI 家庭助理</h1>

    <section class="section-panel env-panel">
      <div class="env-head">
        <span class="env-title">
          <Activity :size="14" />
          家庭环境
        </span>
        <span class="env-updated">
          <button type="button" class="env-refresh" title="刷新环境数据" aria-label="刷新环境数据" @click="loadEnvironment">
            <RefreshCw :size="12" :class="{ spinning: envLoading }" />
          </button>
          30 秒自动刷新
        </span>
      </div>
      <div class="env-grid">
        <div v-for="metric in metrics" :key="metric.label" class="env-tile" :class="{ alert: metric.alert }">
          <span class="env-icon" :class="metric.color">
            <component :is="metric.icon" :size="15" />
          </span>
          <div class="env-copy">
            <span class="env-label">{{ metric.label }}</span>
            <span class="env-value">
              {{ metric.value }}<small v-if="metric.unit">{{ metric.unit }}</small>
            </span>
          </div>
        </div>
      </div>
    </section>

    <div class="agent-layout">
      <section class="section-panel chat-card">
        <div class="chat-head">
          <div class="chat-title-wrap">
            <span class="chat-avatar"><Bot :size="18" /></span>
            <div class="min-w-0">
              <h2 class="chat-title">智能对话</h2>
              <p class="chat-subtitle">设备控制、场景联动、家庭咨询</p>
            </div>
          </div>
          <span class="model-chip">{{ selectedModelLabel }}</span>
        </div>

        <AgentStreamPanel
          class="shrink-0"
          :steps="agentStore.streamSteps"
          :current="agentStore.currentStreamNode"
        />

        <ChatWindow class="flex-1 min-h-0" :messages="messages" :thinking="isThinking" @send="sendQuickText" />

        <div class="composer">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            resize="none"
            maxlength="500"
            placeholder="描述你的需求，例如：把卧室空调调到 27 度，并打开加湿器"
            @keydown.enter.exact.prevent="onSendText"
          />
          <div class="composer-bar">
            <div class="composer-left">
              <VoiceRecorder @recorded="onVoiceRecorded" />
              <span class="composer-hint">Enter 发送 · Shift + Enter 换行</span>
            </div>
            <el-button type="primary" :loading="isThinking" :disabled="isInterrupting || !inputText.trim()" @click="onSendText">
              <Send :size="14" class="mr-1.5" />
              发送
            </el-button>
          </div>
        </div>
      </section>

      <aside class="agent-aside">
        <section class="section-panel aside-card">
          <div class="aside-head">
            <div class="aside-head-main">
              <span class="aside-icon"><Settings2 :size="14" /></span>
              <h3 class="aside-title">对话设置</h3>
            </div>
            <span class="assistant-state" :class="statusTone">
              <i></i>
              {{ statusLabel }}
            </span>
          </div>

          <div class="setting-row">
            <div class="setting-copy">
              <span class="setting-label">对话模型</span>
              <span class="setting-desc">{{ selectedModelLabel }}</span>
            </div>
            <el-select
              v-model="selectedModel"
              class="model-select"
              placeholder="请先添加模型"
              @change="onModelChange"
            >
              <el-option
                v-for="opt in modelOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>

          <div class="setting-row">
            <div class="setting-copy">
              <span class="setting-label">语音播报</span>
              <span class="setting-desc">自动朗读助手回复</span>
            </div>
            <el-switch v-model="ttsEnabled" />
          </div>

          <el-button class="reset-chat-btn" plain @click="resetChat">
            <RotateCcw :size="14" class="mr-1.5" />
            重置对话
          </el-button>
        </section>

        <section class="section-panel aside-card quick-card">
          <div class="aside-head">
            <div class="aside-head-main">
              <span class="aside-icon amber"><Zap :size="14" /></span>
              <h3 class="aside-title">快捷指令</h3>
            </div>
          </div>
          <div class="quick-list">
            <button
              v-for="command in quickCommands"
              :key="command"
              class="quick-item"
              type="button"
              @click="sendQuickText(command)"
            >
              <Play :size="11" class="quick-play" />
              <span class="quick-text">{{ command }}</span>
              <ChevronRight :size="13" class="quick-arrow" />
            </button>
          </div>
        </section>
      </aside>
    </div>

    <AgentInterruptPanel
      v-if="agentStore.pendingInterrupt"
      :interrupt="agentStore.pendingInterrupt"
      @submit="submitInterrupt"
      @close="agentStore.clearPendingInterrupt"
    />

    <ModelConfigDialog
      v-model="showModelDialog"
      :loading="modelSaving"
      :config="editingModelConfig"
      @submit="handleCreateModelConfig"
    />

    <el-dialog
      v-model="showModelManager"
      title="模型配置管理"
      width="520px"
      append-to-body
      align-center
    >
      <div v-if="modelConfigs.length" class="manager-list">
        <div v-for="config in modelConfigs" :key="config.id" class="manager-row">
          <div class="manager-main">
            <span class="manager-name">{{ config.name }}</span>
            <span class="manager-meta">
              {{ providerLabel(config.provider) }} · {{ config.model }}
              <template v-if="config.base_url"> · {{ config.base_url }}</template>
            </span>
          </div>
          <div class="manager-actions">
            <el-button link type="primary" @click="openEditModelConfig(config)">编辑</el-button>
            <el-button link type="danger" @click="deleteModelConfiguration(config)">删除</el-button>
          </div>
        </div>
      </div>
      <div v-else class="manager-empty">还没有模型配置，先新增一个再开始对话。</div>

      <template #footer>
        <el-button @click="showModelManager = false">关闭</el-button>
        <el-button type="primary" @click="openCreateModelConfig">新增模型</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  Send,
  Zap,
  Play,
  Thermometer,
  Droplets,
  Wind,
  Activity,
  Sun,
  CloudSun,
  Wifi,
  ShieldAlert,
  Wallet,
  Flame,
  Gauge,
  RotateCcw,
  Bot,
  Settings2,
  ChevronRight,
  RefreshCw,
} from 'lucide-vue-next'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { useVoice } from '@/composables/useVoice'
import { useWebSocket } from '@/composables/useWebSocket'
import { chatWithAgent, getAgentHistory, getAgentOpening, resetAgentChat, resumeAgent, speechToText, textToSpeech, getEnvironment } from '@/api/agent'
import { createModelConfig, deleteModelConfig, listModelConfigs, updateModelConfig } from '@/api/modelConfig'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChatWindow from '@/components/agent/ChatWindow.vue'
import VoiceRecorder from '@/components/agent/VoiceRecorder.vue'
import AgentInterruptPanel from '@/components/agent/AgentInterruptPanel.vue'
import AgentStreamPanel from '@/components/agent/AgentStreamPanel.vue'
import ModelConfigDialog from '@/components/agent/ModelConfigDialog.vue'

const agentStore = useAgentStore()
const userStore = useUserStore()
const { ttsEnabled, playBlob } = useVoice()
const { sendAgentMessage } = useWebSocket()

// 模型列表只包含用户自己新增的配置；不再提供 .env 默认模型选项
const modelConfigs = ref([])
const showModelDialog = ref(false)
const showModelManager = ref(false)
const modelSaving = ref(false)
const editingModelConfig = ref(null)

const messages = computed(() => agentStore.messages)
const isThinking = computed(() => agentStore.isThinking)
const isInterrupting = computed(() => agentStore.isInterrupting)

const statusTone = computed(() => {
  if (agentStore.pendingInterrupt) return 'waiting'
  if (isThinking.value) return 'busy'
  return 'online'
})

const statusLabel = computed(() => {
  if (agentStore.pendingInterrupt) return '等待确认'
  if (isThinking.value) return '思考中'
  return '在线待命'
})

const inputText = ref('')
const currentModelSelection = () =>
  agentStore.modelConfigId ? `config:${agentStore.modelConfigId}` : ''
const selectedModel = ref(currentModelSelection())
const environment = ref({})
const envLoading = ref(false)
let envTimer = null

const modelOptions = computed(() => [
  ...modelConfigs.value.map((config) => ({
    value: `config:${config.id}`,
    provider: config.provider,
    label: `${config.name} · ${config.model}`,
    model: config.model,
  })),
  { value: '__manage__', provider: '', label: '模型管理', model: '' },
])

const selectedModelLabel = computed(() => {
  const option = modelOptions.value.find((item) => item.value === selectedModel.value)
  return option && option.value !== '__manage__' ? option.label : '未配置模型'
})

const metrics = computed(() => [
  { label: '室内温度', value: environment.value.indoor_temperature ?? '--', unit: '°C', icon: Thermometer, color: 'text-orange-500' },
  { label: '室外温度', value: environment.value.outdoor_temperature ?? '--', unit: '°C', icon: CloudSun, color: 'text-sky-500' },
  { label: '室内湿度', value: environment.value.indoor_humidity ?? '--', unit: '%', icon: Droplets, color: 'text-blue-500' },
  { label: '空气质量', value: environment.value.air_quality || '--', unit: '', icon: Wind, color: 'text-emerald-500' },
  { label: '天气', value: environment.value.weather || '--', unit: '', icon: Sun, color: 'text-amber-500' },
  { label: '网络状态', value: environment.value.network_status || '--', unit: '', icon: Wifi, color: 'text-indigo-500' },
  {
    label: '安全警报',
    value: environment.value.security_alarm
      ? environment.value.security_alarm.status === 'alert'
        ? '有告警'
        : '正常'
      : '--',
    unit: '',
    icon: ShieldAlert,
    color: environment.value.security_alarm?.status === 'alert' ? 'text-red-500' : 'text-teal-500',
    alert: environment.value.security_alarm?.status === 'alert',
  },
  { label: '电费余额', value: environment.value.electricity_balance ?? '--', unit: '元', icon: Wallet, color: 'text-amber-500' },
  { label: '水费余额', value: environment.value.water_balance ?? '--', unit: '元', icon: Gauge, color: 'text-cyan-500' },
  { label: '燃气费余额', value: environment.value.gas_balance ?? '--', unit: '元', icon: Flame, color: 'text-orange-500' },
])

const quickCommands = [
  '将卧室空调调整到 27 度',
  '打开客厅灯',
  '把客厅窗帘全部拉开',
  '我要回家了',
  '开启睡眠模式',
  '我感冒了',
  '生成一份家庭情况报告',
]

const loadOpening = async () => {
  if (agentStore.messages.length) return
  try {
    const data = await getAgentOpening(agentStore.sessionId)
    if (data.opening) {
      agentStore.addMessage({ role: 'assistant', content: data.opening })
    }
  } catch (error) {
    // 开场白获取失败时保持空会话，不阻断页面
  }
}

const loadEnvironment = async () => {
  if (envLoading.value) return
  envLoading.value = true
  try {
    environment.value = await getEnvironment()
  } catch (error) {
    // 中控指标加载失败不影响对话
  } finally {
    envLoading.value = false
  }
}

const loadHistory = async () => {
  try {
    const data = await getAgentHistory(agentStore.sessionId)
    if (data.messages?.length) {
      agentStore.loadHistory(data.messages)
    }
  } catch (error) {
    // 历史恢复失败时保留欢迎语，不阻断页面
  }
}

const loadModelConfigs = async () => {
  try {
    modelConfigs.value = await listModelConfigs()
    if (
      agentStore.modelConfigId &&
      !modelConfigs.value.some((config) => config.id === agentStore.modelConfigId)
    ) {
      agentStore.setModel(agentStore.provider, agentStore.model, null)
      selectedModel.value = currentModelSelection()
    }
  } catch (error) {
    // 模型配置加载失败不阻断聊天，继续使用后端默认模型
  }
}

const handleCreateModelConfig = async (payload) => {
  modelSaving.value = true
  try {
    const config = editingModelConfig.value
      ? await updateModelConfig(editingModelConfig.value.id, payload)
      : await createModelConfig(payload)
    await loadModelConfigs()
    agentStore.setModel(config.provider, config.model, config.id)
    selectedModel.value = `config:${config.id}`
    showModelDialog.value = false
    showModelManager.value = false
    editingModelConfig.value = null
    ElMessage.success(`模型配置「${config.name}」已保存`)
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    modelSaving.value = false
  }
}

const openCreateModelConfig = () => {
  editingModelConfig.value = null
  showModelManager.value = false
  showModelDialog.value = true
}

const openEditModelConfig = (config) => {
  editingModelConfig.value = config
  showModelManager.value = false
  showModelDialog.value = true
}

const deleteModelConfiguration = async (config) => {
  try {
    await ElMessageBox.confirm(
      `确定删除模型配置「${config.name}」吗？`,
      '删除模型配置',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch (error) {
    return
  }

  try {
    await deleteModelConfig(config.id)
    await loadModelConfigs()
    if (agentStore.modelConfigId === config.id) {
      agentStore.setModel(agentStore.provider, agentStore.model, null)
      selectedModel.value = ''
    }
    ElMessage.success('模型配置已删除')
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

const providerLabel = (provider) =>
  ({ qwen: '阿里云通义千问', deepseek: 'DeepSeek', zhipu: '智谱 GLM', ollama: '本地 Ollama' }[provider] || provider)

const resetChat = async () => {
  try {
    await ElMessageBox.confirm('确定要清空当前聊天记录吗？此操作不可恢复。', '重置聊天', {
      confirmButtonText: '确认重置',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (error) {
    return
  }

  try {
    await resetAgentChat(agentStore.sessionId)
    agentStore.resetSession()
    await loadOpening()
    ElMessage.success('聊天记录已重置')
  } catch (error) {
    ElMessage.error('重置失败，请稍后再试')
  }
}

onMounted(async () => {
  await loadHistory()
  await loadOpening()
  loadModelConfigs()
  loadEnvironment()
  envTimer = setInterval(loadEnvironment, 30000)
})

onUnmounted(() => {
  if (envTimer) clearInterval(envTimer)
})

const ensureModelSelected = () => {
  if (agentStore.modelConfigId) return true
  ElMessage.warning('请先新增并选择一个模型配置')
  selectedModel.value = ''
  showModelManager.value = true
  return false
}

const onSendText = async () => {
  const text = inputText.value.trim()
  if (!text || isThinking.value || isInterrupting.value) return
  if (!ensureModelSelected()) return
  inputText.value = ''
  await sendMessage(text)
}

const sendQuickText = (text) => {
  if (isThinking.value || isInterrupting.value) return
  if (!ensureModelSelected()) return
  inputText.value = ''
  sendMessage(text)
}

const sendMessage = async (text) => {
  if (!ensureModelSelected()) return
  agentStore.addMessage({ role: 'user', content: text })
  agentStore.setThinking(true)
  agentStore.setAvatarState('thinking')
  agentStore.startStream()

  const sent = sendAgentMessage({
    type: 'chat',
    message: text,
    session_id: agentStore.sessionId,
    provider: agentStore.provider,
    model: agentStore.model,
    model_config_id: agentStore.modelConfigId || undefined,
  })
  if (sent) return

  try {
    const result = await chatWithAgent({
      message: text,
      session_id: agentStore.sessionId,
      provider: agentStore.provider,
      model: agentStore.model,
      model_config_id: agentStore.modelConfigId || undefined,
    })
    await handleAgentResult(result)
  } catch (error) {
    agentStore.addMessage({
      role: 'assistant',
      content: '抱歉，我暂时无法连接智能服务，请稍后再试。',
    })
    agentStore.setAvatarState('sad')
  } finally {
    agentStore.setThinking(false)
    agentStore.finishStream()
  }
}

const handleAgentResult = async (result) => {
  if (result.interrupt) {
    // 只弹出审批/澄清面板，不把问询写入聊天记录
    agentStore.setPendingInterrupt({ ...result.interrupt, thread_id: result.thread_id })
    agentStore.setAvatarState('idle')
    return
  }

  const response = result.response || '好的。'
  agentStore.addMessage({
    role: 'assistant',
    content: response,
    warning: result.model_warning || undefined,
  })
  agentStore.setAvatarState(result.avatar_emotion || 'speaking')

  if (ttsEnabled.value && response) {
    try {
      const audioBlob = await textToSpeech(response)
      playBlob(audioBlob)
    } catch (error) {
      // 语音合成失败不影响对话
    }
  }
}

const submitInterrupt = async (resumeData) => {
  if (!ensureModelSelected()) return
  const interrupt = agentStore.pendingInterrupt
  agentStore.clearPendingInterrupt()
  agentStore.setThinking(true)
  agentStore.setAvatarState('thinking')
  agentStore.startStream()

  const sent = sendAgentMessage({
    type: 'resume',
    thread_id: interrupt.thread_id,
    resume_data: resumeData,
    session_id: agentStore.sessionId,
    provider: agentStore.provider,
    model: agentStore.model,
    model_config_id: agentStore.modelConfigId || undefined,
  })
  if (sent) return

  try {
    const result = await resumeAgent({
      thread_id: interrupt.thread_id,
      resume_data: resumeData,
      provider: agentStore.provider,
      model: agentStore.model,
      model_config_id: agentStore.modelConfigId || undefined,
    })
    await handleAgentResult(result)
  } catch (error) {
    agentStore.addMessage({
      role: 'assistant',
      content: '抱歉，恢复对话时出现问题，请重试。',
    })
    agentStore.setAvatarState('sad')
  } finally {
    agentStore.setThinking(false)
    agentStore.finishStream()
  }
}

const onModelChange = (value) => {
  if (value === '__manage__') {
    selectedModel.value = currentModelSelection()
    showModelManager.value = true
    return
  }

  if (value.startsWith('config:')) {
    const configId = Number(value.slice('config:'.length))
    const config = modelConfigs.value.find((item) => item.id === configId)
    if (config) {
      agentStore.setModel(config.provider, config.model, config.id)
      selectedModel.value = value
    }
  }
}

const onVoiceRecorded = async (audioBlob) => {
  try {
    const result = await speechToText(audioBlob)
    const text = (result.text || '').trim()
    if (text) {
      inputText.value = text
      await sendMessage(text)
    }
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

watch(
  () => userStore.familyId,
  async () => {
    agentStore.clearConversation()
    await loadHistory()
    await loadOpening()
    loadEnvironment()
  },
)
</script>

<style scoped>
.agent-view {
  height: calc(100dvh - 104px);
}

.assistant-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: #2c7a5f;
  background: rgba(236, 253, 245, 0.86);
  border: 1px solid rgba(16, 185, 129, 0.18);
}

.assistant-state i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.16);
}

.assistant-state.busy {
  color: #3f57d6;
  background: rgba(79, 107, 237, 0.08);
  border-color: rgba(79, 107, 237, 0.18);
}

.assistant-state.busy i {
  animation: state-pulse 1.2s ease-in-out infinite;
  box-shadow: 0 0 0 3px rgba(79, 107, 237, 0.14);
}

.assistant-state.waiting {
  color: #9a6b2f;
  background: rgba(255, 251, 235, 0.92);
  border-color: rgba(217, 154, 78, 0.24);
}

@keyframes state-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.8);
  }
}

.env-panel {
  padding: 12px 14px;
  flex: none;
}

.env-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.env-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-700);
}

.env-title svg {
  color: var(--accent);
}

.env-updated {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--ink-400);
}

.env-refresh {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 7px;
  color: var(--ink-400);
}

.env-refresh:hover {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.08);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.env-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}

.env-tile {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 7px 9px;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.6);
}

.env-tile.alert {
  background: rgba(254, 242, 242, 0.9);
  border-color: rgba(239, 68, 68, 0.24);
}

.env-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
}

.env-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.env-label {
  font-size: 10px;
  line-height: 1.2;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.env-value {
  margin-top: 1px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--ink-900);
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.env-value small {
  margin-left: 2px;
  font-size: 9px;
  font-weight: 500;
  color: var(--ink-400);
}

.agent-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.chat-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 16px;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex: none;
}

.chat-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.chat-avatar {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 11px;
  color: #fff;
  background: linear-gradient(135deg, #6d84f2, #4f6bed 55%, #3f57d6);
  box-shadow: 0 6px 16px rgba(79, 107, 237, 0.24);
}

.chat-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--ink-900);
}

.chat-subtitle {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--ink-400);
}

.model-chip {
  flex: none;
  max-width: 210px;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-500);
  background: rgba(255, 255, 255, 0.66);
  border: 1px solid rgba(255, 255, 255, 0.8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composer {
  flex: none;
  padding: 10px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(255, 255, 255, 0.72);
}

.composer :deep(.el-textarea__inner) {
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 2px 4px 6px;
  font-size: 13px;
  line-height: 1.55;
  min-height: 52px !important;
}

.composer :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

.composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 2px;
}

.composer-left {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.composer-hint {
  font-size: 10px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-aside {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.aside-card {
  padding: 14px;
  flex: none;
}

.aside-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.aside-head-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.aside-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
}

.aside-icon.amber {
  color: #b0742e;
  background: rgba(217, 154, 78, 0.14);
}

.aside-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-900);
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 2px;
}

.setting-row + .setting-row {
  border-top: 1px solid rgba(23, 28, 43, 0.06);
}

.setting-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.setting-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-700);
}

.setting-desc {
  margin-top: 1px;
  font-size: 10px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-select {
  width: 118px;
  flex: none;
}

.manager-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.manager-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(23, 28, 43, 0.06);
}

.manager-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.manager-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-900);
}

.manager-meta {
  margin-top: 2px;
  font-size: 11px;
  color: var(--ink-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.manager-actions {
  display: flex;
  align-items: center;
  flex: none;
}

.manager-empty {
  padding: 18px 8px;
  text-align: center;
  font-size: 12px;
  color: var(--ink-400);
}

.reset-chat-btn {
  width: 100%;
  margin-top: 10px;
}

.quick-card {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.quick-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow-y: auto;
}

.quick-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 9px;
  border-radius: 10px;
  font-size: 12px;
  color: var(--ink-500);
  text-align: left;
  transition: background 0.16s ease, color 0.16s ease;
}

.quick-item:hover {
  background: rgba(79, 107, 237, 0.07);
  color: var(--accent-strong);
}

.quick-play {
  flex: none;
  color: #b0742e;
}

.quick-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-arrow {
  flex: none;
  color: #b6bbc8;
}

.quick-item:hover .quick-arrow {
  color: var(--accent);
}

@media (max-width: 1180px) {
  .agent-view {
    height: auto;
  }

  .agent-layout {
    grid-template-columns: 1fr;
    flex: none;
  }

  .chat-card {
    min-height: min(620px, calc(100dvh - 160px));
  }

  .agent-aside {
    overflow: visible;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  .quick-card {
    flex: none;
  }

  .quick-list {
    overflow: visible;
  }
}

@media (max-width: 900px) {
  .env-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .env-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .agent-aside {
    grid-template-columns: 1fr;
  }

  .chat-card {
    min-height: 560px;
    padding: 12px;
  }

  .composer-hint {
    display: none;
  }

  .model-chip {
    display: none;
  }
}
</style>
