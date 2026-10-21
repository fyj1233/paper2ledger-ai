from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import log_action
from app.config import settings
from app.database import get_db
from app.deps import get_current_user, require_admin, require_manager
from app.models import Document, FinanceRecord, LedgerEntry, PendingEntry, Product, User
from app.schemas import DocumentDetailOut, DocumentOut
from app.services.extractor import process_document_task
from app.services.parsers import FORMAT_NAMES, SUPPORTED_EXTS

router = APIRouter(prefix="/api/documents", tags=["文档"])

ROLE_LABEL = {"admin": "管理员", "manager": "经理", "employee": "员工"}
TYPE_LABELS = {"production": "生产入库", "shipment": "出货", "scrap": "报废", "return": "退货", "initial": "期初"}


def _can_view(user: User, doc: Document) -> bool:
    return user.role in ("admin", "manager") or doc.uploader_id == user.id


def _item_out(entry: LedgerEntry, products: dict[int, Product]) -> dict:
    product = products.get(entry.product_id)
    return {
        "id": entry.id,
        "entry_date": entry.entry_date.isoformat(),
        "product_id": entry.product_id,
        "product_name": product.name if product else "（已删除）",
        "spec": product.spec if product else "",
        "unit": product.unit if product else "",
        "entry_type": entry.entry_type,
        "entry_type_label": TYPE_LABELS.get(entry.entry_type, entry.entry_type),
        "quantity": entry.quantity,
        "unit_price": entry.unit_price,
        "amount": entry.amount,
        "customer": entry.customer,
        "source": entry.source,
        "evidence": entry.evidence,
    }


def _pending_out(entry: PendingEntry) -> dict:
    return {
        "id": entry.id,
        "entry_date": entry.entry_date.isoformat(),
        "product_name": entry.product_name,
        "spec": entry.spec,
        "entry_type": entry.entry_type,
        "entry_type_label": TYPE_LABELS.get(entry.entry_type, entry.entry_type),
        "quantity": entry.quantity,
        "unit": entry.unit,
        "unit_price": entry.unit_price,
        "amount": entry.amount,
        "customer": entry.customer,
        "source": entry.source,
        "evidence": entry.evidence,
    }


def _doc_counts(db: Session, doc_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    """批量统计每个文档的台账条目数与待确认条目数。"""
    if not doc_ids:
        return {}, {}
    item_counts = dict(
        db.query(LedgerEntry.document_id, func.count())
        .filter(LedgerEntry.document_id.in_(doc_ids))
        .group_by(LedgerEntry.document_id)
        .all()
    )
    pending_counts = dict(
        db.query(PendingEntry.document_id, func.count())
        .filter(PendingEntry.document_id.in_(doc_ids))
        .group_by(PendingEntry.document_id)
        .all()
    )
    return item_counts, pending_counts


@router.get("", response_model=list[DocumentOut])
def list_documents(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Document)
    if user.role == "employee":
        query = query.filter(Document.uploader_id == user.id)
    if status:
        query = query.filter(Document.status == status)
    docs = query.order_by(Document.id.desc()).limit(500).all()

    doc_ids = [d.id for d in docs]
    item_counts, pending_counts = _doc_counts(db, doc_ids)

    result = []
    for doc in docs:
        uploader = db.query(User).filter(User.id == doc.uploader_id).first()
        record_count = (
            db.query(FinanceRecord).filter(FinanceRecord.document_id == doc.id).count()
        )
        result.append(
            DocumentOut(
                id=doc.id,
                filename=doc.filename,
                file_type=doc.file_type,
                size=doc.size,
                status=doc.status,
                error=doc.error,
                uploader=uploader.username if uploader else "",
                record_count=record_count,
                item_count=item_counts.get(doc.id, 0),
                pending_count=pending_counts.get(doc.id, 0),
                created_at=doc.created_at,
                parsed_at=doc.parsed_at,
            )
        )
    return result


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    original = Path(file.filename or "未命名").name
    ext = Path(original).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        supported = "、".join(f"{ext_} ({FORMAT_NAMES[ext_]})" for ext_ in sorted(SUPPORTED_EXTS))
        raise HTTPException(status_code=400, detail=f"不支持的文件格式，支持：{supported}")

    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = file.file.read(limit + 1)  # 只多读 1 字节用于判限，超大请求不会整份进内存
    if len(data) > limit:
        raise HTTPException(status_code=400, detail=f"文件大小不能超过 {settings.MAX_UPLOAD_MB}MB")

    doc = Document(
        uploader_id=user.id,
        filename=original,
        file_type=ext.lstrip("."),
        stored_path="",
        size=len(data),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    stored = settings.UPLOAD_DIR / f"doc_{doc.id}{ext}"
    stored.write_bytes(data)
    doc.stored_path = str(stored)
    db.commit()

    log_action(db, user, "上传文档", original)
    background_tasks.add_task(process_document_task, doc.id)
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        size=doc.size,
        status=doc.status,
        error=doc.error,
        uploader=user.username,
        record_count=0,
        created_at=doc.created_at,
        parsed_at=doc.parsed_at,
    )


@router.get("/{doc_id}", response_model=DocumentDetailOut)
def document_detail(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not _can_view(user, doc):
        raise HTTPException(status_code=404, detail="文档不存在")
    uploader = db.query(User).filter(User.id == doc.uploader_id).first()
    records = (
        db.query(FinanceRecord)
        .filter(FinanceRecord.document_id == doc.id)
        .order_by(FinanceRecord.biz_date, FinanceRecord.id)
        .all()
    )
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.document_id == doc.id)
        .order_by(LedgerEntry.entry_date, LedgerEntry.id)
        .all()
    )
    pending = (
        db.query(PendingEntry)
        .filter(PendingEntry.document_id == doc.id)
        .order_by(PendingEntry.entry_date, PendingEntry.id)
        .all()
    )
    product_ids = {e.product_id for e in entries}
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()} if product_ids else {}
    return DocumentDetailOut(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        size=doc.size,
        status=doc.status,
        error=doc.error,
        uploader=uploader.username if uploader else "",
        record_count=len(records),
        item_count=len(entries),
        pending_count=len(pending),
        created_at=doc.created_at,
        parsed_at=doc.parsed_at,
        raw_text=(doc.raw_text or "") if user.role in ("admin", "manager") else None,
        records=records,
        items=[_item_out(e, products) for e in entries],
        pending=[_pending_out(p) for p in pending],
    )


@router.post("/{doc_id}/reparse")
def reparse_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc.status = "pending"
    db.commit()
    log_action(db, user, "重新解析", doc.filename)
    background_tasks.add_task(process_document_task, doc.id, True)
    return {"message": "已加入解析队列"}


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.stored_path:
        Path(doc.stored_path).unlink(missing_ok=True)
    db.query(FinanceRecord).filter(FinanceRecord.document_id == doc.id).delete()
    db.query(LedgerEntry).filter(LedgerEntry.document_id == doc.id).delete()
    db.query(PendingEntry).filter(PendingEntry.document_id == doc.id).delete()
    db.delete(doc)
    db.commit()
    log_action(db, user, "删除文档", doc.filename)
    return {"message": "已删除"}


@router.get("/{doc_id}/download")
def download_document(
    doc_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not doc.stored_path or not Path(doc.stored_path).exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    log_action(db, _, "下载原始文档", doc.filename)
    return FileResponse(
        doc.stored_path,
        filename=doc.filename,
        media_type="application/octet-stream",
    )
