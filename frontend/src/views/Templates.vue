<template>
  <el-card shadow="never">
    <el-tabs v-model="tab">
      <!-- ── 提取模板 ── -->
      <el-tab-pane :label="`提取模板 (${templates.length})`" name="tpl">
        <div class="toolbar">
          <el-button type="primary" :icon="'Plus'" @click="openTplCreate">新建模板</el-button>
          <span class="tip">命中关键词的固定格式文档将用模板正则直接提取，不消耗大模型；未命中的自动走 AI / 规则。</span>
        </div>
        <el-table :data="templates" v-loading="tplLoading" size="large">
          <el-table-column prop="name" label="模板名称" min-width="150" />
          <el-table-column label="匹配关键词" min-width="160">
            <template #default="{ row }">
              <el-tag v-for="kw in row.keywords" :key="kw" size="small" effect="plain" style="margin: 2px">{{ kw }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="默认分类" width="100" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="openTplEdit(row)">编辑</el-button>
              <el-button text type="warning" size="small" @click="openTest(row)">试提取</el-button>
              <el-button text type="danger" size="small" @click="removeTpl(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 数据字典 ── -->
      <el-tab-pane label="数据字典" name="dict">
        <div class="dict-grid">
          <el-card v-for="(meta, type) in DICT_TYPES" :key="type" shadow="never">
            <template #header>
              <div class="dict-head">
                <span>{{ meta.label }}</span>
                <el-button size="small" :icon="'Plus'" @click="openDictCreate(type)">添加</el-button>
              </div>
            </template>
            <div v-for="item in dicts[type] || []" :key="item.id" class="dict-item">
              <span :class="{ inactive: !item.is_active }">{{ item.name }}</span>
              <span>
                <el-button text size="small" @click="toggleDict(item)">{{ item.is_active ? '停用' : '启用' }}</el-button>
                <el-button text type="danger" size="small" @click="removeDict(item)">删除</el-button>
              </span>
            </div>
            <el-empty v-if="!(dicts[type] || []).length" description="暂无，点击上方添加" :image-size="60" />
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>

  <!-- 模板编辑弹窗 -->
  <el-dialog v-model="tplDialog" :title="editingTpl ? '编辑模板' : '新建模板'" width="680px">
    <el-form :model="tplForm" label-width="110px">
      <el-form-item label="模板名称">
        <el-input v-model="tplForm.name" placeholder="例如：生产日报模板" />
      </el-form-item>
      <el-form-item label="匹配关键词">
        <el-select
          v-model="tplForm.keywords"
          multiple filterable allow-create default-first-option
          :reserve-keyword="false"
          placeholder="输入关键词后回车，任一命中即适用（如：生产日报、车间日报）"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item v-for="f in FIELDS" :key="f.key" :label="f.label">
        <el-select
          v-model="tplForm.fields[f.key]"
          multiple filterable allow-create default-first-option
          :reserve-keyword="false"
          :placeholder="f.placeholder"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="默认分类">
        <el-select v-model="tplForm.category" style="width: 220px">
          <el-option v-for="c in dicts.category || []" :key="c.id" :label="c.name" :value="c.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="tplForm.is_active" />
      </el-form-item>
      <el-form-item label="正则说明">
        <div class="tip">
          按行提取，一行一条：每行需同时命中「数量」和「品名/规格」才算一条；「日期」命中后作为后续行的默认日期。
          捕获值请用分组（第 1 组或命名组 <code>?P&lt;value&gt;</code>），如数量 <code>(\d+(?:\.\d+)?)\s*千件</code>；同一字段可配多条正则，按顺序取第一个命中的。
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="tplDialog = false">取消</el-button>
      <el-button type="primary" @click="saveTpl">保存</el-button>
    </template>
  </el-dialog>

  <!-- 试提取弹窗 -->
  <el-dialog v-model="testDialog" title="试提取（不保存数据）" width="640px">
    <el-input
      v-model="testText"
      type="textarea"
      :rows="8"
      placeholder="粘贴一段该格式文档的文本内容，点下方按钮试提取"
    />
    <div style="margin-top: 12px">
      <el-button type="primary" :loading="testing" @click="runTest">试提取</el-button>
    </div>
    <div v-if="testResult" class="test-result">
      <el-alert
        :title="testResult.matched ? `命中模板：${testResult.template_name}，提取 ${testResult.items.length} 条规格条目` : '没有模板命中'"
        :type="testResult.matched ? 'success' : 'warning'"
        :closable="false"
        show-icon
      />
      <pre v-if="testResult.matched">{{ JSON.stringify(testResult.items, null, 2) }}</pre>
    </div>
  </el-dialog>

  <!-- 字典添加弹窗 -->
  <el-dialog v-model="dictDialog" :title="`添加${DICT_TYPES[dictType]?.label || ''}`" width="360px">
    <el-input v-model="dictName" placeholder="名称，如：餐饮" />
    <template #footer>
      <el-button @click="dictDialog = false">取消</el-button>
      <el-button type="primary" @click="saveDict">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errMsg } from '../api'

