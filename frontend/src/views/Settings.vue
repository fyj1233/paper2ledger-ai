<template>
  <div>
    <el-alert
      v-if="!config.llm_configured"
      title="当前未配置大模型 API，系统使用内置规则提取模式（效果有限）。在下方填写 OpenAI 兼容接口配置后即可启用 AI 智能提取。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <el-card shadow="never">
      <template #header>大模型 API 配置（OpenAI 兼容接口）</template>
      <el-form :model="form" label-width="130px" style="max-width: 640px">
        <el-form-item label="API 地址">
          <el-input v-model="form.llm_api_base" placeholder="例如 https://api.deepseek.com/v1" />
          <div class="tip">OpenAI 兼容的 base_url，将拼接 /chat/completions 调用</div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="form.llm_api_key"
            type="password"
            show-password
            :placeholder="config.llm_api_key_set ? `已配置（${config.llm_api_key_hint}），留空表示不修改` : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.llm_model" placeholder="例如 deepseek-chat / qwen-plus / gpt-4o-mini" />
        </el-form-item>
        <el-form-item label="月度营业额目标">
          <el-input v-model="form.monthly_target" placeholder="例如 50000（填数字，看板显示完成进度；留空不显示进度条）" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存配置</el-button>
          <el-button @click="testLlm" :loading="testing">测试连接</el-button>
          <el-button v-if="config.llm_api_key_set" text type="danger" @click="clearKey">清除已保存的 Key</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="backup-head">
          <span>备用大模型（兜底）—— 主服务商报错时自动切换</span>
          <el-tag v-if="config.llm_backup_configured" type="success" size="small">已启用</el-tag>
          <el-tag v-else type="info" size="small">未配置</el-tag>
        </div>
      </template>
      <el-alert
        title="填写另一家服务商的配置后，AI 提取 / AI 问答 / AI 报告在主 API 报错（超时、5xx、欠费）时会自动改用备用接口重试一次，无需人工干预。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-form :model="form" label-width="130px" style="max-width: 640px">
        <el-form-item label="备用 API 地址">
          <el-input v-model="form.llm_backup_api_base" placeholder="例如 https://api.siliconflow.cn/v1（留空默认 OpenAI）" />
        </el-form-item>
        <el-form-item label="备用 API Key">
          <el-input
            v-model="form.llm_backup_api_key"
            type="password"
            show-password
            :placeholder="config.llm_backup_key_set ? `已配置（${config.llm_backup_key_hint}），留空表示不修改` : 'sk-...'"
          />
        </el-form-item>
        <el-form-item label="备用模型名称">
          <el-input v-model="form.llm_backup_model" placeholder="例如 deepseek-chat / glm-4-flash" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存配置</el-button>
          <el-button @click="testLlmBackup" :loading="testingBackup">测试备用连接</el-button>
          <el-button v-if="config.llm_backup_key_set" text type="danger" @click="clearBackupKey">清除备用 Key</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="backup-head">
          <span>数据备份（数据库 + 上传文件打包，自动清理 30 天前的备份）</span>
          <el-button type="primary" size="small" :loading="backingUp" @click="doBackup">立即备份</el-button>
        </div>
      </template>
      <div class="auto-backup-row">
        <span class="ab-label">每日自动备份</span>
        <el-switch v-model="form.auto_backup_enabled" />
        <el-time-select
          v-model="form.auto_backup_time"
          start="00:00"
          end="23:30"
          step="00:30"
          :disabled="!form.auto_backup_enabled"
          style="width: 110px"
        />
        <el-button size="small" @click="save">保存</el-button>
        <el-tag v-if="config.auto_backup_enabled" type="success" size="small">已开启</el-tag>
        <span class="tip" style="margin-left: 0">到点自动打包；错过时间点服务启动后会补跑一次，当日已有备份则跳过</span>
      </div>
      <el-table :data="backups" size="small" v-loading="backupLoading" max-height="260">
        <el-table-column prop="file" label="备份文件" min-width="220" />
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ (row.size / 1024).toFixed(1) }} KB</template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.modified_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="downloadBackup(row)">下载</el-button>
            <el-button text type="danger" size="small" @click="removeBackup(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>操作审计日志（最近 100 条）</template>
      <el-table :data="audit" v-loading="auditLoading" size="small" max-height="420">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="操作人" width="120" />
        <el-table-column prop="action" label="操作" width="140" />
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errMsg } from '../api'
import { formatTime } from '../utils'

