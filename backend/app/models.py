from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(20), default="employee")  # admin / manager / employee
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False)  # 首次登录强制改密
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))  # txt / csv / docx / xlsx / pdf
    stored_path: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / processing / parsed / failed
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FinanceRecord(Base):
    __tablename__ = "finance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=True)
    biz_date: Mapped[date] = mapped_column(Date, index=True)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    tx_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 交易笔数（可选）
    payments: Mapped[str | None] = mapped_column(Text, nullable=True)  # 支付方式拆分 JSON，如 {"微信":1200,"现金":300}
    category: Mapped[str] = mapped_column(String(50), default="默认")
    # extract=文档中明确数字提取 / calc=模型推算汇总
    extraction_type: Mapped[str] = mapped_column(String(20), default="extract")
    # 数据来源：template=模板 / llm=大模型 / rule=规则 / manual=手工记账
    source: Mapped[str] = mapped_column(String(20), default="llm")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RecordEdit(Base):
    """数据修改留痕：谁在何时把哪些字段从原值改成了新值。"""

    __tablename__ = "record_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("finance_records.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="")
    changes: Mapped[str] = mapped_column(Text)  # JSON：[{"field":"revenue","old":100,"new":120}]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtractTemplate(Base):
    """提取模板：对固定格式的文档用关键词 + 字段正则直接提取，不消耗大模型。"""

    __tablename__ = "extract_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组：任一关键词命中即适用
    fields: Mapped[str] = mapped_column(Text, default="{}")  # JSON：{"date":[正则...],"revenue":[...],"cost":[...],"profit":[...],"tx_count":[...]}
    category: Mapped[str] = mapped_column(String(50), default="默认")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DictItem(Base):
    """数据字典：分类 / 支付方式 / 账户等枚举统一维护。"""

    __tablename__ = "dict_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dict_type: Mapped[str] = mapped_column(String(20), index=True)  # category / payment
    name: Mapped[str] = mapped_column(String(50))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(20))  # weekly / monthly
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    charts: Mapped[str | None] = mapped_column(Text, nullable=True)  # 可视化数据 JSON（旧报告为空则降级纯文本）
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    creator_name: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100), default="新对话")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Product(Base):
    """产品主数据：小工厂出品的规格清单（如：六角螺母 M8×1.25 镀锌 8.8级）。"""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("name", "spec", name="uq_product_name_spec"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))  # 品名，如 六角螺母
    spec: Mapped[str] = mapped_column(String(100), default="")  # 规格，如 M8×1.25 镀锌 8.8级
    unit: Mapped[str] = mapped_column(String(20), default="千件")  # 基准单位：千件 / 件 / kg / 米
    category: Mapped[str] = mapped_column(String(50), default="螺母")  # 产品分类
    warn_stock: Mapped[float | None] = mapped_column(Float, nullable=True)  # 低库存预警阈值
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LedgerEntry(Base):
    """台账明细：一行 = 某日期某产品的一笔出入库。数量恒为正，方向由类型决定。

    库存结存 = 期初 + 生产入库 + 退货 − 出货 − 报废（实时计算，不建库存表）。
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    # production=生产入库 / shipment=出货 / scrap=报废 / return=退货 / initial=期初
    entry_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)  # 恒为正数
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # 出货单价（元/单位）
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # 金额（出货 = 数量 × 单价）
    customer: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 客户（出货）
    # 数据来源：template=模板 / llm=大模型 / rule=规则 / manual=手工台账
    source: Mapped[str] = mapped_column(String(20), default="manual")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PendingEntry(Base):
    """待确认条目：文档提取出但无法自动匹配产品的规格条目，等人工认领/建产品/忽略后删除。"""

    __tablename__ = "pending_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    entry_date: Mapped[date] = mapped_column(Date)
    product_name: Mapped[str] = mapped_column(String(100), default="")  # 提取出的品名（自由文本）
    spec: Mapped[str] = mapped_column(String(200), default="")  # 提取出的规格（自由文本）
    entry_type: Mapped[str] = mapped_column(String(20))  # 与 ledger_entries 同：production/shipment/scrap/return/initial
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="")  # 文本中的单位（千件/件/kg…）
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="llm")  # template / llm / rule
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LedgerEdit(Base):
    """台账修改留痕：与 record_edits 同构，独立成表避免外键指向歧义。"""

    __tablename__ = "ledger_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("ledger_entries.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(50), default="")
    changes: Mapped[str] = mapped_column(Text)  # JSON：[{"field":"quantity","old":100,"new":120}]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
