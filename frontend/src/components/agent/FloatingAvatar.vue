<template>
  <div
    v-if="visible"
    ref="rootRef"
    class="floating-avatar"
    :class="{ dragging, minimized }"
    :style="{
      left: `${position.left}px`,
      top: `${position.top}px`,
      width: `${currentSize}px`,
      height: `${currentSize}px`,
    }"
    role="button"
    tabindex="0"
    :title="minimized ? '展开 AI 智能助理' : 'AI 智能助理（可拖拽，点击进入）'"
    :aria-label="minimized ? '展开 AI 智能助理' : 'AI 智能助理，可拖拽，点击进入助理页'"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
    @keydown.enter.prevent="onActivate"
    @keydown.space.prevent="onActivate"
  >
    <button
      v-if="!minimized"
      type="button"
      class="avatar-dock"
      title="收起悬浮头像"
      aria-label="收起悬浮头像"
      @pointerdown.stop
      @click.stop="minimize"
    >
      <Minus :size="11" />
    </button>

    <div class="avatar-glow" :class="state"></div>
    <div class="avatar-core" :class="state">
      <img
        :src="currentImage"
        alt="AI 智能助理"
        class="avatar-image"
        draggable="false"
      />
    </div>
    <div v-if="!minimized && state === 'speaking'" class="mini-bars">
      <span v-for="i in 3" :key="i"></span>
    </div>
    <div v-if="!minimized && state === 'thinking'" class="mini-dots">
      <span v-for="i in 3" :key="i"></span>
    </div>
    <span class="status-dot" :class="state"></span>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Minus } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { useAgentStore } from '@/stores/agent'
import { useUserStore } from '@/stores/user'
import idleImage from '@/assets/avatar/idle.png'
import greetingImage from '@/assets/avatar/greeting.png'
import leisureImage from '@/assets/avatar/leisure.png'
import sideImage from '@/assets/avatar/side.png'
import securityImage from '@/assets/avatar/security.png'
import workingImage from '@/assets/avatar/working.png'
import controllingImage from '@/assets/avatar/controlling.png'
import sleepingImage from '@/assets/avatar/sleeping.png'
import energySavingImage from '@/assets/avatar/energy-saving.png'

const MINI_SIZE = 52
const STORAGE_KEY = 'smart-home-avatar-position'

const route = useRoute()
const router = useRouter()
const agentStore = useAgentStore()
const userStore = useUserStore()

const rootRef = ref(null)
const position = ref(loadPosition() || { left: 0, top: 0 })
const dragging = ref(false)
const minimized = ref(false)
const viewportWidth = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)
const viewportHeight = ref(typeof window === 'undefined' ? 900 : window.innerHeight)
let moved = false
let startX = 0
let startY = 0
let startLeft = 0
let startTop = 0

const state = computed(() => agentStore.avatarState)
const isAgentRoute = computed(() => route.path.startsWith('/agent'))
const visible = computed(() => userStore.isLoggedIn && !isAgentRoute.value)

function sizeForWidth(width) {
  if (width <= 640) return 64
  if (width <= 1024) return 80
  return 96
}

const currentSize = computed(() => (minimized.value ? MINI_SIZE : sizeForWidth(viewportWidth.value)))

const avatarImages = {
  idle: idleImage,
  greeting: greetingImage,
  leisure: leisureImage,
  side: sideImage,
  security: securityImage,
  working: workingImage,
  controlling: controllingImage,
  sleeping: sleepingImage,
  energy_saving: energySavingImage,
  speaking: idleImage,
  thinking: workingImage,
  happy: leisureImage,
  sad: sideImage,
  caring: leisureImage,
  neutral: idleImage,
}

const IDLE_SCENE_ORDER = ['idle', 'side']
const IDLE_ROTATE_MS = 4000
const MIN_EXPRESSION_MS = 10000
const GREETING_MS = 10000
const EXIT_SECURITY_MS = 10000
const INACTIVITY_STEPS = [
  { delay: 30000, state: 'leisure' },
  { delay: 15000, state: 'energy_saving' },
  { delay: 15000, state: 'sleeping' },
]
const INACTIVITY_START_BY_STATE = {
  idle: 0,
  neutral: 0,
  speaking: 0,
  greeting: 0,
  leisure: 1,
  energy_saving: 2,
  sleeping: 3,
}
const idleSceneIndex = ref(0)
let idleTimer = null
let greetingTimer = null
let inactivityTimer = null
let inactivityStep = 0
let inactivityAdvancing = false
let exitSecurityTimer = null
let lastPoseChangeAt = 0

