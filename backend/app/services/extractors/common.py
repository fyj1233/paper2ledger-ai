"""规格条目提取的公共工具：类型推断、数量/单位解析、品名/规格拆分。

所有提取器（模板/LLM/规则）输出统一的条目 dict：
    date(YYYY-MM-DD|None) / product_name / spec / entry_type /
    quantity(>0) / unit / unit_price / amount / customer /
    evidence / confidence
"""

import re

from app.services.text_utils import parse_date

# 五类台账类型（与 ledger_entries 一致）
ENTRY_TYPES = ("production", "shipment", "scrap", "return", "initial")
TYPE_LABELS = {
    "production": "生产入库",
    "shipment": "出货",
    "scrap": "报废",
    "return": "退货",
    "initial": "期初",
}

# 类型关键词（顺序即优先级：报废/退货先于出货，出货先于生产；长词在前）
_TYPE_KEYWORDS = (
    ("scrap", r"报废|不良|次品|废品"),
    ("return", r"退货|退回"),
    ("shipment", r"出货|发货|提货|售出|销售"),
    ("initial", r"期初|盘点|结存"),
    ("production", r"生产入库|生产|入库|产出|完工"),
)

_KEYWORD_ALT = "生产入库|生产|入库|产出|完工|出货|发货|提货|售出|销售|报废|不良|次品|废品|退货|退回|期初|盘点|结存"

# 「类型关键词 + 数量(可选单位)」逐段匹配，一行多个类型各成一条；间隔容忍 ： | 空格
TYPED_QTY_RE = re.compile(
    rf"({_KEYWORD_ALT})[\s:：|｜]*([0-9]+(?:[.,，][0-9]+)*)[\s|｜]*(万件|千件|件|kg|KG|Kg|千克|公斤|吨|米)?"
)

UNIT_RE = re.compile(r"([0-9]+(?:[.,，][0-9]+)*)\s*(万件|千件|件|kg|KG|Kg|千克|公斤|吨|米)")

SPEC_CORE_RE = re.compile(r"[Mm]\s?\d+(?:\s?[×xX*·]\s?\d+(?:\.\d+)?)?")
# 品名：规格核心前紧邻的连续中文
NAME_BEFORE_SPEC_RE = re.compile(r"([\u4e00-\u9fa5]{1,12})\s*(?=[Mm]\s?\d)")
# 客户：客户：XXX（容忍「客户退货：」这类间隔词）
CUSTOMER_LABEL_RE = re.compile(r"客户\s*[^：:\n]{0,8}[：:]\s*([\u4e00-\u9fa5A-Za-z0-9（）()]+?)(?=\s|$|，|。|,|；)")
# 组织名启发式（无「客户：」标签时的兜底）
ORG_NAME_RE = re.compile(r"([\u4e00-\u9fa5]{2,16}(?:公司|厂|五金|机电|商行|门市|紧固件|标准件))")
UNIT_PRICE_RE = re.compile(r"单价\s*[：:]?\s*([0-9]+(?:[.,，][0-9]+)*)\s*元?")
AMOUNT_RE = re.compile(r"金额\s*[：:]?\s*([0-9]+(?:[.,，][0-9]+)*)\s*元?")

# 规格后缀的终止符：类型关键词或分隔符（数字不算，避免切断 8.8级 这类规格）
_SPEC_CUT_RE = re.compile(rf"\s*(?:{_KEYWORD_ALT}|数量|单价|金额|合计|：|:|，|,|；|;|\|)")
_DATE_FULL_RE = re.compile(r"20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}\s*日?")
_DATE_MD_START_RE = re.compile(r"^\s*\d{1,2}[-/.月]\d{1,2}日?")


def parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = str(raw).replace(",", "").replace("，", "").strip()
    if not cleaned or cleaned == ".":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def infer_entry_type(text: str) -> str | None:
    """从文本片段推断台账类型；中文关键词或英文键都认。"""
    low = (text or "").strip().lower()
    if low in ENTRY_TYPES:
        return low
    for etype, pattern in _TYPE_KEYWORDS:
        if re.search(pattern, text or ""):
            return etype
    return None


def parse_item_date(raw: str | None) -> str | None:
    if not raw:
        return None
    parsed = parse_date(str(raw).strip())
    return parsed.isoformat() if parsed else None


def split_product(text: str) -> tuple[str, str]:
    """从一行文本里拆出品名与规格。

    品名 = 规格核心（M6×1.0）前紧邻的连续中文；规格 = 核心起到第一个
    类型关键词/分隔符为止（数字不算终止符，保住「8.8级」这类规格尾巴）。
    """
    core = SPEC_CORE_RE.search(text)
    if not core:
        return "", ""
    name_m = NAME_BEFORE_SPEC_RE.search(text[: core.start() + 2])
    name = name_m.group(1) if name_m else ""
    rest = text[core.end():]
    cut = _SPEC_CUT_RE.search(rest)
    suffix = rest[: cut.start()] if cut else rest
    suffix = suffix.strip(" ：:，,;；|-—|").strip()
    spec = (core.group(0) + (" " + suffix if suffix else "")).strip()
    spec = re.sub(r"\s+", " ", spec)
    return name, spec


def line_date(line: str):
    """行级日期：完整日期（2026-09-03）任意位置；月-日（09-03）仅认行首。"""
    m = _DATE_FULL_RE.search(line)
    if m:
        return parse_date(m.group(0))
    m = _DATE_MD_START_RE.match(line)
    if m:
        return parse_date(m.group(0))
    return None


def valid_item(item: dict) -> bool:
    """条目有效性：类型合法、数量为正、品名或规格至少有一样。"""
    return (
        isinstance(item, dict)
        and item.get("entry_type") in ENTRY_TYPES
        and isinstance(item.get("quantity"), (int, float))
        and float(item["quantity"]) > 0
        and bool(str(item.get("product_name") or "").strip() or str(item.get("spec") or "").strip())
    )
