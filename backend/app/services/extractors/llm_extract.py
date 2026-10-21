"""LLM 提取器：OpenAI 兼容接口，按固定 JSON 结构提取工厂台账规格条目。"""

import json
import re

from app.services.extractors.common import ENTRY_TYPES, infer_entry_type, parse_number
from app.services.llm import smart_chat

EXTRACT_PROMPT = """你是工厂台账数据提取助手。从下面的工厂经营记录文本中提取所有产品出入库条目（生产入库、出货、报废、退货、期初库存盘点）。

要求：
1. 每个日期、每个产品规格一条；同一行出现多个类型（如「生产 52，报废 0.5」）必须拆成多条。
2. product_name 填品名（如"六角螺母"），spec 填规格（如"M6×1.0 镀锌 8.8级"）；文本没拆开时尽量合理拆分。
3. entry_type 只能是：production(生产入库)、shipment(出货/发货/销售)、scrap(报废/不良)、return(退货/退回)、initial(期初/盘点结存)。
4. quantity 填数量数字；unit 填文本中的单位（千件/件/kg/吨/米等），没有填 null。
5. 单价、金额、客户不限条目类型（出货、退货等都可能带），分别填 unit_price（元）、amount（元）、customer；客户名常出现在条目上方单独一行（如「客户：XX」「客户退货：XX」），需关联到其下方条目；没有填 null。
6. date 输出 YYYY-MM-DD；相对日期结合上下文推算；无法确定填 null。盘点/期初的结存数量作为 initial 类型提取。
7. 没有的字段填 null，不要编造。confidence 取 0~1。evidence 填该条数据的原文片段。
8. 只输出一个 JSON 对象，不要任何解释或 markdown 标记。格式：
{{"items":[{{"date":"2026-09-03","product_name":"六角螺母","spec":"M6×1.0 镀锌 8.8级","entry_type":"production","quantity":52,"unit":"千件","unit_price":null,"amount":null,"customer":null,"confidence":1.0,"evidence":"..."}}]}}

工厂经营记录文本：
<<<
{text}
>>>"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("模型未返回 JSON")
    return json.loads(text[start : end + 1])


def _clean_item(raw: dict) -> dict:
    """类型归一（中文类型词也接受）+ 数值清洗。"""
    entry_type = infer_entry_type(str(raw.get("entry_type") or "")) or "production"
    quantity = parse_number(str(raw.get("quantity") or ""))
    unit_price = parse_number(str(raw.get("unit_price") or "")) if raw.get("unit_price") is not None else None
    amount = parse_number(str(raw.get("amount") or "")) if raw.get("amount") is not None else None
    confidence = parse_number(str(raw.get("confidence") or ""))
    date = raw.get("date")
    return {
        "date": str(date)[:10] if date else None,
        "product_name": str(raw.get("product_name") or "").strip()[:100],
        "spec": str(raw.get("spec") or "").strip()[:200],
        "entry_type": entry_type,
        "quantity": quantity,
        "unit": str(raw.get("unit") or "").strip()[:20] or None,
        "unit_price": unit_price,
        "amount": amount,
        "customer": str(raw.get("customer") or "").strip()[:100] or None,
        "confidence": round(confidence, 2) if confidence is not None and 0 <= confidence <= 1 else 0.9,
        "evidence": str(raw.get("evidence") or "")[:300],
    }


def extract(cfg: dict, text: str) -> list[dict]:
    """调用大模型提取规格条目，JSON 解析失败自动重试一次。"""
    prompt = EXTRACT_PROMPT.format(text=text)
    messages = [{"role": "user", "content": prompt}]
    last_err: Exception | None = None
    for _ in range(2):
        try:
            reply = smart_chat(cfg, messages)
            data = _extract_json(reply)
            items = data.get("items", [])
            if isinstance(items, list):
                cleaned = [_clean_item(r) for r in items if isinstance(r, dict)]
                return [r for r in cleaned if r["entry_type"] in ENTRY_TYPES and r["quantity"]]
            raise ValueError("items 字段不是列表")
        except Exception as e:  # noqa: BLE001 - 统一重试后上抛
            last_err = e
    raise RuntimeError(f"大模型提取失败：{last_err}")
