<template>
  <div>
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索品名 / 规格 / 分类" clearable style="width: 240px" :prefix-icon="'Search'" />
        <el-button :icon="'Refresh'" @click="fetchProducts">刷新</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新增产品</el-button>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <el-table :data="filtered" v-loading="loading" size="large">
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="name" label="品名" width="140" />
        <el-table-column label="规格" min-width="180">
          <template #default="{ row }">{{ row.spec || '—' }}</template>
        </el-table-column>
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column label="预警库存" width="110" align="right">
          <template #default="{ row }">{{ row.warn_stock ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'" effect="plain">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" size="small" @click="removeProduct(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="tip">台账录入与提取只允许「启用」状态的产品；已有台账记录的产品不能删除，只能停用。</div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑产品' : '新增产品'" width="460px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="品名">
          <el-input v-model="form.name" maxlength="100" placeholder="如：六角螺母" />
        </el-form-item>
        <el-form-item label="规格">
          <el-input v-model="form.spec" maxlength="100" placeholder="如：M8×1.25 镀锌 8.8级" />
        </el-form-item>
        <el-form-item label="单位">
          <el-select v-model="form.unit" filterable allow-create style="width: 100%">
            <el-option v-for="u in UNITS" :key="u" :label="u" :value="u" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" maxlength="50" placeholder="如：螺母 / 螺栓 / 垫片" />
        </el-form-item>
        <el-form-item label="预警库存">
          <el-input-number v-model="form.warn_stock" :min="0" :precision="2" style="width: 100%" placeholder="结存低于该值时告警" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errMsg } from '../api'

const UNITS = ['千件', '件', 'kg', '吨', '米', '箱']

const keyword = ref('')
const loading = ref(false)
const products = ref([])
const dialog = ref(false)
const form = reactive({ id: null, name: '', spec: '', unit: '千件', category: '螺母', warn_stock: null, is_active: true })

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return products.value
  return products.value.filter((p) =>
    [p.name, p.spec, p.category].some((v) => String(v || '').toLowerCase().includes(kw)),
  )
})

async function fetchProducts() {
  loading.value = true
  try {
    const { data } = await api.get('/products')
    products.value = data
  } catch (e) {
    ElMessage.error(errMsg(e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', spec: '', unit: '千件', category: '螺母', warn_stock: null, is_active: true })
  dialog.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    spec: row.spec,
    unit: row.unit,
    category: row.category,
    warn_stock: row.warn_stock,
    is_active: row.is_active,
  })
  dialog.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('品名不能为空')
    return
  }
  try {
    if (form.id) {
      await api.put(`/products/${form.id}`, form)
      ElMessage.success('已保存')
    } else {
      await api.post('/products', form)
      ElMessage.success('已新增')
    }
    dialog.value = false
    fetchProducts()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function removeProduct(row) {
  const ok = await ElMessageBox.confirm(
    `确定删除产品「${row.name} ${row.spec}」？`,
    '删除确认',
    { type: 'warning' },
  ).catch(() => false)
  if (!ok) return
  try {
    await api.delete(`/products/${row.id}`)
    ElMessage.success('已删除')
    fetchProducts()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

onMounted(fetchProducts)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.tip {
  margin-top: 12px;
  font-size: 12px;
  color: #999;
}
</style>
