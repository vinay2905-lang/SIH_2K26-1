"""Runs the pre-check: document processing on upload, then the application-level checks."""
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import imagehash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import audit, clock
from ..alerts import raise_alert, resolve_alerts
from ..db import SessionLocal
from ..jobs import enqueue
from ..models import (Application, Document, ExtractedField, Finding, Institution, InstitutionRecord, Job,
                      PrecheckRun, RulebookVersion, Verification)
from ..storage import store
from . import classify as classify_mod
from . import extract as extract_mod
from . import forensics, ingest, qr, rules_engine, signatures, verify
from .facts import build_facts, doc_ref
from .templates import DOC_TYPES

log = logging.getLogger("pramaan.pipeline")
WEIGHTS = {"critical": 25, "high": 12, "warning": 5, "info": 0}
DEFAULT_RULEBOOK = Path(__file__).resolve().parent.parent / "rulebook" / "default_rulebook.json"
AADHAAR = re.compile(r"\b(\d{4})\s?(\d{4})\s?(\d{4})\b")


def mask_pii(text: str) -> str:
    return AADHAAR.sub(lambda m: f"XXXX XXXX {m.group(3)}", text or "")


def default_rulebook() -> dict:
    return json.loads(DEFAULT_RULEBOOK.read_text(encoding="utf-8"))


def published_rulebook(db, cycle: str) -> RulebookVersion:
    query = (select(RulebookVersion).where(RulebookVersion.cycle == cycle, RulebookVersion.status == "PUBLISHED")
             .order_by(RulebookVersion.version.desc()))
    rb = db.execute(query).scalar()
    if rb is None:
        rb = RulebookVersion(cycle=cycle, version=1, status="PUBLISHED", content=default_rulebook(),
                             change_note="Initial rulebook", effective_from=clock.now().date())
        db.add(rb)
        try:
            db.commit()
        except IntegrityError:  # another process published v1 first
            db.rollback()
            rb = db.execute(query).scalar()
            if rb is None:
                raise
    return rb


def as_of_date(app: Application) -> date:
    if app.submitted_at:
        return app.submitted_at.date()
    return clock.now().date()


def enqueue_precheck(application_id: str, trigger: str) -> None:
    db = SessionLocal()
    try:
        queued = db.execute(select(Job).where(Job.kind == "run_precheck", Job.status == "QUEUED")).scalars().all()
        if any(j.payload.get("application_id") == application_id for j in queued):
            return
    finally:
        db.close()
    enqueue("run_precheck", application_id=application_id, trigger=trigger)


