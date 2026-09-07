<template>
  <div class="page upload-view">
    <div class="upload-grid grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] gap-4 items-stretch flex-1 min-h-0">
      <section class="section-panel h-full flex flex-col">
        <div class="flex rounded-xl bg-white/60 border border-white/40 p-1 gap-1 mb-3">
          <button
            type="button"
            class="collection-btn"
            :class="{ active: collection === 'user_documents' }"
            @click="switchCollection('user_documents')"
          >
            <FileText :size="13" class="mr-1" />
            私人知识文档
          </button>
          <button
            type="button"
            class="collection-btn"
            :class="{ active: collection === 'family_regulations' }"
            :disabled="!canUploadRegulation"
            @click="switchCollection('family_regulations')"
          >
            <BookOpen :size="13" class="mr-1" />
            家庭规章制度
          </button>
        </div>

        <p class="text-xs text-gray-400 mb-3 leading-relaxed">{{ collectionHint }}</p>

        <el-upload
          drag
          accept=".pdf,.docx,.doc"
          :http-request="handleUpload"
          :show-file-list="false"
          :disabled="uploadDisabled"
          class="drag-zone"
        >
          <div class="flex flex-col items-center py-4">
            <span class="w-14 h-14 rounded-2xl bg-blue-500/10 text-blue-500 flex items-center justify-center mb-3">
              <UploadCloud :size="28" />
            </span>
            <p class="text-sm text-gray-700">拖拽文件到此处，或<em class="text-blue-500 not-italic font-medium">点击上传</em></p>
            <p class="text-xs text-gray-400 mt-1.5">支持 PDF、Word 格式，单文件最大 10MB</p>
          </div>
        </el-upload>

        <div v-if="uploading" class="flex items-center gap-2 mt-4 px-3 py-2.5 rounded-xl bg-blue-500/10 text-blue-600 text-sm">
          <RefreshCw :size="15" class="animate-spin" />
          <span class="truncate">正在上传并解析 {{ uploading.name }} ...</span>
        </div>

        <div class="flex flex-col gap-2.5 mt-5">
          <div v-for="(tip, index) in tips" :key="index" class="flex items-center gap-2.5 text-xs text-gray-500">
            <span class="w-5 h-5 rounded-full bg-blue-500/10 text-blue-500 flex items-center justify-center text-[11px] font-bold shrink-0">
              {{ index + 1 }}
            </span>
            <span>{{ tip }}</span>
          </div>
        </div>
      </section>

      <section class="section-panel h-full flex flex-col">
        <div class="panel-head shrink-0">
          <div class="flex items-center gap-2">
            <span class="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-500 flex items-center justify-center">
              <FileText :size="16" />
            </span>
            <h3 class="panel-title">知识库文件</h3>
          </div>
          <el-button size="small" :loading="loading" @click="loadFiles">
            <RefreshCw :size="13" class="mr-1" />
            刷新
          </el-button>
        </div>

        <div class="flex-1 min-h-0 overflow-y-auto pr-0.5">
          <el-table :data="files" style="width: 100%">
            <el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ row.file_type === 'pdf' ? 'PDF' : 'Word' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
            </el-table-column>
            <el-table-column label="处理状态" width="130">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="切片数" width="80" />
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="requestDelete(row)">
                  <Trash2 :size="14" class="mr-1" />
                  删除
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <div class="text-center text-sm text-gray-400 py-8">暂无上传文件</div>
            </template>
          </el-table>
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
    : '私人文档按用户隔离，仅本人与房主可见，适用于生活习惯、偏好说明等',
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

const statusLabel = (status) => ({ pending: '等待中', processing: '解析中', ready: '就绪', failed: '失败' }[status] || status)
const statusTagType = (status) =>
  ({ pending: 'info', processing: 'warning', ready: 'success', failed: 'danger' }[status] || 'info')

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
.collection-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 7px 10px;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  transition: all 0.2s ease;
}

.collection-btn:hover:not(:disabled) {
  color: #2563eb;
}

.collection-btn.active {
  background: #2563eb;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.22);
}

.collection-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.drag-zone :deep(.el-upload-dragger) {
  padding: 18px 16px;
}

@media (max-width: 1023px) {
  .upload-grid {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
  .upload-grid > * {
    height: auto;
  }
}
</style>