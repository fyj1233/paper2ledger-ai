<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新增用户</el-button>
      </div>

      <el-table :data="users" v-loading="loading" size="large">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'manager' ? 'warning' : 'info'" effect="plain">
              {{ ROLE_LABELS[row.role] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              :disabled="row.id === auth.user?.id"
              @change="(v) => toggleActive(row, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" size="small" :disabled="row.id === auth.user?.id" @click="remove(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新增用户'" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="editing" placeholder="2-50 个字符" />
        </el-form-item>
        <el-form-item :label="editing ? '重置密码' : '密码'">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editing ? '留空表示不修改密码' : '至少 6 位'"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="form.role">
            <el-radio value="employee">员工（仅上传）</el-radio>
            <el-radio value="manager">经理（看板+管理）</el-radio>
            <el-radio value="admin">管理员（全部权限）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errMsg } from '../api'
import { useAuthStore } from '../stores/auth'
import { ROLE_LABELS, formatTime } from '../utils'

const auth = useAuthStore()
const users = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({ username: '', password: '', role: 'employee' })

async function fetchUsers() {
  loading.value = true
  try {
    const { data } = await api.get('/users')
    users.value = data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.username = ''
  form.password = ''
  form.role = 'employee'
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  form.username = row.username
  form.password = ''
  form.role = row.role
  dialogVisible.value = true
}

async function submit() {
  try {
    if (editing.value) {
      const body = { role: form.role }
      if (form.password) body.password = form.password
      await api.put(`/users/${editing.value.id}`, body)
      ElMessage.success('已保存')
    } else {
      if (!form.username || form.username.length < 2) {
        ElMessage.warning('用户名至少 2 个字符')
        return
      }
      if (!form.password || form.password.length < 6) {
        ElMessage.warning('密码至少 6 位')
        return
      }
      await api.post('/users', { username: form.username, password: form.password, role: form.role })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    fetchUsers()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function toggleActive(row, value) {
  try {
    await api.put(`/users/${row.id}`, { is_active: value })
    row.is_active = value
    ElMessage.success(value ? '已启用' : '已停用')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function remove(row) {
  const confirmed = await ElMessageBox.confirm(`确定删除用户「${row.username}」？`, '删除确认', {
    type: 'warning',
  }).catch(() => false)
  if (!confirmed) return
  try {
    await api.delete(`/users/${row.id}`)
    ElMessage.success('已删除')
    fetchUsers()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(fetchUsers)
</script>

<style scoped>
.toolbar {
  margin-bottom: 14px;
}
</style>
