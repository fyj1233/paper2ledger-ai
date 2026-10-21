"""备份核心逻辑：打包 app.db + agent_memory.db + uploads 为 zip，清理过期备份。

手动备份（backup 路由）与定时自动备份（auto_backup 服务）共用，勿在路由里内联重复实现。
"""

import sqlite3
import zipfile
from datetime import datetime, timedelta

from app.config import settings

BACKUP_DIR = settings.UPLOAD_DIR.parent / "backups"
KEEP_DAYS = 30

DB_FILES = ("app.db", "agent_memory.db")


def _snapshot_into(zf: zipfile.ZipFile, db_file, arcname: str) -> None:
    """用 SQLite 备份 API 取一致性快照。

    直接打包 app.db 会漏掉还在 -wal 里未落盘的近期写入（正跑着的库必然如此）。
    """
    tmp = BACKUP_DIR / f".{arcname}.snapshot"
    src = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    zf.write(tmp, arcname)
    tmp.unlink(missing_ok=True)


def create_backup_zip() -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = BACKUP_DIR / f"backup_{stamp}.zip"

    data_dir = settings.UPLOAD_DIR.parent
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for db_name in DB_FILES:
            db_file = data_dir / db_name
            if db_file.exists():
                _snapshot_into(zf, db_file, db_name)
        for f in settings.UPLOAD_DIR.rglob("*"):
            if f.is_file():
                zf.write(f, f"uploads/{f.relative_to(settings.UPLOAD_DIR)}")

    # 清理过期旧备份
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    removed = 0
    for old in BACKUP_DIR.glob("backup_*.zip"):
        try:
            if datetime.strptime(old.stem.replace("backup_", ""), "%Y%m%d_%H%M%S") < cutoff:
                old.unlink()
                removed += 1
        except ValueError:
            continue

    return {
        "message": "备份完成",
        "file": zip_path.name,
        "size": zip_path.stat().st_size,
        "removed_old": removed,
    }