# ---------------------------------------------------------------- documents --
def process_document_job(document_id: str) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        app = db.get(Application, doc.application_id)
        inst = db.get(Institution, app.institution_id)
        doc.status = "PROCESSING"
        db.commit()
        started = time.monotonic()
        try:
            data = store().get(doc.storage_key)
            ing = ingest.ingest(data)
            detected, conf, hits = classify_mod.classify(ing)
            extract_type = detected if (detected and conf >= 0.5) else doc.slot
            fields = extract_mod.extract(ing, extract_type, inst.state_code)
            meta = {k: v for k, v in ing.meta.items() if k != "exif"}
            meta["classify_hits"] = hits
            meta["seconds"] = 0.0
            sig = None
            if ing.kind == "pdf":
                sig = signatures.check_signature(data)
                signals = forensics.pdf_signals(ing, fields, sig)
            else:
                info, signals = forensics.photo_info(ing.image, data)
                meta["photo"] = info
                doc.phash = info.get("phash")
            meta["forensics"] = signals
            doc.qr_payload = ((qr.read_qr(data) or "")[:500] or None) if extract_type != "LAB_PHOTO" else None
            doc.signature = sig
            doc.detected_type, doc.detected_confidence = detected, conf
            doc.pages, doc.page_count = ing.pages, len(ing.pages)
            doc.text_source, doc.ocr_confidence = ing.text_source, ing.ocr_confidence
            doc.text = mask_pii(ing.text)[:200_000]
            doc.meta = meta
            doc.fields.clear()
            for f in fields:
                doc.fields.append(ExtractedField(name=f.name, value=f.value[:400], normalized=(f.normalized or "")[:400] or None,
                                                 page=f.page, bbox=f.bbox, confidence=f.confidence))
            doc.status, doc.error = "PROCESSED", None
        except Exception as exc:
            log.exception("document %s failed", document_id)
            doc.status, doc.error = "FAILED", str(exc)[:500]
        took = round(time.monotonic() - started, 2)
        doc.meta = dict(doc.meta or {}, seconds=took)
        doc.processed_at = clock.now()
        db.commit()
        if doc.status == "PROCESSED":
            audit.record("Text extracted", "document", doc.id, actor="OCR worker", actor_type="SYSTEM",
                         application_id=app.id, details={"file": doc.filename, "source": doc.text_source,
                                                         "fields": len(doc.fields), "ocr_confidence": doc.ocr_confidence,
                                                         "seconds": took})
            audit.record("Document classified", "document", doc.id, actor="Classifier", actor_type="SYSTEM",
                         application_id=app.id, details={"detected": doc.detected_type,
                                                         "confidence": doc.detected_confidence, "uploaded_as": doc.slot})
            if doc.meta.get("forensics"):
                audit.record("Forensic signals", "document", doc.id, actor="Forensics", actor_type="SYSTEM",
                             application_id=app.id, details={"signals": [s["code"] for s in doc.meta["forensics"]]})
        else:
            audit.record("Document failed", "document", doc.id, actor="OCR worker", actor_type="SYSTEM",
                         application_id=app.id, details={"error": doc.error})
        app_id = app.id
    finally:
        db.close()
    enqueue_precheck(app_id, "document processed")


# ------------------------------------------------------------- application --
def _verifications(db, app, docs, as_of, record, run_id) -> dict:
    out = {}
    on_record = {f["faculty_id"] for f in (record.faculty if record else [])}
    for d in docs:
        if d.slot == "LAB_PHOTO":
            continue
        if d.status != "PROCESSED":
            res = verify.VResult(d.slot, "—", "—", "PENDING", note="Document is still being read.")
        else:
            fields = {f.name: (f.normalized or f.value) for f in d.fields}
            fields["faculty_ids"] = [f.value for f in d.fields if f.name == "faculty_id"]
            res = verify.verify_document(d.slot, fields, d.qr_payload, d.signature, as_of, on_record)
        if res is None:
            continue
        row = Verification(application_id=app.id, document_id=d.id, doc_type=d.slot, source=res.source[:80],
                           method=res.method[:40], reference=(res.reference or "")[:120] or None, status=res.status,
                           compared=res.compared,
                           response=res.response, note=res.note[:300], attempts=res.attempts,
                           latency_ms=res.latency_ms, run_id=run_id)
        db.add(row)
        out[d.id] = res
        if res.status != "PENDING":
            audit.record("Source response" if res.status != "SOURCE_UNAVAILABLE" else "Source unavailable",
                         "verification", res.reference or d.id, actor=f"Adapter: {res.source}", actor_type="ADAPTER",
                         application_id=app.id, details={"document": d.filename, "method": res.method,
                                                         "status": res.status, "note": res.note,
                                                         "attempts": res.attempts, "latency_ms": res.latency_ms})
    return out


def _evidence(keys: list[str], ev: dict, scope_doc_id: str | None) -> list[dict]:
    items, seen = [], set()
    for k in keys:
        lookup = f"{scope_doc_id}::{k}" if k.startswith("this.") else k
        for e in ev.get(lookup, []):
            sig = json.dumps(e, sort_keys=True, default=str)
            if sig in seen:
                continue
            seen.add(sig)
            items.append(dict(e))
    for i, e in enumerate(items, start=1):
        e["label"] = f"E{i}"
    return items


