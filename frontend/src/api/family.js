import request from './request'

// 家庭概览：文档 5.13 家庭管理页使用，返回家庭统计与房主信息
export const getFamilyOverview = (id) => request.get(`/families/${id}`)
