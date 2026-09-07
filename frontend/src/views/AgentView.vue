<template>
  <div class="page agent-view flex flex-col gap-3 min-h-0">
    <!-- 顶部中控指标：室内外温度、湿度、空气质量等居中展示 -->
    <section class="env-bar section-panel shrink-0 px-4 py-2.5">
      <div class="env-metrics flex flex-wrap items-center justify-center gap-x-5 gap-y-2 min-w-0">
        <div v-for="metric in metrics" :key="metric.label" class="env-metric">
          <component :is="metric.icon" :size="16" :class="metric.color" class="shrink-0" />
          <div class="flex flex-col min-w-0">
            <span class="text-[11px] text-gray-400 leading-none">{{ metric.label }}</span>
            <span class="text-sm font-bold text-gray-800 leading-tight whitespace-nowrap">
              {{ metric.value }}<span v-if="metric.unit" class="text-[10px] font-medium text-gray-400 ml-0.5">{{ metric.unit }}</span>
            </span>
          </div>
        </div>
      </div>
    </section>

    <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4 items-stretch flex-1 min-h-0">
      <section class="section-panel flex flex-col gap-3 min-h-[520px] xl:min-h-0 xl:h-full">
        <div class="flex items-center justify-between shrink-0">
          <span class="text-sm font-bold text-gray-800 flex items-center gap-1.5">
            <MessageCircle :size="15" class="text-blue-500" />
            智能对话
          </span>
          <button
            type="button"
            class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-gray-500 bg-white/60 border border-white/30 hover:border-red-300 hover:text-red-500 hover:bg-red-50 transition-all"
            @click="resetChat"
          >
            <RotateCcw :size="13" />
            重置聊天
          </button>
        </div>
        <AgentStreamPanel
          class="shrink-0"
          :steps="agentStore.streamSteps"
          :current="agentStore.currentStreamNode"
        />
        <ChatWindow class="flex-1 min-h-0" :messages="messages" :thinking="isThinking" @send="sendQuickText" />
      </section>

      <aside class="section-panel flex flex-col gap-4 min-h-0 xl:h-full overflow-y-auto pr-1">
        <div>
          <div class="flex items-center gap-2 mb-2">
            <Sparkles :size="15" class="text-blue-500" />
            <span class="text-sm font-bold text-gray-800">发送指令</span>
          </div>
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="例如：将卧室空调调整到 27 度"
            @keydown.enter.exact.prevent="onSendText"
          />
        </div>

        <div class="flex items-center gap-2 flex-wrap">
          <VoiceRecorder @recorded="onVoiceRecorded" />
          <span class="flex items-center gap-1.5 text-xs text-gray-500">
            语音播报
            <el-switch v-model="ttsEnabled" size="small" />
          </span>
          <span class="ml-auto flex items-center gap-1.5 text-xs text-gray-500">
            高级模式
            <el-switch
              :model-value="agentStore.permissionMode === 'high'"
              size="small"
              @change="onPermissionChange"
            />
          </span>
          <el-select
            v-model="selectedModel"
            class="model-select"
            placeholder="选择模型"
            @change="onModelChange"
          >
            <el-option
              v-for="opt in MODEL_OPTIONS"
              :key="opt.provider"
              :label="opt.label"
              :value="opt.provider"
            >
              <span class="flex items-center justify-between gap-2">
                <span>{{ opt.label }}</span>
                <span class="text-xs text-gray-400">{{ opt.model }}</span>
              </span>
            </el-option>
          </el-select>
          <el-button type="primary" :loading="isThinking" :disabled="isInterrupting" @click="onSendText">
            <Send :size="14" class="mr-1" />
            发送
          </el-button>
        </div>

        <div class="pt-3 border-t border-white/40">
          <div class="flex items-center gap-2 mb-2.5">
            <Zap :size="15" class="text-amber-500" />
            <span class="text-sm font-bold text-gray-800">快捷指令</span>
          </div>
          <div class="flex flex-col gap-2">
            <button
              v-for="command in quickCommands"
              :key="command"
              class="flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs text-left text-gray-500 bg-white/60 border border-white/30 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50 transition-all"
              type="button"
              @click="sendQuickText(command)"
            >
              <Play :size="12" class="shrink-0" />
              <span class="truncate">{{ command }}</span>
            </button>
          </div>
        </div>
      </aside>
    </div>

    <AgentInterruptPanel
      v-if="agentStore.pendingInterrupt"
      :interrupt="agentStore.pendingInterrupt"
      @submit="submitInterrupt"
      @close="agentStore.clearPendingInterrupt"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  Sparkles,
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
  MessageCircle,
  RotateCcw,
} from 'lucide-vue-next'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import { useVoice } from '@/composables/useVoice'
import { useWebSocket } from '@/composables/useWebSocket'
import { chatWithAgent, getAgentHistory, getAgentOpening, resetAgentChat, resumeAgent, speechToText, textToSpeech, getEnvironment } from '@/api/agent'
import { ElMessage, ElMessageBox } from 'element-plus'
import ChatWindow from '@/components/agent/ChatWindow.vue'
import VoiceRecorder from '@/components/agent/VoiceRecorder.vue'
import AgentInterruptPanel from '@/components/agent/AgentInterruptPanel.vue'
import AgentStreamPanel from '@/components/agent/AgentStreamPanel.vue'

