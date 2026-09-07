import { computed } from 'vue'
import { useUserStore } from '@/stores/user'

/**
 * 权限矩阵（开发文档 5.13）：
 * 住户和访客通过 family_id 共享家庭数据，差异仅在"能否修改"。
 */
export function usePermission() {
  const userStore = useUserStore()

  const canControlDevice = computed(() => !userStore.isGuest)
  const canManageDevices = computed(() => userStore.isOwner)
  const canManageRooms = computed(() => userStore.isOwner)
  const canManageUsers = computed(() => userStore.isOwner)
  const canManageScenes = computed(() => userStore.isOwner)
  const canUploadFile = computed(() => !userStore.isGuest)

  return {
    canControlDevice,
    canManageDevices,
    canManageRooms,
    canManageUsers,
    canManageScenes,
    canUploadFile,
  }
}
