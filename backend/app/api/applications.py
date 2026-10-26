"""Applications, documents, findings, deficiency letters and decisions."""
import hashlib
import re
import uuid
from collections import Counter
from functools import lru_cache

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, clock
from ..alerts import raise_alert, resolve_alerts
from ..config import get_settings
from ..db import get_db
from ..jobs import enqueue
from ..models import (Application, AuditEvent, Document, Finding, InstitutionRecord, Job, Letter,
                      PrecheckRun, User, Verification)
from ..pipeline.ingest import render_page, sniff_kind
from ..pipeline.orchestrator import enqueue_precheck, published_rulebook
from ..pipeline.templates import DOC_TYPES
from ..security import OFFICIALS, current_user, get_application_for, require_roles
from ..storage import store
from .serializers import (APP_TYPES, app_summary, audit_json, document_json, finding_json, institution_json, iso,
                          letter_json, record_json, verification_json)

router = APIRouter(prefix="/api", tags=["applications"])
EDITABLE = ("DRAFT", "DEFICIENCY_ISSUED")
DECISIONS = {"APPROVED": "Approved", "APPROVED_WITH_CONDITIONS": "Approved with conditions",
             "INSPECTION_ORDERED": "Physical inspection ordered", "NOT_APPROVED": "Not approved"}


def _users(db: Session) -> dict[int, str]:
    return {u.id: u.full_name for u in db.execute(select(User)).scalars()}


def _load(user: User, app_id: str, db: Session) -> Application:
    app = get_application_for(user, app_id, db)
    if user.role in OFFICIALS and app.status == "DRAFT":
        raise HTTPException(404, "Application not found")
    return app


def current_findings(db: Session, app: Application, institution_view: bool) -> list[Finding]:
    if app.last_run_id is None:
        return []
    q = select(Finding).where(Finding.application_id == app.id, Finding.status.notin_(["SUPERSEDED", "RESOLVED"]))
    if institution_view:
        q = q.where(Finding.visible_to_institution.is_(True))
    order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
    return sorted(db.execute(q).scalars().all(), key=lambda f: (order.get(f.severity, 9), f.id))


def finding_counts(findings: list[Finding]) -> dict:
    live = [f for f in findings if f.status in ("OPEN", "ACCEPTED")]
    c = Counter(f.severity for f in live)
    return {"critical": c.get("critical", 0), "high": c.get("high", 0), "warning": c.get("warning", 0),
            "info": c.get("info", 0), "open": sum(1 for f in findings if f.status == "OPEN"), "total": len(findings)}


def is_processing(db: Session, app: Application) -> bool:
    busy = db.execute(select(Document.id).where(Document.application_id == app.id, Document.superseded.is_(False),
                                                Document.status.in_(["UPLOADED", "PROCESSING"]))).first()
    if busy:
        return True
    jobs = db.execute(select(Job).where(Job.status.in_(["QUEUED", "RUNNING"]), Job.kind == "run_precheck")).scalars()
    return any(j.payload.get("application_id") == app.id for j in jobs)


# ------------------------------------------------------------------ list --
@router.get("/applications")
def list_applications(status: str | None = None, q: str | None = None, sort: str = "risk",
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Application)
    if user.role == "institution":
        query = query.where(Application.institution_id == user.institution_id)
    else:
        query = query.where(Application.status != "DRAFT")
    if status:
        query = query.where(Application.status.in_(status.split(",")))
    apps = db.execute(query).scalars().all()
    if q:
        needle = q.lower()
        apps = [a for a in apps if needle in a.id.lower() or needle in a.institution.name.lower()
                or needle in a.institution.city.lower()]
    out = []
    for a in apps:
        out.append(app_summary(a, finding_counts(current_findings(db, a, user.role == "institution"))))
    if sort == "risk":
        out.sort(key=lambda a: (-a["risk_score"], a["submitted_at"] or ""))
    else:
        out.sort(key=lambda a: a["submitted_at"] or a["created_at"] or "", reverse=True)
    return out


