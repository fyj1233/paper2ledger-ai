<template>
  <el-card shadow="never" class="ai-card">
    <div class="assistant-layout">
      <!-- ── 会话栏 ── -->
      <aside class="session-bar">
        <el-button type="primary" class="new-chat" @click="newSession">＋ 新建对话</el-button>
        <div class="session-list" v-loading="sessionsLoading">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: currentSession?.id === s.id }"
            @click="switchSession(s)"
          >
            <div class="s-main">
              <div class="s-title">{{ s.title }}</div>
              <div class="s-time">{{ s.updated_at?.slice(5, 16).replace('T', ' ') }}</div>
            </div>
            <el-icon class="s-del" @click.stop="removeSession(s)"><Delete /></el-icon>
          </div>
          <div v-if="!sessionsLoading && sessions.length === 0" class="s-empty">暂无历史会话</div>
        </div>
      </aside>

      <!-- ── 主区 ── -->
      <div class="main-area">
        <el-tabs v-model="tab">
          <!-- ── 台账问答 ── -->
          <el-tab-pane label="台账问答" name="chat">
            <div class="chat-wrap">
              <div class="chat-messages" ref="msgBox">
                <div v-if="messages.length === 0" class="chat-empty">
                  <div class="chat-empty-title">问我任何台账相关的问题</div>
                  <div class="chat-tips">
                    <el-tag
                      v-for="q in suggestions"
                      :key="q"
                      class="tip-tag"
                      effect="plain"
                      @click="input = q"
                    >{{ q }}</el-tag>
                  </div>
                </div>
                <div
                  v-for="(m, i) in messages"
                  :key="i"
                  class="chat-row"
                  :class="m.role === 'user' ? 'me' : 'ai'"
                >
                  <div class="bubble" :class="{ 'tool-line': m.tool }">
                    <span class="bubble-text">{{ m.content }}</span>
                    <span v-if="m.role === 'assistant' && m.streaming" class="cursor">▌</span>
                  </div>
                </div>
              </div>
              <div class="chat-input">
                <el-input
                  v-model="input"
                  type="textarea"
                  :rows="2"
                  resize="none"
                  :placeholder="`例如：这个月哪天出货最多？（Ctrl + Enter 发送）`"
                  :disabled="chatting"
                  @keydown.ctrl.enter.prevent="send"
                />
                <div class="chat-actions">
                  <span class="ctx-tip">对话自动保留上下文，可连续追问</span>
                  <el-button type="primary" :loading="chatting" @click="send">发送</el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <!-- ── 报告中心 ── -->
          <el-tab-pane label="报告中心" name="report">
            <div class="report-toolbar">
              <el-radio-group v-model="reportType">
                <el-radio-button value="weekly">周报</el-radio-button>
                <el-radio-button value="monthly">月报</el-radio-button>
              </el-radio-group>
              <el-date-picker
                v-model="anchorDate"
                type="date"
                placeholder="选择基准日期（默认今天）"
                value-format="YYYY-MM-DD"
                style="width: 200px"
              />
              <el-button type="primary" :loading="generating" @click="generate">一键生成报告</el-button>
            </div>

            <el-card v-if="currentReport" shadow="never" class="report-view">
              <template #header>
                <div class="report-head">
                  <span>
                    {{ currentReport.report_type === 'weekly' ? '周报' : '月报' }}
                    （{{ currentReport.period_start }} ~ {{ currentReport.period_end }}）
                  </span>
                  <div>
                    <el-button text type="primary" size="small" @click="copyReport">复制全文</el-button>
                    <el-button text type="primary" size="small" :disabled="!currentReport.charts" @click="printReport">打印 / 存 PDF</el-button>
                  </div>
                </div>
              </template>

              <!-- 可视化报告（新报告：图表数据由后端计算，AI 只写文字） -->
              <div v-if="currentReport.charts" class="print-area">
                <el-row :gutter="12" class="r-cards">
                  <el-col v-for="c in currentReport.charts.cards" :key="c.label" :xs="12" :span="6">
                    <div class="r-card">
                      <div class="r-card-label">{{ c.label }}</div>
                      <div class="r-card-value">
                        {{ fmtNum(c.value) }}<span class="r-card-unit">{{ c.unit }}</span>
                      </div>
                      <div v-if="c.change !== null && c.change !== undefined" class="r-card-change" :class="c.change >= 0 ? 'up' : 'down'">
                        {{ c.change >= 0 ? '↑' : '↓' }} 较上期 {{ (Math.abs(c.change) * 100).toFixed(1) }}%
                      </div>
                      <div v-else class="r-card-change muted">—</div>
                    </div>
                  </el-col>
                </el-row>

                <div class="r-chart-grid">
                  <div class="r-chart-box">
                    <div class="r-chart-title">产量 / 出货趋势（含出货金额）</div>
                    <div ref="trendRef" class="r-chart"></div>
                  </div>
                  <div class="r-chart-box">
                    <div class="r-chart-title">规格出货排行</div>
                    <div ref="rankRef" class="r-chart"></div>
                  </div>
                </div>

                <div class="r-chart-title" style="margin-top: 4px">库存结存（红字为低于预警线）</div>
                <el-table :data="currentReport.charts.inventory" size="small" class="r-inv-table">
                  <el-table-column label="产品" min-width="180">
                    <template #default="{ row }">{{ row.name }}（{{ row.spec }}）</template>
                  </el-table-column>
                  <el-table-column label="结存" width="140" align="right">
                    <template #default="{ row }">
                      <span :style="row.low ? 'color:#f56c6c;font-weight:700' : ''">{{ row.balance }} {{ row.unit }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="110" align="center">
                    <template #default="{ row }">
                      <el-tag v-if="row.low" type="danger" size="small" effect="plain">库存告急</el-tag>
                      <el-tag v-else type="success" size="small" effect="plain">正常</el-tag>
                    </template>
                  </el-table-column>
                </el-table>

                <div class="r-analysis">
                  <div class="r-analysis-title">AI 分析</div>
                  <pre class="report-content">{{ currentReport.content }}</pre>
                </div>
              </div>

              <!-- 旧报告降级：纯文本 -->
              <pre v-else class="report-content">{{ currentReport.content }}</pre>
            </el-card>

            <el-card shadow="never" style="margin-top: 16px">
              <template #header>历史报告</template>
              <el-table :data="reports" v-loading="reportsLoading" size="small">
                <el-table-column label="类型" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.report_type === 'weekly' ? 'primary' : 'success'" effect="plain">
                      {{ row.report_type === 'weekly' ? '周报' : '月报' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="统计期间" min-width="200">
                  <template #default="{ row }">{{ row.period_start }} ~ {{ row.period_end }}</template>
                </el-table-column>
                <el-table-column prop="creator_name" label="生成人" width="110" />
                <el-table-column label="生成时间" width="170">
                  <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="130">
                  <template #default="{ row }">
                    <el-button text type="primary" size="small" @click="viewReport(row)">查看</el-button>
                    <el-button text type="danger" size="small" @click="removeReport(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api, { errMsg } from '../api'
import { useAuthStore } from '../stores/auth'
import { formatTime } from '../utils'

const auth = useAuthStore()
const tab = ref('chat')

/* ── 会话管理 ── */
const sessions = ref([])
const sessionsLoading = ref(false)
const currentSession = ref(null)
const SESSION_KEY = 'chat_session_id'

async function fetchSessions() {
  sessionsLoading.value = true
  try {
    const { data } = await api.get('/assistant/sessions')
    sessions.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    sessionsLoading.value = false
  }
}

async function newSession() {
  try {
    const { data } = await api.post('/assistant/sessions')
    sessions.value.unshift(data)
    activateSession(data)
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function activateSession(s) {
  currentSession.value = s
  messages.value = []
  localStorage.setItem(SESSION_KEY, String(s.id))
}

async function switchSession(s) {
  if (currentSession.value?.id === s.id || chatting.value) return
  activateSession(s)
  try {
    const { data } = await api.get(`/assistant/sessions/${s.id}/messages`)
    messages.value = data.messages.map((m) =>
      m.tool ? { role: 'assistant', content: `🔧 调用工具：${m.tool}`, tool: true } : m
    )
    scrollBottom()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeSession(s) {
  const confirmed = await ElMessageBox.confirm(`确定删除会话「${s.title}」？`, '删除确认', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  try {
    await api.delete(`/assistant/sessions/${s.id}`)
    sessions.value = sessions.value.filter((x) => x.id !== s.id)
    if (currentSession.value?.id === s.id) {
      if (sessions.value.length) switchSession(sessions.value[0])
      else newSession()
    }
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

/* ── 台账问答 ── */
const suggestions = [
  '这个月出货量一共多少？',
  '现在的库存结存情况？',
  '各规格的出货排行怎么样？',
  '对比一下本月和上月的出货量',
  '最近有什么异常需要注意？',
]
const messages = ref([])
const input = ref('')
const chatting = ref(false)
const msgBox = ref()

function scrollBottom() {
  nextTick(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text || chatting.value) return
  if (!currentSession.value) await newSession()
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  chatting.value = true
  scrollBottom()

  // 注意：取代理对象（而非原始对象），否则流式修改不触发重新渲染
  messages.value.push({ role: 'assistant', content: '', streaming: true })
  const reply = messages.value[messages.value.length - 1]
  scrollBottom()

  try {
    const resp = await fetch('/api/assistant/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        message: text,
        session_id: currentSession.value?.id ?? null,
      }),
    })
    if (!resp.ok) {
      let detail = `请求失败（${resp.status}）`
      try {
        detail = (await resp.json()).detail || detail
      } catch { /* ignore */ }
      reply.content += `[${detail}]`
    } else {
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const raw = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          for (const line of raw.split('\n')) {
            if (!line.startsWith('data:')) continue
            const payload = line.slice(5).trim()
            if (payload === '[DONE]') continue
            try {
              const obj = JSON.parse(payload)
              if (obj.session_id) {
                // 新建会话：首帧返回会话 id/标题，刷新列表
                if (currentSession.value?.id !== obj.session_id) {
                  currentSession.value = { id: obj.session_id, title: obj.title }
                  localStorage.setItem(SESSION_KEY, String(obj.session_id))
                  fetchSessions()
                } else if (currentSession.value.title !== obj.title) {
                  currentSession.value.title = obj.title
                  fetchSessions()
                }
              } else if (obj.tool) {
                reply.content += `\n🔧 调用工具：${obj.tool}\n`
                scrollBottom()
              } else if (obj.delta) {
                reply.content += obj.delta
                scrollBottom()
              }
            } catch { /* 忽略不完整片段 */ }
          }
        }
      }
    }
  } catch (e) {
    reply.content += `[网络异常：${e.message}]`
  } finally {
    reply.streaming = false
    chatting.value = false
    scrollBottom()
  }
}

/* ── 报告中心 ── */
const reportType = ref('weekly')
const anchorDate = ref('')
const generating = ref(false)
const currentReport = ref(null)
const reports = ref([])
const reportsLoading = ref(false)
const trendRef = ref()
const rankRef = ref()
let trendChart = null
let rankChart = null

function fmtNum(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

function renderCharts() {
  const c = currentReport.value?.charts
  if (!c || !trendRef.value || !rankRef.value) return
  trendChart?.dispose()
  rankChart?.dispose()
  trendChart = echarts.init(trendRef.value)
  rankChart = echarts.init(rankRef.value)

  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['产量', '出货量', '出货金额'], top: 0 },
    grid: { left: 62, right: 62, top: 32, bottom: 26 },
    xAxis: { type: 'category', data: c.trend.dates },
    yAxis: [
      // 轴名放成竖排：放在轴顶端会和图例挤在同一行
      { type: 'value', name: '数量', nameLocation: 'middle', nameGap: 44 },
      { type: 'value', name: '金额(元)', nameLocation: 'middle', nameGap: 46, splitLine: { show: false } },
    ],
    series: [
      { name: '产量', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#1677ff', borderRadius: [3, 3, 0, 0] }, data: c.trend.production },
      { name: '出货量', type: 'bar', barMaxWidth: 22, itemStyle: { color: '#52c41a', borderRadius: [3, 3, 0, 0] }, data: c.trend.shipment },
      { name: '出货金额', type: 'line', yAxisIndex: 1, smooth: true, itemStyle: { color: '#faad14' }, lineStyle: { width: 2 }, data: c.trend.ship_amount },
    ],
  })

  const rank = [...c.spec_rank].reverse()
  rankChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 140, right: 40, top: 12, bottom: 26 },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: rank.map((s) => `${s.name} ${s.spec}`),
      axisLabel: { width: 130, overflow: 'truncate' },
    },
    series: [
      {
        name: '出货量',
        type: 'bar',
        barMaxWidth: 16,
        itemStyle: { color: '#1677ff', borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', formatter: ({ value }) => `${value}` },
        data: rank.map((s) => s.shipment),
      },
    ],
  })
}

function resizeCharts() {
  trendChart?.resize()
  rankChart?.resize()
}

async function fetchReports() {
  reportsLoading.value = true
  try {
    const { data } = await api.get('/assistant/reports')
    reports.value = data
  } finally {
    reportsLoading.value = false
  }
}

async function generate() {
  generating.value = true
  try {
    const { data } = await api.post('/assistant/report', {
      report_type: reportType.value,
      anchor_date: anchorDate.value || null,
    })
    currentReport.value = data
    nextTick(renderCharts)
    ElMessage.success('报告已生成')
    fetchReports()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    generating.value = false
  }
}

async function viewReport(row) {
  try {
    const { data } = await api.get(`/assistant/reports/${row.id}`)
    currentReport.value = data
    nextTick(renderCharts)
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeReport(row) {
  const confirmed = await ElMessageBox.confirm('确定删除该报告？', '删除确认', { type: 'warning' }).catch(() => false)
  if (!confirmed) return
  try {
    await api.delete(`/assistant/reports/${row.id}`)
    if (currentReport.value?.id === row.id) currentReport.value = null
    ElMessage.success('已删除')
    fetchReports()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function copyReport() {
  try {
    await navigator.clipboard.writeText(currentReport.value.content)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本复制')
  }
}

function printReport() {
  nextTick(() => window.print())
}

onMounted(async () => {
  await fetchSessions()
  // 恢复上次会话（刷新/切页面不丢）；不存在则新建
  const saved = Number(localStorage.getItem(SESSION_KEY))
  const found = sessions.value.find((s) => s.id === saved)
  if (found) switchSession(found)
  else newSession()
  fetchReports()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  rankChart?.dispose()
})
</script>

<style scoped>
.ai-card :deep(.el-tabs__content) {
  overflow: visible;
}
.assistant-layout {
  display: flex;
  gap: 16px;
  min-height: 560px;
}
.session-bar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid #ebeef5;
  padding-right: 14px;
}
.new-chat {
  width: 100%;
  margin-bottom: 12px;
}
.session-list {
  max-height: 640px;
  overflow: auto;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
}
.session-item:hover {
  background: #f5f7fa;
}
.session-item.active {
  background: #e8f1ff;
}
.s-main {
  flex: 1;
  min-width: 0;
}
.s-title {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #303133;
}
.session-item.active .s-title {
  color: #1677ff;
  font-weight: 600;
}
.s-time {
  font-size: 12px;
  color: #a8abb2;
  margin-top: 2px;
}
.s-del {
  color: #c0c4cc;
  flex-shrink: 0;
}
.s-del:hover {
  color: #f56c6c;
}
.s-empty {
  text-align: center;
  color: #c0c4cc;
  font-size: 13px;
  padding: 20px 0;
}
.main-area {
  flex: 1;
  min-width: 0;
}
.chat-wrap {
  display: flex;
  flex-direction: column;
}
.chat-messages {
  height: 440px;
  overflow: auto;
  background: #f7f8fa;
  border-radius: 8px;
  padding: 16px;
}
.chat-empty {
  text-align: center;
  padding-top: 130px;
  color: #999;
}
.chat-empty-title {
  font-size: 15px;
  margin-bottom: 16px;
}
.tip-tag {
  margin: 0 6px 10px;
  cursor: pointer;
}
.chat-row {
  display: flex;
  margin-bottom: 12px;
}
.chat-row.me {
  justify-content: flex-end;
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.chat-row.me .bubble {
  background: #1677ff;
  color: #fff;
  border-top-left-radius: 2px;
}
.chat-row.ai .bubble {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-top-right-radius: 2px;
}
.bubble.tool-line {
  background: transparent;
  border: none;
  color: #a8abb2;
  font-size: 12px;
  padding: 2px 4px;
}
.cursor {
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.chat-input {
  margin-top: 12px;
}
.chat-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.ctx-tip {
  font-size: 12px;
  color: #a8abb2;
  margin-right: auto;
}
.report-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.report-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.report-content {
  font-family: inherit;
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
  margin: 0;
}
/* ── 可视化报告 ── */
.r-cards {
  margin-bottom: 14px;
}
.r-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.r-card-label {
  font-size: 13px;
  color: #909399;
}
.r-card-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  margin: 4px 0 2px;
}
.r-card-unit {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  margin-left: 4px;
}
.r-card-change {
  font-size: 12px;
}
.r-card-change.up {
  color: #52c41a;
}
.r-card-change.down {
  color: #f56c6c;
}
.r-card-change.muted {
  color: #c0c4cc;
}
.r-chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
@media (max-width: 1100px) {
  .r-chart-grid {
    grid-template-columns: 1fr;
  }
}
.r-chart-box {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px 12px 6px;
}
.r-chart-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 4px;
}
.r-chart {
  height: 260px;
  width: 100%;
}
.r-inv-table {
  margin-bottom: 14px;
}
.r-analysis {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 14px 16px;
}
.r-analysis-title {
  font-size: 13px;
  font-weight: 600;
  color: #1677ff;
  margin-bottom: 8px;
}
/* ── 打印：只输出报告区 ── */
@media print {
  body * {
    visibility: hidden;
  }
  .print-area,
  .print-area * {
    visibility: visible;
  }
  .print-area {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
  }
  .r-chart {
    height: 300px;
  }
}
</style>