def compute_findings(db, app, inst, record, docs, verifs, content, as_of) -> list[dict]:
    """Rule matches + checklist gaps + forensic and duplicate signals, as finding dicts."""
    settings = content.get("settings", {})
    facts, ev, scopes = build_facts(app, inst, record, docs, verifs, settings, as_of)
    out = []
    active = [d for d in docs if not d.superseded]

    for item in (content.get("checklists") or {}).get(app.app_type, []):
        if not item.get("required"):
            continue
        have = [d for d in active if d.slot == item["doc_type"]]
        need = int(item.get("min_count", 1))
        label = DOC_TYPES.get(item["doc_type"], item["doc_type"])
        if not have:
            out.append(dict(category="MISSING_DOCUMENT", severity="critical", title=f"{label} not uploaded",
                            message=f"{label} is required for this application type and has not been uploaded.",
                            doc_type=item["doc_type"], rule_id="CHECKLIST", source_ref=f"APH {app.cycle} · document checklist",
                            evidence=[{"label": "E1", "kind": "checklist", "field": "required document", "value": label}],
                            dedupe_key=f"CHECKLIST:{item['doc_type']}"))
        elif len(have) < need:
            out.append(dict(category="MISSING_DOCUMENT", severity="warning",
                            title=f"Only {len(have)} of {need} {label.lower()}s uploaded",
                            message=f"At least {need} are required.", doc_type=item["doc_type"], rule_id="CHECKLIST",
                            source_ref=f"APH {app.cycle} · document checklist",
                            evidence=[dict(doc_ref(d), label=f"E{i}") for i, d in enumerate(have, 1)],
                            dedupe_key=f"CHECKLIST:{item['doc_type']}:count"))

    for m in rules_engine.evaluate(content, facts, scopes):
        evidence = _evidence(m.evidence_keys, ev, m.scope_doc_id)
        doc_ids = sorted({e["document_id"] for e in evidence if e.get("document_id")})
        out.append(dict(category=m.category, severity=m.severity, title=m.title, message=m.message, doc_type=m.doc_type,
                        rule_id=m.rule_id, source_ref=m.source, evidence=evidence,
                        dedupe_key=f"{m.rule_id}:{m.row}:{','.join(doc_ids)}"))

    for d in active:
        for s in (d.meta or {}).get("forensics", []):
            out.append(dict(category="ANOMALY", severity=s["severity"], title=f"{DOC_TYPES.get(d.slot, d.slot)}: {s['title']}",
                            message=s["message"], doc_type=d.slot, rule_id=f"FORENSIC-{s['code']}",
                            source_ref="Preliminary indicator · needs human verification",
                            evidence=[dict(doc_ref(d, s.get("page", 0), s.get("bbox"), "forensic signal", s["code"]),
                                           label="E1", note=s["message"])],
                            preliminary=True, visible_to_institution=False, dedupe_key=f"FORENSIC:{s['code']}:{d.id}"))

    out.extend(_duplicates(db, app, active))
    return out


def _duplicates(db, app, active) -> list[dict]:
    out = []
    others = db.execute(select(Document, Application).join(Application, Document.application_id == Application.id)
                        .where(Application.institution_id != app.institution_id, Document.superseded.is_(False))).all()
    for d in active:
        for od, oapp in others:
            same_file = d.sha256 == od.sha256
            similar_photo = False
            distance = None
            if not same_file and d.slot == "LAB_PHOTO" and d.phash and od.phash:
                distance = imagehash.hex_to_hash(d.phash) - imagehash.hex_to_hash(od.phash)
                similar_photo = distance <= 6
            if same_file or similar_photo:
                inst = oapp.institution
                how = "the identical file" if same_file else f"a near-identical photo (difference {distance} of 64)"
                out.append(dict(
                    category="ANOMALY", severity="high",
                    title=f"{DOC_TYPES.get(d.slot, d.slot)} matches a document from another institution",
                    message=f"{d.filename} matches {how} filed by {inst.name} in {oapp.id}.",
                    doc_type=d.slot, rule_id="FORENSIC-DUPLICATE", source_ref="Preliminary indicator · needs human verification",
                    evidence=[dict(doc_ref(d), label="E1", note="this application"),
                              dict(doc_ref(od), label="E2", note=f"{oapp.id} · {inst.name}")],
                    preliminary=True, visible_to_institution=False, dedupe_key=f"DUP:{d.id}:{od.id}"))
                break
    return out


