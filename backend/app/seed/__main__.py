"""Load synthetic demo data: `python -m app.seed` (wipes and rebuilds the database and document store).

Creates institutions, AICTE records, demo users, a sandbox PKI, issuer registry records and eight
applications with planted problems, then runs the real pipeline over every document.
"""
import argparse
import hashlib
import json
import math
import os
import random
import shutil
import uuid
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault("PRAMAAN_JOB_MODE", "worker")  # the seed drives the pipeline itself

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from .. import audit, clock  # noqa: E402
from ..alerts import raise_alert  # noqa: E402
from ..config import get_settings  # noqa: E402
from ..db import Base, SessionLocal, engine, init_db  # noqa: E402
from ..models import (Application, Document, Finding, Institution, InstitutionRecord, Job, Letter,  # noqa: E402
                      RulebookVersion, User)
from ..pipeline import orchestrator, verify  # noqa: E402
from ..pipeline.templates import DOC_TYPES  # noqa: E402
from ..sandbox.main import app as sandbox_app  # noqa: E402
from ..security import hash_password  # noqa: E402
from ..storage import store  # noqa: E402
from . import documents as D  # noqa: E402
from . import pki  # noqa: E402
from .data import APPLICATIONS, DEMO_PASSWORD, DESIGNATIONS, FIRST, INSTITUTIONS, LAST, OFFICIALS  # noqa: E402

UTC = timezone.utc
YEARS = {"B.Tech": 4, "B.Pharm": 4, "Diploma": 3, "M.Tech": 2, "M.Pharm": 2, "MBA": 2, "MCA": 2}


class SeedClock:
    """Monotonic fake clock so the audit trail reads like the real submission window."""

    def __init__(self):
        self.t = datetime(2026, 1, 10, 5, 0, tzinfo=UTC)

    def at(self, t: datetime):
        self.t = max(self.t, t)

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=random.randint(2, 9))
        return self.t


def years(programme: str) -> int:
    return next((y for p, y in YEARS.items() if programme.startswith(p)), 3)


def faculty_rows(idx: int, count: int, rnd: random.Random, prefix: int = 100000) -> list[dict]:
    rows = []
    for i in range(count):
        desig, qual = DESIGNATIONS[i % len(DESIGNATIONS)] if i > 2 else DESIGNATIONS[0]
        rows.append({"faculty_id": f"FID-{prefix + idx * 1000 + i}", "name": f"{rnd.choice(['Dr. ', '', ''])}{rnd.choice(FIRST)} {rnd.choice(LAST)}",
                     "designation": desig, "qualification": qual})
    return rows


