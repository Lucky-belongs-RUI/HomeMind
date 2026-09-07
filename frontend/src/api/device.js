import request from './request'

export const getDevices = () => request.get('/devices')
export const createDevice = (data) => request.post('/devices', data)
export const updateDevice = (id, data) => request.put(`/devices/${id}`, data)
export const deleteDevice = (id) => request.delete(`/devices/${id}`)
export const updateDeviceStatus = (id, attributes) =>
  request.patch(`/devices/${id}/status`, { attributes })
