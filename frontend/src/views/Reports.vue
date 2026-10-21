<template>
  <div>
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-row">
        <div class="toolbar-left">
          <el-date-picker
            v-model="range"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            :clearable="false"
            style="width: 280px"
          />
          <el-button-group>
            <el-button v-for="q in quicks" :key="q.label" size="small" @click="applyQuick(q)">{{ q.label }}</el-button>
          </el-button-group>
        </div>
        <div>
          <el-button type="primary" :icon="'Search'" @click="fetchReport">查询</el-button>
          <el-button type="success" :icon="'Download'" :loading="exporting" @click="exportExcel">导出 Excel</el-button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" class="cards">
      <el-col :xs="12" :span="4" v-for="card in cards" :key="card.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat">
            <div class="stat-icon" :class="card.cls"><el-icon><component :is="card.icon" /></el-icon></div>
            <div class="stat-body">
              <div class="stat-label">{{ card.label }}</div>
              <div class="stat-value" :style="card.color ? `color:${card.color}` : ''">{{ card.value }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>规格汇总（期间结存流转）</template>
      <el-table :data="report.products || []" size="small" :default-sort="{ prop: 'closing', order: 'descending' }">
        <el-table-column label="产品" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.name }}<br /><el-text size="small" type="info">{{ row.spec }}</el-text></template>
        </el-table-column>
        <el-table-column prop="unit" label="单位" width="60" />
        <el-table-column prop="opening" label="期初结存" width="90" align="right" />
        <el-table-column prop="initial" label="期初调整" width="90" align="right">
          <template #default="{ row }">{{ row.initial || '' }}</template>
        </el-table-column>
        <el-table-column prop="production" label="生产入库" width="90" align="right" />
        <el-table-column prop="return" label="退货" width="80" align="right">
          <template #default="{ row }">{{ row.return || '' }}</template>
        </el-table-column>
        <el-table-column prop="shipment" label="出货" width="80" align="right" />
        <el-table-column prop="scrap" label="报废" width="80" align="right">
          <template #default="{ row }">{{ row.scrap || '' }}</template>
        </el-table-column>
        <el-table-column label="期末结存" width="90" align="right">
          <template #default="{ row }">
            <span :style="row.warn_stock !== null && row.closing <= row.warn_stock ? 'color:#f56c6c;font-weight:700' : 'font-weight:700'">
              {{ row.closing }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="ship_amount" label="出货金额(元)" width="110" align="right" />
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="toolbar-row">
          <span>日台账明细（{{ report.range?.start }} ~ {{ report.range?.end }}）</span>
          <el-tag type="info" size="small">共 {{ report.summary?.row_count || 0 }} 行</el-tag>
        </div>
      </template>
      <el-table :data="pagedDaily" size="small">
        <el-table-column prop="date" label="日期" width="105" />
        <el-table-column label="产品" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.name }}<br /><el-text size="small" type="info">{{ row.spec }}</el-text></template>
        </el-table-column>
        <el-table-column prop="unit" label="单位" width="60" />
        <el-table-column prop="opening" label="开仓" width="85" align="right" />
        <el-table-column prop="initial" label="期初调整" width="90" align="right">
          <template #default="{ row }">{{ row.initial || '' }}</template>
        </el-table-column>
        <el-table-column prop="production" label="生产入库" width="90" align="right" />
        <el-table-column prop="return" label="退货" width="80" align="right">
          <template #default="{ row }">{{ row.return || '' }}</template>
        </el-table-column>
        <el-table-column prop="shipment" label="出货" width="80" align="right" />
        <el-table-column prop="scrap" label="报废" width="80" align="right">
          <template #default="{ row }">{{ row.scrap || '' }}</template>
        </el-table-column>
        <el-table-column label="结存" width="85" align="right">
          <template #default="{ row }"><span class="closing">{{ row.closing }}</span></template>
        </el-table-column>
        <el-table-column prop="ship_amount" label="出货金额(元)" width="110" align="right" />
      </el-table>
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="daily.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Coin, Delete, Histogram, RefreshLeft, Van } from '@element-plus/icons-vue'
import api from '../api'

