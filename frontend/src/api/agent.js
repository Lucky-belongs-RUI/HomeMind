import request from './request'

export const chatWithAgent = (payload) => request.post('/agent/chat', payload)

// 中断恢复：clarification 传 { answer }，approval 传 { approved, task_ids }
export const resumeAgent = (payload) => request.post('/agent/resume', payload)

// 语音转文字：上传录音文件
export const speechToText = (audioBlob) => {
  const formData = new FormData()
  formData.append('file', audioBlob, 'voice.wav')
  return request.post('/agent/stt', formData)
}

// 文字转语音：返回音频 Blob，由前端 Audio 播放
export const textToSpeech = (text) =>
  request.post('/agent/tts', { text }, { responseType: 'blob' })

// 家庭中控指标：温度、湿度、空气质量、光照
export const getEnvironment = () => request.get('/agent/environment')

// 会话历史：刷新页面后恢复聊天记录
export const getAgentHistory = (sessionId) =>
  request.get('/agent/history', { params: { session_id: sessionId } })

// 首次进入聊天界面：获取全屋状态动态开场白
export const getAgentOpening = (sessionId) =>
  request.post('/agent/opening', { session_id: sessionId })

// 重置会话：清空当前会话的全部聊天记录
export const resetAgentChat = (sessionId) =>
  request.post('/agent/reset', { session_id: sessionId })