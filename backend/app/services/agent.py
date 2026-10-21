"""AI 助手智能体（LangGraph）：带工具的多步问答，台账口径。

工具集：查每日产销 / 规格出货排行 / 台账明细 / 库存结存 / 异常预警 / 最近单据 / 生成报告。
数据来源与看板、台账报表同一套模型（LedgerEntry / Product），口径一致。
"""

import json
from datetime import date

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, LedgerEntry, Product
from app.services import report_builder
from app.services.insights import compute_anomalies, daily_rows, inventory_rows, spec_rank

SYSTEM_PROMPT = """你是「一纸成账」系统的 AI 助手，帮助工厂老板分析每日台账数据（螺母等轻工业品的产量、出货、库存）。
今天是 {today}。台账条目五类型：期初盘点(initial)、生产(production)、退货(return) 加库存；出货(shipment)、报废(scrap) 减库存。

规则：
1. 涉及产量、出货、库存、金额的问题必须调用工具查询后再回答，禁止凭空编造数字。
2. 需要多步分析时（如先查汇总再查异常），依次调用多个工具。
3. 回答用中文，简明实用；数量带单位（如千件），金额单位元，引用具体日期与数字，并适当给出经营建议。
4. 查不到数据时如实说明（例如该时间段没有记录），不要猜测。"""


def _d(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return fallback


def build_agent(cfg: dict, db: Session, checkpointer=None):
    """构建智能体。db 会话由调用方管理生命周期（流式结束后关闭）；
    checkpointer 传入进程级单例时按 thread_id 携带多轮上下文。"""
    today = date.today()

    @tool
    def query_daily(start: str, end: str) -> str:
        """查询一段时间内每天的产量、出货量、出货金额、退货、报废汇总。start/end 为 YYYY-MM-DD。"""
        rows = daily_rows(db, _d(start, today), _d(end, today))
        return json.dumps(
            [{"date": d["date"].isoformat(), **{f: round(d[f], 2) for f in
              ("production", "shipment", "ship_amount", "return", "scrap")}} for d in rows],
            ensure_ascii=False,
        )

    @tool
    def query_spec_rank(start: str, end: str) -> str:
        """查询一段时间内各产品规格的产量/出货量/出货金额排行（按出货量降序）。start/end 为 YYYY-MM-DD。"""
        return json.dumps(spec_rank(db, _d(start, today), _d(end, today)), ensure_ascii=False)

    @tool
    def query_ledger_entries(start: str, end: str, product_name: str = "", entry_type: str = "") -> str:
        """查询台账明细（每条含日期/品名/规格/类型/数量/单价/金额/客户）。start/end 为 YYYY-MM-DD；
        product_name 可选按品名过滤；entry_type 可选：initial/production/shipment/return/scrap。"""
        query = db.query(LedgerEntry).filter(
            LedgerEntry.entry_date >= _d(start, today), LedgerEntry.entry_date <= _d(end, today)
        )
        if entry_type:
            query = query.filter(LedgerEntry.entry_type == entry_type)
        product_query = db.query(Product)
        if product_name:
            product_query = product_query.filter(Product.name.contains(product_name))
            query = query.filter(LedgerEntry.product_id.in_(p.id for p in product_query.all()))
        rows = query.order_by(LedgerEntry.entry_date.desc(), LedgerEntry.id.desc()).limit(100).all()
        products = {p.id: p for p in db.query(Product).all()}
        return json.dumps(
            [
                {
                    "date": r.entry_date.isoformat(), "name": products[r.product_id].name,
                    "spec": products[r.product_id].spec,
                    "entry_type": r.entry_type, "quantity": r.quantity, "unit": products[r.product_id].unit,
                    "unit_price": r.unit_price, "amount": r.amount, "customer": r.customer,
                }
                for r in rows if r.product_id in products
            ],
            ensure_ascii=False,
        )

    @tool
    def query_inventory() -> str:
        """查询全部产品的当前库存结存（期初+生产+退货−出货−报废），含预警线，低于预警线的已标记 low=true。"""
        return json.dumps(inventory_rows(db), ensure_ascii=False)

    @tool
    def get_anomalies(days: int = 14) -> str:
        """获取最近的台账异常预警（断产无生产记录、出货骤降、库存告急）。days 为检查的最近天数。"""
        return json.dumps(compute_anomalies(db, days), ensure_ascii=False)

    @tool
    def list_recent_documents(limit: int = 10) -> str:
        """查询最近上传的单据（文件名、解析状态、上传时间）。"""
        rows = db.query(Document).order_by(Document.id.desc()).limit(min(limit, 50)).all()
        return json.dumps(
            [{"id": d.id, "filename": d.filename, "status": d.status, "uploaded_at": d.created_at.isoformat()} for d in rows],
            ensure_ascii=False,
        )

    @tool
    def generate_report(report_type: str) -> str:
        """生成生产台账报告并保存到报告中心。report_type 只能是 weekly（周报）或 monthly（月报）。"""
        result = report_builder.create_report(cfg, db, None, report_type, date.today())
        return json.dumps({"message": "报告已生成并保存到报告中心", **{k: result[k] for k in ("id", "period_start", "period_end")}}, ensure_ascii=False)

    @tool
    def count_entries(start: str, end: str) -> str:
        """统计一段时间内的台账条目数与涉及单据数。"""
        start_d, end_d = _d(start, today), _d(end, today)
        entries = db.query(func.count(LedgerEntry.id)).filter(
            LedgerEntry.entry_date >= start_d, LedgerEntry.entry_date <= end_d
        ).scalar()
        docs = db.query(func.count(Document.id)).filter(
            Document.created_at >= f"{start_d} 00:00:00", Document.created_at <= f"{end_d} 23:59:59"
        ).scalar()
        return json.dumps({"entry_count": entries, "document_count": docs}, ensure_ascii=False)

    tools = [query_daily, query_spec_rank, query_ledger_entries, query_inventory, get_anomalies,
             list_recent_documents, generate_report, count_entries]

    llm = ChatOpenAI(
        model=cfg["model"],
        api_key=cfg["key"],
        base_url=cfg["base"],
        temperature=0.3,
        streaming=True,
        timeout=settings.LLM_TIMEOUT,
    )
    # 兜底：配置了备用服务商时，主模型故障自动切换（bind_tools 会同步转发到备用）
    backup = cfg.get("backup")
    if backup:
        llm = llm.with_fallbacks([
            ChatOpenAI(
                model=backup["model"],
                api_key=backup["key"],
                base_url=backup["base"],
                temperature=0.3,
                streaming=True,
                timeout=settings.LLM_TIMEOUT,
            )
        ])
    return create_react_agent(
        llm, tools, prompt=SYSTEM_PROMPT.format(today=today.isoformat()),
        checkpointer=checkpointer,
    )
