import request from './request'

export const getUsers = () => request.get('/users')
export const deleteUser = (id) => request.delete(`/users/${id}`)
export const getUserPreferences = (id) => request.get(`/users/${id}/preferences`)
export const analyzeUserPreferences = (id) => request.post(`/users/${id}/preferences/analyze`)
