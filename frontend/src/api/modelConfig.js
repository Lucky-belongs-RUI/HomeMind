import request from './request'

export const listModelConfigs = () => request.get('/model-configs')

export const createModelConfig = (payload) => request.post('/model-configs', payload)

export const updateModelConfig = (id, payload) => request.put(`/model-configs/${id}`, payload)

export const deleteModelConfig = (id) => request.delete(`/model-configs/${id}`)
