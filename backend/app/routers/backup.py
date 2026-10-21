"""数据备份：把数据库和上传文件打包为 zip，自动清理 30 天前的旧备份。"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import require_admin
from app.models import User
from app.services.backup_service import BACKUP_DIR, create_backup_zip

router = APIRouter(prefix="/api/backup", tags=["数据备份"])


@router.post("")
def create_backup(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    result = create_backup_zip()
    log_action(db, admin, "数据备份", result["file"])
    return result


@router.get("")
def list_backups(_: User = Depends(require_admin)):
    if not BACKUP_DIR.exists():
        return []
    items = []
    for f in sorted(BACKUP_DIR.glob("backup_*.zip"), reverse=True):
        items.append({"file": f.name, "size": f.stat().st_size, "modified_at": datetime.fromtimestamp(f.stat().st_mtime)})
    return items


@router.get("/download")
def download_backup(name: str, _: User = Depends(require_admin)):
    # 防路径穿越
    safe = Path(name).name
    path = BACKUP_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    return FileResponse(path, filename=safe, media_type="application/zip")


@router.delete("/{name}")
def delete_backup(name: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    safe = Path(name).name
    path = BACKUP_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    path.unlink()
    log_action(db, admin, "删除备份", safe)
    return {"message": "已删除"}
