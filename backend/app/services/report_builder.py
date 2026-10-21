"""AI 报告生成：周期计算、台账数据汇总、可视化图表数据、提示词与入库。路由与智能体工具共用。

数据流原则：图表数字全部由本模块从数据库计算（经 insights），LLM 只负责文字分析，杜绝编造。
"""

import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Report
from app.services.llm import smart_chat
from app.services.insights import daily_rows, inventory_rows, spec_rank

REPORT_PROMPT = """你是「一纸成账」系统的 AI 经营顾问。请根据以下{period_name}生产台账数据，为工厂老板写一份简明经营报告。

要求：
1. 用中文，总长度 400 字以内，分四个小节：总体概况、经营亮点、存在问题、改进建议。
2. 全部结论必须基于给出的数据计算，不得编造数字；数字保留合理精度。
3. 语气务实，建议具体可执行（不超过 3 条）。
4. 直接输出报告正文，不要输出标题以外的寒暄或解释。

本期（{start} 至 {end}）每日台账（数量单位与产品单位一致）：日期 | 产量 | 出货量 | 出货金额(元) | 退货 | 报废
{daily_table}

汇总：产量 {production}，出货量 {shipment}，出货金额 {ship_amount} 元，有数据天数 {days} 天，日均出货 {avg_ship}
上期（{prev_start} 至 {prev_end}）汇总：出货量 {prev_shipment}，出货金额 {prev_ship_amount} 元
环比变化：出货量 {ship_change}，出货金额 {amount_change}
单日出货最高：{best_line}
单日出货最低：{worst_line}
规格出货排行（本期）：{spec_lines}
当前库存结存：{inventory_lines}
"""


def period_range(report_type: str, anchor: date) -> tuple[date, date, date, date]:
    """返回 (本期起, 本期止, 上期起, 上期止)。本期止不超过锚点日期。"""
    if report_type == "monthly":
        start = anchor.replace(day=1)
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = nxt - timedelta(days=1)
        prev_end = start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return start, min(end, anchor), prev_start, prev_end
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=6)
    prev_start = start - timedelta(days=7)
    prev_end = start - timedelta(days=1)
    return start, min(end, anchor), prev_start, prev_end


def _summarize(daily: list[dict]) -> dict:
    total_prod = sum(d["production"] for d in daily)
    total_ship = sum(d["shipment"] for d in daily)
    total_amount = sum(d["ship_amount"] for d in daily)
    best = max(daily, key=lambda d: d["shipment"]) if daily else None
    worst = min(daily, key=lambda d: d["shipment"]) if daily else None
    return {
        "days": len(daily),
        "production": round(total_prod, 2),
        "shipment": round(total_ship, 2),
        "ship_amount": round(total_amount, 2),
        "avg_ship": round(total_ship / len(daily), 2) if daily else 0,
        "best": best,
        "worst": worst,
    }


def create_report(cfg: dict, db: Session, creator, report_type: str, anchor: date) -> dict:
    """生成报告并入库，返回 {"id", "report_type", "period_start", "period_end", "content", "created_at"}。"""
    start, end, prev_start, prev_end = period_range(report_type, anchor)
    daily = daily_rows(db, start, end)
    if not daily:
        raise ValueError("该时间段没有任何台账数据，无法生成报告")
    cur = _summarize(daily)
    prev = _summarize(daily_rows(db, prev_start, prev_end)) if prev_end >= prev_start else _summarize([])

    def pct(now, before):
        if not before:
            return "上期无数据"
        change = (now - before) / before
        return f"{'上升' if change >= 0 else '下降'} {abs(change) * 100:.1f}%"

    spec_list = spec_rank(db, start, end)
    inv_list = inventory_rows(db)
    spec_lines = "；".join(
        f"{s['name']} {s['spec']} 出货 {s['shipment']:.1f}{s['unit']}（{s['ship_amount']:.0f} 元）"
        for s in spec_list[:5]
    ) or "无数据"
    inventory_lines = "；".join(
        f"{p['name']} {p['spec']} {p['balance']}{p['unit']}" + ("（低于预警线）" if p["low"] else "")
        for p in inv_list
    ) or "无产品"

    daily_table = "\n".join(
        f"{d['date'].isoformat()} | {d['production']:.1f} | {d['shipment']:.1f} | {d['ship_amount']:.2f} | {d['return']:.1f} | {d['scrap']:.1f}"
        for d in daily
    )
    period_name = "周" if report_type == "weekly" else "月"

    prompt = REPORT_PROMPT.format(
        period_name=f"{period_name}度",
        start=start.isoformat(), end=end.isoformat(),
        daily_table=daily_table,
        production=cur["production"], shipment=cur["shipment"], ship_amount=cur["ship_amount"],
        days=cur["days"], avg_ship=cur["avg_ship"],
        prev_start=prev_start.isoformat(), prev_end=prev_end.isoformat(),
        prev_shipment=prev["shipment"], prev_ship_amount=prev["ship_amount"],
        ship_change=pct(cur["shipment"], prev["shipment"]),
        amount_change=pct(cur["ship_amount"], prev["ship_amount"]),
        best_line=(f"{cur['best']['date'].isoformat()} 出货 {cur['best']['shipment']:.1f}（金额 {cur['best']['ship_amount']:.2f} 元）" if cur["best"] else "无"),
        worst_line=(f"{cur['worst']['date'].isoformat()} 出货 {cur['worst']['shipment']:.1f}（金额 {cur['worst']['ship_amount']:.2f} 元）" if cur["worst"] else "无"),
        spec_lines=spec_lines,
        inventory_lines=inventory_lines,
    )
    content = smart_chat(cfg, [{"role": "user", "content": prompt}], temperature=0.4)

    # 可视化数据：数字全部来自上面的库内计算，与 AI 文字相互独立
    def _pct_value(now, before):
        if not before:
            return None
        return round((now - before) / before, 4)

    main_unit = max((s["unit"] for s in spec_list), key=lambda u: sum(s["shipment"] for s in spec_list if s["unit"] == u), default="")
    charts = {
        "cards": [
            {"label": "总产量", "value": cur["production"], "unit": main_unit, "change": _pct_value(cur["production"], prev["production"])},
            {"label": "出货量", "value": cur["shipment"], "unit": main_unit, "change": _pct_value(cur["shipment"], prev["shipment"])},
            {"label": "出货金额", "value": cur["ship_amount"], "unit": "元", "change": _pct_value(cur["ship_amount"], prev["ship_amount"])},
            {"label": "有数据天数", "value": cur["days"], "unit": "天", "change": None},
        ],
        "trend": {
            "dates": [d["date"].strftime("%m-%d") for d in daily],
            "production": [round(d["production"], 2) for d in daily],
            "shipment": [round(d["shipment"], 2) for d in daily],
            "ship_amount": [round(d["ship_amount"], 2) for d in daily],
        },
        "spec_rank": [
            {"name": s["name"], "spec": s["spec"], "shipment": s["shipment"],
             "unit": s["unit"], "ship_amount": s["ship_amount"]}
            for s in spec_list[:10]
        ],
        "inventory": [
            {"name": p["name"], "spec": p["spec"], "balance": p["balance"],
             "unit": p["unit"], "low": p["low"]}
            for p in inv_list
        ],
    }

    report = Report(
        report_type=report_type,
        period_start=start,
        period_end=end,
        content=content,
        charts=json.dumps(charts, ensure_ascii=False),
        creator_id=creator.id if creator else None,
        creator_name=creator.username if creator else "AI 助手",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "content": content,
        "charts": charts,
        "created_at": report.created_at,
    }
