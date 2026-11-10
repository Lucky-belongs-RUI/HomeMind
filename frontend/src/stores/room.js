import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getRooms } from '@/api/room'

export const useRoomStore = defineStore('room', () => {
  const rooms = ref([])
  const selectedRoomId = ref(null)

  const selectedRoom = computed(
    () => rooms.value.find((room) => room.id === selectedRoomId.value) || null,
  )

  const fetchRooms = async () => {
    rooms.value = await getRooms()
  }

  const selectRoom = (roomId) => {
    selectedRoomId.value = roomId
  }

  return { rooms, selectedRoomId, selectedRoom, fetchRooms, selectRoom }
})