class NewApplication(BaseModel):
    app_type: str


@router.post("/applications")
def create_application(body: NewApplication, user: User = Depends(require_roles("institution")),
                       db: Session = Depends(get_db)):
    if body.app_type not in APP_TYPES:
        raise HTTPException(422, "Unknown application type")
    cycle = get_settings().current_cycle
    if db.execute(select(Application).where(Application.institution_id == user.institution_id,
                                            Application.cycle == cycle, Application.app_type == body.app_type,
                                            Application.status != "DECIDED")).scalar():
        raise HTTPException(409, "You already have an open application of this type for this cycle")
    record = db.execute(select(InstitutionRecord).where(InstitutionRecord.institution_id == user.institution_id)).scalar()
    programmes = [{"name": p["programme"], "level": p.get("level", "UG"), "intake_requested": p["approved_intake"]}
                  for p in (record.programmes if record else [])]
    year = cycle[:4]
    last = db.execute(select(func.max(Application.id)).where(Application.id.like(f"APP-{year}-%"))).scalar()
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    app = Application(id=f"APP-{year}-{seq:05d}", institution_id=user.institution_id, app_type=body.app_type, cycle=cycle,
                      status="DRAFT", form={"programmes": programmes, "fire_noc_valid_till": "", "built_up_area_m2": "",
                                            "computer_count": "", "land_area_acres": ""})
    db.add(app)
    db.commit()
    audit.record("Application created", "application", app.id, user=user, application_id=app.id,
                 details={"type": APP_TYPES[body.app_type], "cycle": cycle})
    return app_summary(app, {})


# ---------------------------------------------------------------- detail --
def _checklist(db: Session, app: Application, docs: list[Document], verifs: dict) -> list[dict]:
    rb = published_rulebook(db, app.cycle)
    items = []
    for item in rb.content.get("checklists", {}).get(app.app_type, []):
        mine = [d for d in docs if d.slot == item["doc_type"]]
        latest = max(mine, key=lambda d: d.uploaded_at, default=None)
        if latest is None:
            state = "MISSING" if item.get("required") else "OPTIONAL"
        elif latest.status in ("UPLOADED", "PROCESSING"):
            state = "PROCESSING"
        elif latest.status == "FAILED":
            state = "UNREADABLE"
        elif item["doc_type"] == "LAB_PHOTO":
            state = "UPLOADED" if len(mine) >= int(item.get("min_count", 1)) else "INCOMPLETE"
        else:
            v = verifs.get(latest.id)
            state = v.status if v else "UPLOADED"
        items.append({"doc_type": item["doc_type"], "label": DOC_TYPES.get(item["doc_type"], item["doc_type"]),
                      "required": bool(item.get("required")), "min_count": int(item.get("min_count", 1)),
                      "uploaded": len(mine), "document_ids": [d.id for d in mine], "state": state,
                      "note": verifs[latest.id].note if latest is not None and latest.id in verifs else None})
    return items


