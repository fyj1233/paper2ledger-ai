"""认证：登录（含失败锁定）、当前用户、修改密码。"""

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ChangePasswordRequest, LoginRequest, LoginResponse, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 登录失败锁定：连续 5 次错误锁 10 分钟（单进程内存态，微小型企业够用）
MAX_FAILURES = 5
LOCK_SECONDS = 600
_login_failures: dict[str, list] = {}  # username -> [失败次数, 锁定截止时间戳]


def _locked_remaining(username: str) -> int:
    info = _login_failures.get(username)
    if not info:
        return 0
    count, locked_until = info
    if locked_until and locked_until > time.time():
        return int(locked_until - time.time())
    if count >= MAX_FAILURES:  # 锁已过期，重置
        _login_failures.pop(username, None)
    return 0


def _record_failure(username: str) -> None:
    info = _login_failures.setdefault(username, [0, 0])
    info[0] += 1
    if info[0] >= MAX_FAILURES:
        info[1] = time.time() + LOCK_SECONDS


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    remaining = _locked_remaining(body.username)
    if remaining:
        raise HTTPException(
            status_code=429,
            detail=f"密码连续错误次数过多，账号已锁定，请 {remaining // 60 + 1} 分钟后再试",
        )
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        _record_failure(body.username)
        left = MAX_FAILURES - _login_failures.get(body.username, [0, 0])[0]
        detail = "用户名或密码错误"
        if 0 < left <= MAX_FAILURES and left <= 2:
            detail += f"（再错 {left} 次将锁定 10 分钟）"
        raise HTTPException(status_code=401, detail=detail)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被停用，请联系管理员")
    _login_failures.pop(body.username, None)
    log_action(db, user, "登录")
    return LoginResponse(access_token=create_access_token(user.username), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    log_action(db, user, "修改密码")
    return {"message": "密码修改成功"}
