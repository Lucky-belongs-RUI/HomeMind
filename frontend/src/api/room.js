import request from './request'

export const getRooms = () => request.get('/rooms')
export const createRoom = (data) => request.post('/rooms', data)
export const deleteRoom = (id) => request.delete(`/rooms/${id}`)