def application_detail(db: Session, app: Application, user: User) -> dict:
    institution_view = user.role == "institution"
    users = _users(db)
    docs = db.execute(select(Document).where(Document.application_id == app.id, Document.superseded.is_(False))
                      .order_by(Document.uploaded_at)).scalars().all()
    verifs = {}
    if app.last_run_id:
        for v in db.execute(select(Verification).where(Verification.run_id == app.last_run_id)).scalars():
            if v.document_id:
                verifs[v.document_id] = v
    findings = current_findings(db, app, institution_view)
    letters = db.execute(select(Letter).where(Letter.application_id == app.id).order_by(Letter.created_at)).scalars().all()
    if institution_view:
        letters = [l for l in letters if l.status in ("ISSUED", "RESPONDED")]
    run = db.get(PrecheckRun, app.last_run_id) if app.last_run_id else None
    record = db.execute(select(InstitutionRecord).where(InstitutionRecord.institution_id == app.institution_id)).scalar()
    unreviewed = [f for f in findings if f.status == "OPEN" and f.severity in ("critical", "high")]
    out = {
        "application": app_summary(app, finding_counts(findings)),
        "institution": institution_json(app.institution),
        "form": app.form,
        "checklist": _checklist(db, app, docs, verifs),
        "documents": [document_json(d, not institution_view) for d in docs],
        "findings": [finding_json(f, users) for f in findings],
        "verifications": [verification_json(v) for v in verifs.values()],
        "letters": [letter_json(l, users) for l in letters],
        "processing": is_processing(db, app),
        "run": {"id": run.id, "trigger": run.trigger, "started_at": iso(run.started_at), "finished_at": iso(run.finished_at),
                "stats": run.stats, "rulebook": run.rulebook_version} if run else None,
        "permissions": {
            "edit": institution_view and app.status in EDITABLE,
            "submit": institution_view and app.status == "DRAFT",
            "respond": institution_view and app.status == "DEFICIENCY_ISSUED",
            "review": user.role in ("scrutinizer", "senior_officer") and app.status != "DECIDED",
            "draft_letter": user.role == "scrutinizer" and app.status in ("UNDER_SCRUTINY", "RESPONDED"),
            "decide": user.role == "senior_officer" and app.status in ("UNDER_SCRUTINY", "RESPONDED"),
        },
        "unreviewed_blocking": len(unreviewed),
        "decisions": DECISIONS,
    }
    if not institution_view:
        out["record"] = record_json(record)
        out["assigned_to_name"] = users.get(app.assigned_to) if app.assigned_to else None
    return out


