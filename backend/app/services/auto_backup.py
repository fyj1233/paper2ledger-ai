"""定时自动备份：main.py lifespan 启动的后台循环。

每 30 秒检查一次：开关开启 + 当前时间已过当日计划时间 + 当日还没有备份 → 自动打包。
错过时间点也能补跑（如计划 23:30，服务 23:45 才启动，当日仍会备份一次）。
"""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import SessionLocal
from app.models import Setting
from app.services.backup_service import BACKUP_DIR, create_backup_zip

logger = logging.getLogger("auto_backup")

CHECK_INTERVAL_SECONDS = 30
DEFAULT_TIME = "23:30"


def parse_hhmm(raw: str) -> tuple[int, int] | None:
    try:
        hh, mm = raw.strip().split(":")
        hh, mm = int(hh), int(mm)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, AttributeError):
        pass
    return None


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return (row.value if row else "") or default


def should_backup_now(db: Session) -> bool:
    if _get_setting(db, "auto_backup_enabled") != "1":
        return False
    hhmm = parse_hhmm(_get_setting(db, "auto_backup_time", DEFAULT_TIME))
    if hhmm is None:
        logger.warning("自动备份时间配置非法，回退默认 %s", DEFAULT_TIME)
        hhmm = parse_hhmm(DEFAULT_TIME)
    now = datetime.now()
    if (now.hour, now.minute) < hhmm:
        return False
    return not any(BACKUP_DIR.glob(f"backup_{now:%Y%m%d}_*.zip"))


async def auto_backup_loop() -> None:
    while True:
        try:
            db = SessionLocal()
            try:
                due = should_backup_now(db)
            finally:
                db.close()
            if due:
                # 打包在线程池执行，避免阻塞事件循环（SSE 流式在同一个循环上）
                info = await asyncio.to_thread(create_backup_zip)
                audit_db = SessionLocal()
                try:
                    log_action(audit_db, None, "定时自动备份", info["file"])
                finally:
                    audit_db.close()
                logger.info("定时自动备份完成：%s", info["file"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("自动备份任务异常，将继续重试")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
