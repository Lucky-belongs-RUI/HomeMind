import request from './request'

export const listScenes = () => request.get('/scenes')
export const createScene = (data) => request.post('/scenes', data)
export const executeScene = (name) =>
  request.post(`/scenes/${encodeURIComponent(name)}/execute`)
export const updateScene = (id, data) => request.put(`/scenes/${id}`, data)
export const deleteScene = (id) => request.delete(`/scenes/${id}`)
