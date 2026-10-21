"""提取模板管理：对固定格式文档用关键词+字段正则直接提取，省 LLM 成本。"""

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import require_admin
from app.models import ExtractTemplate, User
from app.services.extractors.template import render_test

router = APIRouter(prefix="/api/templates", tags=["提取模板"])

ALLOWED_FIELDS = {
    "date",
    "product_name",
    "spec",
    "entry_type",
    "quantity",
    "unit",
    "unit_price",
    "amount",
    "customer",
}


class TemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    keywords: list[str] = Field(min_length=1)
    fields: dict[str, list[str]] = {}
    category: str = "默认"
    is_active: bool = True


class TemplateTestRequest(BaseModel):
    text: str = Field(min_length=1)
    template_id: int | None = None


def _validate(body: TemplateRequest) -> tuple[str, str]:
    if len(body.keywords) > 20:
        raise HTTPException(status_code=400, detail="关键词最多 20 个")
    clean_fields = {}
    for field, patterns in body.fields.items():
        if field not in ALLOWED_FIELDS:
            raise HTTPException(status_code=400, detail=f"不支持的字段：{field}")
        if not isinstance(patterns, list) or len(patterns) > 10:
            raise HTTPException(status_code=400, detail=f"字段 {field} 的正则最多 10 条")
        for p in patterns:
            try:
                re.compile(p)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"字段 {field} 的正则不合法：{p}（{e}）")
        clean_fields[field] = [p for p in patterns if p]
    if not clean_fields.get("quantity") or not (clean_fields.get("product_name") or clean_fields.get("spec")):
        raise HTTPException(status_code=400, detail="至少要给 quantity 和 product_name/spec 中的一个配正则")
    return json.dumps(body.keywords, ensure_ascii=False), json.dumps(clean_fields, ensure_ascii=False)


@router.get("")
def list_templates(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(ExtractTemplate).order_by(ExtractTemplate.id.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "keywords": json.loads(r.keywords or "[]"),
            "fields": json.loads(r.fields or "{}"),
            "category": r.category,
            "is_active": r.is_active,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("", status_code=201)
def create_template(
    body: TemplateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(ExtractTemplate).filter(ExtractTemplate.name == body.name).first():
        raise HTTPException(status_code=400, detail="模板名称已存在")
    keywords, fields = _validate(body)
    tpl = ExtractTemplate(
        name=body.name,
        keywords=keywords,
        fields=fields,
        category=body.category or "默认",
        is_active=body.is_active,
    )
    db.add(tpl)
    db.commit()
    log_action(db, admin, "创建提取模板", body.name)
    return {"id": tpl.id, "message": "已创建"}


@router.put("/{template_id}")
def update_template(
    template_id: int,
    body: TemplateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    tpl = db.query(ExtractTemplate).filter(ExtractTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    dup = (
        db.query(ExtractTemplate)
        .filter(ExtractTemplate.name == body.name, ExtractTemplate.id != template_id)
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail="模板名称已存在")
    keywords, fields = _validate(body)
    tpl.name = body.name
    tpl.keywords = keywords
    tpl.fields = fields
    tpl.category = body.category or "默认"
    tpl.is_active = body.is_active
    db.commit()
    log_action(db, admin, "更新提取模板", body.name)
    return {"message": "已保存"}


@router.delete("/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    tpl = db.query(ExtractTemplate).filter(ExtractTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(tpl)
    db.commit()
    log_action(db, admin, "删除提取模板", tpl.name)
    return {"message": "已删除"}


@router.post("/test")
def test_template(
    body: TemplateTestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    name, items = render_test(db, body.text, body.template_id)
    if not name:
        return {"matched": False, "message": "没有模板命中（或未提取到规格条目）"}
    return {"matched": True, "template_name": name, "items": items}
