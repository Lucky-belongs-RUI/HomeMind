import { ref, onMounted } from 'vue'
import { useDeviceStore } from '@/stores/device'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'

const isConnected = ref(false)

let ws = null
let started = false
let intentionalClose = false
let reconnectAttempts = 0
let heartbeatTimer = null

function dispatch(data) {
  const userStore = useUserStore()
  const deviceStore = useDeviceStore()
  const agentStore = useAgentStore()

  switch (data.type) {
    case 'device_status_update':
      // 家庭隔离：仅处理当前家庭的设备更新
      if (data.family_id === userStore.familyId) {
        deviceStore.updateDeviceFromWS(data)
      }
      break
    case 'agent_token':
      agentStore.appendToken(data.content)
      break
    case 'agent_step':
      agentStore.setStreamStep({
        node: data.node,
        label: data.label,
        status: data.status,
        chain: data.chain,
      })
      break
    case 'agent_done':
      agentStore.completeResponse(data.content, data.avatar_emotion)
      break
    case 'agent_error':
      agentStore.addMessage({
        role: 'assistant',
        content: data.content || '抱歉，智能服务暂时不可用，请稍后再试。',
      })
      agentStore.setThinking(false)
      agentStore.finishStream()
      agentStore.setAvatarState('sad')
      break
    case 'avatar_state':
      agentStore.setAvatarState(data.state)
      break
    case 'agent_interrupt':
      // WebSocket 场景下收到中断：展示询问/审批面板
      if (data.interrupt && !agentStore.pendingInterrupt) {
        agentStore.setPendingInterrupt(data.interrupt)
        agentStore.setThinking(false)
        agentStore.finishStream()
      }
      break
  }
}

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }))
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer)
  heartbeatTimer = null
}

function connect() {
  // 防重入：连接已建立或正在建立时直接返回
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return

  const userStore = useUserStore()
  const baseUrl =
    import.meta.env?.VITE_WS_URL || `ws://${window.location.hostname}:8000/api/agent/ws`
  const separator = baseUrl.includes('?') ? '&' : '?'
  const wsUrl = `${baseUrl}${separator}token=${encodeURIComponent(userStore.token || '')}`
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    isConnected.value = true
    reconnectAttempts = 0
    startHeartbeat()
  }

  ws.onmessage = (event) => {
    try {
      dispatch(JSON.parse(event.data))
    } catch (error) {
      console.error('WebSocket 消息解析失败:', error)
    }
  }

  ws.onclose = () => {
    isConnected.value = false
    stopHeartbeat()
    ws = null
    // 主动关闭（登出）不重连；异常断开最多重试 5 次
    if (!intentionalClose && reconnectAttempts < 5) {
      reconnectAttempts += 1
      setTimeout(connect, 3000)
    }
  }

  ws.onerror = (error) => {
    console.error('WebSocket 错误:', error)
  }
}

function ensureConnect() {
  if (started) return
  started = true
  connect()
}

function sendAgentMessage(payload) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload))
    return true
  }
  ensureConnect()
  return false
}

function closeWs() {
  intentionalClose = true
  stopHeartbeat()
  if (ws) {
    ws.onclose = null
    try {
      ws.close()
    } catch (error) {
      console.error('WebSocket 关闭失败:', error)
    }
  }
  ws = null
  isConnected.value = false
  started = false
  reconnectAttempts = 0
}

/**
 * 全局单例 WebSocket：多个页面复用同一连接。
 * 设备状态推送按当前家庭过滤，Agent 流式输出分发到对话 store。
 */
export function useWebSocket() {
  onMounted(ensureConnect)

  return { isConnected, closeWs, sendAgentMessage }
}
