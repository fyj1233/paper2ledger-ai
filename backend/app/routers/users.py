from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import require_admin
from app.models import AuditLog, User
from app.schemas import UserCreateRequest, UserOut, UserUpdateRequest
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["用户管理"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, admin, "创建用户", f"{body.username} ({body.role})")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="不能停用自己的账号")
    if user.id == admin.id and body.role and body.role != "admin":
        raise HTTPException(status_code=400, detail="不能降级自己的角色")
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    log_action(db, admin, "更新用户", user.username)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    db.delete(user)
    db.commit()
    log_action(db, admin, "删除用户", user.username)
    return {"message": "已删除"}


@router.get("/audit")
def list_audit(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 300)).all()
    return [
        {
            "id": r.id,
            "username": r.username,
            "action": r.action,
            "detail": r.detail,
            "created_at": r.created_at,
        }
        for r in rows
    ]
