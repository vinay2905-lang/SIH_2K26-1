"""Turn an application, its documents, AICTE records and verification results into flat facts for the rules,
and remember where each fact came from so findings can cite their evidence."""
import math
from datetime import date, datetime

from ..models import Application, Document, Institution, InstitutionRecord
from .rules_engine import display
from .templates import DOC_TYPES

PROGRAMME_YEARS = {"B.Tech": 4, "B.Pharm": 4, "Diploma": 3, "M.Tech": 2, "M.Pharm": 2, "MBA": 2, "MCA": 2}
INTERNAL_SOURCES = {"AICTE faculty records"}


def _years(programme: str) -> int:
    for prefix, years in PROGRAMME_YEARS.items():
        if programme.startswith(prefix):
            return years
    return 3


def _km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def doc_ref(d: Document, page: int = 0, bbox=None, field=None, value=None, confidence=None, note=None) -> dict:
    return {"kind": "document", "document_id": d.id, "doc_type": d.slot, "filename": d.filename, "page": page,
            "bbox": bbox, "field": field, "value": value, "confidence": confidence, "note": note}


def build_facts(app: Application, inst: Institution, record: InstitutionRecord | None, docs: list[Document],
                verifs: dict, settings: dict, as_of: date):
    """verifs: document_id -> object with .status .note .source"""
    facts: dict = {}
    ev: dict[str, list[dict]] = {}
    form = app.form or {}

    facts.update({
        "application.id": app.id, "application.type": app.app_type, "application.cycle": app.cycle,
        "application.as_of_date": as_of.isoformat(), "application.submitted": app.submitted_at is not None,
        "institution.name": inst.name, "institution.state_code": inst.state_code, "institution.aicte_id": inst.aicte_id,
        "institution.city": inst.city,
    })
    ev["application.as_of_date"] = [{"kind": "application", "field": "application date", "value": display(as_of.isoformat())}]
    ev["application.cycle"] = [{"kind": "application", "field": "cycle", "value": app.cycle}]
    ev["institution.name"] = [{"kind": "aicte_record", "field": "institution name", "value": inst.name}]

    for k, v in form.items():
        if isinstance(v, (str, int, float)) and v != "":
            facts[f"form.{k}"] = v
            ev[f"form.{k}"] = [{"kind": "form", "field": k.replace("_", " "), "value": display(v)}]
    programmes = [p for p in form.get("programmes", []) if p.get("name")]
    total_intake = sum(int(p.get("intake_requested") or 0) for p in programmes)
    facts["form.total_intake"] = total_intake

    if record:
        facts.update({"records.last_approved_cycle": record.last_approved_cycle,
                      "records.approval_status": record.approval_status,
                      "records.open_deficiencies": record.open_deficiencies})

    active = [d for d in docs if not d.superseded]
    by_type: dict[str, list[Document]] = {}
    for d in active:
        by_type.setdefault(d.slot, []).append(d)
    for doc_type, group in by_type.items():
        facts[f"doc.{doc_type}.present"] = True
        facts[f"doc.{doc_type}.count"] = len(group)
        latest = max(group, key=lambda d: d.uploaded_at)
        for f in latest.fields:
            if f.name in ("faculty_id",) or f.name.startswith("intake::"):
                continue
            key = f"doc.{doc_type}.{f.name}"
            facts[key] = f.normalized or f.value
            ev[key] = [doc_ref(latest, f.page, f.bbox, f.name.replace("_", " "), f.value, f.confidence)]
        v = verifs.get(latest.id)
        if v is not None:
            facts[f"verify.{doc_type}.status"] = v.status

    # derived: intake against affiliation letter and AICTE records
    aff = max(by_type.get("AFFILIATION_LETTER", []), key=lambda d: d.uploaded_at, default=None)
    over_aff, missing_aff = [], []
    aff_ev = []
    if aff is not None and aff.status == "PROCESSED":
        intakes = {f.name.split("::", 1)[1]: f for f in aff.fields if f.name.startswith("intake::")}
        if intakes:
            for p in programmes:
                f = intakes.get(p["name"])
                req = int(p.get("intake_requested") or 0)
                if f is None:
                    missing_aff.append(p["name"])
                elif req > int(f.value):
                    over_aff.append(f"{p['name']}: {req} requested, {f.value} in affiliation letter")
                    aff_ev.append(doc_ref(aff, f.page, f.bbox, f"approved intake · {p['name']}", f.value, f.confidence))
    facts["derived.intake_over_affiliation"] = over_aff
    facts["derived.programmes_missing_in_affiliation"] = missing_aff
    form_prog_ev = [{"kind": "form", "field": f"intake requested · {p['name']}", "value": str(p.get("intake_requested"))}
                    for p in programmes]
    ev["derived.intake_over_affiliation"] = aff_ev + form_prog_ev
    ev["derived.programmes_missing_in_affiliation"] = form_prog_ev + ([doc_ref(aff)] if aff else [])

    over_rec, rec_ev = [], []
    if record:
        approved = {p["programme"]: int(p["approved_intake"]) for p in record.programmes or []}
        for p in programmes:
            req = int(p.get("intake_requested") or 0)
            if p["name"] in approved and req > approved[p["name"]]:
                over_rec.append(f"{p['name']}: {req} requested, {approved[p['name']]} approved in {record.last_approved_cycle}")
                rec_ev.append({"kind": "aicte_record", "field": f"approved intake {record.last_approved_cycle} · {p['name']}",
                               "value": str(approved[p["name"]])})
    facts["derived.intake_over_records"] = over_rec
    ev["derived.intake_over_records"] = rec_ev + form_prog_ev

    # derived: faculty
    fac = max(by_type.get("FACULTY_LIST", []), key=lambda d: d.uploaded_at, default=None)
    on_record = {f["faculty_id"] for f in (record.faculty if record else [])}
    if fac is not None and fac.status == "PROCESSED":
        ids = [f for f in fac.fields if f.name == "faculty_id"]
        unknown = [f for f in ids if f.value not in on_record]
        facts["derived.faculty_count"] = len({f.value for f in ids}) or None
        facts["derived.faculty_not_in_records"] = sorted({f.value for f in unknown})
        ev["derived.faculty_not_in_records"] = [doc_ref(fac, f.page, f.bbox, "faculty ID", f.value, f.confidence) for f in unknown] + \
            [{"kind": "aicte_record", "field": "faculty on AICTE record", "value": f"{len(on_record)} faculty"}]
        ev["derived.faculty_count"] = [doc_ref(fac, 0, None, "faculty listed", str(facts["derived.faculty_count"]))]
    else:
        facts["derived.faculty_not_in_records"] = []
    students = sum(int(p.get("intake_requested") or 0) * _years(p["name"]) for p in programmes)
    facts["derived.student_estimate"] = students
    if facts.get("derived.faculty_count"):
        facts["derived.student_faculty_ratio"] = round(students / facts["derived.faculty_count"], 1)
        ev["derived.student_faculty_ratio"] = form_prog_ev + ev.get("derived.faculty_count", [])
    facts["derived.required_computers"] = math.ceil(total_intake / 2) if total_intake else None
    ev["derived.required_computers"] = form_prog_ev
    ev["form.computer_count"] = ev.get("form.computer_count", [])

    # derived: photographs
    photos = by_type.get("LAB_PHOTO", [])
    facts["derived.lab_photo_count"] = len(photos)
    far, no_loc, old = [], [], []
    far_ev, no_loc_ev, old_ev = [], [], []
    max_km = float(settings.get("photo_max_distance_km", 2.0))
    window = int(settings.get("photo_window_days", 365))
    for d in photos:
        info = (d.meta or {}).get("photo") or {}
        if info.get("gps_lat") is not None and info.get("gps_lon") is not None:
            km = _km(inst.lat, inst.lon, info["gps_lat"], info["gps_lon"])
            if km > max_km:
                far.append(f"{d.filename} ({km:.1f} km away)")
                far_ev.append(doc_ref(d, note=f"GPS {info['gps_lat']:.4f}, {info['gps_lon']:.4f} · {km:.1f} km from campus"))
        elif d.status == "PROCESSED":
            no_loc.append(d.filename)
            no_loc_ev.append(doc_ref(d, note="no GPS tag"))
        if info.get("taken_at"):
            try:
                taken = datetime.fromisoformat(info["taken_at"]).date()
                if (as_of - taken).days > window:
                    old.append(f"{d.filename} ({taken:%d-%m-%Y})")
                    old_ev.append(doc_ref(d, note=f"taken {taken:%d-%m-%Y}"))
            except ValueError:
                pass
    facts["derived.photos_far_from_campus"], ev["derived.photos_far_from_campus"] = far, far_ev
    facts["derived.photos_without_location"], ev["derived.photos_without_location"] = no_loc, no_loc_ev
    facts["derived.photos_outside_window"], ev["derived.photos_outside_window"] = old, old_ev

    # per-document scopes for each_document rules
    scopes = []
    for d in active:
        v = verifs.get(d.id)
        s = {"this.document_id": d.id, "this.doc_type": d.slot, "this.label": DOC_TYPES.get(d.slot, d.slot),
             "this.filename": d.filename, "this.slot": d.slot, "this.detected_type": d.detected_type,
             "this.detected_confidence": d.detected_confidence}
        if d.text_source in ("OCR", "MIXED") and d.ocr_confidence is not None and d.slot != "LAB_PHOTO":
            s["this.ocr_confidence"] = d.ocr_confidence
        if v is not None:
            s["this.verify_status"], s["this.verify_note"] = v.status, v.note
            s["this.verify_external"] = v.source not in INTERNAL_SOURCES
        if d.detected_type and d.detected_type != d.slot and (d.detected_confidence or 0) >= 0.6:
            s["this.misfiled_as"] = DOC_TYPES.get(d.detected_type, d.detected_type)
        if d.status == "FAILED":
            s["this.unreadable"] = d.error or "The file could not be read."
        elif d.status == "PROCESSED" and d.slot != "LAB_PHOTO" and d.text_source == "NONE":
            s["this.unreadable"] = "No text could be read from this file."
        scopes.append(s)
        ref = doc_ref(d)
        ev[f"{d.id}::this.verify_status"] = [dict(ref, kind="issuer", field=v.source if v else None,
                                                  value=v.status if v else None, note=v.note if v else None)]
        ev[f"{d.id}::this.ocr_confidence"] = [dict(ref, field="OCR confidence", value=str(d.ocr_confidence))]
        ev[f"{d.id}::this.misfiled_as"] = [dict(ref, field="detected type", value=s.get("this.misfiled_as"),
                                                confidence=d.detected_confidence)]
        ev[f"{d.id}::this.unreadable"] = [dict(ref, field="reading", value=s.get("this.unreadable"))]
    return facts, ev, scopes
