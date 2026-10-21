"""SQLite 轻量迁移：create_all 只建新表，不给旧表加列/改约束，这里统一补齐。

启动时调用，幂等：已应用过的变更自动跳过。
"""

import logging

from sqlalchemy.engine import Engine

logger = logging.getLogger("migrations")

# finance_records 最新的建表结构（用于检测是否需要重建表以放开 document_id 可空）
_FINANCE_NEW_SCHEMA = """
CREATE TABLE finance_records_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    biz_date DATE NOT NULL,
    revenue FLOAT,
    cost FLOAT,
    profit FLOAT,
    tx_count INTEGER,
    payments TEXT,
    category VARCHAR(50),
    extraction_type VARCHAR(20),
    source VARCHAR(20),
    confidence FLOAT,
    evidence TEXT,
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
)
"""

_FINANCE_COPY = """
INSERT INTO finance_records_new
    (id, document_id, biz_date, revenue, cost, profit, tx_count, payments,
     category, extraction_type, source, confidence, evidence, created_at)
SELECT id, document_id, biz_date, revenue, cost, profit, tx_count, payments,
       category, extraction_type,
       CASE WHEN source IS NULL AND extraction_type = 'mock' THEN 'rule' ELSE source END,
       confidence, evidence, created_at
FROM finance_records
"""


def _columns(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def run_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        # 0) reports.charts（可视化报告数据 JSON；旧报告为 NULL 走纯文本降级）
        if "reports" in _existing_tables(conn) and "charts" not in _columns(conn, "reports"):
            conn.exec_driver_sql("ALTER TABLE reports ADD COLUMN charts TEXT")
            logger.info("reports 新增列 charts")

        # finance_records 可能还不存在（全新库，create_all 会直接建最新结构）
        if "finance_records" not in _existing_tables(conn):
            logger.info("finance_records 不存在，跳过迁移")
            return

        cols = _columns(conn, "finance_records")

        # 1) 补新列
        added = []
        if "source" not in cols:
            conn.exec_driver_sql("ALTER TABLE finance_records ADD COLUMN source VARCHAR(20) DEFAULT 'llm'")
            added.append("source")
        if "tx_count" not in cols:
            conn.exec_driver_sql("ALTER TABLE finance_records ADD COLUMN tx_count INTEGER")
            added.append("tx_count")
        if "payments" not in cols:
            conn.exec_driver_sql("ALTER TABLE finance_records ADD COLUMN payments TEXT")
            added.append("payments")
        if added:
            logger.info("finance_records 新增列：%s", ", ".join(added))

        # 2) 历史数据来源修正：mock → rule
        conn.exec_driver_sql(
            "UPDATE finance_records SET source = 'rule' WHERE extraction_type = 'mock' AND (source IS NULL OR source = 'llm')"
        )

        # 3) users.must_change_password（首次登录强制改密）
        if "users" in _existing_tables(conn):
            user_cols = _columns(conn, "users")
            if "must_change_password" not in user_cols:
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0"
                )
                # 种子出来的默认 admin 需要首次改密
                conn.exec_driver_sql(
                    "UPDATE users SET must_change_password = 1 WHERE username = 'admin'"
                )
                logger.info("users 新增列 must_change_password")

        # 4) document_id 放开为可空（手工记账没有关联文档）：SQLite 需重建表
        doc_notnull = conn.exec_driver_sql("PRAGMA table_info(finance_records)").fetchall()
        doc_col = next((r for r in doc_notnull if r[1] == "document_id"), None)
        if doc_col is not None and doc_col[3]:  # notnull 标记为 1 → 需要重建
            logger.info("重建 finance_records 以放开 document_id 可空")
            conn.exec_driver_sql(_FINANCE_NEW_SCHEMA)
            conn.exec_driver_sql(_FINANCE_COPY)
            conn.exec_driver_sql("DROP TABLE finance_records")
            conn.exec_driver_sql("ALTER TABLE finance_records_new RENAME TO finance_records")
            # 重建索引
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_finance_records_biz_date ON finance_records (biz_date)")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_finance_records_document_id ON finance_records (document_id)"
            )

        conn.commit()
        logger.info("迁移完成")


def _existing_tables(conn) -> set[str]:
    rows = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {r[0] for r in rows}
