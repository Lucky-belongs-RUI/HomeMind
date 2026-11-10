import request from './request'

export const login = (data) => request.post('/auth/login', data)
export const register = (data) => request.post('/auth/register', data)
export const createSubAccount = (data) => request.post('/auth/sub-account', data)