const config = ref({})
const form = reactive({
  llm_api_base: '', llm_api_key: '', llm_model: '', monthly_target: '',
  llm_backup_api_base: '', llm_backup_api_key: '', llm_backup_model: '',
  auto_backup_enabled: false, auto_backup_time: '23:30',
})
const testing = ref(false)
const testingBackup = ref(false)
const audit = ref([])
const auditLoading = ref(false)
const backups = ref([])
const backupLoading = ref(false)
const backingUp = ref(false)

async function fetchBackups() {
  backupLoading.value = true
  try {
    const { data } = await api.get('/backup')
    backups.value = data
  } finally {
    backupLoading.value = false
  }
}

async function doBackup() {
  backingUp.value = true
  try {
    const { data } = await api.post('/backup')
    ElMessage.success(data.message)
    fetchBackups()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    backingUp.value = false
  }
}

async function downloadBackup(row) {
  try {
    const resp = await api.get('/backup/download', { params: { name: row.file }, responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = row.file
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeBackup(row) {
  const ok = await ElMessageBox.confirm(`确定删除备份「${row.file}」？`, '删除确认', { type: 'warning' }).catch(() => false)
  if (!ok) return
  try {
    await api.delete(`/backup/${encodeURIComponent(row.file)}`)
    ElMessage.success('已删除')
    fetchBackups()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function fetchConfig() {
  const { data } = await api.get('/settings')
  config.value = data
  form.llm_api_base = data.llm_api_base
  form.llm_api_key = ''
  form.llm_model = data.llm_model
  form.monthly_target = data.monthly_target ?? ''
  form.llm_backup_api_base = data.llm_backup_api_base || ''
  form.llm_backup_api_key = ''
  form.llm_backup_model = data.llm_backup_model || ''
  form.auto_backup_enabled = !!data.auto_backup_enabled
  form.auto_backup_time = data.auto_backup_time || '23:30'
}

async function save() {
  try {
    const { data } = await api.put('/settings', {
      llm_api_base: form.llm_api_base,
      llm_api_key: form.llm_api_key || null,
      llm_model: form.llm_model,
      monthly_target: form.monthly_target === '' ? '' : Number(form.monthly_target),
      llm_backup_api_base: form.llm_backup_api_base,
      llm_backup_api_key: form.llm_backup_api_key || null,
      llm_backup_model: form.llm_backup_model,
      auto_backup_enabled: form.auto_backup_enabled,
      auto_backup_time: form.auto_backup_time,
    })
    config.value = data
    form.llm_api_key = ''
    form.llm_backup_api_key = ''
    form.monthly_target = data.monthly_target ?? ''
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function clearKey() {
  try {
    const { data } = await api.put('/settings', { llm_api_key: '' })
    config.value = data
    ElMessage.success('已清除保存的 API Key')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function clearBackupKey() {
  try {
    const { data } = await api.put('/settings', {
      llm_backup_api_key: '',
      llm_backup_api_base: '',
      llm_backup_model: '',
    })
    config.value = data
    form.llm_backup_api_base = ''
    form.llm_backup_model = ''
    ElMessage.success('已清除备用配置')
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function testLlm() {
  testing.value = true
  try {
    const { data } = await api.post('/settings/test-llm')
    if (data.ok) {
      ElMessage.success(data.message)
    } else {
      ElMessage.error(data.message)
    }
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    testing.value = false
  }
}

async function testLlmBackup() {
  testingBackup.value = true
  try {
    const { data } = await api.post('/settings/test-llm-backup')
    if (data.ok) {
      ElMessage.success(data.message)
    } else {
      ElMessage.error(data.message)
    }
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    testingBackup.value = false
  }
}

async function fetchAudit() {
  auditLoading.value = true
  try {
    const { data } = await api.get('/users/audit')
    audit.value = data
  } finally {
    auditLoading.value = false
  }
}

onMounted(() => {
  fetchConfig()
  fetchAudit()
  fetchBackups()
})
</script>

<style scoped>
.tip {
  color: #aaa;
  font-size: 12px;
  line-height: 1.6;
}
.backup-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.auto-backup-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.ab-label {
  font-size: 13px;
  color: #666;
}
</style>
