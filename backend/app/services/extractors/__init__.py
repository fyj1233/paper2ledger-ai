"""提取流水线：模板 → LLM（已配置才走，失败自动降级）→ 规则。

所有提取器输出统一的规格条目结构（dict 列表），字段：
    date / product_name / spec / entry_type / quantity / unit /
    unit_price / amount / customer / evidence / confidence
流水线负责打上 source 标记（template / llm / rule）并做有效性过滤。
"""

import logging

from sqlalchemy.orm import Session

from app.services.extractors import llm_extract, rule, template
from app.services.extractors.common import parse_item_date, valid_item

logger = logging.getLogger("extractors")


def _finalize(items: list[dict], fallback_date) -> list[dict]:
    """过滤无效条目 + 补默认日期。"""
    result = []
    for item in items:
        if not valid_item(item):
            continue
        if not item.get("date"):
            item["date"] = fallback_date.isoformat()
        else:
            item["date"] = parse_item_date(item["date"]) or fallback_date.isoformat()
        result.append(item)
    return result


def extract_items(db: Session, text: str, fallback_date):
    """级联提取规格条目。返回 (items, source)；items 已带 source 字段。"""
    # ① 模板提取：命中即用，快、免费、结果确定
    items = template.try_extract(db, text)
    if items:
        cleaned = _finalize(items, fallback_date)
        if cleaned:
            logger.info("提取方式：模板，%d 条", len(cleaned))
            return [dict(r, source="template") for r in cleaned], "template"

    # ② LLM 提取（已配置才走；失败降级到规则）
    from app.services.llm import get_effective_llm_config

    cfg = get_effective_llm_config(db)
    if cfg:
        try:
            items = llm_extract.extract(cfg, text)
            cleaned = _finalize(items, fallback_date)
            if cleaned:
                logger.info("提取方式：LLM，%d 条", len(cleaned))
                return [dict(r, source="llm") for r in cleaned], "llm"
        except Exception as e:  # noqa: BLE001 - LLM 失败降级规则，不让单据卡死
            logger.warning("LLM 提取失败，降级规则提取：%s", e)

    # ③ 规则提取兜底
    items = rule.extract(text, fallback_date)
    cleaned = _finalize(items, fallback_date)
    logger.info("提取方式：规则，%d 条", len(cleaned))
    return [dict(r, source="rule") for r in cleaned], "rule"
