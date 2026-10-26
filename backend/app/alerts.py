"""Alerts for officials and institutions. One open alert per (kind, application, audience); repeats update it."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .models import Alert


def raise_alert(db: Session, severity: str, kind: str, message: str, audience: str,
                application_id: str | None = None) -> Alert:
    kind, message = kind[:120], message[:400]
    existing = db.execute(select(Alert).where(Alert.kind == kind, Alert.audience == audience,
                                              Alert.application_id == application_id,
                                              Alert.resolved.is_(False))).scalar()
    if existing:
        existing.message, existing.severity = message, severity
        existing.created_at, existing.read_by = clock.now(), []
        return existing
    alert = Alert(severity=severity, kind=kind, message=message, audience=audience, application_id=application_id)
    db.add(alert)
    return alert


def resolve_alerts(db: Session, kind: str, application_id: str | None, audience: str | None = None) -> None:
    q = select(Alert).where(Alert.kind == kind, Alert.application_id == application_id, Alert.resolved.is_(False))
    if audience:
        q = q.where(Alert.audience == audience)
    for a in db.execute(q).scalars():
        a.resolved = True