const DICT_TYPES = { category: { label: '业务分类' }, payment: { label: '支付方式' } }
const FIELDS = [
  { key: 'product_name', label: '品名正则', placeholder: '(螺母|螺栓|垫片)' },
  { key: 'spec', label: '规格正则', placeholder: '(M\\d+(?:×|x|X)\\d+(?:\\.\\d+)?)' },
  { key: 'quantity', label: '数量正则', placeholder: '(\\d+(?:\\.\\d+)?)\\s*千件' },
  { key: 'entry_type', label: '类型正则', placeholder: '(生产|入库|出货|报废|退货|期初)' },
  { key: 'date', label: '日期正则', placeholder: '(\\d{1,2}月\\d{1,2}日)' },
  { key: 'unit', label: '单位正则', placeholder: '(千件|万件|件|kg|吨)' },
  { key: 'unit_price', label: '单价正则', placeholder: '单价[：:]\\s*([\\d,.]+)' },
  { key: 'amount', label: '金额正则', placeholder: '金额[：:]\\s*([\\d,.]+)' },
  { key: 'customer', label: '客户正则', placeholder: '客户[：:]\\s*(\\S+)' },
]

const tab = ref('tpl')
const templates = ref([])
const tplLoading = ref(false)
const dicts = ref({})
const tplDialog = ref(false)
const editingTpl = ref(null)
const testDialog = ref(false)
const testText = ref('')
const testResult = ref(null)
const testing = ref(false)
const dictDialog = ref(false)
const dictType = ref('category')
const dictName = ref('')

const tplForm = reactive({ name: '', keywords: [], fields: {}, category: '默认', is_active: true })

async function fetchTemplates() {
  tplLoading.value = true
  try {
    const { data } = await api.get('/templates')
    templates.value = data
  } finally {
    tplLoading.value = false
  }
}

async function fetchDicts() {
  const { data } = await api.get('/dicts')
  dicts.value = data
}

function emptyFields() {
  const f = {}
  for (const item of FIELDS) f[item.key] = []
  return f
}

function openTplCreate() {
  editingTpl.value = null
  tplForm.name = ''
  tplForm.keywords = []
  tplForm.fields = emptyFields()
  tplForm.category = (dicts.value.category || [])[0]?.name || '默认'
  tplForm.is_active = true
  tplDialog.value = true
}

function openTplEdit(row) {
  editingTpl.value = row
  tplForm.name = row.name
  tplForm.keywords = [...row.keywords]
  // 只回填条目字段，旧财务字段（revenue/cost 等）丢弃，否则保存会被后端字段校验拒绝
  const known = emptyFields()
  for (const k of Object.keys(known)) {
    if (Array.isArray(row.fields?.[k]) && row.fields[k].length) known[k] = row.fields[k]
  }
  tplForm.fields = known
  tplForm.category = row.category
  tplForm.is_active = row.is_active
  tplDialog.value = true
}

async function saveTpl() {
  if (!tplForm.name) {
    ElMessage.warning('请填写模板名称')
    return
  }
  try {
    if (editingTpl.value) {
      await api.put(`/templates/${editingTpl.value.id}`, tplForm)
    } else {
      await api.post('/templates', tplForm)
    }
    ElMessage.success('已保存')
    tplDialog.value = false
    fetchTemplates()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeTpl(row) {
  const ok = await ElMessageBox.confirm(`确定删除模板「${row.name}」？`, '删除确认', { type: 'warning' }).catch(() => false)
  if (!ok) return
  try {
    await api.delete(`/templates/${row.id}`)
    ElMessage.success('已删除')
    fetchTemplates()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

function openTest(row) {
  testText.value = ''
  testResult.value = null
  testDialog.value = true
  testRowId.value = row.id
}
const testRowId = ref(null)

async function runTest() {
  testing.value = true
  try {
    const { data } = await api.post('/templates/test', {
      text: testText.value,
      template_id: testRowId.value || null,
    })
    testResult.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    testing.value = false
  }
}

function openDictCreate(type) {
  dictType.value = type
  dictName.value = ''
  dictDialog.value = true
}

async function saveDict() {
  if (!dictName.value.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  try {
    await api.post('/dicts', { dict_type: dictType.value, name: dictName.value.trim() })
    ElMessage.success('已添加')
    dictDialog.value = false
    fetchDicts()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function toggleDict(item) {
  try {
    await api.put(`/dicts/${item.id}`, { is_active: !item.is_active })
    item.is_active = !item.is_active
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeDict(item) {
  const ok = await ElMessageBox.confirm(`确定删除「${item.name}」？`, '删除确认', { type: 'warning' }).catch(() => false)
  if (!ok) return
  try {
    await api.delete(`/dicts/${item.id}`)
    ElMessage.success('已删除')
    fetchDicts()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(() => {
  fetchTemplates()
  fetchDicts()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.tip {
  color: #999;
  font-size: 12px;
}
.tip code {
  background: #f0f2f5;
  padding: 1px 6px;
  border-radius: 4px;
}
.dict-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.dict-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.dict-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 4px;
  border-bottom: 1px solid #f2f3f5;
  font-size: 14px;
}
.dict-item .inactive {
  color: #bbb;
  text-decoration: line-through;
}
.test-result {
  margin-top: 12px;
}
.test-result pre {
  background: #f6f8fa;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  max-height: 260px;
  overflow: auto;
  margin-top: 10px;
}
</style>
