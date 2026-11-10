<template>
  <div class="page upload-view">
    <h1 class="sr-only">家庭知识库</h1>

    <div class="upload-grid">
      <section class="section-panel upload-card">
        <div class="segmented">
          <button
            type="button"
            class="segment-btn"
            :class="{ active: collection === 'user_documents' }"
            @click="switchCollection('user_documents')"
          >
            <FileText :size="13" />
            私人知识文档
          </button>
          <button
            type="button"
            class="segment-btn"
            :class="{ active: collection === 'family_regulations' }"
            :disabled="!canUploadRegulation"
            @click="switchCollection('family_regulations')"
          >
            <BookOpen :size="13" />
            家庭规章制度
          </button>
        </div>

        <p class="upload-hint">{{ collectionHint }}</p>

        <el-upload
          drag
          accept=".pdf,.docx"
          :http-request="handleUpload"
          :show-file-list="false"
          :disabled="uploadDisabled"
          class="drag-zone"
        >
          <div class="drop-content">
            <span class="drop-icon"><UploadCloud :size="26" /></span>
            <p class="drop-title">拖拽文件到此处，或<em>点击上传</em></p>
            <p class="drop-sub">支持 PDF、Word（.docx），单文件最大 10MB</p>
          </div>
        </el-upload>

        <div v-if="uploading" class="upload-progress">
          <span class="progress-icon"><RefreshCw :size="14" class="animate-spin" /></span>
          <div class="progress-copy">
            <span class="progress-title">正在上传并解析</span>
            <span class="progress-file">{{ uploading.name }}</span>
          </div>
        </div>

        <div class="tip-list">
          <div v-for="(tip, index) in tips" :key="index" class="tip-item">
            <span class="tip-index">{{ index + 1 }}</span>
            <span>{{ tip }}</span>
          </div>
        </div>
      </section>

      <section class="section-panel files-card">
        <div class="panel-head">
          <div class="flex items-center gap-2.5">
            <span class="panel-icon"><FileText :size="15" /></span>
            <div>
              <h3 class="panel-title">知识库文件</h3>
              <p class="text-[11px] text-gray-400 mt-0.5">
                共 {{ files.length }} 个 · {{ readyCount }} 个可用于问答
              </p>
            </div>
          </div>
          <el-button size="small" :loading="loading" @click="loadFiles">
            <RefreshCw :size="13" class="mr-1" />
            刷新
          </el-button>
        </div>

        <div class="file-list">
          <template v-if="loading && !files.length">
            <div v-for="n in 4" :key="n" class="file-skeleton">
              <div class="skeleton sk-badge"></div>
              <div class="sk-lines">
                <div class="skeleton sk-line-lg"></div>
                <div class="skeleton sk-line-sm"></div>
              </div>
            </div>
          </template>

          <template v-else-if="files.length">
            <article v-for="row in files" :key="row.id" class="file-row">
              <span class="file-type" :class="row.file_type">
                {{ row.file_type === 'pdf' ? 'PDF' : 'DOC' }}
              </span>
              <div class="file-main">
                <div class="file-name-line">
                  <span class="file-name" :title="row.filename">{{ row.filename }}</span>
                  <span class="collection-pill" :class="row.collection">
                    {{ row.collection === 'family_regulations' ? '家庭规章' : '私人' }}
                  </span>
                  <span class="status-pill" :class="row.status">{{ statusLabel(row.status) }}</span>
                </div>
                <div class="file-meta">
                  <span>{{ formatSize(row.file_size) }}</span>
                  <i>·</i>
                  <span>{{ row.chunk_count || 0 }} 个切片</span>
                  <template v-if="row.status === 'processing' || row.status === 'pending'">
                    <i>·</i>
                    <span>后台解析中</span>
                  </template>
                </div>
              </div>
              <button
                type="button"
                class="file-remove"
                title="删除文件"
                aria-label="删除文件"
                @click="requestDelete(row)"
              >
                <Trash2 :size="15" />
              </button>
            </article>
          </template>

          <div v-else class="empty-state files-empty">
            <span class="empty-icon"><UploadCloud :size="24" /></span>
            <p class="text-sm font-medium text-gray-600">还没有上传文件</p>
            <p class="mt-1 text-xs text-gray-400">上传文档后，AI 助理即可检索其中的内容</p>
          </div>
        </div>
      </section>
    </div>

    <ConfirmDialog
      v-model="showDelete"
      title="删除文件"
      :message="`确定删除文件「${deleteTarget?.filename || ''}」及其向量数据吗？`"
      type="danger"
      confirm-text="删除"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadCloud, RefreshCw, FileText, Trash2, BookOpen } from 'lucide-vue-next'
