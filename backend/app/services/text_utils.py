"""文本提取通用工具：日期识别、金额识别。"""

import re
from datetime import date, timedelta

DATE_FULL = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
DATE_MD = re.compile(r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})日?")


def parse_date(text: str, today: date | None = None) -> date | None:
    today = today or date.today()
    m = DATE_FULL.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = DATE_MD.search(text)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            return date(today.year, mo, d)
        except ValueError:
            return None
    return None


def resolve_date(text: str, fallback: date) -> date:
    """识别日期，识别不了时兼容『今天/昨日』并回退到 fallback。"""
    d = parse_date(text)
    if d:
        return d
    if "昨日" in text or "昨天" in text:
        return fallback - timedelta(days=1)
    return fallback


MONEY_RE = re.compile(r"[¥￥]?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(万)?\s*[元块]?")

KEYWORDS = {
    "revenue": re.compile(r"营业额|销售额|营收|收入|流水|销售|进账|收款|卖了"),
    "cost": re.compile(r"成本|支出|进货|开销|花费|采购|房租|人工|水电"),
    "profit": re.compile(r"利润|盈利|赚|净收入|毛利"),
}


def _parse_money(text: str, keyword_match_end: int) -> float | None:
    """在关键词之后最近的一处金额。"""
    window = text[keyword_match_end : keyword_match_end + 16]
    m = MONEY_RE.search(window)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    if m.group(2):  # 万
        value *= 10000
    return value


def cell_to_float(cell: str) -> float | None:
    """把表格单元格文本解析为金额，解析失败返回 None。"""
    m = MONEY_RE.search(cell)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    if m.group(2):  # 万
        value *= 10000
    return value


def extract_amount_after(line: str, pattern: re.Pattern) -> float | None:
    m = pattern.search(line)
    if not m:
        return None
    return _parse_money(line, m.end())
