"""管理员密码重置工具：把 admin 账号重置为 admin / admin123。

忘记管理员密码时使用：
    cd backend
    python reset_admin.py

说明：
- admin 账号存在 → 重置密码为 admin123，并恢复为启用状态的管理员角色
- admin 账号不存在 → 重新创建
- 其他账号和数据不受影响
"""

from app.database import SessionLocal
from app.models import User
from app.security import hash_password


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if user:
            user.password_hash = hash_password("admin123")
            user.role = "admin"
            user.is_active = True
            print("已重置管理员账号：admin / admin123（其他数据不受影响）")
        else:
            db.add(User(username="admin", password_hash=hash_password("admin123"), role="admin"))
            print("管理员不存在，已重新创建：admin / admin123")
        db.commit()
        print("请用该账号登录后，在右上角菜单中修改密码。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
