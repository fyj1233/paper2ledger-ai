"""文档处理主流程：解析文本 → 提取规格条目 → 产品匹配 → 入台账/待确认。

方案 A（完全切换）：新上传的文档只产出台账条目，不再生成旧口径的
财务记录（finance_records 里的历史数据保持不动，供旧看板/报表使用）。
"""

from datetime import date, datetime
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import DictItem, Document, LedgerEntry, PendingEntry, Product
from app.services.extractors import extract_items
from app.services.parsers import parse_file
from app.services.product_matcher import match_product


def get_categories(db: Session) -> list[str]:
    """启用的业务分类字典（records 路由与 AI 助手仍在使用）。"""
    rows = (
        db.query(DictItem)
        .filter(DictItem.dict_type == "category", DictItem.is_active.is_(True))
        .order_by(DictItem.sort, DictItem.id)
        .all()
    )
    return [r.name for r in rows]


def process_document(db: Session, doc: Document, force: bool = False) -> None:
    """处理一个文档。阻塞执行，上传路由中通过 BackgroundTasks 调用。"""
    doc.status = "processing"
    doc.error = None
    db.commit()

    try:
        if force or doc.raw_text is None:
            data = Path(doc.stored_path).read_bytes()
            doc.raw_text = parse_file(data, doc.file_type)
        text = doc.raw_text

        items, source = extract_items(db, text, _fallback_date(doc))

        # 重解析时清掉本文档旧的自动台账与待确认条目（手工台账 document_id 为空，不受影响）
        db.query(LedgerEntry).filter(LedgerEntry.document_id == doc.id).delete()
        db.query(PendingEntry).filter(PendingEntry.document_id == doc.id).delete()

        products = db.query(Product).filter(Product.is_active.is_(True)).all()
        matched = 0
        for item in items:
            product = match_product(products, item.get("product_name", ""), item.get("spec", ""))
            if product:
                matched += 1
                db.add(
                    LedgerEntry(
                        document_id=doc.id,
                        entry_date=_as_date(item["date"], _fallback_date(doc)),
                        product_id=product.id,
                        entry_type=item["entry_type"],
                        quantity=round(float(item["quantity"]), 4),
                        unit_price=_round(item.get("unit_price")),
                        amount=_round(item.get("amount")),
                        customer=(str(item.get("customer") or "").strip() or None),
                        source=source,
                        confidence=_round(item.get("confidence")) or 0.8,
                        evidence=str(item.get("evidence") or "")[:500] or None,
                    )
                )
            else:
                db.add(
                    PendingEntry(
                        document_id=doc.id,
                        entry_date=_as_date(item["date"], _fallback_date(doc)),
                        product_name=str(item.get("product_name") or "").strip()[:100],
                        spec=str(item.get("spec") or "").strip()[:200],
                        entry_type=item["entry_type"],
                        quantity=round(float(item["quantity"]), 4),
                        unit=str(item.get("unit") or "").strip()[:20],
                        unit_price=_round(item.get("unit_price")),
                        amount=_round(item.get("amount")),
                        customer=(str(item.get("customer") or "").strip() or None),
                        source=source,
                        confidence=_round(item.get("confidence")) or 0.8,
                        evidence=str(item.get("evidence") or "")[:500] or None,
                    )
                )

        logging.getLogger("extractor").info(
            "文档 #%s：提取 %d 条，自动匹配入库 %d 条，待确认 %d 条",
            doc.id, len(items), matched, len(items) - matched,
        )
        doc.status = "parsed"
        doc.parsed_at = datetime.now()
        db.commit()
    except Exception as e:  # noqa: BLE001 - 任何失败都落库为 failed，可重新解析
        db.rollback()
        doc.status = "failed"
        doc.error = str(e)[:500]
        db.commit()


def process_document_task(doc_id: int, force: bool = False) -> None:
    """BackgroundTasks 入口：自建数据库会话。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            process_document(db, doc, force=force)
    finally:
        db.close()


def _fallback_date(doc: Document) -> date:
    return doc.created_at.date() if doc.created_at else date.today()


def _as_date(value, fallback: date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return fallback


def _round(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None
