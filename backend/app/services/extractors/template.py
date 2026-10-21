"""模板提取器：对固定格式的工厂文档用「关键词匹配 + 字段正则」按行提取规格条目。

每行一条条目：一行同时出现多个类型（如「生产 52，报废 0.5」）只取第一段，
这类混合行交给 LLM/规则提取器。旧财务字段模板（营业额/成本）不会再产出条目，
命中关键词但提不出条目时返回 None 继续级联。
"""

import json
import re

from sqlalchemy.orm import Session

from app.models import ExtractTemplate
from app.services.extractors.common import (
    infer_entry_type,
    parse_item_date,
    parse_number,
)
from app.services.text_utils import parse_date

# 条目字段（date/product_name/spec/entry_type/quantity/unit/unit_price/amount/customer）
FIELD_NAMES = (
    "date",
    "product_name",
    "spec",
    "entry_type",
    "quantity",
    "unit",
    "unit_price",
    "amount",
    "customer",
)


def _apply_first_match(text: str, patterns: list[str]):
    for pattern in patterns or []:
        try:
            m = re.search(pattern, text)
        except re.error:
            continue
        if not m:
            continue
        value = m.group("value") if m.groupdict().get("value") else (m.group(1) if m.groups() else None)
        if value is not None:
            return value.strip()
    return None


def try_extract(db: Session, text: str) -> list[dict] | None:
    """返回命中模板提取出的条目；没有模板命中或提不出条目返回 None（级联继续）。"""
    templates = db.query(ExtractTemplate).filter(ExtractTemplate.is_active.is_(True)).all()
    for tpl in templates:
        items = _extract_by_template(tpl, text)
        if items:
            return items
    return None


def _extract_by_template(tpl: ExtractTemplate, text: str) -> list[dict] | None:
    try:
        keywords = json.loads(tpl.keywords or "[]")
        fields = json.loads(tpl.fields or "{}")
    except json.JSONDecodeError:
        return None
    if not keywords or not any(kw and kw in text for kw in keywords):
        return None

    items: list[dict] = []
    current_date: str | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # 日期字段：命中则更新上下文日期
        raw_date = _apply_first_match(line, fields.get("date") or [])
        if raw_date:
            parsed = parse_date(raw_date)
            if parsed:
                current_date = parsed.isoformat()

        raw_qty = _apply_first_match(line, fields.get("quantity") or [])
        quantity = parse_number(raw_qty)
        if quantity is None or quantity <= 0:
            continue

        product_name = (_apply_first_match(line, fields.get("product_name") or []) or "").strip()
        spec = (_apply_first_match(line, fields.get("spec") or []) or "").strip()
        if not product_name and not spec:
            continue

        raw_type = _apply_first_match(line, fields.get("entry_type") or [])
        entry_type = infer_entry_type(raw_type or "") or infer_entry_type(line)
        if not entry_type:
            continue

        unit = (_apply_first_match(line, fields.get("unit") or []) or "").strip() or None
        unit_price = parse_number(_apply_first_match(line, fields.get("unit_price") or []))
        amount = parse_number(_apply_first_match(line, fields.get("amount") or []))
        customer = (_apply_first_match(line, fields.get("customer") or []) or "").strip() or None

        items.append(
            {
                "date": current_date,
                "product_name": product_name[:100],
                "spec": spec[:200],
                "entry_type": entry_type,
                "quantity": quantity,
                "unit": unit,
                "unit_price": unit_price,
                "amount": amount,
                "customer": customer,
                "evidence": f"模板「{tpl.name}」提取：{line[:120]}",
                "confidence": 1.0,
            }
        )

    return items or None


def render_test(db: Session, text: str, template_id: int | None = None):
    """试提取：给管理页调试用，返回命中的模板名和条目，不落库。"""
    query = db.query(ExtractTemplate).filter(ExtractTemplate.is_active.is_(True))
    if template_id:
        query = query.filter(ExtractTemplate.id == template_id)
    for tpl in query.all():
        items = _extract_by_template(tpl, text)
        if items:
            return tpl.name, items
    return None, None
