<template>
  <div>
    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="search"
          placeholder="按文件名搜索"
          clearable
          :prefix-icon="'Search'"
          style="width: 220px"
        />
        <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px" @change="fetchDocs">
          <el-option label="待处理" value="pending" />
          <el-option label="解析中" value="processing" />
          <el-option label="已完成" value="parsed" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button :icon="'Refresh'" @click="fetchDocs">刷新</el-button>
      </div>

      <el-table :data="pagedDocs" v-loading="loading" size="large">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="filename" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ EXT_LABELS[row.file_type] || row.file_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="auth.isManager" prop="uploader" label="上传人" width="110" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tooltip :disabled="!row.error" :content="row.error" placement="top">
              <el-tag :type="STATUS[row.status]?.type || 'info'" size="small">
                {{ STATUS[row.status]?.label || row.status }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="台账条目" width="100" align="center">
          <template #default="{ row }">
            <span>{{ row.item_count ?? 0 }}</span>
            <el-tag v-if="row.pending_count" size="small" type="danger" effect="plain" style="margin-left: 4px">{{ row.pending_count }} 待确认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openDetail(row)">详情</el-button>
            <el-button v-if="auth.isManager" text type="warning" size="small" @click="reparse(row)">重新解析</el-button>
            <el-button v-if="auth.isAdmin" text size="small" @click="download(row)">下载</el-button>
            <el-button v-if="auth.isManager" text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="filteredDocs.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" :title="detail?.filename" size="60%">
      <template v-if="detail">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="上传人">{{ detail.uploader }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="STATUS[detail.status]?.type || 'info'" size="small">
              {{ STATUS[detail.status]?.label || detail.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="条目 / 待确认">{{ detail.item_count ?? 0 }} / {{ detail.pending_count ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="上传时间" :span="3">{{ formatTime(detail.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="detail.error && detail.status === 'failed'"
          :title="detail.error"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        />

        <h4>提取的台账条目（已自动匹配产品入库）</h4>
        <el-table :data="detail.items" size="small" border>
          <el-table-column prop="entry_date" label="日期" width="105" />
          <el-table-column label="产品" min-width="160">
            <template #default="{ row }">
              <div>{{ row.product_name }}</div>
              <div class="sub">{{ row.spec }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="entry_type_label" label="类型" width="90" />
          <el-table-column label="数量" width="100" align="right">
            <template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template>
          </el-table-column>
          <el-table-column label="金额(元)" width="100" align="right">
            <template #default="{ row }">{{ row.amount != null ? formatMoney(row.amount) : '—' }}</template>
          </el-table-column>
          <el-table-column label="客户" width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.customer || '—' }}</template>
          </el-table-column>
          <el-table-column label="来源" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="SOURCE_LABELS[row.source]?.type || 'info'" effect="plain">
                {{ SOURCE_LABELS[row.source]?.label || row.source }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="evidence" label="原文依据" min-width="160" show-overflow-tooltip />
        </el-table>
        <el-empty v-if="!detail.items?.length" description="本文档没有提取出台账条目" :image-size="60" />

        <template v-if="detail.pending?.length">
          <h4 style="margin-top: 20px">待确认条目（未匹配到产品，需人工处理）</h4>
          <el-table :data="detail.pending" size="small" border>
            <el-table-column prop="entry_date" label="日期" width="105" />
            <el-table-column label="品名 / 规格" min-width="160">
              <template #default="{ row }">
                <div>{{ row.product_name || '（未识别品名）' }}</div>
                <div class="sub">{{ row.spec }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="entry_type_label" label="类型" width="90" />
            <el-table-column label="数量" width="100" align="right">
              <template #default="{ row }">{{ row.quantity }} {{ row.unit }}</template>
            </el-table-column>
            <el-table-column label="客户" width="110" show-overflow-tooltip>
              <template #default="{ row }">{{ row.customer || '—' }}</template>
            </el-table-column>
            <el-table-column label="来源" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="SOURCE_LABELS[row.source]?.type || 'info'" effect="plain">
                  {{ SOURCE_LABELS[row.source]?.label || row.source }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div class="pending-tip">请到「工厂台账 → 待确认」标签页处理这些条目。</div>
        </template>

        <template v-if="detail.raw_text !== null && detail.raw_text !== undefined">
          <h4 style="margin-top: 20px">解析出的文本内容</h4>
          <pre class="raw-text">{{ detail.raw_text }}</pre>
        </template>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errMsg } from '../api'
import { useAuthStore } from '../stores/auth'
import { EXT_LABELS, formatMoney, formatTime, STATUS, SOURCE_LABELS } from '../utils'

const auth = useAuthStore()
const route = useRoute()
const docs = ref([])
const loading = ref(false)
const statusFilter = ref('')
const search = ref('')
const page = ref(1)
const pageSize = 15
const drawerVisible = ref(false)
const detail = ref(null)
let timer = null

const filteredDocs = computed(() =>
  docs.value.filter((d) => !search.value || d.filename.toLowerCase().includes(search.value.toLowerCase())),
)
const pagedDocs = computed(() =>
  filteredDocs.value.slice((page.value - 1) * pageSize, page.value * pageSize),
)

async function fetchDocs() {
  loading.value = docs.value.length === 0
  try {
    const { data } = await api.get('/documents', { params: statusFilter.value ? { status: statusFilter.value } : {} })
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

async function openDetail(row) {
  const { data } = await api.get(`/documents/${row.id}`)
  detail.value = data
  drawerVisible.value = true
}

async function reparse(row) {
  try {
    await api.post(`/documents/${row.id}/reparse`)
    ElMessage.success('已加入解析队列')
    fetchDocs()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function download(row) {
  const resp = await api.get(`/documents/${row.id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = row.filename
  a.click()
  URL.revokeObjectURL(url)
}

async function remove(row) {
  const confirmed = await ElMessageBox.confirm(`确定删除「${row.filename}」及其提取的数据？`, '删除确认', {
    type: 'warning',
  }).catch(() => false)
  if (!confirmed) return
  try {
    await api.delete(`/documents/${row.id}`)
    ElMessage.success('已删除')
    fetchDocs()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(() => {
  fetchDocs()
  const detailId = Number(route.query.detail)
  if (detailId) {
    const row = { id: detailId }
    openDetail(row).catch(() => {})
  }
})
onUnmounted(() => clearTimeout(timer))
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.raw-text {
  background: #f6f8fa;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 300px;
  overflow: auto;
}
.sub {
  font-size: 12px;
  color: #999;
}
.pending-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #e6a23c;
}
</style>
