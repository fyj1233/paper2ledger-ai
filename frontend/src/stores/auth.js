import { defineStore } from 'pinia'
import api, { errMsg } from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null'),
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    role: (s) => s.user?.role || '',
    isManager: (s) => ['admin', 'manager'].includes(s.user?.role),
    isAdmin: (s) => s.user?.role === 'admin',
  },
  actions: {
    async login(username, password) {
      const { data } = await api.post('/auth/login', { username, password })
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', this.token)
      localStorage.setItem('user', JSON.stringify(this.user))
    },
    async refreshToken() {
      try {
        const { data } = await api.get('/auth/me')
        this.user = data
        localStorage.setItem('user', JSON.stringify(data))
      } catch (e) {
        if (e.response?.status === 401) this.logout()
      }
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    },
    loginError: errMsg,
  },
})
