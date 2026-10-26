"""Rulebook versions: draft (maker), dry run, approval (checker), publish."""
import copy
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, clock
from ..alerts import raise_alert, resolve_alerts
from ..config import get_settings
from ..db import get_db
from ..jobs import enqueue
from ..models import Application, Document, Institution, InstitutionRecord, RulebookVersion, User, Verification
from ..pipeline import rules_engine
from ..pipeline.facts import build_facts
from ..pipeline.orchestrator import as_of_date, enqueue_precheck, published_rulebook
from ..security import OFFICIALS, require_roles
from .serializers import rulebook_json

router = APIRouter(prefix="/api/rulebook", tags=["rulebook"])


def _users(db) -> dict[int, str]:
    return {u.id: u.full_name for u in db.execute(select(User)).scalars()}


def _get(db, version_id: int) -> RulebookVersion:
    rb = db.get(RulebookVersion, version_id)
    if rb is None:
        raise HTTPException(404, "Rulebook version not found")
    return rb


@router.get("")
def versions(cycle: str | None = None, user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    cycle = cycle or get_settings().current_cycle
    published_rulebook(db, cycle)
    rows = db.execute(select(RulebookVersion).where(RulebookVersion.cycle == cycle)
                      .order_by(RulebookVersion.version.desc())).scalars().all()
    users = _users(db)
    return [rulebook_json(r, users, content=False) for r in rows]


@router.get("/{version_id}")
def version(version_id: int, user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    return rulebook_json(_get(db, version_id), _users(db))


class NewDraft(BaseModel):
    base_id: int
    change_note: str = ""


@router.post("")
def new_draft(body: NewDraft, user: User = Depends(require_roles("rule_admin")), db: Session = Depends(get_db)):
    base = _get(db, body.base_id)
    open_one = db.execute(select(RulebookVersion).where(RulebookVersion.cycle == base.cycle,
                                                        RulebookVersion.status.in_(["DRAFT", "PENDING_APPROVAL"]))).scalar()
    if open_one:
        raise HTTPException(409, f"Version {open_one.version} is already open as {open_one.status.lower().replace('_', ' ')}")
    n = db.execute(select(func.max(RulebookVersion.version)).where(RulebookVersion.cycle == base.cycle)).scalar() or 0
    rb = RulebookVersion(cycle=base.cycle, version=n + 1, status="DRAFT", content=copy.deepcopy(base.content),
                         change_note=body.change_note.strip(), created_by=user.id)
    db.add(rb)
    db.commit()
    audit.record("Rulebook draft created", "rulebook", rb.label, user=user, details={"based_on": base.label})
    return rulebook_json(rb, _users(db))


class ContentIn(BaseModel):
    content: dict
    change_note: str | None = None


@router.put("/{version_id}")
def save(version_id: int, body: ContentIn, user: User = Depends(require_roles("rule_admin")), db: Session = Depends(get_db)):
    rb = _get(db, version_id)
    if rb.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be edited")
    problems = rules_engine.validate_rulebook(body.content)
    if problems:
        raise HTTPException(422, {"message": "The rulebook has problems", "problems": problems})
    rb.content = body.content
    if body.change_note is not None:
        rb.change_note = body.change_note.strip()
    rb.dry_run = None
    db.commit()
    audit.record("Rulebook draft edited", "rulebook", rb.label, user=user, details={"rules": len(body.content.get("rules", []))})
    return rulebook_json(rb, _users(db))


@router.post("/{version_id}/dry-run")
def dry_run(version_id: int, user: User = Depends(require_roles("rule_admin", "senior_officer")), db: Session = Depends(get_db)):
    rb = _get(db, version_id)
    rb.dry_run = {"status": "running"}
    db.commit()
    enqueue("dry_run", version_id=rb.id)
    audit.record("Dry run started", "rulebook", rb.label, user=user)
    return {"queued": True}


@router.post("/{version_id}/submit")
def submit(version_id: int, user: User = Depends(require_roles("rule_admin")), db: Session = Depends(get_db)):
    rb = _get(db, version_id)
    if rb.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be sent for approval")
    problems = rules_engine.validate_rulebook(rb.content)
    if problems:
        raise HTTPException(422, {"message": "Fix the rulebook before sending it", "problems": problems})
    if not rb.change_note.strip():
        raise HTTPException(422, "Describe what changed before sending for approval")
    rb.status, rb.submitted_at = "PENDING_APPROVAL", clock.now()
    raise_alert(db, "info", f"rulebook_review:{rb.id}", f"Rulebook {rb.label} is waiting for checker approval.", "senior_officer")
    db.commit()
    audit.record("Rulebook sent for approval", "rulebook", rb.label, user=user, details={"note": rb.change_note})
    return rulebook_json(rb, _users(db))


class ReviewIn(BaseModel):
    approve: bool
    note: str = ""
    effective_from: date | None = None


@router.post("/{version_id}/review")
def review(version_id: int, body: ReviewIn, user: User = Depends(require_roles("senior_officer")), db: Session = Depends(get_db)):
    rb = _get(db, version_id)
    if rb.status != "PENDING_APPROVAL":
        raise HTTPException(409, "This version is not waiting for approval")
    if rb.created_by == user.id:
        raise HTTPException(403, "Maker-checker: the author of a rulebook version cannot approve it")
    rb.reviewed_by, rb.reviewed_at, rb.review_note = user.id, clock.now(), body.note.strip() or None
    resolve_alerts(db, f"rulebook_review:{rb.id}", None)
    if body.approve:
        for old in db.execute(select(RulebookVersion).where(RulebookVersion.cycle == rb.cycle,
                                                            RulebookVersion.status == "PUBLISHED")).scalars():
            old.status = "RETIRED"
        rb.status, rb.effective_from = "PUBLISHED", body.effective_from or clock.now().date()
        action = "Rulebook published"
    else:
        rb.status = "DRAFT"
        action = "Rulebook returned"
    db.commit()
    audit.record(action, "rulebook", rb.label, user=user, details={"note": body.note.strip()})
    if body.approve:
        apps = db.execute(select(Application.id).where(Application.cycle == rb.cycle, Application.status != "DECIDED")).scalars().all()
        for app_id in apps:
            enqueue_precheck(app_id, f"rulebook {rb.label} published")
    return rulebook_json(rb, _users(db))


class TryIn(BaseModel):
    application_id: str


@router.post("/{version_id}/test")
def try_on(version_id: int, body: TryIn, user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    rb = _get(db, version_id)
    problems = rules_engine.validate_rulebook(rb.content)
    if problems:
        raise HTTPException(422, {"message": "The rulebook has problems", "problems": problems})
    app = db.get(Application, body.application_id.strip().upper())
    if app is None or app.status == "DRAFT":
        raise HTTPException(404, "No submitted application with that ID")
    inst = db.get(Institution, app.institution_id)
    record = db.execute(select(InstitutionRecord).where(InstitutionRecord.institution_id == inst.id)).scalar()
    docs = db.execute(select(Document).where(Document.application_id == app.id, Document.superseded.is_(False))).scalars().all()
    verifs = {v.document_id: v for v in db.execute(select(Verification).where(Verification.run_id == app.last_run_id)).scalars()
              if v.document_id}
    facts, _, scopes = build_facts(app, inst, record, docs, verifs, rb.content.get("settings", {}), as_of_date(app))
    matches = rules_engine.evaluate(rb.content, facts, scopes)
    return {"application_id": app.id, "institution": inst.name, "matches": [
        {"rule_id": m.rule_id, "row": m.row, "severity": m.severity, "category": m.category, "title": m.title,
         "message": m.message, "facts": {k: rules_engine.display(v) if v is not None else None for k, v in m.facts_used.items()}}
        for m in matches]}
