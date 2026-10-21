<template>
  <!-- 登录页独立渲染 -->
  <router-view v-if="isLoginRoute" />

  <el-container class="layout" v-else-if="auth.isLoggedIn">
    <el-aside width="200px" class="aside" :class="{ open: menuOpen }">
      <div class="logo">
        <svg viewBox="0 0 56 56" width="26" height="26" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs>
            <linearGradient id="p2lBadgeSide" x1="4" y1="4" x2="52" y2="52" gradientUnits="userSpaceOnUse">
              <stop stop-color="#3b8bff" />
              <stop offset="1" stop-color="#0f3a8d" />
            </linearGradient>
          </defs>
          <rect x="4" y="4" width="48" height="48" rx="13" fill="url(#p2lBadgeSide)" />
          <path d="M19 11.5h12.5L39 19v20.5A3.5 3.5 0 0 1 35.5 43H19a3.5 3.5 0 0 1-3.5-3.5V15a3.5 3.5 0 0 1 3.5-3.5z" fill="#ffffff" />
          <path d="M31.5 11.5V16a3 3 0 0 0 3 3H39l-7.5-7.5z" fill="#c9defc" />
          <rect x="20.5" y="24" width="8.5" height="3" rx="1.5" fill="#1677ff" />
          <rect x="31" y="24" width="5" height="3" rx="1.5" fill="#8fbcff" />
          <rect x="20.5" y="30" width="11" height="3" rx="1.5" fill="#1677ff" />
          <rect x="33" y="30" width="3" height="3" rx="1.5" fill="#8fbcff" />
          <rect x="20.5" y="36" width="6" height="3" rx="1.5" fill="#52c41a" />
          <rect x="28" y="36" width="8" height="3" rx="1.5" fill="#a5df8f" />
        </svg>
        <span class="logo-name">一纸成账</span>
      </div>
      <el-menu :default-active="$route.path" router class="menu" @click="menuOpen = false">
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <div v-if="menuOpen" class="aside-mask" @click="menuOpen = false"></div>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button class="menu-btn" text :icon="'Menu'" @click="menuOpen = !menuOpen" />
          <span class="page-title">{{ $route.meta.title || '' }}</span>
          <el-tag v-if="auth.isManager" :type="llmConfigured ? 'success' : 'warning'" size="small" effect="plain">
            {{ llmConfigured ? `AI 模型：${llmModel}` : 'AI 未配置（规则提取模式）' }}
          </el-tag>
        </div>
        <el-dropdown @command="onCommand">
          <span class="user-info">
            <el-icon><User /></el-icon>
            {{ auth.user?.username }}（{{ roleLabel }}）
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    <el-dialog
      v-model="pwdVisible"
      title="修改密码"
      width="400px"
      :show-close="!needForcePwd"
      :close-on-click-modal="!needForcePwd"
      :close-on-press-escape="!needForcePwd"
    >
      <el-alert
        v-if="needForcePwd"
        title="首次登录请先修改默认密码，修改后才能继续使用系统"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-form :model="pwdForm" label-width="90px">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="!needForcePwd" @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" @click="changePassword">确定</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api, { errMsg } from './api'
import { useAuthStore } from './stores/auth'
import { ROLE_LABELS } from './utils'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const isLoginRoute = computed(() => !!route.meta.public)

const menuItems = computed(() => {
  const items = [
    { path: '/upload', title: '上传单据', icon: 'Upload' },
    { path: '/documents', title: '单据管理', icon: 'FolderOpened' },
  ]
  if (auth.isManager) {
    items.unshift(
      { path: '/dashboard', title: '生产看板', icon: 'DataAnalysis' },
      { path: '/ledger', title: '工厂台账', icon: 'List' },
      { path: '/reports', title: '台账报表', icon: 'TrendCharts' },
      { path: '/assistant', title: 'AI 助手', icon: 'ChatDotRound' },
    )
  }
  if (auth.isAdmin) {
    items.push(
      { path: '/products', title: '产品管理', icon: 'Goods' },
      { path: '/templates', title: '模板与字典', icon: 'Document' },
      { path: '/users', title: '用户管理', icon: 'UserFilled' },
      { path: '/settings', title: '系统设置', icon: 'Setting' },
    )
  }
  return items
})

const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role)

const menuOpen = ref(false)
const needForcePwd = computed(() => !!auth.user?.must_change_password)

const llmConfigured = ref(false)
const llmModel = ref('')

// 登录后 App.vue 不会重新挂载：只在 onMounted 里取一次的话，
// 徽标会一直停在"未配置"，强制改密标志也拿不到——所以同时监听 user 变化。
async function syncLlmStatus() {
  if (!auth.isManager) return
  try {
    const { data } = await api.get('/settings/system-info')
    llmConfigured.value = data.llm_configured
    llmModel.value = data.llm_model
  } catch {
    /* 忽略：仅用于展示 */
  }
  // 刷新用户信息（获取强制改密标志等）
  try {
    await auth.refreshToken()
  } catch {
    /* 401 由拦截器处理 */
  }
  if (auth.user?.must_change_password) pwdVisible.value = true
}

onMounted(syncLlmStatus)
watch(() => auth.user, syncLlmStatus)

const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })

function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  } else if (cmd === 'password') {
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm = ''
    pwdVisible.value = true
  }
}

async function changePassword() {
  if (!pwdForm.new_password || pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  try {
    await api.post('/auth/change-password', {
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
    })
    ElMessage.success('密码修改成功')
    auth.user.must_change_password = false
    localStorage.setItem('user', JSON.stringify(auth.user))
    pwdVisible.value = false
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background: linear-gradient(180deg, #0b1c2c 0%, #10263f 55%, #0b1c2c 100%);
  display: flex;
  flex-direction: column;
  position: relative;
}
.logo {
  color: #fff;
  font-size: 16px;
  font-weight: bold;
  padding: 16px;
  white-space: nowrap;
  letter-spacing: 2px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(90deg, rgba(22, 119, 255, 0.25), transparent);
  display: flex;
  align-items: center;
  gap: 8px;
}
.logo svg {
  flex-shrink: 0;
}
.menu {
  border-right: none;
  background: transparent;
  flex: 1;
  padding: 8px 0;
  overflow-y: auto;
}
.menu::-webkit-scrollbar {
  width: 0;
}
.menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.68);
  margin: 4px 10px;
  border-radius: 8px;
  height: 44px;
}
.menu :deep(.el-menu-item.is-active) {
  color: #fff;
  background: linear-gradient(90deg, #1677ff, #3d8bff);
  box-shadow: 0 4px 10px rgba(22, 119, 255, 0.35);
}
.menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(16, 24, 40, 0.06);
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  position: sticky;
  top: 0;
  z-index: 20;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-title {
  font-size: 17px;
  font-weight: 600;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #333;
  font-size: 14px;
  padding: 6px 10px;
  border-radius: 8px;
  transition: background 0.2s;
}
.user-info:hover {
  background: #f0f2f7;
}
.main {
  background: var(--page-bg);
  overflow: auto;
}
.menu-btn {
  display: none;
}
.aside-mask {
  display: none;
}
@media (max-width: 768px) {
  .menu-btn {
    display: inline-flex;
  }
  .aside {
    position: fixed;
    z-index: 200;
    height: 100vh;
    transform: translateX(-100%);
    transition: transform 0.25s;
  }
  .aside.open {
    transform: none;
  }
  .aside-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 150;
  }
  .page-title {
    font-size: 15px;
  }
  .stat-value {
    font-size: 18px;
  }
}
</style>
