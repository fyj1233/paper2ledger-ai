"""生产看板：台账口径汇总（产量/出货/金额趋势、规格排行、单据状态）。"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_manager
from app.models import Document, LedgerEntry, PendingEntry, Product, Setting, User

router = APIRouter(prefix="/api/dashboard", tags=["看板"])


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def _entry_amount(r: LedgerEntry) -> float:
    if r.amount is not None:
        return r.amount
    return (r.unit_price or 0) * (r.quantity or 0)


def _summarize(rows: list[LedgerEntry]) -> dict[str, float]:
    production = shipment = ship_amount = 0.0
    for r in rows:
        if r.entry_type == "production":
            production += r.quantity or 0
        elif r.entry_type == "shipment":
            shipment += r.quantity or 0
            ship_amount += _entry_amount(r)
    return {"production": production, "shipment": shipment, "ship_amount": ship_amount}


@router.get("/overview")
def overview(
    start: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
    end: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    product_id: int | None = Query(None, description="产品下钻（规格排行饼图点击）"),
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    today = date.today()
    end_date = _parse_date(end, today)
    start_date = _parse_date(start, end_date - timedelta(days=29))

    product = None
    if product_id:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="产品不存在")

    def fetch(s: date, e: date) -> list[LedgerEntry]:
        q = db.query(LedgerEntry).filter(LedgerEntry.entry_date >= s, LedgerEntry.entry_date <= e)
        if product:
            q = q.filter(LedgerEntry.product_id == product.id)
        return q.all()

    rows = fetch(start_date, end_date)

    # 上一等长周期（环比基准）
    length = (end_date - start_date).days + 1
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    prev_rows = fetch(prev_start, prev_end)

    total = _summarize(rows)
    prev_total = _summarize(prev_rows)
    prev_summary = {k: round(v, 2) for k, v in prev_total.items()}

    # 每日 / 每月趋势
    daily: dict[date, dict[str, float]] = {}
    monthly: dict[str, dict[str, float]] = {}
    for r in rows:
        d = daily.setdefault(r.entry_date, {"production": 0.0, "shipment": 0.0, "ship_amount": 0.0})
        m = monthly.setdefault(r.entry_date.strftime("%Y-%m"), {"production": 0.0, "shipment": 0.0, "ship_amount": 0.0})
        amount = _entry_amount(r)
        if r.entry_type == "production":
            d["production"] += r.quantity or 0
            m["production"] += r.quantity or 0
        elif r.entry_type == "shipment":
            d["shipment"] += r.quantity or 0
            d["ship_amount"] += amount
            m["shipment"] += r.quantity or 0
            m["ship_amount"] += amount

    # 规格排行（期间，不受下钻影响）
    products = {p.id: p for p in db.query(Product).all()}
    spec_stats: dict[int, dict] = {}
    for r in rows:
        p = products.get(r.product_id)
        if not p:
            continue
        s = spec_stats.setdefault(r.product_id, {
            "product_id": p.id, "name": p.name, "spec": p.spec, "unit": p.unit,
            "production": 0.0, "shipment": 0.0, "ship_amount": 0.0,
        })
        if r.entry_type == "production":
            s["production"] += r.quantity or 0
        elif r.entry_type == "shipment":
            s["shipment"] += r.quantity or 0
            s["ship_amount"] += _entry_amount(r)

    # 今日 / 本月快照
    today_rows = [r for r in rows if r.entry_date == today]
    today_stat = _summarize(today_rows)
    month_prefix = today.strftime("%Y-%m")
    month_ship_amount = round(
        sum(_entry_amount(r) for r in rows
            if r.entry_type == "shipment" and r.entry_date.strftime("%Y-%m") == month_prefix),
        2,
    )

    # 单据状态 + 待确认条目（工作台提醒）
    recent_docs = db.query(Document).order_by(Document.id.desc()).limit(5).all()
    doc_count = db.query(Document).count()
    status_rows = db.query(Document.status, Document.id).all()
    pending_count = sum(1 for s, _ in status_rows if s in ("pending", "processing"))
    failed_count = sum(1 for s, _ in status_rows if s == "failed")
    pending_entry_count = db.query(PendingEntry).count()

    # 月度目标（管理员在系统设置中配置，按出货金额衡量）
    target_row = db.query(Setting).filter(Setting.key == "monthly_target").first()
    try:
        monthly_target = float(target_row.value) if target_row and target_row.value else None
    except ValueError:
        monthly_target = None

    return {
        "range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "product_filter": (
            {"id": product.id, "name": product.name, "spec": product.spec} if product else None
        ),
        "summary": {
            **{k: round(v, 2) for k, v in total.items()},
            "entry_count": len(rows),
            "today_production": round(today_stat["production"], 2),
            "today_shipment": round(today_stat["shipment"], 2),
            "today_ship_amount": round(today_stat["ship_amount"], 2),
            "month_ship_amount": month_ship_amount,
            "document_count": doc_count,
            "pending_count": pending_count,
            "failed_count": failed_count,
            "pending_entry_count": pending_entry_count,
        },
        "prev_summary": prev_summary,
        "prev_range": {"start": prev_start.isoformat(), "end": prev_end.isoformat()},
        "monthly_target": monthly_target,
        "daily": [
            {"date": k.isoformat(), **{f: round(v[f], 2) for f in v}}
            for k, v in sorted(daily.items())
        ],
        "monthly": [
            {"month": k, **{f: round(v[f], 2) for f in v}} for k, v in sorted(monthly.items())
        ],
        "spec_stats": sorted(spec_stats.values(), key=lambda s: -s["shipment"]),
        "recent_documents": [
            {"id": d.id, "filename": d.filename, "status": d.status, "created_at": d.created_at}
            for d in recent_docs
        ],
    }
