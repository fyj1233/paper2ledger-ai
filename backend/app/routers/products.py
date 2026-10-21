"""产品主数据管理：规格清单维护（登录可读，admin 写）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import log_action
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import LedgerEntry, Product, User

router = APIRouter(prefix="/api/products", tags=["产品管理"])


class ProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    spec: str = Field(default="", max_length=100)
    unit: str = Field(default="千件", max_length=20)
    category: str = Field(default="螺母", max_length=50)
    warn_stock: float | None = None
    is_active: bool = True


def _out(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "spec": p.spec,
        "unit": p.unit,
        "category": p.category,
        "warn_stock": p.warn_stock,
        "is_active": p.is_active,
        "created_at": p.created_at,
    }


def _dup(db: Session, name: str, spec: str, exclude_id: int | None = None) -> Product | None:
    query = db.query(Product).filter(Product.name == name, Product.spec == spec)
    if exclude_id:
        query = query.filter(Product.id != exclude_id)
    return query.first()


@router.get("")
def list_products(
    category: str | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(Product)
    if category:
        query = query.filter(Product.category == category)
    if active_only:
        query = query.filter(Product.is_active.is_(True))
    rows = query.order_by(Product.category, Product.name, Product.spec).all()
    return [_out(p) for p in rows]


@router.post("", status_code=201)
def create_product(
    body: ProductRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    name, spec = body.name.strip(), body.spec.strip()
    if not name:
        raise HTTPException(status_code=400, detail="品名不能为空")
    if _dup(db, name, spec):
        raise HTTPException(status_code=400, detail="同名同规格的产品已存在")
    product = Product(
        name=name,
        spec=spec,
        unit=body.unit.strip() or "千件",
        category=body.category.strip() or "螺母",
        warn_stock=body.warn_stock,
        is_active=body.is_active,
    )
    db.add(product)
    db.commit()
    log_action(db, admin, "新增产品", f"{product.name} {product.spec}")
    return _out(product)


@router.put("/{product_id}")
def update_product(
    product_id: int,
    body: ProductRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    name, spec = body.name.strip(), body.spec.strip()
    if not name:
        raise HTTPException(status_code=400, detail="品名不能为空")
    if (name, spec) != (product.name, product.spec) and _dup(db, name, spec, exclude_id=product.id):
        raise HTTPException(status_code=400, detail="同名同规格的产品已存在")
    product.name = name
    product.spec = spec
    product.unit = body.unit.strip() or "千件"
    product.category = body.category.strip() or "螺母"
    product.warn_stock = body.warn_stock
    product.is_active = body.is_active
    db.commit()
    log_action(db, admin, "修改产品", f"{product.name} {product.spec}")
    return _out(product)


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    used = db.query(LedgerEntry).filter(LedgerEntry.product_id == product.id).count()
    if used:
        raise HTTPException(status_code=400, detail=f"该产品已有 {used} 条台账记录，不能删除；可改为「停用」")
    db.delete(product)
    db.commit()
    log_action(db, admin, "删除产品", f"{product.name} {product.spec}")
    return {"message": "已删除"}