const currentImage = computed(() => {
  const active = state.value
  if (active === 'speaking' || active === 'idle' || active === 'neutral') {
    return avatarImages[IDLE_SCENE_ORDER[idleSceneIndex.value]] || avatarImages.idle
  }
  return avatarImages[active] || avatarImages.idle
})

function stopIdleRotation() {
  if (idleTimer) clearInterval(idleTimer)
  idleTimer = null
}

function startIdleRotation() {
  stopIdleRotation()
  idleTimer = setInterval(() => {
    if (state.value === 'idle' || state.value === 'neutral' || state.value === 'speaking') {
      if (Date.now() - lastPoseChangeAt < MIN_EXPRESSION_MS) return
      idleSceneIndex.value = Math.random() < 0.5 ? 0 : 1
      markPoseChanged()
    }
  }, IDLE_ROTATE_MS)
}

function clearInactivityTimer() {
  if (inactivityTimer) clearTimeout(inactivityTimer)
  inactivityTimer = null
  inactivityStep = 0
  inactivityAdvancing = false
}

function scheduleNextInactivityStep() {
  const step = INACTIVITY_STEPS[inactivityStep]
  if (!step) {
    inactivityTimer = null
    return
  }
  inactivityTimer = setTimeout(() => {
    inactivityAdvancing = true
    agentStore.setAvatarState(step.state)
    inactivityStep += 1
    inactivityAdvancing = false
    scheduleNextInactivityStep()
  }, step.delay)
}

function startInactivityTimer(startStep = 0) {
  clearInactivityTimer()
  inactivityStep = startStep
  scheduleNextInactivityStep()
}

function syncInactivityForState(value) {
  if (value === 'thinking') {
    clearInactivityTimer()
    return
  }
  const startStep = INACTIVITY_START_BY_STATE[value]
  if (startStep === undefined) {
    clearInactivityTimer()
    return
  }
  if (inactivityAdvancing) return
  startInactivityTimer(startStep)
}

function onUserActivity() {
  clearTimeout(exitSecurityTimer)
  exitSecurityTimer = null
  const active = agentStore.avatarState
  if (!['thinking', 'speaking'].includes(active)) {
    agentStore.setAvatarState('idle')
  }
  syncInactivityForState(agentStore.avatarState)
}

function markPoseChanged() {
  lastPoseChangeAt = Date.now()
}

function handleStateChange(value) {
  markPoseChanged()
  clearTimeout(greetingTimer)
  greetingTimer = null
  idleSceneIndex.value = 0
  if (value === 'greeting') {
    greetingTimer = setTimeout(() => {
      agentStore.setAvatarState('idle')
    }, GREETING_MS)
  }
  syncInactivityForState(value)
}

// 位置与视口一起存储：视口宽度变化过大时位置已失效，回退到默认位置
const VIEWPORT_TOLERANCE = 240

function loadPosition() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const pos = JSON.parse(raw)
    if (typeof pos.left !== 'number' || typeof pos.top !== 'number') return null
    if (typeof pos.vw !== 'number' || Math.abs(pos.vw - window.innerWidth) > VIEWPORT_TOLERANCE) {
      return null
    }
    return { left: pos.left, top: pos.top }
  } catch (error) {
    // 本地位置读取失败时使用默认位置
  }
  return null
}

function savePosition() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        left: position.value.left,
        top: position.value.top,
        vw: window.innerWidth,
        vh: window.innerHeight,
      }),
    )
  } catch (error) {
    // 存储失败不影响拖拽
  }
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function clampToViewport() {
  const size = currentSize.value
  const maxLeft = Math.max(8, window.innerWidth - size - 8)
  const maxTop = Math.max(8, window.innerHeight - size - 8)
  position.value = {
    left: clamp(position.value.left, 8, maxLeft),
    top: clamp(position.value.top, 8, maxTop),
  }
}

function defaultPosition() {
  const size = currentSize.value
  return {
    left: Math.max(12, window.innerWidth - size - 20),
    top: Math.max(12, window.innerHeight - size - 24),
  }
}

function minimize() {
  minimized.value = true
  clampToViewport()
  savePosition()
}

function expand() {
  minimized.value = false
  clampToViewport()
  savePosition()
}

function onActivate() {
  if (minimized.value) {
    expand()
    return
  }
  router.push('/agent')
}

function onPointerDown(event) {
  if (event.button !== 0) return
  dragging.value = true
  moved = false
  startX = event.clientX
  startY = event.clientY
  startLeft = position.value.left
  startTop = position.value.top
  rootRef.value?.setPointerCapture(event.pointerId)
  event.preventDefault()
}

