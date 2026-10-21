<template>
  <div>
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-radio-group v-model="quickRange" @change="applyQuickRange">
          <el-radio-button value="today">今天</el-radio-button>
          <el-radio-button value="week">本周</el-radio-button>
          <el-radio-button value="month">本月</el-radio-button>
          <el-radio-button value="30d">近30天</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="range"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          :clearable="false"
          style="width: 270px"
          @change="onFilterChange"
        />
        <el-select v-model="productFilter" placeholder="全部产品" clearable filterable style="width: 200px" @change="onFilterChange">
          <el-option v-for="p in products" :key="p.id" :label="p.name + ' ' + p.spec" :value="p.id" />
        </el-select>
        <el-select v-model="typeFilter" placeholder="全部类型" clearable style="width: 130px" @change="onFilterChange">
          <el-option v-for="(label, key) in TYPE_LABELS" :key="key" :label="label" :value="key" />
        </el-select>
        <el-button :icon="'Refresh'" @click="fetchAll">刷新</el-button>
        <el-button type="primary" :icon="'EditPen'" @click="openCreate">录入台账</el-button>
      </div>
    </el-card>

    <el-row :gutter="16" class="summary-row">
      <el-col :xs="12" :span="6"><el-card shadow="never"><div class="mini"><span>期内台账笔数</span><b>{{ total }}</b></div></el-card></el-col>
      <el-col :xs="12" :span="6"><el-card shadow="never"><div class="mini"><span>期内出货金额</span><b>¥{{ formatMoney(shipAmount) }}</b></div></el-card></el-col>
      <el-col :xs="12" :span="6"><el-card shadow="hover" class="clickable" @click="goPending"><div class="mini"><span>待确认条目</span><b :class="{ red: pendingTotal > 0 }">{{ pendingTotal }}</b></div></el-card></el-col>
      <el-col :xs="12" :span="6"><el-card shadow="never"><div class="mini"><span>库存告急产品</span><b :class="{ red: lowStockCount > 0 }">{{ lowStockCount }}</b></div></el-card></el-col>
    </el-row>

    <el-card shadow="never">
      <el-tabs v-model="tab" @tab-change="onTabChange">
        <!-- ── 台账明细 ── -->
        <el-tab-pane label="台账明细" name="entries">
          <el-table :data="entries" v-loading="loading" size="large">
            <el-table-column prop="entry_date" label="日期" width="110" />
            <el-table-column label="产品" min-width="190">
              <template #default="{ row }">
                <div>{{ row.product_name }}</div>
                <div class="sub">{{ row.spec }}</div>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="TYPE_TAGS[row.entry_type]?.type || 'info'" effect="plain">
                  {{ TYPE_LABELS[row.entry_type] || row.entry_type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="130" align="right">
              <template #default="{ row }">{{ row.quantity }}<span class="sub"> {{ row.unit }}</span></template>
            </el-table-column>
            <el-table-column label="单价(元)" width="100" align="right">
              <template #default="{ row }">{{ row.unit_price ?? '—' }}</template>
            </el-table-column>
            <el-table-column label="金额(元)" width="110" align="right">
              <template #default="{ row }">{{ row.amount != null ? formatMoney(row.amount) : '—' }}</template>
            </el-table-column>
            <el-table-column label="客户" min-width="130">
              <template #default="{ row }">{{ row.customer || '—' }}</template>
            </el-table-column>
            <el-table-column label="来源" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="SOURCE_LABELS[row.source]?.type || 'info'" effect="plain">
                  {{ SOURCE_LABELS[row.source]?.label || row.source }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button text type="primary" size="small" @click="openEdit(row)">修改</el-button>
                <el-button text type="info" size="small" @click="showEdits(row)">留痕</el-button>
                <el-button text type="danger" size="small" @click="removeEntry(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pager-row">
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="total"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="fetchEntries"
              @size-change="onFilterChange"
            />
          </div>
          <el-empty v-if="!loading && !entries.length" description="该条件下暂无台账记录" :image-size="80" />
        </el-tab-pane>

        <!-- ── 待确认条目 ── -->
        <el-tab-pane name="pending">
          <template #label>
            <span>待确认<el-badge v-if="pendingTotal" :value="pendingTotal" :max="99" type="danger" style="margin-left: 6px" /></span>
          </template>
          <el-alert
            title="这里是从文档中提取出、但找不到对应产品的规格条目。处理后才会写入台账；新建产品或认领到已有产品均可。"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
          />
          <el-table :data="pending" v-loading="pendingLoading" size="large">
            <el-table-column prop="entry_date" label="日期" width="110" />
            <el-table-column label="品名 / 规格" min-width="200">
              <template #default="{ row }">
                <div>{{ row.product_name || '（未识别品名）' }}</div>
                <div class="sub">{{ row.spec || '' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="TYPE_TAGS[row.entry_type]?.type || 'info'" effect="plain">
                  {{ row.entry_type_label || TYPE_LABELS[row.entry_type] || row.entry_type }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="120" align="right">
              <template #default="{ row }">{{ row.quantity }}<span class="sub"> {{ row.unit }}</span></template>
            </el-table-column>
            <el-table-column label="金额(元)" width="110" align="right">
              <template #default="{ row }">{{ row.amount != null ? formatMoney(row.amount) : '—' }}</template>
            </el-table-column>
            <el-table-column label="客户" min-width="110">
              <template #default="{ row }">{{ row.customer || '—' }}</template>
            </el-table-column>
            <el-table-column label="来源" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="SOURCE_LABELS[row.source]?.type || 'info'" effect="plain">
                  {{ SOURCE_LABELS[row.source]?.label || row.source }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="document_name" label="来源文档" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">{{ row.document_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button text type="primary" size="small" @click="openResolve(row)">处理</el-button>
                <el-button text type="danger" size="small" @click="ignorePending(row)">忽略</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!pendingLoading && !pending.length" description="没有待确认条目，文档里提取出的规格都已自动匹配产品" :image-size="80" />
        </el-tab-pane>

        <!-- ── 库存结存 ── -->
        <el-tab-pane label="库存结存" name="inventory">
          <el-table :data="inventory" v-loading="invLoading" size="large">
            <el-table-column type="index" label="#" width="60" />
            <el-table-column label="产品" min-width="190">
              <template #default="{ row }">
                <div>{{ row.name }}</div>
                <div class="sub">{{ row.spec }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="unit" label="单位" width="80" />
            <el-table-column label="期初" width="90" align="right">
              <template #default="{ row }">{{ row.initial }}</template>
            </el-table-column>
            <el-table-column label="累计生产" width="100" align="right">
              <template #default="{ row }">{{ row.production }}</template>
            </el-table-column>
            <el-table-column label="累计出货" width="100" align="right">
              <template #default="{ row }">{{ row.shipment }}</template>
            </el-table-column>
            <el-table-column label="累计报废" width="100" align="right">
              <template #default="{ row }">{{ row.scrap }}</template>
            </el-table-column>
            <el-table-column label="当前结存" width="130" align="right">
              <template #default="{ row }">
                <b :class="{ red: row.low_stock }">{{ row.balance }}</b>
                <el-tag v-if="row.low_stock" size="small" type="danger" effect="plain" style="margin-left: 4px">告急</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="预警阈值" width="100" align="right">
              <template #default="{ row }">{{ row.warn_stock ?? '—' }}</template>
            </el-table-column>
          </el-table>
          <div class="inv-tip">结存 = 期初 + 生产入库 + 退货 − 出货 − 报废，实时计算</div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 录入/修改台账弹窗 -->
    <el-dialog v-model="dialog" :title="form.id ? '修改台账（自动留痕）' : '录入台账'" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="日期">
          <el-date-picker v-model="form.entry_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="产品">
          <el-select v-model="form.product_id" filterable placeholder="选择产品" style="width: 100%">
            <el-option v-for="p in activeProducts" :key="p.id" :label="p.name + ' ' + p.spec" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.entry_type">
            <el-radio-button v-for="(label, key) in TYPE_LABELS" :key="key" :value="key">{{ label }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.quantity" :min="0.0001" :precision="3" style="width: 100%" />
        </el-form-item>
        <el-form-item label="单价(元)">
          <el-input-number v-model="form.unit_price" :min="0" :precision="2" style="width: 100%" placeholder="出货时可填" />
        </el-form-item>
        <el-form-item label="金额(元)">
          <el-input-number v-model="form.amount" :min="0" :precision="2" style="width: 100%" :placeholder="autoAmountHint" />
        </el-form-item>
        <el-form-item v-if="form.entry_type === 'shipment' || form.entry_type === 'return'" label="客户">
          <el-input v-model="form.customer" placeholder="选填" maxlength="100" />
        </el-form-item>
        <el-form-item v-if="!form.id" label="备注">
          <el-input v-model="form.note" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">{{ form.id ? '保存' : '入账' }}</el-button>
      </template>
    </el-dialog>

    <!-- 留痕弹窗 -->
    <el-dialog v-model="editsDialog" title="修改留痕" width="520px">
      <el-timeline v-if="edits.length">
        <el-timeline-item v-for="e in edits" :key="e.id" :timestamp="formatTime(e.created_at) + ' · ' + e.username">
          <div v-for="(c, i) in e.changes" :key="i" class="edit-line">
            {{ FIELD_LABELS[c.field] || c.field }}：<s>{{ formatValue(c.old) }}</s> → <b>{{ formatValue(c.new) }}</b>
          </div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="这条记录还没有修改过" :image-size="70" />
    </el-dialog>

    <!-- 待确认处理弹窗 -->
    <el-dialog v-model="resolveDialog" title="处理待确认条目" width="540px">
      <el-descriptions v-if="resolving" :column="2" border size="small">
        <el-descriptions-item label="日期">{{ resolving.entry_date }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ resolving.entry_type_label }}</el-descriptions-item>
        <el-descriptions-item label="品名">{{ resolving.product_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="规格">{{ resolving.spec || '—' }}</el-descriptions-item>
        <el-descriptions-item label="数量">{{ resolving.quantity }} {{ resolving.unit }}</el-descriptions-item>
        <el-descriptions-item label="客户">{{ resolving.customer || '—' }}</el-descriptions-item>
      </el-descriptions>
      <el-radio-group v-model="resolveAction" style="margin: 14px 0">
        <el-radio-button value="create">新建产品并入库</el-radio-button>
        <el-radio-button value="assign">认领已有产品</el-radio-button>
        <el-radio-button value="ignore">忽略</el-radio-button>
      </el-radio-group>
      <el-form v-if="resolveAction === 'create'" label-width="90px">
        <el-form-item label="单位">
          <el-input v-model="resolveForm.unit" placeholder="默认沿用文档中的单位" maxlength="20" style="width: 200px" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="resolveForm.category" placeholder="如：螺母" maxlength="50" style="width: 200px" />
        </el-form-item>
        <el-form-item label="预警阈值">
          <el-input-number v-model="resolveForm.warn_stock" :min="0" :precision="2" style="width: 200px" placeholder="选填" />
        </el-form-item>
        <div class="tip">
          将按「{{ resolving?.product_name || '未命名产品' }} {{ resolving?.spec }}」新建产品，并自动写入这笔台账。
        </div>
      </el-form>
      <el-form v-else-if="resolveAction === 'assign'" label-width="90px">
        <el-form-item label="产品">
          <el-select v-model="resolveForm.product_id" filterable placeholder="这条记录对应哪个产品？" style="width: 100%">
            <el-option v-for="p in activeProducts" :key="p.id" :label="p.name + ' ' + p.spec" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div v-else class="tip">忽略后这条记录将被删除，不写入台账（适用：与产品无关的杂项文字被误提取）。</div>
      <template #footer>
        <el-button @click="resolveDialog = false">取消</el-button>
        <el-button type="primary" :loading="resolvingBusy" @click="submitResolve">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errMsg } from '../api'
import { SOURCE_LABELS, formatMoney, formatTime } from '../utils'

const TYPE_LABELS = {
  production: '生产入库',
  shipment: '出货',
  scrap: '报废',
  return: '退货',
  initial: '期初',
}
const TYPE_TAGS = {
  production: { type: 'success' },
  shipment: { type: 'primary' },
  scrap: { type: 'danger' },
  return: { type: 'warning' },
  initial: { type: 'info' },
}
const FIELD_LABELS = {
  entry_date: '日期', product_id: '产品', entry_type: '类型', quantity: '数量',
  unit_price: '单价', amount: '金额', customer: '客户',
}

const tab = ref('entries')
const quickRange = ref('30d')
const range = ref(last30())
const productFilter = ref(null)
const typeFilter = ref('')
const loading = ref(false)
const invLoading = ref(false)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

const products = ref([])
const entries = ref([])
const inventory = ref([])
const shipAmount = ref(0)
const pending = ref([])
const pendingTotal = ref(0)
const pendingLoading = ref(false)

const activeProducts = computed(() => products.value.filter((p) => p.is_active))
const lowStockCount = computed(() => inventory.value.filter((i) => i.low_stock).length)
const autoAmountHint = computed(() => {
  if (form.quantity && form.unit_price) return `留空自动 = ${form.quantity} × ${form.unit_price}`
  return '留空按 数量×单价 自动计算'
})

function last30() {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 29)
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return [fmt(start), fmt(end)]
}

function applyQuickRange(v) {
  const end = new Date()
  const start = new Date()
  if (v === 'today') {
    // 同一天
  } else if (v === 'week') {
    const day = (end.getDay() + 6) % 7
    start.setDate(end.getDate() - day)
  } else if (v === 'month') {
    start.setDate(1)
  } else {
    start.setDate(end.getDate() - 29)
  }
  const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  range.value = [fmt(start), fmt(end)]
  onFilterChange()
}

async function fetchProducts() {
  try {
    const { data } = await api.get('/products')
    products.value = data
  } catch {
    products.value = []
  }
}

async function fetchEntries() {
  loading.value = true
  try {
    const { data } = await api.get('/ledger', {
      params: {
        start: range.value?.[0],
        end: range.value?.[1],
        product_id: productFilter.value || undefined,
        entry_type: typeFilter.value || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
    })
    entries.value = data.items
    total.value = data.total
    shipAmount.value = data.summary?.ship_amount ?? 0
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  fetchEntries()
}

async function fetchInventory() {
  invLoading.value = true
  try {
    const { data } = await api.get('/ledger/inventory')
    inventory.value = data
  } catch {
    inventory.value = []
  } finally {
    invLoading.value = false
  }
}

async function fetchPending() {
  pendingLoading.value = true
  try {
    const { data } = await api.get('/ledger/pending')
    pending.value = data.items || []
    pendingTotal.value = data.total || 0
  } catch {
    pending.value = []
    pendingTotal.value = 0
  } finally {
    pendingLoading.value = false
  }
}

function fetchAll() {
  fetchProducts()
  fetchEntries()
  fetchInventory()
  fetchPending()
}

function goPending() {
  tab.value = 'pending'
  fetchPending()
}

function onTabChange(name) {
  if (name === 'pending') fetchPending()
}

/* ── 待确认条目处理 ── */
const resolveDialog = ref(false)
const resolving = ref(null)
const resolvingBusy = ref(false)
const resolveAction = ref('create')
const resolveForm = reactive({ product_id: null, unit: '', category: '螺母', warn_stock: null })

function openResolve(row) {
  resolving.value = row
  resolveAction.value = 'create'
  resolveForm.product_id = null
  resolveForm.unit = row.unit || ''
  resolveForm.category = '螺母'
  resolveForm.warn_stock = null
  resolveDialog.value = true
}

async function submitResolve() {
  if (!resolving.value) return
  if (resolveAction.value === 'assign' && !resolveForm.product_id) {
    ElMessage.warning('请选择要认领的产品')
    return
  }
  resolvingBusy.value = true
  try {
    const payload = { action: resolveAction.value }
    if (resolveAction.value === 'assign') payload.product_id = resolveForm.product_id
    if (resolveAction.value === 'create') {
      payload.unit = resolveForm.unit || null
      payload.category = resolveForm.category || null
      payload.warn_stock = resolveForm.warn_stock
    }
    const { data } = await api.post(`/ledger/pending/${resolving.value.id}/resolve`, payload)
    ElMessage.success(resolveAction.value === 'ignore' ? '已忽略' : data.message || '已入库')
    resolveDialog.value = false
    fetchPending()
    fetchEntries()
    fetchInventory()
    fetchProducts()
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    resolvingBusy.value = false
  }
}

async function ignorePending(row) {
  const ok = await ElMessageBox.confirm(
    `确定忽略 ${row.entry_date}「${row.product_name || '未识别品名'} ${row.spec}」这条记录？忽略后不会写入台账。`,
    '忽略确认',
    { type: 'warning' },
  ).catch(() => false)
  if (!ok) return
  try {
    await api.post(`/ledger/pending/${row.id}/resolve`, { action: 'ignore' })
    ElMessage.success('已忽略')
    fetchPending()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

/* ── 录入 / 修改 ── */
const dialog = ref(false)
const form = reactive({ id: null, entry_date: '', product_id: null, entry_type: 'production', quantity: null, unit_price: null, amount: null, customer: '', note: '' })

function openCreate() {
  Object.assign(form, {
    id: null,
    entry_date: new Date().toISOString().slice(0, 10),
    product_id: productFilter.value,
    entry_type: typeFilter.value || 'production',
    quantity: null,
    unit_price: null,
    amount: null,
    customer: '',
    note: '',
  })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    entry_date: row.entry_date,
    product_id: row.product_id,
    entry_type: row.entry_type,
    quantity: row.quantity,
    unit_price: row.unit_price,
    amount: row.amount,
    customer: row.customer || '',
    note: '',
  })
  dialog.value = true
}

async function save() {
  if (!form.entry_date || !form.product_id || !form.entry_type || !form.quantity) {
    ElMessage.warning('请填写日期、产品、类型和数量')
    return
  }
  const payload = {
    entry_date: form.entry_date,
    product_id: form.product_id,
    entry_type: form.entry_type,
    quantity: form.quantity,
    unit_price: form.unit_price,
    amount: form.amount,
    customer: form.customer || null,
  }
  try {
    if (form.id) {
      const { data } = await api.put(`/ledger/${form.id}`, payload)
      ElMessage.success(`已保存（${(data.changes || []).length} 处修改已留痕）`)
    } else {
      await api.post('/ledger', { ...payload, note: form.note })
      ElMessage.success('入账成功')
    }
    dialog.value = false
    fetchEntries()
    fetchInventory()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

/* ── 留痕 ── */
const editsDialog = ref(false)
const edits = ref([])

async function showEdits(row) {
  try {
    const { data } = await api.get(`/ledger/${row.id}/edits`)
    edits.value = data
    editsDialog.value = true
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeEntry(row) {
  const ok = await ElMessageBox.confirm(
    `确定删除 ${row.entry_date}「${row.product_name} ${row.spec}」的${TYPE_LABELS[row.entry_type]}记录？`,
    '删除确认',
    { type: 'warning' },
  ).catch(() => false)
  if (!ok) return
  try {
    await api.delete(`/ledger/${row.id}`)
    ElMessage.success('已删除')
    fetchEntries()
    fetchInventory()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function formatValue(v) {
  if (v === null || v === undefined) return '空'
  if (typeof v === 'string' && TYPE_LABELS[v]) return TYPE_LABELS[v]
  return String(v)
}

onMounted(fetchAll)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.summary-row {
  margin: 16px 0;
}
.mini {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: #666;
}
.mini b {
  font-size: 20px;
  color: #1677ff;
}
.mini b.red {
  color: #f56c6c;
}
.sub {
  font-size: 12px;
  color: #999;
}
.inv-tip {
  margin-top: 12px;
  font-size: 12px;
  color: #999;
}
.pager-row {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.edit-line {
  font-size: 13px;
  line-height: 1.9;
}
.red {
  color: #f56c6c;
}
.clickable {
  cursor: pointer;
}
.tip {
  color: #999;
  font-size: 12px;
  line-height: 1.8;
}
</style>
