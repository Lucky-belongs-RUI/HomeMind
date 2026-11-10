import request from './request'

// collection: user_documents（个人私有）或 family_regulations（家庭规章制度）
export const uploadFile = (file, collection = 'user_documents') => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/files/upload', formData, { params: { collection } })
}

export const getFiles = () => request.get('/files')
export const deleteFile = (id) => request.delete(`/files/${id}`)