def build(inst: dict, spec: dict, idx: int, files: dict, photo_bank: dict) -> tuple[list, dict, list, dict]:
    rnd = random.Random(idx * 97)
    code = inst["city"][:3].upper()
    programmes = [(n, lvl, i) for n, lvl, i in spec["approved"]] + list(spec.get("new_programmes", []))
    aff_progs = [{"programme": n, "approved_intake": (spec.get("affiliation_override") or {}).get(n, i)} for n, _, i in programmes]
    area = 9000 + idx * 1700
    docs, reg = [], {"fire_noc": {}, "land": {}, "affiliations": {}, "nba": {}, "payments": {}}

    reg_no = f"{inst['state_code']}/{inst['established'] - 1}/{rnd.randint(10000, 99999)}"
    land = dict(city=inst["city"], registration_no=reg_no, registration_date=f"{inst['established'] - 1}-11-14",
                owner_name=inst["trust"], survey_no=f"{rnd.randint(100, 499)}/2A", area_acres=round(8 + idx * 1.5, 1))
    docs.append(("LAND_DEED", "Land_sale_deed.pdf", D.land_deed(land)))
    reg["land"][reg_no] = {k: land[k] for k in ("owner_name", "survey_no", "area_acres", "registration_date")}

    bcc_area = spec.get("bcc_area", area)
    bcc = dict(city=inst["city"], cert_no=f"BCC/{inst['established'] + 2}/{code}/{rnd.randint(100, 999)}",
               issue_date=f"{inst['established'] + 2}-06-12", premises_name=inst["name"], address=inst["address"],
               built_up_area=bcc_area)
    pdf = D.building_completion(bcc)
    if not spec.get("bcc_unsigned"):
        pdf = pki.sign_pdf(pdf, files)
        if spec.get("bcc_modified"):
            pdf = pki.modify_after_signing(pdf, f"{bcc_area:,} m2", f"{bcc_area + 3500:,} m2")
    docs.append(("BUILDING_COMPLETION", "Building_completion_certificate.pdf", pdf))

    till = spec["fire_till"]
    frm = (date.fromisoformat(till) - timedelta(days=364)).isoformat()
    cert = f"FNOC/2025/{code}/{rnd.randint(10000, 99999)}"
    fire = dict(state=inst["state"], cert_no=cert, issue_date=(date.fromisoformat(frm) - timedelta(days=4)).isoformat(),
                premises_name=inst["name"], address=inst["address"], built_up_area=area, valid_from=frm, valid_till=till,
                valid_label="Valid up to" if inst["state_code"] == "MH" else "Valid till")
    pdf = D.fire_noc(fire)
    if spec.get("fire_tampered_to"):
        pdf = D.tamper_cover_text(pdf, D.d(till), D.d(spec["fire_tampered_to"]))
    docs.append(("FIRE_NOC", "Fire_NOC.pdf", pdf))
    reg["fire_noc"][cert] = {"premises_name": inst["name"], "address": inst["address"], "valid_from": frm,
                             "valid_till": till, "status": "ACTIVE"}

    if "STRUCTURAL_STABILITY" not in spec.get("skip", []):
        st = dict(state_code=inst["state_code"], cert_no=f"SSC/2024/{code}/{rnd.randint(100, 999)}", issue_date="2024-08-20",
                  premises_name=inst["name"], valid_till="2029-08-19")
        docs.append(("STRUCTURAL_STABILITY", "Structural_stability.pdf", D.structural(st)))

    letter = f"AFF/2026/{rnd.randint(1000, 9999)}"
    aff = dict(university=inst["university"], letter_no=letter, issue_date="2026-03-02", academic_year="2026-27",
               institution_name=inst["name"], programmes=aff_progs)
    docs.append(("AFFILIATION_LETTER", "Affiliation_letter_2026-27.pdf", D.affiliation(aff)))
    reg["affiliations"][letter] = {k: aff[k] for k in ("university", "institution_name", "academic_year", "programmes")}

    acc_no = None
    if spec.get("nba_till") or inst["id"] == "INST-VCE":
        acc_no = f"NBA/2023/{rnd.randint(1000, 9999)}"
        nb = dict(accreditation_no=acc_no, issue_date="2023-07-01", institution_name=inst["name"],
                  programmes=[n for n, _, _ in spec["approved"]][:2], valid_till=spec.get("nba_till", "2028-06-30"))
        docs.append(("NBA_ACCREDITATION", "NBA_accreditation.pdf", D.nba(nb)))
        reg["nba"][acc_no] = {"institution_name": inst["name"], "valid_till": nb["valid_till"]}

    amount = 150000 if inst["kind"] == "Engineering" else 100000
    txn = f"TER-2026-{rnd.randint(10000, 99999)}"
    ter = dict(txn_id=txn, institution_name=inst["name"], amount_text=f"{amount // 100000},{(amount % 100000) // 1000:02d},000",
               payment_date="2026-03-28")
    docs.append(("TER_RECEIPT", "TER_payment_receipt.pdf", D.ter_receipt(ter)))
    reg["payments"][txn] = {"amount": amount, "status": spec.get("ter_status", "SUCCESS"), "institution": inst["name"],
                            "payment_date": "2026-03-28"}

    afd = dict(deponent=inst["principal"], institution_name=inst["name"], date="2026-04-02",
               notary_reg_no=f"{inst['state_code']}/NOT/{rnd.randint(1000, 9999)}")
    pdf = D.affidavit(afd)
    docs.append(("AFFIDAVIT", "Affidavit_undertaking.pdf", D.scanned(pdf) if spec.get("scanned_affidavit") else pdf))

    students = sum(i * years(n) for n, _, i in programmes)
    faculty = faculty_rows(idx, math.ceil(students / 17.5), rnd)
    listed = list(faculty)
    for k in range(spec.get("unknown_faculty", 0)):
        listed.insert(5 + k * 7, {"faculty_id": f"FID-9{idx}{k:04d}", "name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
                                  "designation": "Assistant Professor", "qualification": "M.Tech"})
    docs.append(("FACULTY_LIST", "Faculty_list.pdf", D.faculty_list({"institution_name": inst["name"], "faculty": listed})))

    for k in range(2):
        lat, lon = inst["lat"] + 0.0011 * (k + 1), inst["lon"] + 0.0008 * (k + 1)
        if spec.get("photos_far"):
            lat += 0.33
        taken = datetime(2026, 3, 10 + k, 11, 20)
        if k == 1 and spec.get("duplicate_photo_from"):
            img = D.recapture(photo_bank[spec["duplicate_photo_from"]], (lat, lon), taken)
        else:
            img = D.lab_photo(idx * 10 + k, (lat, lon), taken)
            photo_bank.setdefault(inst["id"], img)
        docs.append(("LAB_PHOTO", f"Computer_lab_{k + 1}.jpg", img))

    record_progs = [{"programme": n, "level": lvl, "approved_intake": i} for n, lvl, i in spec["approved"]]
    return docs, reg, faculty, {"programmes": record_progs, "accreditation_no": acc_no, "area": area,
                                "land_area": land["area_acres"], "all_programmes": programmes}