const range = ref(weekRange())
const report = ref({})
const page = ref(1)
const pageSize = 20
const exporting = ref(false)

const quicks = [
  { label: '本周', days: 'week' },
  { label: '上周', days: 'lastWeek' },
  { label: '本月', days: 'month' },
  { label: '上月', days: 'lastMonth' },
]

function fmt(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function weekRange() {
  const now = new Date()
  const start = new Date(now)
  start.setDate(now.getDate() - now.getDay() + 1) // 周一
  return [fmt(start), fmt(now)]
}

function applyQuick(q) {
  const now = new Date()
  let start, end = now
  if (q.days === 'week') {
    start = new Date(now)
    start.setDate(now.getDate() - now.getDay() + 1)
  } else if (q.days === 'lastWeek') {
    end = new Date(now)
    end.setDate(now.getDate() - now.getDay())
    start = new Date(end)
    start.setDate(end.getDate() - 6)
  } else if (q.days === 'month') {
    start = new Date(now.getFullYear(), now.getMonth(), 1)
  } else {
    start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    end = new Date(now.getFullYear(), now.getMonth(), 0)
  }
  range.value = [fmt(start), fmt(end)]
  page.value = 1
  fetchReport()
}

function formatQty(v) {
  return Number(v ?? 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const cards = computed(() => {
  const s = report.value.summary || {}
  return [
    { label: '生产入库', value: formatQty(s.production), icon: Histogram, cls: 'blue' },
    { label: '出货量', value: formatQty(s.shipment), icon: Van, cls: 'green' },
    { label: '退货', value: formatQty(s.return), icon: RefreshLeft, cls: 'cyan' },
    { label: '报废', value: formatQty(s.scrap), icon: Delete, cls: 'red', color: '#f56c6c' },
    { label: '出货金额(元)', value: formatQty(s.ship_amount), icon: Coin, cls: 'gold', color: '#d48806' },
  ]
})

const daily = computed(() => report.value.daily || [])
const pagedDaily = computed(() => daily.value.slice((page.value - 1) * pageSize, page.value * pageSize))

async function fetchReport() {
  const [start, end] = range.value || []
  const resp = await api.get('/ledger/report', { params: { start, end } })
  report.value = resp.data
  page.value = 1
}

async function exportExcel() {
  exporting.value = true
  try {
    const [start, end] = range.value || []
    const resp = await api.get('/ledger/report/export', { params: { start, end }, responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `日台账报表_${start}_${end}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 Excel')
  } catch {
    ElMessage.error('导出失败，请重试')
  } finally {
    exporting.value = false
  }
}

onMounted(fetchReport)
</script>

<style scoped>
.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.cards {
  margin: 16px 0;
}
.stat-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(16, 24, 40, 0.1) !important;
}
.stat {
  display: flex;
  gap: 12px;
  align-items: center;
}
.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.stat-icon.blue { background: rgba(22, 119, 255, 0.1); color: #1677ff; }
.stat-icon.green { background: rgba(82, 196, 26, 0.12); color: #52c41a; }
.stat-icon.cyan { background: rgba(0, 178, 255, 0.1); color: #00b2ff; }
.stat-icon.red { background: rgba(255, 77, 79, 0.1); color: #ff4d4f; }
.stat-icon.gold { background: rgba(250, 173, 20, 0.12); color: #d48806; }
.stat-label {
  color: #999;
  font-size: 12px;
  white-space: nowrap;
}
.stat-value {
  font-size: 20px;
  font-weight: 700;
  margin-top: 4px;
  color: #1677ff;
  white-space: nowrap;
}
.closing {
  font-weight: 700;
  color: #1677ff;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
