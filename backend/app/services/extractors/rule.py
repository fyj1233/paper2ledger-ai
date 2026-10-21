"""规则提取器：关键词+正则的兜底条目提取（LLM 未配置或失败时使用）。

逐行扫描：维护当前日期/客户上下文；「类型关键词+数量」逐段匹配，
一行含多个类型（生产 52、报废 0.5）时拆成多条；品名/规格按规格核心拆分。
"""

from app.services.extractors.common import (
    AMOUNT_RE,
    CUSTOMER_LABEL_RE,
    ORG_NAME_RE,
    TYPED_QTY_RE,
    UNIT_PRICE_RE,
    UNIT_RE,
    infer_entry_type,
    line_date,
    parse_number,
    split_product,
)


def _line_customer(line: str) -> str | None:
    """行级客户：优先「客户：」标签，其次组织名启发式（如「杭州宏达五金机电 提货 …」）。"""
    m = CUSTOMER_LABEL_RE.search(line)
    if m:
        return m.group(1).strip()
    m = ORG_NAME_RE.search(line)
    if m:
        return m.group(1).strip()
    return None


def extract(text: str, fallback_date) -> list[dict]:
    items: list[dict] = []
    current_date = fallback_date
    current_customer: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parsed = line_date(line)
        if parsed:
            current_date = parsed

        cust_m = CUSTOMER_LABEL_RE.search(line)
        if cust_m:
            current_customer = cust_m.group(1).strip()

        product_name, spec = split_product(line)
        if not product_name and not spec:
            continue

        # 类型+数量逐段；类型词与数量隔开（提货 … 30 千件）时退化取首个「数量+单位」
        typed: list[tuple[str, str, str | None]] = [
            (m.group(1), m.group(2), m.group(3)) for m in TYPED_QTY_RE.finditer(line)
        ]
        if not typed:
            etype = infer_entry_type(line)
            if etype:
                um = UNIT_RE.search(line)
                if um:
                    typed = [(etype, um.group(1), um.group(2))]

        if not typed:
            continue

        line_customer = _line_customer(line)
        price_m = UNIT_PRICE_RE.search(line)
        price = parse_number(price_m.group(1)) if price_m else None
        amount_m = AMOUNT_RE.search(line)
        amount = parse_number(amount_m.group(1)) if amount_m else None

        for keyword, number, unit in typed:
            entry_type = infer_entry_type(keyword)
            qty = parse_number(number)
            if entry_type is None or not qty or qty <= 0:
                continue
            customer = (line_customer or current_customer) if entry_type in ("shipment", "return") else None
            items.append(
                {
                    "date": current_date.isoformat() if current_date else None,
                    "product_name": product_name,
                    "spec": spec,
                    "entry_type": entry_type,
                    "quantity": qty,
                    "unit": unit,
                    "unit_price": price if entry_type == "shipment" else None,
                    "amount": amount if entry_type == "shipment" else None,
                    "customer": customer,
                    "confidence": 0.5,
                    "evidence": line[:200],
                }
            )

    return items
