export const ROLE_LABELS = { admin: '管理员', manager: '经理', employee: '员工' }

export const STATUS = {
  pending: { label: '待处理', type: 'info' },
  processing: { label: '解析中', type: 'warning' },
  parsed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

export const EXT_LABELS = {
  txt: 'TXT', csv: 'CSV', docx: 'Word', xlsx: 'Excel', pdf: 'PDF',
  jpg: '图片', jpeg: '图片', png: '图片',
}

export function formatMoney(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

export const EXTRACTION_LABELS = {
  extract: '文档提取',
  calc: '推算汇总',
}

export const SOURCE_LABELS = {
  template: { label: '模板提取', type: 'success' },
  llm: { label: 'AI 提取', type: 'primary' },
  rule: { label: '规则提取', type: 'warning' },
  manual: { label: '手工记账', type: 'info' },
}
