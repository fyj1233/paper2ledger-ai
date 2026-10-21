from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(db: Session, user, action: str, detail: str = "") -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else "",
            action=action,
            detail=detail[:1000],
        )
    )
    db.commit()
