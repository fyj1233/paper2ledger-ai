import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 60000 })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401 && location.pathname !== '/login') {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export function errMsg(error) {
  return error.response?.data?.detail || error.message || '请求失败'
}

export default api