import { usePermission } from '@/composables/usePermission'
import { useUserStore } from '@/stores/user'
import { uploadFile, getFiles, deleteFile } from '@/api/file'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const { canUploadFile } = usePermission()
const userStore = useUserStore()

const collection = ref('user_documents')
const canUploadRegulation = computed(() => userStore.isOwner)
const uploadDisabled = computed(
  () => !canUploadFile.value || (collection.value === 'family_regulations' && !canUploadRegulation.value),
)
const collectionLabel = computed(() =>
  collection.value === 'family_regulations' ? '家庭规章制度' : '私人知识文档',
)
const collectionHint = computed(() =>
  collection.value === 'family_regulations'
    ? '规章制度全家成员可检索，仅房主可上传，适用于家庭规则、设备使用规范等'
    : '私人文档按账号隔离，仅本人可见、仅本人问答时检索，适用于生活习惯、偏好说明等',
)
const tips = computed(() =>
  collection.value === 'family_regulations'
    ? [
        '上传家庭规则、设备使用规范等制度文件',
        '系统解析文本并切片，构建家庭规章向量库',
        '全家成员可在 AI 助理中检索制度内容',
      ]
    : [
        '上传生活习惯、偏好说明等私人数据',
        '系统解析文本并切片，构建个人向量库',
        'AI 助理基于知识库给出个性化回答',
      ],
)

const files = ref([])
const loading = ref(false)
const uploading = ref(null)
const showDelete = ref(false)
const deleteTarget = ref(null)
let pollTimer = null

const readyCount = computed(() => files.value.filter((file) => file.status === 'ready').length)

const switchCollection = (value) => {
  if (value === 'family_regulations' && !canUploadRegulation.value) return
  collection.value = value
}

const loadFiles = async () => {
  loading.value = true
  try {
    files.value = await getFiles()
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    loading.value = false
  }
}

const handleUpload = async ({ file }) => {
  uploading.value = file
  try {
    await uploadFile(file, collection.value)
    ElMessage.success(`「${file.name}」${collectionLabel.value}上传成功，正在解析`)
    await loadFiles()
    startPolling()
  } catch (error) {
    // 错误提示已由请求层统一处理
  } finally {
    uploading.value = null
  }
}

const startPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    await loadFiles()
    const hasProcessing = files.value.some((file) => file.status === 'processing' || file.status === 'pending')
    if (!hasProcessing) stopPolling()
  }, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const requestDelete = (file) => {
  deleteTarget.value = file
  showDelete.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return
  try {
    await deleteFile(deleteTarget.value.id)
    ElMessage.success('文件已删除')
    await loadFiles()
  } catch (error) {
    // 错误提示已由请求层统一处理
  }
}

const statusLabel = (status) => ({ pending: '等待中', processing: '解析中', ready: '已就绪', failed: '失败' }[status] || status)

const formatSize = (bytes) => {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

onMounted(loadFiles)
onUnmounted(stopPolling)
</script>

<style scoped>
.upload-view {
  height: calc(100dvh - 104px);
}

.upload-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.upload-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.segmented {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.7);
}

.segment-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 8px;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-500);
  transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
}

.segment-btn:hover:not(:disabled) {
  color: var(--accent-strong);
}

.segment-btn.active {
  color: var(--accent-strong);
  background: #fff;
  box-shadow: 0 4px 12px rgba(79, 107, 237, 0.1);
}

.segment-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.upload-hint {
  margin: 10px 2px 12px;
  font-size: 11px;
  line-height: 1.65;
  color: var(--ink-400);
}

.drag-zone {
  display: flex;
  flex: 1;
  min-height: 180px;
}

