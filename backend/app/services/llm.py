"""大模型调用管道：OpenAI 兼容接口的配置解析与底层调用。

提取逻辑在 extractors/llm_extract.py，这里只保留配置与底层请求。
支持备用大模型（兜底）：主服务商报错时自动切换备用重试一次。
"""

import logging

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Setting

logger = logging.getLogger("llm")

LLM_KEYS = ("llm_api_base", "llm_api_key", "llm_model")
LLM_BACKUP_KEYS = ("llm_backup_api_base", "llm_backup_api_key", "llm_backup_model")

DEFAULT_BASE = "https://api.openai.com/v1"


def get_effective_llm_config(db: Session) -> dict | None:
    db_vals = {s.key: s.value for s in db.query(Setting).filter(Setting.key.in_(LLM_KEYS + LLM_BACKUP_KEYS)).all()}

    def pick(key: str, env_val: str) -> str:
        v = (db_vals.get(key) or "").strip()
        return v or env_val

    base = pick("llm_api_base", settings.LLM_API_BASE)
    key = pick("llm_api_key", settings.LLM_API_KEY)
    model = pick("llm_model", settings.LLM_MODEL)
    if not (key and model):
        return None
    base = (base or DEFAULT_BASE).rstrip("/")

    # 备用配置：Key 和模型都填了才算启用（地址可省略，默认 OpenAI）
    b_base = pick("llm_backup_api_base", settings.LLM_BACKUP_API_BASE)
    b_key = pick("llm_backup_api_key", settings.LLM_BACKUP_API_KEY)
    b_model = pick("llm_backup_model", settings.LLM_BACKUP_MODEL)
    backup = None
    if b_key and b_model:
        backup = {"base": (b_base or DEFAULT_BASE).rstrip("/"), "key": b_key, "model": b_model}

    return {"base": base, "key": key, "model": model, "backup": backup}


def _chat(base: str, key: str, model: str, messages: list[dict], temperature: float = 0.1) -> str:
    resp = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=settings.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def smart_chat(cfg: dict, messages: list[dict], temperature: float = 0.1) -> str:
    """带兜底的调用：主服务商报错时自动切备用重试一次；备用也失败则抛出最后异常。"""
    backup = cfg.get("backup")
    try:
        return _chat(cfg["base"], cfg["key"], cfg["model"], messages, temperature)
    except Exception as e:  # noqa: BLE001 - 任何主服务商故障（超时/5xx/401）都值得试备用
        if not backup:
            raise
        logger.warning("主 LLM 调用失败（%s），切换备用 %s @ %s", e, backup["model"], backup["base"])
        return _chat(backup["base"], backup["key"], backup["model"], messages, temperature)


def test_llm(base: str, key: str, model: str) -> str:
    reply = _chat(base, key, model, [{"role": "user", "content": "请只回复两个字：正常"}], temperature=0)
    return reply.strip()[:50]