function onPointerMove(event) {
  if (!dragging.value) return
  const deltaX = event.clientX - startX
  const deltaY = event.clientY - startY
  if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) moved = true
  const size = currentSize.value
  position.value = {
    left: clamp(startLeft + deltaX, 8, Math.max(8, window.innerWidth - size - 8)),
    top: clamp(startTop + deltaY, 8, Math.max(8, window.innerHeight - size - 8)),
  }
}

function onPointerUp(event) {
  if (!dragging.value) return
  dragging.value = false
  if (rootRef.value?.hasPointerCapture(event.pointerId)) {
    rootRef.value.releasePointerCapture(event.pointerId)
  }
  savePosition()
  // 只有未拖拽的点击才触发：收起态展开，展开态进入 AI 助理
  if (!moved) onActivate()
}

function onPointerCancel() {
  dragging.value = false
}

function handleResize() {
  const prevWidth = viewportWidth.value
  const prevHeight = viewportHeight.value
  const nextWidth = window.innerWidth
  const nextHeight = window.innerHeight
  if (prevWidth === nextWidth && prevHeight === nextHeight) return

  // 按可用空间比例平移，避免在视口大幅变化后停留在内容中间
  const prevSize = minimized.value ? MINI_SIZE : sizeForWidth(prevWidth)
  viewportWidth.value = nextWidth
  viewportHeight.value = nextHeight
  const nextSize = currentSize.value
  const prevFreeWidth = Math.max(1, prevWidth - prevSize - 16)
  const prevFreeHeight = Math.max(1, prevHeight - prevSize - 16)
  const ratioX = clamp((position.value.left - 8) / prevFreeWidth, 0, 1)
  const ratioY = clamp((position.value.top - 8) / prevFreeHeight, 0, 1)
  position.value = {
    left: 8 + ratioX * Math.max(1, nextWidth - nextSize - 16),
    top: 8 + ratioY * Math.max(1, nextHeight - nextSize - 16),
  }

  clampToViewport()
  savePosition()
}

watch(visible, (value) => {
  if (value) clampToViewport()
})

watch(state, handleStateChange, { immediate: true, flush: 'sync' })

watch(
  isAgentRoute,
  (isAgent, wasAgent) => {
    clearTimeout(exitSecurityTimer)
    exitSecurityTimer = null
    if (isAgent && !wasAgent) {
      agentStore.setAvatarState('greeting')
      startInactivityTimer()
    } else if (!isAgent && wasAgent) {
      clearInactivityTimer()
      agentStore.setAvatarState('security')
      exitSecurityTimer = setTimeout(() => {
        agentStore.setAvatarState('idle')
      }, EXIT_SECURITY_MS)
    }
  },
  { immediate: true },
)

onMounted(() => {
  viewportWidth.value = window.innerWidth
  viewportHeight.value = window.innerHeight
  if (!position.value.left && !position.value.top) {
    position.value = defaultPosition()
  }
  clampToViewport()
  startIdleRotation()
  syncInactivityForState(state.value)
  window.addEventListener('resize', handleResize)
  window.addEventListener('pointerdown', onUserActivity)
  window.addEventListener('keydown', onUserActivity)
  window.addEventListener('touchstart', onUserActivity)
  window.addEventListener('wheel', onUserActivity)
})

onBeforeUnmount(() => {
  stopIdleRotation()
  clearTimeout(greetingTimer)
  clearTimeout(exitSecurityTimer)
  clearInactivityTimer()
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('pointerdown', onUserActivity)
  window.removeEventListener('keydown', onUserActivity)
  window.removeEventListener('touchstart', onUserActivity)
  window.removeEventListener('wheel', onUserActivity)
})
</script>

<style scoped>
.floating-avatar {
  position: fixed;
  z-index: 1200;
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  outline: none;
  transition: width 0.2s ease, height 0.2s ease;
}

.floating-avatar:focus-visible {
  outline: 2px solid rgba(79, 107, 237, 0.72);
  outline-offset: 4px;
  border-radius: 50%;
}

.floating-avatar.dragging {
  cursor: grabbing;
}

.avatar-dock {
  position: absolute;
  left: -3px;
  top: -3px;
  z-index: 4;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #5f677a;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.98);
  box-shadow: 0 3px 10px rgba(23, 28, 43, 0.16);
  opacity: 0;
  transform: scale(0.9);
  transition: opacity 0.18s ease, transform 0.18s ease, color 0.18s ease;
}

.floating-avatar:hover .avatar-dock,
.avatar-dock:focus-visible {
  opacity: 1;
  transform: scale(1);
}

