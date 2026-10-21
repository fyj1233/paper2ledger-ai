import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('./views/Dashboard.vue'),
        meta: { roles: ['admin', 'manager'], title: '生产看板' },
      },
      {
        path: 'ledger',
        name: 'ledger',
        component: () => import('./views/Ledger.vue'),
        meta: { roles: ['admin', 'manager'], title: '工厂台账' },
      },
      {
        path: 'products',
        name: 'products',
        component: () => import('./views/Products.vue'),
        meta: { roles: ['admin'], title: '产品管理' },
      },
      {
        path: 'assistant',
        name: 'assistant',
        component: () => import('./views/Assistant.vue'),
        meta: { roles: ['admin', 'manager'], title: 'AI 助手' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('./views/Reports.vue'),
        meta: { roles: ['admin', 'manager'], title: '台账报表' },
      },
      {
        path: 'upload',
        name: 'upload',
        component: () => import('./views/Upload.vue'),
        meta: { title: '上传单据' },
      },
      {
        path: 'documents',
        name: 'documents',
        component: () => import('./views/Documents.vue'),
        meta: { title: '单据管理' },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('./views/Users.vue'),
        meta: { roles: ['admin'], title: '用户管理' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('./views/Settings.vue'),
        meta: { roles: ['admin'], title: '系统设置' },
      },
      {
        path: 'templates',
        name: 'templates',
        component: () => import('./views/Templates.vue'),
        meta: { roles: ['admin'], title: '模板与字典' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  if (to.meta.public) {
    if (token) return '/dashboard'
    return true
  }
  if (!token) return '/login'
  if (to.meta.roles && !to.meta.roles.includes(user?.role)) {
    return user?.role === 'employee' ? '/upload' : '/dashboard'
  }
  return true
})

export default router