def add_document(db, app, slot, name, data, user) -> Document:
    doc = Document(id=f"DOC-{uuid.uuid4().hex[:12]}", application_id=app.id, slot=slot, filename=name,
                   mime="application/pdf" if data[:4] == b"%PDF" else "image/jpeg", size=len(data),
                   sha256=hashlib.sha256(data).hexdigest(), storage_key=store().put(data), uploaded_by=user.id, status="UPLOADED")
    db.add(doc)
    db.commit()
    audit.record("Document uploaded", "document", doc.id, user=user, application_id=app.id,
                 details={"file": name, "slot": DOC_TYPES[slot], "bytes": len(data), "sha256": doc.sha256})
    return doc


def clear_jobs(db, app_id):
    for j in db.execute(select(Job).where(Job.status == "QUEUED")).scalars():
        if j.payload.get("application_id") == app_id or j.kind == "run_precheck":
            db.delete(j)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="do not wipe existing data first")
    parser.add_argument("--yes", action="store_true", help="confirm wiping data when PRAMAAN_ENV=production")
    args = parser.parse_args()
    s = get_settings()
    if s.env == "production" and not args.keep and not args.yes:
        raise SystemExit("This wipes every application, document and audit event. Re-run with --yes to confirm.")
    previous_mode, s.job_mode = s.job_mode, "worker"  # the seed drives each pipeline step itself
    random.seed(7)
    if not args.keep:
        Base.metadata.drop_all(engine)
        for sub in ("storage", "sandbox", "trust", "samples"):
            shutil.rmtree(s.data_dir / sub, ignore_errors=True)
    init_db()
    clk = SeedClock()
    clock.set_clock(clk)
    verify.set_client(TestClient(sandbox_app, base_url="http://sandbox"))
    files = pki.create_pki(s.data_dir / "sandbox", s.data_dir / "trust")

    db = SessionLocal()
    users = {}
    for o in OFFICIALS:
        u = User(username=o["username"], full_name=o["full_name"], role=o["role"], region=o["region"],
                 password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        users[o["username"]] = u
    db.commit()
    rb = RulebookVersion(cycle=s.current_cycle, version=1, status="PUBLISHED", content=orchestrator.default_rulebook(),
                         change_note="Rulebook for cycle 2026-27 derived from the Approval Process Handbook",
                         created_by=users["s.rao"].id, reviewed_by=users["r.menon"].id,
                         reviewed_at=datetime(2026, 1, 9, 6, 0, tzinfo=UTC), submitted_at=datetime(2026, 1, 8, 9, 0, tzinfo=UTC),
                         effective_from=date(2026, 1, 10))
    db.add(rb)
    db.commit()
    audit.record("Rulebook published", "rulebook", rb.label, user=users["r.menon"], details={"note": rb.change_note})

    registry = {"fire_noc": {}, "land": {}, "affiliations": {}, "nba": {}, "payments": {}, "outages": []}
    built, photo_bank = {}, {}
    order = sorted(INSTITUTIONS, key=lambda i: APPLICATIONS[i["id"]]["submitted"] or "9999")
    indices = {inst["id"]: i for i, inst in enumerate(INSTITUTIONS, start=1)}
    # institutions that re-use another's photo are built after the one they copy from
    for inst in sorted(INSTITUTIONS, key=lambda i: 1 if APPLICATIONS[i["id"]].get("duplicate_photo_from") else 0):
        idx = indices[inst["id"]]
        built[inst["id"]] = (*build(inst, APPLICATIONS[inst["id"]], idx, files, photo_bank), idx)
    for inst in INSTITUTIONS:
        docs, reg, faculty, extra, idx = built[inst["id"]]
        for k, v in reg.items():
            registry[k].update(v)
        if APPLICATIONS[inst["id"]].get("university_down"):
            registry["outages"].append(inst["university"])
        sample_dir = s.data_dir / "samples" / inst["id"]
        for slot, name, data in docs:
            (sample_dir / slot).mkdir(parents=True, exist_ok=True)
            (sample_dir / slot / name).write_bytes(data)
    (s.data_dir / "sandbox").mkdir(parents=True, exist_ok=True)
    (s.data_dir / "sandbox" / "registry.json").write_text(json.dumps(registry, indent=1), encoding="utf-8")

    for inst in INSTITUTIONS:
        docs, reg, faculty, extra, idx = built[inst["id"]]
        db.add(Institution(**{k: inst[k] for k in ("id", "aicte_id", "name", "kind", "state", "state_code", "city", "address",
                                                     "region", "lat", "lon", "established", "university")}))
        db.flush()
        db.add(InstitutionRecord(institution_id=inst["id"], last_approved_cycle="2025-26", approval_status="APPROVED",
                                 programmes=extra["programmes"], faculty=faculty, open_deficiencies=0,
                                 accreditation_no=extra["accreditation_no"]))
        u = User(username=inst["username"], full_name=inst["name"], role="institution", institution_id=inst["id"],
                 region=inst["region"], password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        users[inst["username"]] = u
    db.commit()

    for inst in order:
        spec = APPLICATIONS[inst["id"]]
        docs, reg, faculty, extra, idx = built[inst["id"]]
        iu = users[inst["username"]]
        sub = datetime.fromisoformat(spec["submitted"]).replace(tzinfo=UTC) if spec["submitted"] else datetime(2026, 10, 20, 5, 0, tzinfo=UTC)
        clk.at(sub - timedelta(days=3, hours=2))
        programmes = []
        for n, lvl, i in extra["all_programmes"]:
            programmes.append({"name": n, "level": lvl, "intake_requested": (spec.get("requested") or {}).get(n, i)})
        total = sum(p["intake_requested"] for p in programmes)
        app = Application(id=spec["id"], institution_id=inst["id"], app_type=spec["app_type"], cycle=s.current_cycle,
                          status="DRAFT", created_at=clk(),
                          form={"programmes": programmes, "fire_noc_valid_till": spec.get("form_fire", spec["fire_till"]),
                                "built_up_area_m2": spec.get("form_area", spec.get("bcc_area", extra["area"])),
                                "computer_count": spec.get("computers", math.ceil(total / 2) + 12),
                                "land_area_acres": extra["land_area"], "principal_name": inst["principal"],
                                "contact_email": f"principal@{inst['username'].replace('.', '-')}.example.com"})
        db.add(app)
        db.commit()
        audit.record("Application created", "application", app.id, user=iu, application_id=app.id)
        only = spec.get("only")
        photo_limit = 2
        if only:
            photo_limit = int(next((o.split(":")[1] for o in only if o.startswith("LAB_PHOTO")), "0"))
        added_photos = 0
        for slot, name, data in docs:
            if only and slot != "LAB_PHOTO" and slot not in only:
                continue
            if slot == "LAB_PHOTO":
                if added_photos >= photo_limit:
                    continue
                added_photos += 1
            doc = add_document(db, app, slot, name, data, iu)
            orchestrator.process_document_job(doc.id)
        clear_jobs(db, app.id)
        if spec["submitted"]:
            clk.at(sub)
            db.refresh(app)
            app.status, app.submitted_at = "UNDER_SCRUTINY", sub
            db.commit()
            audit.record("Application submitted", "application", app.id, user=iu, application_id=app.id)
        orchestrator.run_precheck_job(app.id, "submitted" if spec["submitted"] else "document processed")
        clear_jobs(db, app.id)
        db.expire_all()
        app = db.get(Application, app.id)
        scrutinizer = users["r.iyer"] if inst["region"] in ("South-Western", "Central") else users["a.kulkarni"]
        if spec["submitted"]:
            app.assigned_to = scrutinizer.id
            db.commit()
        print(f"  {app.id}  {inst['name']:<42} {app.status:<18} risk {app.risk_score:>3}  {app.overall_status}")
    # decisions and letters happen after the submission window closes
    for inst, when in (("INST-KSM", datetime(2026, 4, 20, 5, 30, tzinfo=UTC)), ("INST-WGP", datetime(2026, 4, 21, 6, 10, tzinfo=UTC))):
        inst = next(i for i in INSTITUTIONS if i["id"] == inst)
        spec = APPLICATIONS[inst["id"]]
        app = db.get(Application, spec["id"])
        scrutinizer = db.get(User, app.assigned_to)
        outcome = spec["outcome"]
        clk.at(when)
        findings = db.execute(select(Finding).where(Finding.application_id == app.id, Finding.status == "OPEN")).scalars().all()
        for f in findings:
            if outcome == "approved" or f.severity in ("warning", "high", "critical"):
                f.status, f.decision_by, f.decided_at = "ACCEPTED", scrutinizer.id, clk()
                f.decision_note = "Checked against the document" if outcome == "approved" else "Ask the institution to rectify"
                audit.record("Finding accepted", "finding", f"F-{f.id:04d}", user=scrutinizer, application_id=app.id,
                             details={"title": f.title})
        db.commit()
        if outcome == "approved":
            clk.at(when + timedelta(hours=5))
            app.status = "DECIDED"
            app.decision = {"decision": "APPROVED", "label": "Approved", "note": "All documents verified; no deficiencies.",
                            "by": users["r.menon"].full_name, "at": clk().isoformat()}
            db.commit()
            audit.record("Decision recorded", "application", app.id, user=users["r.menon"], application_id=app.id,
                         details={"decision": "Approved"})
        else:
            accepted = [f for f in findings if f.status == "ACCEPTED"]
            letter = Letter(id=f"DL-{app.id[4:]}-01", application_id=app.id, status="ISSUED", drafted_by=scrutinizer.id,
                            approved_by=users["r.menon"].id, created_at=clk(), issued_at=clk(),
                            items=[{"finding_id": f.id, "title": f.title, "text": f"{f.title}. {f.message}"} for f in accepted],
                            note="Reply within 15 days with the corrected documents.")
            db.add(letter)
            app.status = "DEFICIENCY_ISSUED"
            db.commit()
            audit.record("Letter drafted", "letter", letter.id, user=scrutinizer, application_id=app.id, details={"items": len(accepted)})
            audit.record("Letter issued", "letter", letter.id, user=users["r.menon"], application_id=app.id)
            raise_alert(db, "warning", "letter_issued", f"Deficiency letter {letter.id} has been issued for {app.id}. "
                        "Reply with corrected documents.", f"institution:{inst['id']}", app.id)
            db.commit()
        print(f"  {app.id} -> {app.status}")
    db.execute(delete(Job))
    db.commit()
    db.close()
    clock.set_clock(None)
    verify.set_client(None)
    s.job_mode = previous_mode
    print(f"\nDemo password for every account: {DEMO_PASSWORD}")


if __name__ == "__main__":
    print("Seeding PRAMAAN demo data (synthetic)…")
    main()
