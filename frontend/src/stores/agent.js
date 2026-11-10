import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

function createSessionId() {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

const SESSION_KEY = 'agentSessionId'
const PROVIDER_KEY = 'agentProvider'
const MODEL_KEY = 'agentModel'
const MODEL_CONFIG_KEY = 'agentModelConfigId'

// 各供应商官方默认模型（与后端 factory.PROVIDER_DEFAULT_MODELS 保持一致）
const PROVIDER_DEFAULT_MODELS = {
  qwen: 'qwen-plus',
  deepseek: 'deepseek-v4-flash',
  zhipu: 'glm-4',
  ollama: 'qwen2.5:7b',
}

function getSavedSessionId() {
  const saved = localStorage.getItem(SESSION_KEY)
  if (saved) return saved
  const next = createSessionId()
  localStorage.setItem(SESSION_KEY, next)
  return next
}

export const useAgentStore = defineStore('agent', () => {
  const messages = ref([])
  const avatarState = ref('idle')
  const sessionId = ref(getSavedSessionId())
  const isThinking = ref(false)
  // 默认使用后端 .env 配置的供应商（qwen）
  const savedProvider = localStorage.getItem(PROVIDER_KEY) || 'qwen'
  const savedModel = localStorage.getItem(MODEL_KEY) || ''
  const provider = ref(savedProvider)
  // 模型名归一化：优先使用该供应商的官方默认名，避免旧缓存（如 deepseek-v4-pro）覆盖新配置
  const model = ref(PROVIDER_DEFAULT_MODELS[savedProvider] || savedModel || '')
  const modelConfigId = ref(Number(localStorage.getItem(MODEL_CONFIG_KEY)) || null)
  const pendingInterrupt = ref(null)
  const streamSteps = ref([])
  const currentStreamNode = ref('')

  const isInterrupting = computed(() => Boolean(pendingInterrupt.value))

  const addMessage = (message) => {
    messages.value.push({
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      ...message,
    })
  }

  const setAvatarState = (state) => {
    avatarState.value = state
  }

  const setModel = (p, m, configId = null) => {
    const validProvider = p && PROVIDER_DEFAULT_MODELS[p] ? p : 'qwen'
    provider.value = validProvider
    model.value = m || PROVIDER_DEFAULT_MODELS[validProvider] || 'qwen-plus'
    modelConfigId.value = configId || null
    localStorage.setItem(PROVIDER_KEY, provider.value)
    localStorage.setItem(MODEL_KEY, model.value)
    if (modelConfigId.value) {
      localStorage.setItem(MODEL_CONFIG_KEY, String(modelConfigId.value))
    } else {
      localStorage.removeItem(MODEL_CONFIG_KEY)
    }
  }

  const setPendingInterrupt = (info) => {
    pendingInterrupt.value = info
  }

  const clearPendingInterrupt = () => {
    pendingInterrupt.value = null
  }

  const setStreamStep = ({ node, label, status, chain }) => {
    const existing = streamSteps.value.find((item) => item.node === node)
    if (existing) {
      existing.label = label
      existing.status = status
      if (chain) existing.chain = chain
    } else {
      streamSteps.value.push({ node, label, status, chain: chain || '' })
    }
    if (status === 'running') {
      currentStreamNode.value = label
    }
  }

  const startStream = () => {
    streamSteps.value = []
    currentStreamNode.value = ''
  }

  const finishStream = () => {
    streamSteps.value = streamSteps.value.map((step) => ({
      ...step,
      status: step.status === 'running' ? 'completed' : step.status,
    }))
    currentStreamNode.value = ''
  }

  // Agent 流式输出：追加到最后一条 assistant 消息
  const appendToken = (token) => {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = `${last.content || ''}${token}`
    } else {
      addMessage({ role: 'assistant', content: token })
    }
  }

  const completeResponse = (content, avatarEmotion = 'idle', modelWarning = null) => {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = content
      if (modelWarning) last.warning = modelWarning
    } else {
      addMessage({ role: 'assistant', content, warning: modelWarning || undefined })
    }
    isThinking.value = false
    avatarState.value = avatarEmotion || 'idle'
    finishStream()
  }

  const setThinking = (thinking) => {
    isThinking.value = thinking
  }

  const loadHistory = (history = []) => {
    messages.value = history.map((item, index) => ({
      id: `history_${item.created_at || Date.now()}_${index}`,
      role: item.role,
      content: item.content,
    }))
  }

  const clearConversation = () => {
    messages.value = []
    avatarState.value = 'idle'
    isThinking.value = false
    pendingInterrupt.value = null
    startStream()
  }

  const resetSession = () => {
    clearConversation()
    sessionId.value = createSessionId()
    localStorage.setItem(SESSION_KEY, sessionId.value)
  }

  return {
    messages,
    avatarState,
    sessionId,
    isThinking,
    provider,
    model,
    modelConfigId,
    pendingInterrupt,
    streamSteps,
    currentStreamNode,
    isInterrupting,
    addMessage,
    setAvatarState,
    setModel,
    setPendingInterrupt,
    clearPendingInterrupt,
    setStreamStep,
    startStream,
    finishStream,
    appendToken,
    completeResponse,
    setThinking,
    loadHistory,
    clearConversation,
    resetSession,
  }
})
