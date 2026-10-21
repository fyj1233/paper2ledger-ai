"""数据字典：分类 / 支付方式等枚举统一维护。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import require_admin, get_current_user
from app.models import DictItem, User

router = APIRouter(prefix="/api/dicts", tags=["数据字典"])

DICT_TYPES = {"category": "业务分类", "payment": "支付方式"}


class DictItemRequest(BaseModel):
    dict_type: str = Field(pattern="^(category|payment)$")
    name: str = Field(min_length=1, max_length=50)
    sort: int = 0


class DictItemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None
    sort: int | None = None


@router.get("")
def list_dicts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """全部登录用户可读（上传表单的分类下拉要用）。"""
    rows = db.query(DictItem).order_by(DictItem.dict_type, DictItem.sort, DictItem.id).all()
    grouped: dict[str, list] = {}
    for r in rows:
        grouped.setdefault(r.dict_type, []).append(
            {"id": r.id, "name": r.name, "sort": r.sort, "is_active": r.is_active}
        )
    return grouped


@router.post("", status_code=201)
def create_dict_item(
    body: DictItemRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if body.dict_type not in DICT_TYPES:
        raise HTTPException(status_code=400, detail="不支持的字典类型")
    dup = (
        db.query(DictItem)
        .filter(DictItem.dict_type == body.dict_type, DictItem.name == body.name)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail=f"「{body.name}」已存在")
    item = DictItem(dict_type=body.dict_type, name=body.name, sort=body.sort)
    db.add(item)
    db.commit()
    log_action(db, admin, "新增字典项", f"{DICT_TYPES[body.dict_type]}：{body.name}")
    return {"id": item.id, "message": "已创建"}


@router.put("/{item_id}")
def update_dict_item(
    item_id: int,
    body: DictItemUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="字典项不存在")
    if body.name is not None:
        item.name = body.name
    if body.is_active is not None:
        item.is_active = body.is_active
    if body.sort is not None:
        item.sort = body.sort
    db.commit()
    log_action(db, admin, "更新字典项", f"{item.dict_type}：{item.name}")
    return {"message": "已保存"}


@router.delete("/{item_id}")
def delete_dict_item(
    item_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    item = db.query(DictItem).filter(DictItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="字典项不存在")
    db.delete(item)
    db.commit()
    log_action(db, admin, "删除字典项", f"{item.dict_type}：{item.name}")
    return {"message": "已删除"}