.drag-zone :deep(.el-upload-dragger) {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 0;
  overflow: hidden;
}

.drop-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 26px 16px;
  text-align: center;
}

.drop-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin-bottom: 10px;
  border-radius: 16px;
  color: var(--accent-strong);
  background: linear-gradient(135deg, rgba(79, 107, 237, 0.16), rgba(79, 107, 237, 0.06));
  border: 1px solid rgba(79, 107, 237, 0.12);
}

.drop-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-700);
}

.drop-title em {
  font-style: normal;
  color: var(--accent-strong);
}

.drop-sub {
  margin: 5px 0 0;
  font-size: 10px;
  color: var(--ink-400);
}

.upload-progress {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(79, 107, 237, 0.07);
  border: 1px solid rgba(79, 107, 237, 0.14);
}

.progress-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 8px;
  color: var(--accent-strong);
  background: rgba(255, 255, 255, 0.7);
}

.progress-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.progress-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-strong);
}

.progress-file {
  font-size: 10px;
  color: var(--ink-500);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tip-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(23, 28, 43, 0.06);
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--ink-500);
}

.tip-index {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  flex: none;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
}

.files-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.1);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.64);
  transition: background 0.18s ease, border-color 0.18s ease;
}

.file-row:hover {
  background: rgba(255, 255, 255, 0.8);
  border-color: rgba(255, 255, 255, 0.9);
}

.file-type {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 11px;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.03em;
  color: #b4544a;
  background: rgba(216, 105, 90, 0.1);
  border: 1px solid rgba(216, 105, 90, 0.14);
}

.file-type.docx {
  color: var(--accent-strong);
  background: rgba(79, 107, 237, 0.09);
  border-color: rgba(79, 107, 237, 0.14);
}

.file-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.file-name-line {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.file-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 2px;
  font-size: 10px;
  color: var(--ink-400);
  flex-wrap: wrap;
}

.file-meta i {
  font-style: normal;
  color: #c2c6d0;
}

.status-pill {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  color: var(--ink-500);
  background: rgba(23, 28, 43, 0.06);
}

.collection-pill {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  color: #2f6f5e;
  background: rgba(47, 111, 94, 0.1);
  border: 1px solid rgba(47, 111, 94, 0.14);
}

.collection-pill.family_regulations {
  color: #9a6a24;
  background: rgba(217, 154, 78, 0.13);
  border-color: rgba(217, 154, 78, 0.18);
}

.status-pill.ready {
  color: #2c7a5f;
  background: rgba(16, 185, 129, 0.11);
}

.status-pill.processing,
.status-pill.pending {
  color: #9a6b2f;
  background: rgba(217, 154, 78, 0.14);
}

.status-pill.failed {
  color: #b4544a;
  background: rgba(216, 105, 90, 0.12);
}

.file-remove {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  color: #a3a8b6;
  transition: color 0.16s ease, background 0.16s ease;
}

.file-remove:hover {
  color: #c45a4c;
  background: rgba(216, 105, 90, 0.1);
}

.files-empty {
  flex: 1;
  min-height: 240px;
  border-radius: 14px;
  border: 1px dashed rgba(23, 28, 43, 0.1);
  background: rgba(255, 255, 255, 0.28);
}

.file-skeleton {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
}

.sk-badge {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 11px;
}

.sk-lines {
  display: flex;
  flex-direction: column;
  gap: 7px;
  flex: 1;
}

.sk-line-lg {
  width: 52%;
  height: 10px;
}

.sk-line-sm {
  width: 32%;
  height: 8px;
}

@media (max-width: 1023px) {
  .upload-view {
    height: auto;
    min-height: 100%;
  }

  .upload-grid {
    grid-template-columns: 1fr;
    flex: none;
  }

  .files-card {
    min-height: 360px;
  }
}

@media (max-width: 520px) {
  .segment-btn {
    font-size: 10px;
    padding: 7px 5px;
  }

  .file-row {
    padding: 9px 10px;
  }

  .file-name {
    font-size: 12px;
  }

  .file-type {
    width: 34px;
    height: 34px;
    border-radius: 9px;
    font-size: 9px;
  }
}
</style>