@router.get("/applications/{app_id}")
def get_application(app_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return application_detail(db, _load(user, app_id, db), user)


@router.get("/applications/{app_id}/report")
def report(app_id: str, user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    detail = application_detail(db, app, user)
    detail["generated_at"] = clock.now().isoformat()
    detail["verification_summary"] = dict(Counter(v["status"] for v in detail["verifications"]))
    detail["timeline"] = [audit_json(e) for e in db.execute(select(AuditEvent).where(AuditEvent.application_id == app.id)
                                                            .order_by(AuditEvent.id)).scalars()][-40:]
    return detail


class FormIn(BaseModel):
    form: dict


@router.put("/applications/{app_id}/form")
def update_form(app_id: str, body: FormIn, user: User = Depends(require_roles("institution")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    if app.status not in EDITABLE:
        raise HTTPException(409, "The form can only be changed while the application is a draft or answering a deficiency letter")
    form = dict(body.form)
    programmes = []
    for p in form.get("programmes", []) or []:
        name = str(p.get("name", "")).strip()[:120]
        if not name:
            continue
        try:
            intake = int(p.get("intake_requested") or 0)
        except (TypeError, ValueError):
            raise HTTPException(422, f"Intake for {name} must be a whole number")
        if intake < 0 or intake > 600:
            raise HTTPException(422, f"Intake for {name} must be between 0 and 600")
        programmes.append({"name": name, "level": str(p.get("level", "UG"))[:10], "intake_requested": intake})
    clean = {"programmes": programmes}
    for key in ("fire_noc_valid_till", "built_up_area_m2", "computer_count", "land_area_acres", "principal_name",
                "contact_email"):
        v = form.get(key, "")
        if key == "fire_noc_valid_till" and v and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            raise HTTPException(422, "Fire NOC validity must be a date (YYYY-MM-DD)")
        if key in ("built_up_area_m2", "computer_count", "land_area_acres") and v not in ("", None):
            try:
                v = float(v) if key == "land_area_acres" else int(float(v))
            except (TypeError, ValueError):
                raise HTTPException(422, f"{key.replace('_', ' ')} must be a number")
        clean[key] = v if v is not None else ""
    app.form = clean
    db.commit()
    audit.record("Form updated", "application", app.id, user=user, application_id=app.id,
                 details={"programmes": len(programmes)})
    enqueue_precheck(app.id, "form updated")
    return application_detail(db, app, user)


@router.post("/applications/{app_id}/precheck")
def run_precheck(app_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    if user.role not in ("institution", "scrutinizer", "senior_officer"):
        raise HTTPException(403, "Your role cannot start a pre-check")
    enqueue_precheck(app.id, f"requested by {user.role}")
    return {"queued": True}


@router.post("/applications/{app_id}/submit")
def submit(app_id: str, user: User = Depends(require_roles("institution")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    if app.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be submitted")
    if not db.execute(select(Document.id).where(Document.application_id == app.id, Document.superseded.is_(False))).first():
        raise HTTPException(409, "Upload the required documents before submitting")
    if not any(p.get("intake_requested") for p in app.form.get("programmes", [])):
        raise HTTPException(409, "Fill in at least one programme with its intake before submitting")
    app.status, app.submitted_at = "UNDER_SCRUTINY", clock.now()
    db.commit()
    audit.record("Application submitted", "application", app.id, user=user, application_id=app.id)
    resolve_alerts(db, "draft_issues", app.id)
    db.commit()
    enqueue_precheck(app.id, "submitted")
    return application_detail(db, app, user)


@router.post("/applications/{app_id}/assign")
def assign(app_id: str, user: User = Depends(require_roles("scrutinizer")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    app.assigned_to = user.id
    db.commit()
    audit.record("Assigned to scrutinizer", "application", app.id, user=user, application_id=app.id)
    return {"assigned_to": user.full_name}


class DecisionIn(BaseModel):
    decision: str
    note: str = ""
    confirm: bool = False


@router.post("/applications/{app_id}/decision")
def decide(app_id: str, body: DecisionIn, user: User = Depends(require_roles("senior_officer")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    if body.decision not in DECISIONS:
        raise HTTPException(422, "Unknown decision")
    if app.status not in ("UNDER_SCRUTINY", "RESPONDED"):
        raise HTTPException(409, "A decision can be recorded only while the application is under scrutiny")
    if not body.confirm:
        raise HTTPException(422, "Confirm that you have reviewed the evidence yourself")
    open_blocking = [f for f in current_findings(db, app, False) if f.status == "OPEN" and f.severity in ("critical", "high")]
    if open_blocking and body.decision in ("APPROVED", "APPROVED_WITH_CONDITIONS"):
        raise HTTPException(409, f"{len(open_blocking)} critical/high finding(s) are still unreviewed. Accept or override "
                                 "each one before approving.")
    if body.decision == "NOT_APPROVED" and len(body.note.strip()) < 20:
        raise HTTPException(422, "An adverse decision needs a written reason (at least 20 characters)")
    app.status = "DECIDED"
    app.decision = {"decision": body.decision, "label": DECISIONS[body.decision], "note": body.note.strip(),
                    "by": user.full_name, "at": clock.now().isoformat()}
    db.commit()
    audit.record("Decision recorded", "application", app.id, user=user, application_id=app.id,
                 details={"decision": DECISIONS[body.decision], "note": body.note.strip()})
    raise_alert(db, "info", "decision", f"A decision has been recorded on {app.id}: {DECISIONS[body.decision]}.",
                f"institution:{app.institution_id}", app.id)
    resolve_alerts(db, "critical_findings", app.id)
    db.commit()
    return application_detail(db, app, user)


# ------------------------------------------------------------- documents --
SAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]+")


def _save_upload(db: Session, app: Application, user: User, slot: str, filename: str, data: bytes) -> Document:
    if app.status not in EDITABLE:
        raise HTTPException(409, "Documents can only be uploaded to a draft or in reply to a deficiency letter")
    if slot not in DOC_TYPES:
        raise HTTPException(422, "Unknown document type")
    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    kind = sniff_kind(data)
    if kind is None:
        raise HTTPException(415, "Only PDF, JPEG and PNG files are accepted")
    if slot == "LAB_PHOTO" and kind != "image":
        raise HTTPException(415, "Upload photographs as JPEG or PNG")
    mime = "application/pdf" if kind == "pdf" else ("image/png" if data[:4] == b"\x89PNG" else "image/jpeg")
    name = SAFE_NAME.sub("_", (filename or "document").rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:120] or "document"
    if slot != "LAB_PHOTO":
        for old in db.execute(select(Document).where(Document.application_id == app.id, Document.slot == slot,
                                                     Document.superseded.is_(False))).scalars():
            old.superseded = True
    doc = Document(id=f"DOC-{uuid.uuid4().hex[:12]}", application_id=app.id, slot=slot, filename=name, mime=mime,
                   size=len(data), sha256=hashlib.sha256(data).hexdigest(), storage_key=store().put(data),
                   uploaded_by=user.id, status="UPLOADED")
    db.add(doc)
    db.commit()
    audit.record("Document uploaded", "document", doc.id, user=user, application_id=app.id,
                 details={"file": name, "slot": DOC_TYPES[slot], "bytes": len(data), "sha256": doc.sha256})
    enqueue("process_document", document_id=doc.id)
    return doc


@router.post("/applications/{app_id}/documents")
async def upload(app_id: str, slot: str = Form(...), file: UploadFile = File(...),
                 user: User = Depends(require_roles("institution")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    return document_json(_save_upload(db, app, user, slot, file.filename or "document", data), False)


def _samples_dir(user: User):
    return get_settings().data_dir / "samples" / (user.institution_id or "_")


@router.get("/samples")
def samples(user: User = Depends(require_roles("institution"))):
    """Synthetic sample files for the signed-in institution (sandbox demo convenience)."""
    root = _samples_dir(user)
    out = []
    if root.exists():
        for slot_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for f in sorted(slot_dir.iterdir()):
                out.append({"slot": slot_dir.name, "filename": f.name, "size": f.stat().st_size})
    return out


class SampleIn(BaseModel):
    slot: str
    filename: str


@router.post("/applications/{app_id}/documents/sample")
def upload_sample(app_id: str, body: SampleIn, user: User = Depends(require_roles("institution")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    root = _samples_dir(user).resolve()
    path = (root / body.slot / body.filename).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Sample not found")
    return document_json(_save_upload(db, app, user, body.slot, body.filename, path.read_bytes()), False)


@router.delete("/documents/{doc_id}")
def remove_document(doc_id: str, user: User = Depends(require_roles("institution")), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    app = _load(user, doc.application_id, db)
    if app.status not in EDITABLE:
        raise HTTPException(409, "Documents can no longer be removed")
    doc.superseded = True
    db.commit()
    audit.record("Document removed", "document", doc.id, user=user, application_id=app.id, details={"file": doc.filename})
    enqueue_precheck(app.id, "document removed")
    return {"removed": doc_id}


def _doc_for(user: User, doc_id: str, db: Session) -> tuple[Document, Application]:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc, _load(user, doc.application_id, db)


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, _ = _doc_for(user, doc_id, db)
    return document_json(doc, user.role in OFFICIALS)


@lru_cache(maxsize=64)
def _page_png(storage_key: str, page: int, dpi: int) -> bytes:
    return render_page(store().get(storage_key), page, dpi)


@router.get("/documents/{doc_id}/pages/{page}")
def page_image(doc_id: str, page: int, dpi: int = Query(110, ge=50, le=200), user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    doc, _ = _doc_for(user, doc_id, db)
    try:
        png = _page_png(doc.storage_key, page, dpi)
    except IndexError:
        raise HTTPException(404, "No such page")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=600"})


@router.get("/documents/{doc_id}/file")
def download(doc_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc, app = _doc_for(user, doc_id, db)
    audit.record("Document downloaded", "document", doc.id, user=user, application_id=app.id, details={"file": doc.filename})
    return Response(store().get(doc.storage_key), media_type=doc.mime,
                    headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'})


# -------------------------------------------------------------- findings --
class FindingDecision(BaseModel):
    action: str
    note: str = ""


@router.post("/findings/{finding_id}/decision")
def decide_finding(finding_id: int, body: FindingDecision, user: User = Depends(require_roles("scrutinizer", "senior_officer")),
                   db: Session = Depends(get_db)):
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    app = _load(user, f.application_id, db)
    if app.status == "DECIDED":
        raise HTTPException(409, "The application has been decided")
    if f.status in ("SUPERSEDED", "RESOLVED"):
        raise HTTPException(409, "This finding is from an older pre-check")
    if body.action == "accept":
        f.status = "ACCEPTED"
    elif body.action == "override":
        if len(body.note.strip()) < 10:
            raise HTTPException(422, "Give a reason (at least 10 characters) when you override a finding")
        f.status = "OVERRIDDEN"
    elif body.action == "reopen":
        f.status = "OPEN"
    else:
        raise HTTPException(422, "action must be accept, override or reopen")
    f.decision_by, f.decision_note, f.decided_at = user.id, body.note.strip() or None, clock.now()
    from ..pipeline.orchestrator import score
    app.risk_score, app.overall_status = score(current_findings(db, app, False))
    db.commit()
    audit.record({"accept": "Finding accepted", "override": "Finding overridden", "reopen": "Finding reopened"}[body.action],
                 "finding", f"F-{f.id:04d}", user=user, application_id=app.id,
                 details={"title": f.title, "note": body.note.strip()})
    return finding_json(f, _users(db))


# --------------------------------------------------------------- letters --
class LetterIn(BaseModel):
    finding_ids: list[int] = Field(default_factory=list)
    note: str = ""


def _letter_item(f: Finding) -> dict:
    label = DOC_TYPES.get(f.doc_type or "", "document")
    if f.preliminary:
        # forensic indicators are not conclusive, so the letter asks for proof instead of alleging tampering
        return {"finding_id": f.id, "title": f"Verification of {label}",
                "text": f"Submit the original or an issuer-certified copy of the {label.lower()} for verification."}
    return {"finding_id": f.id, "title": f.title, "text": f"{f.title}. {f.message}"}


@router.post("/applications/{app_id}/letters")
def draft_letter(app_id: str, body: LetterIn, user: User = Depends(require_roles("scrutinizer")), db: Session = Depends(get_db)):
    app = _load(user, app_id, db)
    if app.status not in ("UNDER_SCRUTINY", "RESPONDED"):
        raise HTTPException(409, "A deficiency letter can be drafted only while the application is under scrutiny")
    if db.execute(select(Letter).where(Letter.application_id == app.id, Letter.status.in_(["DRAFT", "PENDING_APPROVAL"]))).scalar():
        raise HTTPException(409, "A letter for this application is already in draft or awaiting approval")
    findings = current_findings(db, app, False)
    chosen = [f for f in findings if f.id in set(body.finding_ids)] if body.finding_ids else \
        [f for f in findings if f.status == "ACCEPTED"]
    if not chosen:
        raise HTTPException(422, "Accept at least one finding (or pick findings) to include in the letter")
    n = db.execute(select(func.count(Letter.id)).where(Letter.application_id == app.id)).scalar() + 1
    letter = Letter(id=f"DL-{app.id[4:]}-{n:02d}", application_id=app.id, status="DRAFT",
                    items=[_letter_item(f) for f in chosen], note=body.note.strip(), drafted_by=user.id)
    db.add(letter)
    db.commit()
    audit.record("Letter drafted", "letter", letter.id, user=user, application_id=app.id, details={"items": len(chosen)})
    return letter_json(letter, _users(db))


class LetterEdit(BaseModel):
    items: list[dict]
    note: str = ""


def _letter_for(user, letter_id, db) -> tuple[Letter, Application]:
    letter = db.get(Letter, letter_id)
    if letter is None:
        raise HTTPException(404, "Letter not found")
    return letter, _load(user, letter.application_id, db)


@router.put("/letters/{letter_id}")
def edit_letter(letter_id: str, body: LetterEdit, user: User = Depends(require_roles("scrutinizer")), db: Session = Depends(get_db)):
    letter, app = _letter_for(user, letter_id, db)
    if letter.status != "DRAFT":
        raise HTTPException(409, "Only a draft letter can be edited")
    items = [{"finding_id": i.get("finding_id"), "title": str(i.get("title", ""))[:200], "text": str(i.get("text", ""))[:2000]}
             for i in body.items if str(i.get("text", "")).strip()]
    if not items:
        raise HTTPException(422, "A letter needs at least one item")
    letter.items, letter.note = items, body.note.strip()
    db.commit()
    audit.record("Letter edited", "letter", letter.id, user=user, application_id=app.id, details={"items": len(items)})
    return letter_json(letter, _users(db))


@router.post("/letters/{letter_id}/submit")
def submit_letter(letter_id: str, user: User = Depends(require_roles("scrutinizer")), db: Session = Depends(get_db)):
    letter, app = _letter_for(user, letter_id, db)
    if letter.status != "DRAFT":
        raise HTTPException(409, "Only a draft letter can be sent for approval")
    letter.status = "PENDING_APPROVAL"
    raise_alert(db, "warning", "letter_approval", f"Deficiency letter {letter.id} for {app.id} is waiting for your approval.",
                "senior_officer", app.id)
    db.commit()
    audit.record("Letter sent for approval", "letter", letter.id, user=user, application_id=app.id)
    return letter_json(letter, _users(db))


class ReviewIn(BaseModel):
    approve: bool
    note: str = ""


@router.post("/letters/{letter_id}/review")
def review_letter(letter_id: str, body: ReviewIn, user: User = Depends(require_roles("senior_officer")), db: Session = Depends(get_db)):
    letter, app = _letter_for(user, letter_id, db)
    if letter.status != "PENDING_APPROVAL":
        raise HTTPException(409, "This letter is not waiting for approval")
    if letter.drafted_by == user.id:
        raise HTTPException(403, "The officer who drafted a letter cannot approve it")
    resolve_alerts(db, "letter_approval", app.id)
    if body.approve:
        letter.status, letter.approved_by, letter.issued_at = "ISSUED", user.id, clock.now()
        app.status = "DEFICIENCY_ISSUED"
        raise_alert(db, "warning", "letter_issued", f"Deficiency letter {letter.id} has been issued for {app.id}. "
                    "Reply with corrected documents.", f"institution:{app.institution_id}", app.id)
        action = "Letter issued"
    else:
        letter.status = "DRAFT"
        letter.note = (letter.note + f"\n[Returned: {body.note.strip()}]").strip()
        action = "Letter returned"
    db.commit()
    audit.record(action, "letter", letter.id, user=user, application_id=app.id, details={"note": body.note.strip()})
    return letter_json(letter, _users(db))


class RespondIn(BaseModel):
    message: str


@router.post("/letters/{letter_id}/respond")
def respond_letter(letter_id: str, body: RespondIn, user: User = Depends(require_roles("institution")), db: Session = Depends(get_db)):
    letter, app = _letter_for(user, letter_id, db)
    if letter.status != "ISSUED":
        raise HTTPException(409, "This letter is not awaiting a reply")
    if len(body.message.strip()) < 5:
        raise HTTPException(422, "Write a short reply describing what you changed")
    letter.status = "RESPONDED"
    letter.response = {"message": body.message.strip()[:4000], "at": clock.now().isoformat(), "by": user.full_name}
    app.status = "RESPONDED"
    resolve_alerts(db, "letter_issued", app.id)
    raise_alert(db, "info", "institution_replied", f"{app.institution.name} replied to {letter.id} ({app.id}).",
                "scrutinizer", app.id)
    db.commit()
    audit.record("Institution replied", "letter", letter.id, user=user, application_id=app.id)
    enqueue_precheck(app.id, "institution replied")
    return letter_json(letter, _users(db))