.avatar-dock:hover {
  color: var(--accent-strong);
}

@media (hover: none) {
  .avatar-dock {
    opacity: 0.85;
    transform: scale(1);
  }
}

.floating-avatar.minimized .avatar-core {
  padding: 7px;
  overflow: hidden;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(255, 255, 255, 0.95);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 8px 20px rgba(23, 28, 43, 0.12);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.floating-avatar.minimized .avatar-glow {
  inset: -2px;
  opacity: 0.4;
  filter: blur(8px);
}

.floating-avatar.minimized:hover .avatar-core {
  transform: translateY(-1px) scale(1.04);
}

.avatar-glow {
  position: absolute;
  inset: -8px;
  border-radius: 999px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.3), rgba(96, 165, 250, 0.14) 62%, transparent 74%);
  filter: blur(14px);
  opacity: 0.6;
  transition: background 0.4s ease;
}

.avatar-glow.speaking {
  background: radial-gradient(circle, rgba(16, 185, 129, 0.28), rgba(59, 130, 246, 0.16) 62%, transparent 74%);
}

.avatar-glow.thinking {
  background: radial-gradient(circle, rgba(96, 165, 250, 0.36), rgba(59, 130, 246, 0.18) 62%, transparent 74%);
}

.avatar-glow.greeting {
  background: radial-gradient(circle, rgba(251, 191, 36, 0.3), rgba(96, 165, 250, 0.14) 62%, transparent 74%);
}

.avatar-glow.leisure {
  background: radial-gradient(circle, rgba(20, 184, 166, 0.28), rgba(59, 130, 246, 0.12) 62%, transparent 74%);
}

.avatar-glow.side {
  background: radial-gradient(circle, rgba(100, 116, 139, 0.28), rgba(59, 130, 246, 0.12) 62%, transparent 74%);
}

.avatar-glow.working {
  background: radial-gradient(circle, rgba(34, 211, 238, 0.28), rgba(59, 130, 246, 0.14) 62%, transparent 74%);
}

.avatar-glow.controlling {
  background: radial-gradient(circle, rgba(139, 92, 246, 0.3), rgba(59, 130, 246, 0.16) 62%, transparent 74%);
}

.avatar-glow.security {
  background: radial-gradient(circle, rgba(245, 158, 11, 0.36), rgba(239, 68, 68, 0.16) 62%, transparent 74%);
}

.avatar-glow.sleeping {
  background: radial-gradient(circle, rgba(99, 102, 241, 0.26), rgba(30, 64, 175, 0.16) 62%, transparent 74%);
}

.avatar-glow.energy_saving {
  background: radial-gradient(circle, rgba(16, 185, 129, 0.32), rgba(132, 204, 22, 0.14) 62%, transparent 74%);
}

.avatar-glow.caring {
  background: radial-gradient(circle, rgba(244, 114, 182, 0.28), rgba(59, 130, 246, 0.12) 62%, transparent 74%);
}

.avatar-glow.happy {
  background: radial-gradient(circle, rgba(251, 191, 36, 0.3), rgba(16, 185, 129, 0.14) 62%, transparent 74%);
}

.avatar-glow.sad {
  background: radial-gradient(circle, rgba(239, 68, 68, 0.2), transparent 72%);
}

.avatar-core {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  background: transparent;
  border: none;
  box-shadow: none;
  overflow: visible;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.avatar-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transform-origin: center;
  user-select: none;
  -webkit-user-drag: none;
  animation: avatar-breathe 3.2s ease-in-out infinite;
  transition: opacity 0.28s ease, filter 0.35s ease, transform 0.35s ease;
}

.avatar-core.greeting .avatar-image {
  animation: avatar-greeting 0.8s ease-out both, avatar-breathe 2.8s 0.8s ease-in-out infinite;
}

.avatar-core.speaking .avatar-image {
  animation: avatar-speak 0.9s ease-in-out infinite;
  filter: saturate(1.06) brightness(1.03);
}

.avatar-core.thinking .avatar-image {
  animation: avatar-think 1.5s ease-in-out infinite;
  filter: saturate(1.04) brightness(1.02);
}

.avatar-core.sad .avatar-image {
  filter: saturate(0.82) brightness(0.92);
}

.avatar-core.sleeping .avatar-image {
  animation: avatar-sleep 4s ease-in-out infinite;
  filter: brightness(0.94) saturate(0.9);
}

.avatar-core.working .avatar-image {
  animation: avatar-work 1.2s ease-in-out infinite;
}

.avatar-core.controlling .avatar-image {
  animation: avatar-control 1.1s ease-in-out infinite;
  filter: saturate(1.08);
}

