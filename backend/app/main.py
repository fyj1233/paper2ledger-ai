from contextlib import asynccontextmanager
from pathlib import Path

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings as app_settings
from app.database import Base, SessionLocal, engine
from app.migrations import run_migrations
from app.models import DictItem, User
from app.routers import (
    assistant,
    auth,
    backup,
    dashboard,
    dicts,
    documents,
    ledger,
    products,
    records,
    reports,
    settings,
    templates,
    users,
)
from app.security import hash_password

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

DEFAULT_DICTS = {
    "category": ["默认", "餐饮", "零售", "服务", "批发"],
    "payment": ["现金", "微信", "支付宝", "银行卡"],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if app_settings.JWT_SECRET_EPHEMERAL:
        print(
            "[警告] 未设置 JWT_SECRET，已临时生成随机密钥：重启后所有登录令牌失效，"
            "多进程部署会互相验签失败。请在 backend/.env 中配置 JWT_SECRET。"
        )
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    db = SessionLocal()
    try:
        # 默认字典（仅首次为空时写入）
        if not db.query(DictItem).first():
            for dict_type, names in DEFAULT_DICTS.items():
                for sort, name in enumerate(names):
                    db.add(DictItem(dict_type=dict_type, name=name, sort=sort))
            db.commit()
        if not db.query(User).first():
            db.add(
                User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    role="admin",
                    must_change_password=True,
                )
            )
            db.commit()
            print("=" * 50)
            print("已创建默认管理员账号：admin / admin123")
            print("请登录后立即在右上角修改密码！")
            print("=" * 50)
    finally:
        db.close()
    from app.services.agent_memory import close_checkpointer, init_checkpointer
    from app.services.auto_backup import auto_backup_loop

    await init_checkpointer()
    auto_backup_task = asyncio.create_task(auto_backup_loop())
    yield
    auto_backup_task.cancel()
    await close_checkpointer()


app = FastAPI(title="一纸成账", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(assistant.router)
app.include_router(templates.router)
app.include_router(dicts.router)
app.include_router(records.router)
app.include_router(reports.router)
app.include_router(backup.router)
app.include_router(products.router)
app.include_router(ledger.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 生产模式：托管前端构建产物（frontend/dist 存在时生效），未命中文件回退 index.html（SPA 路由）
if FRONTEND_DIST.exists():
    _dist = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        from fastapi.responses import FileResponse

        candidate = (_dist / full_path).resolve() if full_path else _dist / "index.html"
        if full_path and candidate.is_file() and candidate.is_relative_to(_dist):
            # 带内容 hash 的静态资源可长缓存；index.html 必须每次校验，否则发版后用户拿到旧 chunk 引用
            if candidate.name == "index.html":
                return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
            return FileResponse(candidate, headers={"Cache-Control": "public, max-age=604800"})
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})