def score(findings: list[Finding]) -> tuple[int, str]:
    live = [f for f in findings if f.status in ("OPEN", "ACCEPTED")]
    risk = min(100, sum(WEIGHTS.get(f.severity, 0) for f in live))
    sev = {f.severity for f in live}
    if "critical" in sev:
        status = "NEEDS_ACTION"
    elif "high" in sev:
        status = "NEEDS_REVIEW"
    elif "warning" in sev:
        status = "MINOR_ISSUES"
    else:
        status = "CLEAR"
    return risk, status


def run_precheck_job(application_id: str, trigger: str = "manual") -> None:
    started = time.monotonic()
    db = SessionLocal()
    try:
        app = db.get(Application, application_id)
        if app is None:
            return
        inst = db.get(Institution, app.institution_id)
        record = db.execute(select(InstitutionRecord).where(InstitutionRecord.institution_id == inst.id)).scalar()
        rb = published_rulebook(db, app.cycle)
        run = PrecheckRun(application_id=app.id, trigger=trigger[:120], rulebook_version=rb.label)
        db.add(run)
        db.commit()
        audit.record("Pre-check started", "application", app.id, actor="Rules engine", actor_type="SYSTEM",
                     application_id=app.id, details={"trigger": trigger, "rulebook": rb.label})
        docs = db.execute(select(Document).where(Document.application_id == app.id, Document.superseded.is_(False))
                          .order_by(Document.uploaded_at)).scalars().all()
        as_of = as_of_date(app)
        verifs = _verifications(db, app, docs, as_of, record, run.id)
        found = compute_findings(db, app, inst, record, docs, verifs, rb.content, as_of)

        previous = db.execute(select(Finding).where(Finding.application_id == app.id,
                                                    Finding.status.notin_(["SUPERSEDED", "RESOLVED"]))).scalars().all()
        prev_by_key = {f.dedupe_key: f for f in previous}
        new_keys, created = set(), []
        for item in found:
            if item["dedupe_key"] in new_keys:
                continue
            new_keys.add(item["dedupe_key"])
            item["title"] = item["title"][:200]
            item["dedupe_key"] = item["dedupe_key"][:160]
            item["source_ref"] = (item.get("source_ref") or "")[:200]
            item["rule_id"] = (item.get("rule_id") or "")[:40]
            f = Finding(application_id=app.id, run_id=run.id, rule_version=rb.label,
                        preliminary=item.get("preliminary", False),
                        visible_to_institution=item.get("visible_to_institution", True),
                        **{k: v for k, v in item.items() if k not in ("preliminary", "visible_to_institution")})
            old = prev_by_key.get(item["dedupe_key"])
            if old is not None and old.status in ("ACCEPTED", "OVERRIDDEN"):
                f.status, f.decision_by, f.decision_note, f.decided_at = old.status, old.decision_by, old.decision_note, old.decided_at
            db.add(f)
            created.append((f, old is None))
        for old in previous:
            old.status = "SUPERSEDED" if old.dedupe_key in new_keys else "RESOLVED"
        db.flush()

        current = [f for f, _ in created]
        app.risk_score, app.overall_status = score(current)
        app.rulebook_version, app.last_run_id = rb.label, run.id
        reading = sum(float((d.meta or {}).get("seconds") or 0) for d in docs)
        app.precheck_seconds = round(time.monotonic() - started + reading, 1)
        run.status, run.finished_at = "DONE", clock.now()
        run.stats = {"findings": len(current), "critical": sum(f.severity == "critical" for f in current),
                     "high": sum(f.severity == "high" for f in current), "verifications": len(verifs),
                     "seconds": app.precheck_seconds}
        _alerts(db, app, inst, current, created, verifs, docs, as_of)
        db.commit()
        for f, is_new in created:
            if is_new and f.severity in ("critical", "high"):
                audit.record("Finding raised", "finding", str(f.id), actor="Rules engine", actor_type="SYSTEM",
                             application_id=app.id, details={"rule": f.rule_id, "severity": f.severity, "title": f.title})
        audit.record("Pre-check completed", "application", app.id, actor="Rules engine", actor_type="SYSTEM",
                     application_id=app.id, details={"risk": app.risk_score, "status": app.overall_status, **run.stats})
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _alerts(db, app, inst, current, created, verifs, docs, as_of) -> None:
    critical = [f for f in current if f.severity == "critical" and f.status == "OPEN"]
    if app.submitted_at:
        if critical:
            raise_alert(db, "critical", "critical_findings",
                        f"{app.id} · {inst.name}: {len(critical)} critical finding(s), e.g. {critical[0].title}",
                        "scrutinizer", app.id)
        else:
            resolve_alerts(db, "critical_findings", app.id)
    down = {v.source for v in verifs.values() if v.status == "SOURCE_UNAVAILABLE"}
    for source in down:
        n = sum(1 for v in verifs.values() if v.source == source and v.status == "SOURCE_UNAVAILABLE")
        raise_alert(db, "serious", f"source_down:{source}",
                    f"{source} did not respond; {n} check(s) on {app.id} routed to manual review", "scrutinizer", app.id)
    for d in docs:
        till = next((f.normalized for f in d.fields if f.name == "valid_till" and f.normalized), None)
        if till:
            days = (date.fromisoformat(till) - as_of).days
            if 0 <= days <= 30:
                raise_alert(db, "warning", f"expiring:{d.slot}",
                            f"{DOC_TYPES.get(d.slot, d.slot)} expires on {date.fromisoformat(till):%d-%m-%Y} "
                            f"({days} days). Renew it before scrutiny.", f"institution:{inst.id}", app.id)
    visible_blocking = [f for f in current if f.visible_to_institution and f.severity == "critical"]
    if not app.submitted_at and visible_blocking:
        raise_alert(db, "warning", "draft_issues",
                    f"Pre-check found {len(visible_blocking)} critical issue(s) in your draft {app.id}.",
                    f"institution:{inst.id}", app.id)
    elif not visible_blocking:
        resolve_alerts(db, "draft_issues", app.id)


