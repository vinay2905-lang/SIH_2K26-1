"""Append-only, hash-chained audit trail.

Every event stores the SHA-256 of (previous hash + canonical event body). Editing or deleting any past
event breaks the chain, which `verify_chain` detects.
"""
import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

try:
    import fcntl
except ImportError:  # Windows: single-process SQLite only
    fcntl = None

from . import clock
from .config import get_settings
from .db import SessionLocal, is_postgres
from .models import AuditEvent, User

GENESIS = "0" * 64
_local_lock = threading.Lock()


@contextmanager
def _process_lock():
    """Cross-process lock for SQLite deployments (PostgreSQL uses an advisory lock instead)."""
    if is_postgres() or fcntl is None:
        yield
        return
    path = get_settings().data_dir / "audit.lock"
    with open(path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _canonical(prev_hash: str, ts: datetime, actor: str, actor_type: str, action: str, object_type: str,
               object_id: str, application_id: str | None, details: dict) -> str:
    body = {
        "prev": prev_hash,
        "ts": ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "actor": actor,
        "actor_type": actor_type,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "application_id": application_id,
        "details": details,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(ev: AuditEvent) -> str:
    ts = ev.ts if ev.ts.tzinfo else ev.ts.replace(tzinfo=timezone.utc)
    payload = _canonical(ev.prev_hash, ts, ev.actor, ev.actor_type, ev.action, ev.object_type, ev.object_id,
                         ev.application_id, ev.details or {})
    return hashlib.sha256(payload.encode()).hexdigest()


def actor_label(user: User | None) -> tuple[str, str]:
    if user is None:
        return "PRAMAAN", "SYSTEM"
    return f"{user.full_name} ({user.role})", "USER"


def record(action: str, object_type: str, object_id: str, *, user: User | None = None, actor: str | None = None,
           actor_type: str | None = None, application_id: str | None = None, details: dict | None = None) -> AuditEvent:
    """Append one event in its own transaction, serialised so the chain never forks."""
    if actor is None:
        actor, default_type = actor_label(user)
        actor_type = actor_type or default_type
    actor_type = actor_type or "SYSTEM"
    details = json.loads(json.dumps(details or {}, default=str))
    actor, action, object_type, object_id = actor[:120], action[:80], object_type[:40], str(object_id)[:80]
    with _local_lock, _process_lock():
        db = SessionLocal()
        try:
            if is_postgres():
                db.execute(text("SELECT pg_advisory_xact_lock(424242)"))
            last = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar()
            ev = AuditEvent(ts=clock.now(), actor=actor, actor_type=actor_type, action=action,
                            object_type=object_type, object_id=str(object_id), application_id=application_id,
                            details=details, prev_hash=last or GENESIS, hash="")
            ev.hash = compute_hash(ev)
            db.add(ev)
            db.commit()
            return ev
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for ev in db.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars():
        count += 1
        if ev.prev_hash != prev or compute_hash(ev) != ev.hash:
            return {"valid": False, "events": count, "broken_at": ev.id,
                    "reason": "previous-hash link broken" if ev.prev_hash != prev else "event content changed"}
        prev = ev.hash
    return {"valid": True, "events": count, "head": prev}