.avatar-core.security .avatar-image {
  animation: avatar-alert 0.8s ease-in-out infinite;
  filter: saturate(1.14) contrast(1.04);
}

.avatar-core.energy_saving .avatar-image {
  animation: avatar-energy 2.2s ease-in-out infinite;
  filter: saturate(0.95) brightness(0.98);
}

.avatar-core.leisure .avatar-image,
.avatar-core.happy .avatar-image,
.avatar-core.caring .avatar-image {
  animation: avatar-idle-sway 3.6s ease-in-out infinite;
}

.avatar-core.side .avatar-image {
  animation: avatar-look 2.6s ease-in-out infinite;
}

.floating-avatar:hover .avatar-core {
  transform: translateY(-2px) scale(1.04);
}

.status-dot {
  position: absolute;
  right: 3px;
  top: 3px;
  z-index: 2;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: #10b981;
  border: 2px solid #ffffff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.16);
}

.floating-avatar.minimized .status-dot {
  right: 1px;
  top: 1px;
  width: 9px;
  height: 9px;
  border-width: 1.5px;
}

.status-dot.speaking {
  background: #f59e0b;
}

.status-dot.thinking {
  background: #3b82f6;
}

.status-dot.sad {
  background: #ef4444;
}

.status-dot.greeting {
  background: #f59e0b;
}

.status-dot.leisure,
.status-dot.happy,
.status-dot.caring {
  background: #14b8a6;
}

.status-dot.side {
  background: #64748b;
}

.status-dot.working {
  background: #06b6d4;
}

.status-dot.controlling {
  background: #8b5cf6;
}

.status-dot.security {
  background: #f97316;
}

.status-dot.sleeping {
  background: #6366f1;
}

.status-dot.energy_saving {
  background: #22c55e;
}

.mini-bars {
  position: absolute;
  left: 50%;
  bottom: 8%;
  z-index: 2;
  display: flex;
  align-items: flex-end;
  gap: 3px;
  transform: translateX(-50%);
}

.mini-bars span {
  width: 3px;
  height: 10px;
  border-radius: 2px;
  background: #3b82f6;
  animation: mini-wave 0.9s ease-in-out infinite;
}

.mini-bars span:nth-child(2) {
  animation-delay: 0.14s;
}

.mini-bars span:nth-child(3) {
  animation-delay: 0.28s;
}

.mini-dots {
  position: absolute;
  left: 50%;
  top: 8%;
  z-index: 2;
  display: flex;
  gap: 4px;
  transform: translateX(-50%);
}

.mini-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #3b82f6;
  animation: mini-think 1.1s ease-in-out infinite;
}

.mini-dots span:nth-child(2) {
  animation-delay: 0.18s;
}

.mini-dots span:nth-child(3) {
  animation-delay: 0.36s;
}

@keyframes mini-wave {
  0%, 100% {
    height: 6px;
  }
  50% {
    height: 16px;
  }
}

@keyframes mini-think {
  0%, 100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@keyframes avatar-breathe {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.035);
  }
}

@keyframes avatar-greeting {
  0% {
    opacity: 0;
    transform: translateY(8px) scale(0.92);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes avatar-speak {
  0%, 100% {
    transform: scale(1.02) translateY(0);
  }
  50% {
    transform: scale(1.055) translateY(-1px);
  }
}

@keyframes avatar-think {
  0%, 100% {
    transform: rotate(0deg) scale(1);
  }
  50% {
    transform: rotate(-2deg) scale(1.025);
  }
}

@keyframes avatar-sleep {
  0%, 100% {
    transform: scale(0.985);
    opacity: 0.94;
  }
  50% {
    transform: scale(1.008);
    opacity: 1;
  }
}

@keyframes avatar-work {
  0%, 100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-2px) rotate(1deg);
  }
}

@keyframes avatar-control {
  0%, 100% {
    transform: translateX(0);
  }
  50% {
    transform: translateX(1.5px);
  }
}

@keyframes avatar-alert {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.045);
  }
}

@keyframes avatar-energy {
  0%, 100% {
    transform: scale(1) rotate(0deg);
  }
  50% {
    transform: scale(1.03) rotate(-1deg);
  }
}

@keyframes avatar-idle-sway {
  0%, 100% {
    transform: rotate(0deg) translateY(0);
  }
  50% {
    transform: rotate(1.5deg) translateY(-2px);
  }
}

@keyframes avatar-look {
  0%, 100% {
    transform: translateX(0) scale(1);
  }
  50% {
    transform: translateX(2px) scale(1.02);
  }
}
</style>
