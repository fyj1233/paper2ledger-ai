"""台账数据查询服务：智能体工具 / 报告生成 / 异常预警共用的查询与计算逻辑（台账口径）。"""

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import LedgerEntry, Product


def _entry_amount(r: LedgerEntry) -> float:
    if r.amount is not None:
        return r.amount
    return (r.unit_price or 0) * (r.quantity or 0)


def daily_rows(db: Session, start: date, end: date) -> list[dict]:
    """按日聚合台账五类型：产量 / 出货量 / 出货金额 / 退货 / 报废。"""
    rows = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.entry_date >= start, LedgerEntry.entry_date <= end)
        .order_by(LedgerEntry.entry_date)
        .all()
    )
    daily: dict[date, dict[str, float]] = {}
    for r in rows:
        d = daily.setdefault(
            r.entry_date,
            {"production": 0.0, "shipment": 0.0, "ship_amount": 0.0, "return": 0.0, "scrap": 0.0},
        )
        if r.entry_type == "production":
            d["production"] += r.quantity or 0
        elif r.entry_type == "shipment":
            d["shipment"] += r.quantity or 0
            d["ship_amount"] += _entry_amount(r)
        elif r.entry_type == "return":
            d["return"] += r.quantity or 0
        elif r.entry_type == "scrap":
            d["scrap"] += r.quantity or 0
    return [{"date": k, **v} for k, v in sorted(daily.items())]


def spec_rank(db: Session, start: date, end: date) -> list[dict]:
    """按产品聚合期间的产量 / 出货量 / 出货金额，按出货量降序。"""
    rows = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.entry_date >= start, LedgerEntry.entry_date <= end)
        .all()
    )
    products = {p.id: p for p in db.query(Product).all()}
    stats: dict[int, dict] = {}
    for r in rows:
        p = products.get(r.product_id)
        if not p:
            continue
        s = stats.setdefault(r.product_id, {
            "product_id": p.id, "name": p.name, "spec": p.spec, "unit": p.unit,
            "production": 0.0, "shipment": 0.0, "ship_amount": 0.0,
        })
        if r.entry_type == "production":
            s["production"] += r.quantity or 0
        elif r.entry_type == "shipment":
            s["shipment"] += r.quantity or 0
            s["ship_amount"] += _entry_amount(r)
    return sorted(
        [{**s, **{f: round(s[f], 2) for f in ("production", "shipment", "ship_amount")}} for s in stats.values()],
        key=lambda x: -x["shipment"],
    )


def inventory_rows(db: Session) -> list[dict]:
    """全部产品的当前库存结存（期初+生产+退货−出货−报废），含预警线与告急标记。"""
    rows = (
        db.query(LedgerEntry.product_id, LedgerEntry.entry_type, func.sum(LedgerEntry.quantity))
        .group_by(LedgerEntry.product_id, LedgerEntry.entry_type)
        .all()
    )
    sums = {(pid, etype): float(total or 0) for pid, etype, total in rows}
    result = []
    for p in db.query(Product).order_by(Product.name, Product.spec).all():
        qty = {t: sums.get((p.id, t), 0.0) for t in ("initial", "production", "return", "shipment", "scrap")}
        balance = round(qty["initial"] + qty["production"] + qty["return"] - qty["shipment"] - qty["scrap"], 2)
        result.append({
            "product_id": p.id, "name": p.name, "spec": p.spec, "unit": p.unit,
            "warn_stock": p.warn_stock, "balance": balance,
            "low": p.warn_stock is not None and balance <= p.warn_stock,
        })
    return result


def compute_anomalies(db: Session, days: int = 14) -> list[dict]:
    """台账口径异常检测：断产 / 出货骤降 / 库存告急。"""
    DEVIATION = 0.4
    BASELINE_MIN = 10.0

    today = date.today()
    series = daily_rows(db, today - timedelta(days=120), today)

    alerts: list[dict] = []

    # 1) 断产：最近一个生产日之后连续多天无生产记录（含今天在内，2 天以上才提醒；超过窗口不报）
    prod_dates = [d["date"] for d in series if d["production"] > 0]
    if prod_dates:
        halt_days = (today - prod_dates[-1]).days
        if 2 <= halt_days <= days:
            alerts.append({
                "type": "halt",
                "date": today.isoformat(),
                "message": f"自 {prod_dates[-1].isoformat()} 后已连续 {halt_days} 天没有生产记录，注意是否漏传生产日报或已停线",
            })

    # 2) 出货骤降：最近一个有出货的日期，出货量较之前最多 7 个有数据日的均值下降超四成
    ship_series = [d for d in series if d["shipment"] > 0]
    if len(ship_series) >= 4:
        last = ship_series[-1]
        history = [x["shipment"] for x in ship_series[-8:-1]]
        avg = sum(history) / len(history)
        if avg >= BASELINE_MIN:
            change = (last["shipment"] - avg) / avg
            if change <= -DEVIATION:
                alerts.append({
                    "type": "ship_drop",
                    "date": last["date"].isoformat(),
                    "shipment": round(last["shipment"], 2),
                    "baseline": round(avg, 2),
                    "change": round(change, 4),
                    "message": (
                        f"{last['date'].strftime('%m月%d日')} 出货 {last['shipment']:.1f}，"
                        f"较前几日均值（{avg:.1f}）下降 {abs(change) * 100:.0f}%，建议核对出货单据是否齐全"
                    ),
                })

    # 3) 库存告急：结存 ≤ 预警线
    for p in inventory_rows(db):
        if p["low"]:
            alerts.append({
                "type": "stock",
                "date": today.isoformat(),
                "message": f"库存告急：{p['name']} {p['spec']} 结存 {p['balance']}{p['unit']}（预警线 {p['warn_stock']}{p['unit']}）",
            })

    return alerts
