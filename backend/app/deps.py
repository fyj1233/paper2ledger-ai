from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# 强制改密期间仍放行的接口：否则前端拿不到标志位、也调不动改密接口
_PASSWORD_FIRST_PATHS = ("/api/auth/me", "/api/auth/change-password")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已被停用")
    # 服务端也要拦：只在弹窗里强制改密的话，直接调 API 仍能沿用初始密码
    if user.must_change_password and request.url.path not in _PASSWORD_FIRST_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先修改初始密码后再使用系统",
            headers={"X-Must-Change-Password": "1"},
        )
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行此操作")
        return user

    return checker


require_admin = require_roles("admin")
require_manager = require_roles("admin", "manager")
