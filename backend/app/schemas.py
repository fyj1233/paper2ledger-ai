from datetime import date, datetime

import json

from pydantic import BaseModel, Field, field_validator


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=72)  # 72 字节是 bcrypt 上限，超出会抛异常


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    user: UserOut


# ---------- 用户管理 ----------
class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=72)
    role: str = Field(pattern="^(admin|manager|employee)$")


class UserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|manager|employee)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=72)


# ---------- 文档 ----------
class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    size: int
    status: str
    error: str | None = None
    uploader: str = ""
    record_count: int = 0
    item_count: int = 0  # 提取出的台账条目（已自动匹配入库）
    pending_count: int = 0  # 待确认条目（无法自动匹配产品）
    created_at: datetime
    parsed_at: datetime | None = None

    model_config = {"from_attributes": True}


class FinanceRecordOut(BaseModel):
    id: int
    biz_date: date
    revenue: float | None
    cost: float | None
    profit: float | None
    tx_count: int | None = None
    payments: dict | None = None
    category: str
    extraction_type: str
    source: str = "llm"
    confidence: float
    evidence: str | None

    model_config = {"from_attributes": True}

    @field_validator("payments", mode="before")
    @classmethod
    def _parse_payments(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return None
        return v


class DocumentDetailOut(DocumentOut):
    raw_text: str | None = None
    records: list[FinanceRecordOut] = []
    items: list[dict] = []  # 台账条目（已入库）
    pending: list[dict] = []  # 待确认条目


# ---------- 设置 ----------
class SettingsUpdateRequest(BaseModel):
    llm_api_base: str | None = None
    llm_api_key: str | None = None  # 传 None 表示不修改
    llm_model: str | None = None
    llm_backup_api_base: str | None = None
    llm_backup_api_key: str | None = None
    llm_backup_model: str | None = None
    auto_backup_enabled: bool | None = None
    auto_backup_time: str | None = None  # HH:MM；空串清除回默认
    monthly_target: str | float | None = None  # 数字或数字字符串；"" 清除；null 不修改


class SettingsOut(BaseModel):
    llm_api_base: str
    llm_api_key_set: bool
    llm_api_key_hint: str
    llm_model: str
    llm_configured: bool
    llm_backup_api_base: str = ""
    llm_backup_model: str = ""
    llm_backup_key_set: bool = False
    llm_backup_key_hint: str = ""
    llm_backup_configured: bool = False
    auto_backup_enabled: bool = False
    auto_backup_time: str = "23:30"
    monthly_target: float | None = None
