import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")


class Settings:
    APP_NAME = "一纸成账"

    # 未配置 JWT_SECRET、或还留着模板占位符时，改为进程内随机生成：
    # 公开的默认密钥等于任何人都能伪造 admin 令牌。代价是重启后需重新登录。
    _INSECURE_SECRETS = {"", "change-me", "dev-secret-change-me", "secret", "your-secret-key", "请改成随机字符串"}
    _jwt_secret = os.getenv("JWT_SECRET", "").strip()
    JWT_SECRET_EPHEMERAL = _jwt_secret.lower() in _INSECURE_SECRETS
    JWT_SECRET = secrets.token_hex(32) if JWT_SECRET_EPHEMERAL else _jwt_secret

    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    _db_path = BASE_DIR / "data" / "app.db"
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_db_path.as_posix()}")
    AGENT_MEMORY_DB = BASE_DIR / "data" / "agent_memory.db"

    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", (BASE_DIR / "data" / "uploads").as_posix()))

    # 大模型配置默认值（可被数据库中 admin 设置的配置覆盖）
    LLM_API_BASE = os.getenv("LLM_API_BASE", "").strip()
    LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
    LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

    # 备用大模型（兜底）：主服务商报错时自动切换，可选
    LLM_BACKUP_API_BASE = os.getenv("LLM_BACKUP_API_BASE", "").strip()
    LLM_BACKUP_API_KEY = os.getenv("LLM_BACKUP_API_KEY", "").strip()
    LLM_BACKUP_MODEL = os.getenv("LLM_BACKUP_MODEL", "").strip()

    MAX_UPLOAD_MB = 20
    MAX_TEXT_CHARS = 60000


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
