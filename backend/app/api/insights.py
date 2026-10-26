"""Dashboard, verification log, audit trail and alerts."""
import csv
import io
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit, clock
from ..db import get_db
from ..models import Alert, Application, AuditEvent, PrecheckRun, User, Verification
from ..security import OFFICIALS, current_user, require_roles
from .applications import current_findings, finding_counts
from .serializers import alert_json, app_summary, audit_json, aware, verification_json

router = APIRouter(prefix="/api", tags=["insights"])


def _latest_verifications(db: Session, apps: list[Application]) -> list[Verification]:
    run_ids = [a.last_run_id for a in apps if a.last_run_id]
    if not run_ids:
        return []
    return db.execute(select(Verification).where(Verification.run_id.in_(run_ids))).scalars().all()


@router.get("/dashboard")
def dashboard(user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    apps = db.execute(select(Application).where(Application.status != "DRAFT")).scalars().all()
    findings = {a.id: current_findings(db, a, False) for a in apps}
    open_findings = [f for fs in findings.values() for f in fs if f.status == "OPEN"]
    verifs = _latest_verifications(db, apps)
    times = [a.precheck_seconds for a in apps if a.precheck_seconds]

    submitted = [a.submitted_at.date() for a in apps if a.submitted_at]
    end = max(submitted) if submitted else clock.now().date()
    days = [end - timedelta(days=i) for i in range(13, -1, -1)]
    runs = db.execute(select(PrecheckRun).where(PrecheckRun.status == "DONE")).scalars().all()
    by_id = {a.id: a for a in apps}
    first_check: dict[str, date] = {}
    for r in runs:
        a = by_id.get(r.application_id)
        if a is None or a.submitted_at is None or r.finished_at is None or aware(r.finished_at) < aware(a.submitted_at):
            continue
        d = aware(r.finished_at).date()
        first_check[a.id] = min(first_check.get(a.id, d), d)
    by_day_sub, by_day_chk = Counter(submitted), Counter(first_check.values())

    states = defaultdict(lambda: {"received": 0, "prechecked": 0, "critical": 0, "risks": []})
    for a in apps:
        s = states[a.institution.state]
        s["received"] += 1
        s["prechecked"] += 1 if a.last_run_id else 0
        s["critical"] += sum(1 for f in findings[a.id] if f.status == "OPEN" and f.severity == "critical")
        s["risks"].append(a.risk_score)
    state_rows = sorted(({"state": k, "received": v["received"], "prechecked": v["prechecked"], "critical_open": v["critical"],
                          "median_risk": int(statistics.median(v["risks"])) if v["risks"] else 0} for k, v in states.items()),
                        key=lambda r: -r["received"])

    alerts = db.execute(select(Alert).where(Alert.resolved.is_(False), Alert.audience.in_([user.role, "scrutinizer"]))
                        .order_by(Alert.created_at.desc()).limit(6)).scalars().all()
    return {
        "kpis": {
            "received": len(apps),
            "prechecked": sum(1 for a in apps if a.last_run_id),
            "awaiting_scrutiny": sum(1 for a in apps if a.status in ("UNDER_SCRUTINY", "RESPONDED")),
            "critical_open": sum(1 for f in open_findings if f.severity == "critical"),
            "issuer_pending": sum(1 for v in verifs if v.status in ("PENDING", "SOURCE_UNAVAILABLE", "MANUAL_REVIEW")),
            "median_precheck_seconds": round(statistics.median(times), 1) if times else None,
            "decided": sum(1 for a in apps if a.status == "DECIDED"),
            "deficiency_letters": sum(1 for a in apps if a.status == "DEFICIENCY_ISSUED"),
        },
        "daily": [{"date": d.isoformat(), "received": by_day_sub.get(d, 0), "prechecked": by_day_chk.get(d, 0)} for d in days],
        "findings_by_category": dict(Counter(f.category for f in open_findings)),
        "verification_outcomes": dict(Counter(v.status for v in verifs)),
        "states": state_rows,
        "alerts": [alert_json(a, user.id) for a in alerts],
        "top_risk": [app_summary(a, finding_counts(findings[a.id])) for a in sorted(apps, key=lambda a: -a.risk_score)[:5]
                     if a.status != "DECIDED"],
    }


@router.get("/verifications")
def verifications(status: str | None = None, user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    apps = db.execute(select(Application).where(Application.status != "DRAFT")).scalars().all()
    names = {a.id: a.institution.name for a in apps}
    rows = _latest_verifications(db, apps)
    if status:
        rows = [v for v in rows if v.status in status.split(",")]
    rows.sort(key=lambda v: v.checked_at, reverse=True)
    return [dict(verification_json(v), institution=names.get(v.application_id)) for v in rows]


@router.get("/audit")
def audit_events(application_id: str | None = None, actor_type: str | None = None, q: str | None = None,
                 limit: int = Query(200, le=1000), offset: int = 0,
                 user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    query = select(AuditEvent)
    if application_id:
        query = query.where(AuditEvent.application_id == application_id)
    if actor_type:
        query = query.where(AuditEvent.actor_type == actor_type)
    if q:
        like = f"%{q}%"
        query = query.where(or_(AuditEvent.action.ilike(like), AuditEvent.actor.ilike(like), AuditEvent.object_id.ilike(like)))
    rows = db.execute(query.order_by(AuditEvent.id.desc()).offset(offset).limit(limit)).scalars().all()
    return [audit_json(e) for e in rows]


@router.get("/audit/verify")
def audit_verify(user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    return audit.verify_chain(db)


@router.get("/audit/export.csv")
def audit_export(application_id: str | None = None, user: User = Depends(require_roles("auditor", "senior_officer")),
                 db: Session = Depends(get_db)):
    query = select(AuditEvent).order_by(AuditEvent.id)
    if application_id:
        query = query.where(AuditEvent.application_id == application_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "time_utc", "actor", "actor_type", "action", "object_type", "object_id", "application_id",
                "details", "prev_hash", "hash"])
    for e in db.execute(query).scalars():
        w.writerow([e.id, e.ts.isoformat(), e.actor, e.actor_type, e.action, e.object_type, e.object_id,
                    e.application_id or "", e.details, e.prev_hash, e.hash])
    audit.record("Audit exported", "audit", application_id or "all", user=user)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="pramaan-audit.csv"'})


def _audiences(user: User) -> list[str]:
    return [f"institution:{user.institution_id}"] if user.role == "institution" else [user.role]


@router.get("/alerts")
def my_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Alert).where(Alert.audience.in_(_audiences(user)), Alert.resolved.is_(False))
                      .order_by(Alert.created_at.desc()).limit(50)).scalars().all()
    return [alert_json(a, user.id) for a in rows]


@router.post("/alerts/{alert_id}/read")
def read_alert(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None or a.audience not in _audiences(user):
        raise HTTPException(404, "Alert not found")
    if user.id not in (a.read_by or []):
        a.read_by = list(a.read_by or []) + [user.id]
        db.commit()
    return alert_json(a, user.id)


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, user: User = Depends(require_roles(*OFFICIALS)), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None or a.audience not in _audiences(user):
        raise HTTPException(404, "Alert not found")
    a.resolved = True
    db.commit()
    audit.record("Alert resolved", "alert", str(a.id), user=user, application_id=a.application_id, details={"message": a.message})
    return {"resolved": True}
