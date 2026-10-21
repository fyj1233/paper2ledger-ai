<template>
  <div class="login-page">
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <el-card class="login-card">
      <div class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 56 56" width="60" height="60" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="p2lBadge" x1="4" y1="4" x2="52" y2="52" gradientUnits="userSpaceOnUse">
              <stop stop-color="#3b8bff" />
              <stop offset="1" stop-color="#0f3a8d" />
            </linearGradient>
          </defs>
          <rect x="4" y="4" width="48" height="48" rx="13" fill="url(#p2lBadge)" />
          <path d="M19 11.5h12.5L39 19v20.5A3.5 3.5 0 0 1 35.5 43H19a3.5 3.5 0 0 1-3.5-3.5V15a3.5 3.5 0 0 1 3.5-3.5z" fill="#ffffff" />
          <path d="M31.5 11.5V16a3 3 0 0 0 3 3H39l-7.5-7.5z" fill="#c9defc" />
          <rect x="20.5" y="24" width="8.5" height="3" rx="1.5" fill="#1677ff" />
          <rect x="31" y="24" width="5" height="3" rx="1.5" fill="#8fbcff" />
          <rect x="20.5" y="30" width="11" height="3" rx="1.5" fill="#1677ff" />
          <rect x="33" y="30" width="3" height="3" rx="1.5" fill="#8fbcff" />
          <rect x="20.5" y="36" width="6" height="3" rx="1.5" fill="#52c41a" />
          <rect x="28" y="36" width="8" height="3" rx="1.5" fill="#a5df8f" />
        </svg>
      </div>
      <h2 class="title">一纸成账</h2>
      <p class="subtitle">Paper2Ledger · 工厂单据智能台账系统</p>
      <el-form :model="form" @keyup.enter="submit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" show-password placeholder="密码" size="large">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
      <p class="hint">首次部署默认管理员：admin / admin123，登录后请立即修改密码</p>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push(auth.role === 'employee' ? '/upload' : '/dashboard')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #0f3a8d 0%, #1677ff 45%, #0b1c2c 100%);
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
  pointer-events: none;
}
.blob-1 {
  width: 420px;
  height: 420px;
  background: #5eb0ff;
  top: -120px;
  left: -100px;
  animation: float 9s ease-in-out infinite;
}
.blob-2 {
  width: 360px;
  height: 360px;
  background: #52c41a;
  bottom: -140px;
  right: -80px;
  opacity: 0.28;
  animation: float 11s ease-in-out infinite reverse;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(30px); }
}
.login-card {
  width: 380px;
  padding: 12px 8px;
  border-radius: 16px !important;
  border: 1px solid rgba(255, 255, 255, 0.35) !important;
  background: rgba(255, 255, 255, 0.92) !important;
  backdrop-filter: blur(14px);
  box-shadow: 0 20px 60px rgba(0, 21, 41, 0.45) !important;
  position: relative;
  z-index: 1;
}
.brand-mark {
  width: 60px;
  margin: 4px auto 10px;
  filter: drop-shadow(0 6px 16px rgba(15, 58, 141, 0.35));
}
.brand-mark svg {
  display: block;
}
.title {
  text-align: center;
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 700;
  color: #0f3a8d;
  letter-spacing: 10px;
  text-indent: 10px;
}
.subtitle {
  text-align: center;
  color: #999;
  margin-bottom: 24px;
  font-size: 13px;
  letter-spacing: 1px;
}
.hint {
  text-align: center;
  color: #bbb;
  font-size: 12px;
  margin-top: 16px;
}
</style>
