"""经营记录：手工记账、修改留痕、明细查询。"""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import require_manager
from app.models import Document, FinanceRecord, RecordEdit, User
from app.services.extractor import get_categories
from app.services.text_utils import parse_date

router = APIRouter(prefix="/api/records", tags=["经营记录"])

EDITABLE_FIELDS = ("biz_date", "revenue", "cost", "profit", "tx_count", "payments", "category")


class ManualRecordRequest(BaseModel):
    biz_date: str = Field(min_length=8, max_length=10)
    revenue: float | None = None
    cost: float | None = None
    profit: float | None = None
    tx_count: int | None = None
    payments: dict[str, float] | None = None
    category: str = "默认"
    note: str = ""


class RecordUpdateRequest(BaseModel):
    biz_date: str | None = Field(default=None, min_length=8, max_length=10)
    revenue: float | None = None
    cost: float | None = None
    profit: float | None = None
    tx_count: int | None = None
    payments: dict[str, float] | None = None
    category: str | None = None


def _parse_biz_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")


def _dump_payments(value: dict | None) -> str | None:
    if not value:
        return None
    cleaned = {}
    for name, amount in value.items():
        try:
            cleaned[str(name)[:20]] = round(float(amount), 2)
        except (TypeError, ValueError):
            continue
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def _load_payments(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


@router.get("")
def list_records(
    start: str | None = Query(None),
    end: str | None = Query(None),
    category: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(500, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    """明细记录（经理/管理员）。"""
    query = db.query(FinanceRecord)
    if start:
        d = _parse_biz_date(start)
        query = query.filter(FinanceRecord.biz_date >= d)
    if end:
        d = _parse_biz_date(end)
        query = query.filter(FinanceRecord.biz_date <= d)
    if category:
        query = query.filter(FinanceRecord.category == category)
    if source:
        query = query.filter(FinanceRecord.source == source)
    rows = query.order_by(FinanceRecord.biz_date.desc(), FinanceRecord.id.desc()).limit(limit).all()

    doc_ids = {r.document_id for r in rows if r.document_id}
    docs = {
        d.id: d.filename
        for d in db.query(Document).filter(Document.id.in_(doc_ids)).all()
    } if doc_ids else {}
    return [
        {
            "id": r.id,
            "biz_date": r.biz_date.isoformat(),
            "revenue": r.revenue,
            "cost": r.cost,
            "profit": r.profit,
            "tx_count": r.tx_count,
            "payments": _load_payments(r.payments),
            "category": r.category,
            "extraction_type": r.extraction_type,
            "source": r.source,
            "confidence": r.confidence,
            "evidence": r.evidence,
            "document_name": docs.get(r.document_id) if r.document_id else None,
        }
        for r in rows
    ]


@router.post("", status_code=201)
def create_manual_record(
    body: ManualRecordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """手工记账（不依赖文档上传）。"""
    if body.revenue is None and body.cost is None and body.profit is None:
        raise HTTPException(status_code=400, detail="营业额/成本/利润至少填一项")
    if body.category not in get_categories(db):
        raise HTTPException(status_code=400, detail=f"分类「{body.category}」不在数据字典中")
    profit = body.profit
    if profit is None and body.revenue is not None and body.cost is not None:
        profit = round(body.revenue - body.cost, 2)
    record = FinanceRecord(
        document_id=None,
        biz_date=_parse_biz_date(body.biz_date),
        revenue=round(body.revenue, 2) if body.revenue is not None else None,
        cost=round(body.cost, 2) if body.cost is not None else None,
        profit=profit,
        tx_count=body.tx_count,
        payments=_dump_payments(body.payments),
        category=body.category,
        extraction_type="extract",
        source="manual",
        confidence=1.0,
        evidence=f"手工记账：{body.note}" if body.note else "手工记账",
    )
    db.add(record)
    db.commit()
    log_action(db, user, "手工记账", f"{body.biz_date} 营业额 {body.revenue}")
    return {"id": record.id, "message": "已记账"}


@router.put("/{record_id}")
def update_record(
    record_id: int,
    body: RecordUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """修改记录，差异写入留痕表。"""
    record = db.query(FinanceRecord).filter(FinanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    changes = []
    if body.biz_date is not None:
        new_date = _parse_biz_date(body.biz_date)
        if new_date != record.biz_date:
            changes.append({"field": "biz_date", "old": record.biz_date.isoformat(), "new": new_date.isoformat()})
            record.biz_date = new_date
    for field in ("revenue", "cost", "profit", "tx_count"):
        new_value = getattr(body, field)
        if new_value is not None:
            old_value = getattr(record, field)
            if old_value != new_value:
                changes.append({"field": field, "old": old_value, "new": new_value})
                setattr(record, field, new_value if new_value is None else round(new_value, 2) if field != "tx_count" else int(new_value))
    if body.payments is not None:
        old_payments = _load_payments(record.payments)
        if old_payments != body.payments:
            changes.append({"field": "payments", "old": old_payments, "new": body.payments})
            record.payments = _dump_payments(body.payments)
    if body.category is not None and body.category != record.category:
        if body.category not in get_categories(db):
            raise HTTPException(status_code=400, detail=f"分类「{body.category}」不在数据字典中")
        changes.append({"field": "category", "old": record.category, "new": body.category})
        record.category = body.category

    if not changes:
        return {"message": "没有变化", "changes": []}

    # 修改后自动重算利润（未显式给出时）
    if body.profit is None and record.revenue is not None and record.cost is not None:
        record.profit = round(record.revenue - record.cost, 2)

    db.add(
        RecordEdit(
            record_id=record.id,
            user_id=user.id,
            username=user.username,
            changes=json.dumps(changes, ensure_ascii=False, default=str),
        )
    )
    db.commit()
    log_action(db, user, "修改经营记录", f"记录 #{record.id}，{len(changes)} 处修改")
    return {"message": "已保存", "changes": changes}


@router.delete("/{record_id}")
def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    record = db.query(FinanceRecord).filter(FinanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(record)
    db.commit()
    log_action(db, user, "删除经营记录", f"记录 #{record_id}（{record.biz_date}）")
    return {"message": "已删除"}


@router.get("/{record_id}/edits")
def record_edits(
    record_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    rows = (
        db.query(RecordEdit)
        .filter(RecordEdit.record_id == record_id)
        .order_by(RecordEdit.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "username": r.username,
            "changes": json.loads(r.changes),
            "created_at": r.created_at,
        }
        for r in rows
    ]
