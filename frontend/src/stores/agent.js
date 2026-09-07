import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

function createSessionId() {
  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

const PERMISSION_KEY = 'agentPermissionMode'
const SESSION_KEY = 'agentSessionId'
const PROVIDER_KEY = 'agentProvider'
const MODEL_KEY = 'agentModel'

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
  const permissionMode = ref(localStorage.getItem(PERMISSION_KEY) || 'high')
  const provider = ref(localStorage.getItem(PROVIDER_KEY) || 'qwen')
  const model = ref(localStorage.getItem(MODEL_KEY) || 'qwen-plus')
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

  const setPermissionMode = (mode) => {
    permissionMode.value = mode === 'high' ? 'high' : 'normal'
    localStorage.setItem(PERMISSION_KEY, permissionMode.value)
  }

  const setModel = (p, m) => {
    provider.value = p || 'qwen'
    model.value = m || 'qwen-plus'
    localStorage.setItem(PROVIDER_KEY, provider.value)
    localStorage.setItem(MODEL_KEY, model.value)
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

  const completeResponse = (content, avatarEmotion = 'idle') => {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = content
    } else {
      addMessage({ role: 'assistant', content })
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
    permissionMode,
    provider,
    model,
    pendingInterrupt,
    streamSteps,
    currentStreamNode,
    isInterrupting,
    addMessage,
    setAvatarState,
    setPermissionMode,
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