const agentStore = useAgentStore()
const userStore = useUserStore()
const { ttsEnabled, playBlob } = useVoice()
const { sendAgentMessage } = useWebSocket()

// 可选模型列表（与后端 factory.SUPPORTED_PROVIDERS 保持一致）
const MODEL_OPTIONS = [
  { provider: 'qwen', label: '通义千问', model: 'qwen-plus' },
  { provider: 'deepseek', label: 'DeepSeek', model: 'deepseek-v4-pro' },
  { provider: 'zhipu', label: '智谱 GLM', model: 'glm-4' },
  { provider: 'ollama', label: '本地 Ollama', model: 'qwen2.5:7b' },
]

const messages = computed(() => agentStore.messages)
const isThinking = computed(() => agentStore.isThinking)
const isInterrupting = computed(() => agentStore.isInterrupting)

const inputText = ref('')
const selectedModel = ref(agentStore.provider || 'qwen')
const environment = ref({})
const envLoading = ref(false)
let envTimer = null

const metrics = computed(() => [
  { label: '室内温度', value: environment.value.indoor_temperature ?? '--', unit: '°C', icon: Thermometer, color: 'text-orange-500' },
  { label: '室外温度', value: environment.value.outdoor_temperature ?? '--', unit: '°C', icon: CloudSun, color: 'text-sky-500' },
  { label: '室内湿度', value: environment.value.indoor_humidity ?? '--', unit: '%', icon: Droplets, color: 'text-blue-500' },
  { label: '空气质量', value: environment.value.air_quality || '--', unit: '', icon: Wind, color: 'text-green-500' },
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
  loadEnvironment()
  envTimer = setInterval(loadEnvironment, 30000)
})

onUnmounted(() => {
  if (envTimer) clearInterval(envTimer)
})

const onSendText = async () => {
  const text = inputText.value.trim()
  if (!text || isThinking.value || isInterrupting.value) return
  inputText.value = ''
  await sendMessage(text)
}

const sendQuickText = (text) => {
  if (isThinking.value || isInterrupting.value) return
  inputText.value = ''
  sendMessage(text)
}

const sendMessage = async (text) => {
  agentStore.addMessage({ role: 'user', content: text })
  agentStore.setThinking(true)
  agentStore.setAvatarState('thinking')
  agentStore.startStream()

  const sent = sendAgentMessage({
    type: 'chat',
    message: text,
    session_id: agentStore.sessionId,
    permission_mode: agentStore.permissionMode,
    provider: agentStore.provider,
    model: agentStore.model,
  })
  if (sent) return

  try {
    const result = await chatWithAgent({
      message: text,
      session_id: agentStore.sessionId,
      permission_mode: agentStore.permissionMode,
      provider: agentStore.provider,
      model: agentStore.model,
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
    agentStore.addMessage({
      role: 'assistant',
      content: result.interrupt.question || '需要您确认以下操作。',
    })
    agentStore.setPendingInterrupt({ ...result.interrupt, thread_id: result.thread_id })
    agentStore.setAvatarState('idle')
    return
  }

  const response = result.response || '好的。'
  agentStore.addMessage({ role: 'assistant', content: response })
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
  })
  if (sent) return

  try {
    const result = await resumeAgent({
      thread_id: interrupt.thread_id,
      resume_data: resumeData,
      provider: agentStore.provider,
      model: agentStore.model,
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
  const opt = MODEL_OPTIONS.find((item) => item.provider === value)
  agentStore.setModel(opt ? opt.provider : value, opt ? opt.model : '')
  selectedModel.value = agentStore.provider
}

const onPermissionChange = (value) => {
  agentStore.setPermissionMode(value ? 'high' : 'normal')
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
.env-bar {
  min-height: 56px;
}

.env-metric {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.model-select {
  width: 140px;
}
</style>
