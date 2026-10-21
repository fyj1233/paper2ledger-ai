<template>
  <div>
    <el-alert
      title="上传生产日报、出货单、盘点表等文档，系统自动提取规格条目（品名 / 规格 / 类型 / 数量），匹配上产品的直接写入台账，匹配不上的进入待确认"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <el-card shadow="never">
      <el-upload
        drag
        multiple
        :accept="accept"
        :show-file-list="false"
        :http-request="customUpload"
        :disabled="uploading"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文件拖到此处，或 <em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">
            支持 TXT / CSV / Word(.docx) / Excel(.xlsx) / PDF / 图片小票拍照（.jpg .png），单个不超过 20MB
          </div>
        </template>
      </el-upload>
    </el-card>

    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6"><el-card shadow="hover"><div class="mini"><span>本周上传</span><b>{{ weekStats.count }} 份</b></div></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><div class="mini"><span>解析成功</span><b class="green">{{ weekStats.ok }} 份</b></div></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><div class="mini"><span>本周台账条目</span><b>{{ weekStats.items }} 条</b></div></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><div class="mini"><span>待处理/待确认/失败</span><b :class="{ red: weekStats.bad > 0 }">{{ weekStats.bad }}</b></div></el-card></el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>我的上传记录</template>
      <el-table :data="docs" v-loading="loading" size="large" @row-click="goDetail">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ EXT_LABELS[row.file_type] || row.file_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tooltip :disabled="!row.error" :content="row.error" placement="top">
              <el-tag :type="STATUS[row.status]?.type || 'info'" size="small">
                {{ STATUS[row.status]?.label || row.status }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="台账条目" width="130" align="center">
          <template #default="{ row }">
            <span>{{ row.item_count ?? 0 }}</span>
            <el-tag v-if="row.pending_count" size="small" type="danger" effect="plain" style="margin-left: 4px">{{ row.pending_count }} 待确认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api, { errMsg } from '../api'
import { EXT_LABELS, formatTime, STATUS } from '../utils'

const accept = '.txt,.csv,.docx,.xlsx,.pdf,.jpg,.jpeg,.png'
const docs = ref([])
const loading = ref(false)
const uploading = ref(false)
const router = useRouter()
let timer = null

const weekStats = computed(() => {
  const now = new Date()
  const monday = new Date(now)
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7))
  monday.setHours(0, 0, 0, 0)
  let count = 0, ok = 0, items = 0, bad = 0
  for (const d of docs.value) {
    const created = new Date(d.created_at)
    if (created < monday) continue
    count++
    if (d.status === 'parsed') {
      ok++
      items += d.item_count || 0
      if (d.pending_count) bad += d.pending_count
    } else {
      bad++
    }
  }
  return { count, ok, items, bad }
})

async function fetchDocs() {
  loading.value = docs.value.length === 0
  try {
    const { data } = await api.get('/documents')
    docs.value = data
  } finally {
    loading.value = false
  }
  schedulePoll()
}

function schedulePoll() {
  clearTimeout(timer)
  const busy = docs.value.some((d) => d.status === 'pending' || d.status === 'processing')
  if (busy) timer = setTimeout(fetchDocs, 3000)
}

async function customUpload({ file }) {
  uploading.value = true
  const form = new FormData()
  form.append('file', file)
  try {
    await api.post('/documents/upload', form)
    ElMessage.success(`${file.name} 上传成功，正在解析`)
    await fetchDocs()
  } catch (e) {
    ElMessage.error(`${file.name} 上传失败：${errMsg(e)}`)
  } finally {
    uploading.value = false
  }
}

function goDetail(row) {
  router.push({ path: '/documents', query: { detail: row.id } })
}

onMounted(fetchDocs)
onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
:deep(.el-upload-dragger) {
  padding: 40px 0;
}
:deep(.el-table__row) {
  cursor: pointer;
}
.mini {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #666;
}
.mini b {
  font-size: 20px;
  color: #1677ff;
}
.mini b.green {
  color: #52c41a;
}
.mini b.red {
  color: #ff4d4f;
}
</style>