# ----------------------------------------------------------------- dry run --
def dry_run_job(version_id: int) -> None:
    db = SessionLocal()
    try:
        draft = db.get(RulebookVersion, version_id)
        if draft is None:
            return
        live = published_rulebook(db, draft.cycle)
        apps = db.execute(select(Application).where(Application.cycle == draft.cycle, Application.last_run_id.isnot(None))).scalars().all()
        changed, by_rule = [], {}
        totals = {"draft": 0, "published": 0}
        flagged = 0
        for app in apps:
            inst = db.get(Institution, app.institution_id)
            record = db.execute(select(InstitutionRecord).where(InstitutionRecord.institution_id == inst.id)).scalar()
            docs = db.execute(select(Document).where(Document.application_id == app.id, Document.superseded.is_(False))).scalars().all()
            rows = db.execute(select(Verification).where(Verification.run_id == app.last_run_id)).scalars().all()
            verifs = {v.document_id: v for v in rows if v.document_id}
            as_of = as_of_date(app)
            a = {f["dedupe_key"]: f for f in compute_findings(db, app, inst, record, docs, verifs, draft.content, as_of)
                 if not f["rule_id"].startswith("FORENSIC")}
            b = {f["dedupe_key"]: f for f in compute_findings(db, app, inst, record, docs, verifs, live.content, as_of)
                 if not f["rule_id"].startswith("FORENSIC")}
            totals["draft"] += len(a)
            totals["published"] += len(b)
            if a:
                flagged += 1
            for f in a.values():
                by_rule.setdefault(f["rule_id"], {"draft": 0, "published": 0})["draft"] += 1
            for f in b.values():
                by_rule.setdefault(f["rule_id"], {"draft": 0, "published": 0})["published"] += 1
            added = [a[k]["title"] for k in a.keys() - b.keys()]
            removed = [b[k]["title"] for k in b.keys() - a.keys()]
            if added or removed:
                changed.append({"application_id": app.id, "institution": inst.name, "added": added, "removed": removed})
        draft.dry_run = {"ran_at": clock.now().isoformat(), "applications": len(apps),
                         "flagged_applications": flagged, "findings": totals, "by_rule": by_rule, "changed": changed}
        db.commit()
    finally:
        db.close()
