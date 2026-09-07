import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const TTS_KEY = 'ttsEnabled'

/**
 * 语音能力：录音（Web Audio API 采集 WAV）与语音播报（播放后端 TTS 返回的音频）。
 */
export function useVoice() {
  const isRecording = ref(false)
  const ttsEnabled = ref(localStorage.getItem(TTS_KEY) !== 'false')

  let stream = null
  let audioContext = null
  let sourceNode = null
  let processorNode = null
  let chunks = []
  let audioEl = null

  watch(ttsEnabled, (value) => {
    localStorage.setItem(TTS_KEY, value ? 'true' : 'false')
  })

  const playBlob = (blob) => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const play = () => {
      const audio = new Audio(url)
      audioEl = audio
      audio.onended = () => {
        URL.revokeObjectURL(url)
        if (audioEl === audio) audioEl = null
      }
      audio.onerror = () => {
        URL.revokeObjectURL(url)
        if (audioEl === audio) audioEl = null
      }
      audio.play().catch(() => {
        URL.revokeObjectURL(url)
        if (audioEl === audio) audioEl = null
      })
    }
    if (audioEl) {
      audioEl.pause()
      audioEl = null
    }
    play()
  }

  const stopTracks = () => {
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
  }

  const cleanupNodes = () => {
    if (processorNode) {
      processorNode.onaudioprocess = null
      try {
        processorNode.disconnect()
      } catch (error) {
        // 节点可能已断开
      }
      processorNode = null
    }
    if (sourceNode) {
      try {
        sourceNode.disconnect()
      } catch (error) {
        // 节点可能已断开
      }
      sourceNode = null
    }
    if (audioContext && audioContext.state !== 'closed') {
      audioContext.close().catch(() => {})
    }
    audioContext = null
  }

  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      ElMessage.error('当前浏览器不支持录音')
      return false
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioContext = new (window.AudioContext || window.webkitAudioContext)()
      sourceNode = audioContext.createMediaStreamSource(stream)
      processorNode = audioContext.createScriptProcessor(4096, 1, 1)
      chunks = []
      processorNode.onaudioprocess = (event) => {
        chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
      }
      sourceNode.connect(processorNode)
      processorNode.connect(audioContext.destination)
      isRecording.value = true
      return true
    } catch (error) {
      ElMessage.error('无法访问麦克风，请检查浏览器权限')
      cleanupNodes()
      stopTracks()
      return false
    }
  }

  const stopRecording = () =>
    new Promise((resolve) => {
      if (!audioContext || !isRecording.value) {
        cleanupNodes()
        stopTracks()
        resolve(null)
        return
      }
      const sampleRate = audioContext.sampleRate
      processorNode.onaudioprocess = null
      cleanupNodes()
      stopTracks()
      isRecording.value = false

      const samples = concatChunks(chunks)
      resolve(encodeWav(samples, sampleRate))
    })

  return { isRecording, ttsEnabled, playBlob, startRecording, stopRecording }
}

function concatChunks(chunks) {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const result = new Float32Array(total)
  let offset = 0
  chunks.forEach((chunk) => {
    result.set(chunk, offset)
    offset += chunk.length
  })
  return result
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeString = (offset, value) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}
