<template>
  <div>
    <!-- 月度出货目标进度 -->
    <el-card v-if="data.monthly_target" shadow="never" class="target-card">
      <div class="target-row">
        <span class="target-label">本月出货目标（¥{{ formatMoney(data.monthly_target) }}）</span>
        <el-progress
          class="target-bar"
          :percentage="targetPct"
          :status="targetPct >= 100 ? 'success' : undefined"
          :stroke-width="14"
        />
        <span class="target-pct">{{ targetPct }}%</span>
      </div>
    </el-card>

    <!-- 日期筛选 -->
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
          <el-tag
            v-if="data.product_filter"
            closable
            type="primary"
            effect="plain"
            @close="clearProduct"
          >产品：{{ data.product_filter.name }} {{ data.product_filter.spec }}</el-tag>
        </div>
        <el-button :icon="'Refresh'" @click="fetchAll">刷新</el-button>
      </div>
    </el-card>

    <!-- 工作台提醒 -->
    <div class="anomaly-box">
      <el-alert
        v-if="data.summary?.pending_count || data.summary?.failed_count"
        :title="`还有 ${data.summary.pending_count} 份单据待解析${data.summary.failed_count ? `，${data.summary.failed_count} 份解析失败需处理` : ''}`"
        :type="data.summary.failed_count ? 'warning' : 'info'"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      />
      <el-alert
        v-if="data.summary?.pending_entry_count"
        :title="`有 ${data.summary.pending_entry_count} 条提取条目无法自动匹配产品，待人工确认`"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      />
      <el-alert
        v-for="a in bizAlerts"
        :key="a.message"
        :title="a.message"
        :type="a.type === 'halt' ? 'error' : 'warning'"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      />
      <el-alert
        v-for="p in lowStocks"
        :key="p.product_id"
        :title="`库存告急：${p.name} ${p.spec} 结存 ${p.balance}${p.unit}（预警线 ${p.warn_stock}${p.unit}）`"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom: 8px"
      />
    </div>

    <!-- 汇总卡片 -->
    <el-row :gutter="16" class="cards">
      <el-col :xs="12" :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat">
            <div class="stat-icon blue"><el-icon><Histogram /></el-icon></div>
            <div class="stat-body">
              <div class="stat-label">今日产量</div>
              <div class="stat-value">{{ formatQty(data.summary?.today_production) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat">
            <div class="stat-icon cyan"><el-icon><Van /></el-icon></div>
            <div class="stat-body">
              <div class="stat-label">今日出货量</div>
              <div class="stat-value">{{ formatQty(data.summary?.today_shipment) }}</div>
              <div class="stat-sub">金额 ¥{{ formatMoney(data.summary?.today_ship_amount) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat">
            <div class="stat-icon green"><el-icon><DataLine /></el-icon></div>
            <div class="stat-body">
              <div class="stat-label">
                期间出货量
                <span v-if="shipChange" :class="['delta', shipChange.up ? 'up' : 'down']">
                  {{ shipChange.up ? '↑' : '↓' }} {{ shipChange.pct }}%
                </span>
              </div>
              <div class="stat-value">{{ formatQty(data.summary?.shipment) }}</div>
              <div class="stat-sub">产量 {{ formatQty(data.summary?.production) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat">
            <div class="stat-icon gold"><el-icon><Coin /></el-icon></div>
            <div class="stat-body">
              <div class="stat-label">
                期间出货金额
                <span v-if="amountChange" :class="['delta', amountChange.up ? 'up' : 'down']">
                  {{ amountChange.up ? '↑' : '↓' }} {{ amountChange.pct }}%
                </span>
              </div>
              <div class="stat-value">¥{{ formatMoney(data.summary?.ship_amount) }}</div>
              <div class="stat-sub">本月 ¥{{ formatMoney(data.summary?.month_ship_amount) }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表 -->
    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            产量 / 出货量 趋势
            <el-text v-if="data.product_filter" type="primary" size="small">
              （{{ data.product_filter.name }} {{ data.product_filter.spec }}）
            </el-text>
          </template>
          <div ref="lineRef" class="chart chart-line"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>规格出货量占比（点击下钻）</template>
          <div ref="pieRef" class="chart chart-pie"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 月度对比 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>月度产量 / 出货量对比</template>
          <div ref="barRef" class="chart chart-bar"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>
            <div class="toolbar-row">
              <span>库存结存</span>
              <el-button text type="primary" size="small" @click="$router.push('/ledger')">台账明细</el-button>
            </div>
          </template>
          <el-table :data="inventory" size="small" max-height="280">
            <el-table-column label="产品" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.name }}<br /><el-text size="small" type="info">{{ row.spec }}</el-text></template>
            </el-table-column>
            <el-table-column prop="unit" label="单位" width="60" />
            <el-table-column label="结存" width="90" align="right">
              <template #default="{ row }">
                <span :style="row.low_stock ? 'color:#f56c6c;font-weight:700' : ''">{{ row.balance }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="70" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.low_stock" type="danger" size="small">告急</el-tag>
                <el-tag v-else type="success" size="small" effect="plain">正常</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近单据 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="toolbar-row">
          <span>最近上传单据</span>
          <el-button text type="primary" @click="$router.push('/documents')">查看全部</el-button>
        </div>
      </template>
      <el-table :data="data.recent_documents || []" size="large">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="STATUS[row.status]?.type || 'info'" size="small">
              {{ STATUS[row.status]?.label || row.status }}
            </el-tag>
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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import api from '../api'
import { formatMoney, formatTime, STATUS } from '../utils'

const range = ref(defaultRange())
const data = ref({})
const inventory = ref([])
const anomalies = ref([])
const lineRef = ref()
const pieRef = ref()
const barRef = ref()
let lineChart = null
let pieChart = null
let barChart = null

function defaultRange() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 29)
  const fmt = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return [fmt(start), fmt(end)]
}

function formatQty(v) {
  const n = Number(v ?? 0)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/* 环比：期间 vs 上一等长周期 */
const shipChange = computed(() => changeOf(data.value.summary?.shipment, data.value.prev_summary?.shipment))
const amountChange = computed(() => changeOf(data.value.summary?.ship_amount, data.value.prev_summary?.ship_amount))

function changeOf(cur, prev) {
  if (cur === undefined || prev === undefined || !prev) return null
  const pct = ((cur - prev) / prev) * 100
  return { pct: Math.abs(pct).toFixed(1), up: pct >= 0 }
}

/* 月度出货目标进度 */
const targetPct = computed(() => {
  const target = data.value.monthly_target
  const amount = data.value.summary?.month_ship_amount || 0
  if (!target) return 0
  return Math.min(100, Math.round((amount / target) * 100))
})

/* 库存告急（来自库存接口） */
const lowStocks = computed(() => inventory.value.filter((p) => p.low_stock))

/* 经营预警（断产/出货骤降；库存告急由 lowStocks 展示，跳过避免重复） */
const bizAlerts = computed(() =>
  (anomalies.value || []).filter((a) => a.type === 'halt' || a.type === 'ship_drop')
)

async function fetchData() {
  const params = { start: range.value?.[0], end: range.value?.[1] }
  if (data.value.product_filter) params.product_id = data.value.product_filter.id
  const resp = await api.get('/dashboard/overview', { params })
  data.value = resp.data
  renderCharts()
}

async function fetchInventory() {
  try {
    const resp = await api.get('/ledger/inventory')
    inventory.value = resp.data || []
  } catch {
    inventory.value = []
  }
}

async function fetchAnomalies() {
  try {
    const resp = await api.get('/assistant/anomalies')
    anomalies.value = resp.data.alerts || []
  } catch {
    anomalies.value = []
  }
}

function fetchAll() {
  fetchData()
  fetchInventory()
  fetchAnomalies()
}

function clearProduct() {
  data.value.product_filter = null
  fetchData()
}

function renderCharts() {
  const daily = data.value.daily || []
  if (lineRef.value) {
    lineChart = lineChart || echarts.init(lineRef.value)
    lineChart.setOption({
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const lines = [params[0]?.axisValue]
          for (const p of params) {
            lines.push(`${p.marker} ${p.seriesName}：${Number(p.value).toLocaleString('zh-CN')}`)
          }
          return lines.join('<br/>')
        },
      },
      legend: { data: ['产量', '出货量'] },
      grid: { left: 60, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: daily.map((d) => d.date.slice(5)) },
      yAxis: { type: 'value' },
      series: [
        { name: '产量', type: 'line', smooth: true, data: daily.map((d) => d.production), itemStyle: { color: '#1677ff' } },
        { name: '出货量', type: 'line', smooth: true, data: daily.map((d) => d.shipment), itemStyle: { color: '#52c41a' }, areaStyle: { opacity: 0.08 } },
      ],
    })
  }

  const specs = (data.value.spec_stats || []).filter((s) => s.shipment > 0)
  if (pieRef.value) {
    pieChart = pieChart || echarts.init(pieRef.value)
    pieChart.setOption({
      tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>出货量：${Number(p.value).toLocaleString('zh-CN')}（${p.percent}%）` },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['38%', '65%'],
          center: ['50%', '45%'],
          data: specs.map((s) => ({ name: `${s.name} ${s.spec}`, value: s.shipment, product_id: s.product_id })),
          label: { formatter: '{b}\n{d}%' },
        },
      ],
    })
    pieChart.off('click')
    pieChart.on('click', (params) => {
      if (!params.data?.product_id) return
      const cur = data.value.product_filter?.id
      data.value.product_filter =
        cur === params.data.product_id ? null : { id: params.data.product_id, name: '', spec: '' }
      // 先取概览返回的完整名称展示，避免标签空白
      if (data.value.product_filter) {
        const s = (data.value.spec_stats || []).find((x) => x.product_id === params.data.product_id)
        if (s) data.value.product_filter = { id: s.product_id, name: s.name, spec: s.spec }
      }
      fetchData()
    })
  }

  const monthly = data.value.monthly || []
  if (barRef.value) {
    barChart = barChart || echarts.init(barRef.value)
    barChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['产量', '出货量'] },
      grid: { left: 60, right: 20, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: monthly.map((m) => m.month) },
      yAxis: { type: 'value' },
      series: [
        { name: '产量', type: 'bar', data: monthly.map((m) => m.production), itemStyle: { color: '#1677ff' }, barMaxWidth: 36 },
        { name: '出货量', type: 'bar', data: monthly.map((m) => m.shipment), itemStyle: { color: '#52c41a' }, barMaxWidth: 36 },
      ],
    })
  }
}

function onResize() {
  lineChart?.resize()
  pieChart?.resize()
  barChart?.resize()
}

onMounted(() => {
  fetchAll()
  window.addEventListener('resize', onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  lineChart?.dispose()
  pieChart?.dispose()
  barChart?.dispose()
})
watch(range, fetchData)
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
.target-card {
  margin-bottom: 16px;
}
.target-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.target-label {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
}
.target-bar {
  flex: 1;
}
.target-pct {
  font-weight: 700;
  color: #1677ff;
  width: 52px;
  text-align: right;
}
.cards {
  margin: 16px 0;
}
.anomaly-box {
  margin-top: 16px;
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
  gap: 14px;
  align-items: center;
}
.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}
.stat-icon.blue {
  background: rgba(22, 119, 255, 0.1);
  color: #1677ff;
}
.stat-icon.green {
  background: rgba(82, 196, 26, 0.12);
  color: #52c41a;
}
.stat-icon.cyan {
  background: rgba(0, 178, 255, 0.1);
  color: #00b2ff;
}
.stat-icon.gold {
  background: rgba(250, 173, 20, 0.12);
  color: #d48806;
}
.stat-body {
  min-width: 0;
}
.stat-label {
  color: #999;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.delta {
  font-size: 12px;
  font-weight: 700;
}
.delta.up {
  color: #52c41a;
}
.delta.down {
  color: #ff4d4f;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  margin-top: 4px;
  color: #1677ff;
  white-space: nowrap;
}
.stat-sub {
  color: #bbb;
  font-size: 12px;
  margin-top: 4px;
}
.chart {
  width: 100%;
}
.chart-line {
  height: 340px;
}
.chart-pie {
  height: 340px;
}
.chart-bar {
  height: 280px;
}
</style>
