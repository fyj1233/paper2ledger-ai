from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import log_action
from app.config import settings as env_settings
from app.database import get_db
from app.deps import require_admin, require_manager
from app.models import Setting, User
from app.schemas import SettingsOut, SettingsUpdateRequest
from app.services.auto_backup import DEFAULT_TIME, parse_hhmm
from app.services.llm import DEFAULT_BASE, LLM_KEYS, get_effective_llm_config, test_llm  # noqa: F401

router = APIRouter(prefix="/api/settings", tags=["系统设置"])


def _get_setting(db: Session, key: str) -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return (row.value if row else "") or ""


def _set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    base = _get_setting(db, "llm_api_base") or env_settings.LLM_API_BASE
    key = _get_setting(db, "llm_api_key") or env_settings.LLM_API_KEY
    model = _get_setting(db, "llm_model") or env_settings.LLM_MODEL
    configured = bool(key and model)

    b_base = _get_setting(db, "llm_backup_api_base") or env_settings.LLM_BACKUP_API_BASE
    b_key = _get_setting(db, "llm_backup_api_key") or env_settings.LLM_BACKUP_API_KEY
    b_model = _get_setting(db, "llm_backup_model") or env_settings.LLM_BACKUP_MODEL

    monthly_target = None
    raw = _get_setting(db, "monthly_target")
    try:
        monthly_target = float(raw) if raw else None
    except ValueError:
        monthly_target = None
    return SettingsOut(
        llm_api_base=base,
        llm_api_key_set=bool(key),
        llm_api_key_hint=(f"****{key[-4:]}" if len(key) > 4 else "已配置"),
        llm_model=model,
        llm_configured=configured,
        llm_backup_api_base=b_base,
        llm_backup_model=b_model,
        llm_backup_key_set=bool(b_key),
        llm_backup_key_hint=(f"****{b_key[-4:]}" if len(b_key) > 4 else "已配置"),
        llm_backup_configured=bool(b_key and b_model),
        auto_backup_enabled=_get_setting(db, "auto_backup_enabled") == "1",
        auto_backup_time=_get_setting(db, "auto_backup_time") or DEFAULT_TIME,
        monthly_target=monthly_target,
    )


@router.put("")
def update_settings(
    body: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if body.llm_api_base is not None:
        _set_setting(db, "llm_api_base", body.llm_api_base.strip())
    if body.llm_api_key is not None:
        # 空字符串表示清除已保存的 Key，null 表示不修改
        _set_setting(db, "llm_api_key", body.llm_api_key.strip())
    if body.llm_model is not None:
        _set_setting(db, "llm_model", body.llm_model.strip())
    if body.llm_backup_api_base is not None:
        _set_setting(db, "llm_backup_api_base", body.llm_backup_api_base.strip())
    if body.llm_backup_api_key is not None:
        _set_setting(db, "llm_backup_api_key", body.llm_backup_api_key.strip())
    if body.llm_backup_model is not None:
        _set_setting(db, "llm_backup_model", body.llm_backup_model.strip())
    if body.auto_backup_enabled is not None:
        _set_setting(db, "auto_backup_enabled", "1" if body.auto_backup_enabled else "0")
    if body.auto_backup_time is not None:
        raw = str(body.auto_backup_time).strip()
        if raw and parse_hhmm(raw) is None:
            raise HTTPException(status_code=400, detail="自动备份时间格式应为 HH:MM（如 23:30）")
        _set_setting(db, "auto_backup_time", raw)
    if body.monthly_target is not None:
        # 空字符串表示清除目标；必须是数字
        raw = str(body.monthly_target).strip()
        if raw:
            try:
                float(raw)
            except ValueError:
                raise HTTPException(status_code=400, detail="月度目标必须是数字")
        _set_setting(db, "monthly_target", raw)
    db.commit()
    log_action(db, admin, "更新系统设置", "LLM API 配置")
    return get_settings(db=db, _=admin)


@router.post("/test-llm")
def test_llm_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    cfg = get_effective_llm_config(db)
    if not cfg:
        raise HTTPException(status_code=400, detail="请先填写 API Key 和模型名称")
    try:
        reply = test_llm(cfg["base"], cfg["key"], cfg["model"])
        return {"ok": True, "message": f"连接成功，模型返回：{reply}"}
    except Exception as e:  # noqa: BLE001 - 把失败原因反馈给管理员
        return {"ok": False, "message": f"连接失败：{e}"}


@router.post("/test-llm-backup")
def test_llm_backup_config(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    cfg = get_effective_llm_config(db)
    backup = (cfg or {}).get("backup")
    if not backup:
        raise HTTPException(status_code=400, detail="请先填写备用 API Key 和备用模型名称")
    try:
        reply = test_llm(backup["base"], backup["key"], backup["model"])
        return {"ok": True, "message": f"备用连接成功，模型返回：{reply}"}
    except Exception as e:  # noqa: BLE001 - 把失败原因反馈给管理员
        return {"ok": False, "message": f"备用连接失败：{e}"}


@router.get("/system-info")
def system_info(db: Session = Depends(get_db), _: User = Depends(require_manager)):
    cfg = get_effective_llm_config(db)
    return {
        "llm_configured": cfg is not None,
        "llm_base": (cfg or {}).get("base") or DEFAULT_BASE,
        "llm_model": (cfg or {}).get("model") or "",
        "llm_backup_configured": bool((cfg or {}).get("backup")),
    }
