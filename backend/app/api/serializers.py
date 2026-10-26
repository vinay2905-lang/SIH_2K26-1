"""Model -> JSON helpers shared by the API routes."""
from datetime import datetime, timezone

from ..models import (Alert, Application, AuditEvent, Document, Finding, Institution, InstitutionRecord, Letter,
                      RulebookVersion, User, Verification)
from ..pipeline.templates import DOC_TYPES

APP_TYPES = {"EOA": "Extension of Approval", "INTAKE_INCREASE": "Increase in intake", "NEW_PROGRAMME": "New programme"}


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def user_json(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "institution_id": u.institution_id, "region": u.region}


def institution_json(i: Institution) -> dict:
    return {"id": i.id, "aicte_id": i.aicte_id, "name": i.name, "kind": i.kind, "state": i.state,
            "state_code": i.state_code, "city": i.city, "address": i.address, "region": i.region,
            "university": i.university, "established": i.established}


def record_json(r: InstitutionRecord | None) -> dict | None:
    if r is None:
        return None
    return {"last_approved_cycle": r.last_approved_cycle, "approval_status": r.approval_status,
            "programmes": r.programmes, "faculty_on_record": len(r.faculty or []),
            "open_deficiencies": r.open_deficiencies, "accreditation_no": r.accreditation_no}


def app_summary(a: Application, counts: dict | None = None) -> dict:
    return {"id": a.id, "institution_id": a.institution_id, "institution": a.institution.name,
            "state": a.institution.state, "city": a.institution.city, "app_type": a.app_type,
            "app_type_label": APP_TYPES.get(a.app_type, a.app_type), "cycle": a.cycle, "status": a.status,
            "created_at": iso(a.created_at), "submitted_at": iso(a.submitted_at), "risk_score": a.risk_score,
            "overall_status": a.overall_status, "rulebook_version": a.rulebook_version,
            "precheck_seconds": a.precheck_seconds, "assigned_to": a.assigned_to, "counts": counts or {},
            "decision": a.decision}


def field_json(f) -> dict:
    return {"name": f.name, "value": f.value, "normalized": f.normalized, "page": f.page, "bbox": f.bbox,
            "confidence": f.confidence}


def document_json(d: Document, official: bool) -> dict:
    meta = d.meta or {}
    out = {"id": d.id, "application_id": d.application_id, "slot": d.slot, "slot_label": DOC_TYPES.get(d.slot, d.slot),
           "detected_type": d.detected_type, "detected_label": DOC_TYPES.get(d.detected_type or "", d.detected_type),
           "detected_confidence": d.detected_confidence, "filename": d.filename, "mime": d.mime, "size": d.size,
           "sha256": d.sha256, "page_count": d.page_count, "pages": d.pages, "status": d.status, "error": d.error,
           "text_source": d.text_source, "ocr_confidence": d.ocr_confidence, "superseded": d.superseded,
           "uploaded_at": iso(d.uploaded_at), "processed_at": iso(d.processed_at),
           "fields": [field_json(f) for f in d.fields], "qr_found": bool(d.qr_payload),
           "signature": {k: v for k, v in (d.signature or {}).items() if k in ("present", "valid", "trusted", "intact",
                                                                                  "modified_after_signing", "summary", "signer")} or None}
    if official:
        out["forensics"] = meta.get("forensics", [])
        out["metadata"] = {k: meta.get(k) for k in ("producer", "creator", "creationDate", "modDate", "eof_markers") if meta.get(k)}
        out["photo"] = meta.get("photo")
        out["classify_hits"] = meta.get("classify_hits", [])
    return out


def finding_json(f: Finding, users: dict[int, str] | None = None) -> dict:
    return {"id": f.id, "ref": f"F-{f.id:04d}", "application_id": f.application_id, "run_id": f.run_id,
            "category": f.category, "severity": f.severity, "title": f.title, "message": f.message,
            "doc_type": f.doc_type, "doc_label": DOC_TYPES.get(f.doc_type or "", f.doc_type), "rule_id": f.rule_id,
            "rule_version": f.rule_version, "source_ref": f.source_ref, "evidence": f.evidence or [],
            "preliminary": f.preliminary, "status": f.status, "decision_note": f.decision_note,
            "decision_by": (users or {}).get(f.decision_by) if f.decision_by else None, "decided_at": iso(f.decided_at),
            "created_at": iso(f.created_at)}


def verification_json(v: Verification) -> dict:
    return {"id": v.id, "application_id": v.application_id, "document_id": v.document_id, "doc_type": v.doc_type,
            "doc_label": DOC_TYPES.get(v.doc_type, v.doc_type), "source": v.source, "method": v.method,
            "reference": v.reference, "status": v.status, "compared": v.compared, "note": v.note,
            "attempts": v.attempts, "latency_ms": v.latency_ms, "checked_at": iso(v.checked_at)}


def letter_json(l: Letter, users: dict[int, str] | None = None) -> dict:
    users = users or {}
    return {"id": l.id, "application_id": l.application_id, "status": l.status, "items": l.items, "note": l.note,
            "drafted_by": users.get(l.drafted_by), "approved_by": users.get(l.approved_by),
            "created_at": iso(l.created_at), "issued_at": iso(l.issued_at), "response": l.response}


def rulebook_json(r: RulebookVersion, users: dict[int, str] | None = None, content: bool = True) -> dict:
    users = users or {}
    out = {"id": r.id, "cycle": r.cycle, "version": r.version, "label": r.label, "status": r.status,
           "change_note": r.change_note, "created_by": users.get(r.created_by), "created_by_id": r.created_by,
           "created_at": iso(r.created_at), "submitted_at": iso(r.submitted_at), "reviewed_by": users.get(r.reviewed_by),
           "reviewed_at": iso(r.reviewed_at), "review_note": r.review_note,
           "effective_from": r.effective_from.isoformat() if r.effective_from else None, "dry_run": r.dry_run,
           "rule_count": len((r.content or {}).get("rules", []))}
    if content:
        out["content"] = r.content
    return out


def alert_json(a: Alert, user_id: int) -> dict:
    return {"id": a.id, "created_at": iso(a.created_at), "severity": a.severity, "kind": a.kind, "message": a.message,
            "application_id": a.application_id, "resolved": a.resolved, "read": user_id in (a.read_by or [])}


def audit_json(e: AuditEvent) -> dict:
    return {"id": e.id, "ts": iso(e.ts), "actor": e.actor, "actor_type": e.actor_type, "action": e.action,
            "object_type": e.object_type, "object_id": e.object_id, "application_id": e.application_id,
            "details": e.details, "prev_hash": e.prev_hash, "hash": e.hash}
