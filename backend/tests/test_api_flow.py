"""End-to-end flows through the HTTP API, in order: seeded outcomes, access control, an institution completing and
submitting a draft, scrutiny, a deficiency letter, a reply, the final decision, the rulebook lifecycle and the audit chain."""
import io

import pytest

STATE = {}


def rules_of(client, headers, app_id):
    detail = client.get(f"/api/applications/{app_id}", headers=headers).json()
    return detail, {f["rule_id"] for f in detail["findings"]}


# ------------------------------------------------------------ seeded data --
def test_seeded_cases_raise_the_planted_findings(client, tokens):
    h = tokens["a.kulkarni"]
    _, vce = rules_of(client, h, "APP-2026-00045")
    assert {"CHECKLIST", "FIRE-NOC-01", "FIRE-NOC-02", "INTAKE-03", "INTAKE-04", "FAC-01", "FORENSIC-DUPLICATE"} <= vce
    _, git = rules_of(client, h, "APP-2026-00150")
    assert {"VERIFY-01", "FORENSIC-TEXT_COVERED", "FORENSIC-EDITING_TOOL"} <= git
    detail, sie = rules_of(client, h, "APP-2026-00231")
    assert {"LAB-COMP-02", "FORENSIC-SIGNATURE_BROKEN"} <= sie
    statuses = {v["doc_type"]: v["status"] for v in detail["verifications"]}
    assert statuses["TER_RECEIPT"] == "MISMATCH" and statuses["BUILDING_COMPLETION"] == "MISMATCH"
    detail, _ = rules_of(client, h, "APP-2026-00112")
    assert {v["doc_type"]: v["status"] for v in detail["verifications"]}["AFFILIATION_LETTER"] == "SOURCE_UNAVAILABLE"
    detail = client.get("/api/applications/APP-2026-00087", headers=h).json()
    assert detail["application"]["overall_status"] == "CLEAR" and detail["application"]["status"] == "DECIDED"


def test_evidence_points_at_the_page_region(client, tokens):
    detail = client.get("/api/applications/APP-2026-00045", headers=tokens["a.kulkarni"]).json()
    f = next(f for f in detail["findings"] if f["rule_id"] == "FIRE-NOC-01")
    doc_ev = [e for e in f["evidence"] if e["kind"] == "document"]
    assert doc_ev and doc_ev[0]["bbox"] and doc_ev[0]["value"] == "31-03-2026" and doc_ev[0]["label"] == "E1"
    assert f["source_ref"].startswith("APH")


# ----------------------------------------------------------- access rules --
def test_login_and_roles(client, tokens):
    assert client.post("/api/auth/login", json={"username": "a.kulkarni", "password": "wrong"}).status_code == 401
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/dashboard", headers=tokens["vce.pune"]).status_code == 403
    assert client.get("/api/applications/APP-2026-00150", headers=tokens["vce.pune"]).status_code == 404
    assert client.get("/api/applications/APP-2026-00301", headers=tokens["a.kulkarni"]).status_code == 404  # drafts are private
    assert client.post("/api/applications/APP-2026-00045/decision", headers=tokens["a.kulkarni"],
                       json={"decision": "APPROVED", "confirm": True}).status_code == 403


def test_institutions_never_see_forensic_flags(client, tokens):
    mine = client.get("/api/applications/APP-2026-00045", headers=tokens["vce.pune"]).json()
    assert mine["findings"] and not any(f["rule_id"].startswith("FORENSIC") for f in mine["findings"])
    assert all("forensics" not in d for d in mine["documents"])


def test_documents_render_and_download_with_access_checks(client, tokens):
    detail = client.get("/api/applications/APP-2026-00045", headers=tokens["vce.pune"]).json()
    doc = next(d for d in detail["documents"] if d["slot"] == "FIRE_NOC")
    r = client.get(f"/api/documents/{doc['id']}/pages/0", headers=tokens["vce.pune"])
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get(f"/api/documents/{doc['id']}/file", headers=tokens["vce.pune"]).content[:5] == b"%PDF-"
    assert client.get(f"/api/documents/{doc['id']}/file", headers=tokens["ksm.kochi"]).status_code == 404


# --------------------------------------------------- institution completes --
def test_upload_validation(client, tokens):
    h = tokens["sit.dehradun"]
    bad = client.post("/api/applications/APP-2026-00301/documents", headers=h, data={"slot": "AFFIDAVIT"},
                      files={"file": ("x.exe", io.BytesIO(b"MZ\x90\x00binary"), "application/octet-stream")})
    assert bad.status_code == 415
    empty = client.post("/api/applications/APP-2026-00301/documents", headers=h, data={"slot": "AFFIDAVIT"},
                        files={"file": ("a.pdf", io.BytesIO(b""), "application/pdf")})
    assert empty.status_code == 422
    photo_pdf = client.post("/api/applications/APP-2026-00301/documents", headers=h, data={"slot": "LAB_PHOTO"},
                            files={"file": ("p.pdf", io.BytesIO(b"%PDF-1.4 tiny"), "application/pdf")})
    assert photo_pdf.status_code == 415
    other = client.post("/api/applications/APP-2026-00045/documents", headers=h, data={"slot": "AFFIDAVIT"},
                        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")})
    assert other.status_code == 404


def test_institution_fills_the_gaps_and_submits(client, tokens):
    h = tokens["sit.dehradun"]
    before = client.get("/api/applications/APP-2026-00301", headers=h).json()
    missing = {c["doc_type"] for c in before["checklist"] if c["state"] in ("MISSING", "INCOMPLETE")}
    assert {"STRUCTURAL_STABILITY", "AFFIDAVIT", "FACULTY_LIST", "LAB_PHOTO"} <= missing
    samples = client.get("/api/samples", headers=h).json()
    for slot in ("STRUCTURAL_STABILITY", "AFFIDAVIT", "FACULTY_LIST"):
        s = next(x for x in samples if x["slot"] == slot)
        r = client.post("/api/applications/APP-2026-00301/documents/sample", headers=h, json=s)
        assert r.status_code == 200, r.text
    photo = [x for x in samples if x["slot"] == "LAB_PHOTO"][1]
    assert client.post("/api/applications/APP-2026-00301/documents/sample", headers=h, json=photo).status_code == 200
    after = client.get("/api/applications/APP-2026-00301", headers=h).json()
    assert not [c for c in after["checklist"] if c["required"] and c["state"] in ("MISSING", "INCOMPLETE", "PROCESSING")]
    assert not any(f["rule_id"] == "CHECKLIST" for f in after["findings"])
    form = after["form"]
    form["fire_noc_valid_till"] = "2027-03-31"
    r = client.put("/api/applications/APP-2026-00301/form", headers=h, json={"form": form})
    assert r.status_code == 200, r.text
    bad = dict(form, programmes=[{"name": "B.Tech X", "intake_requested": "lots"}])
    assert client.put("/api/applications/APP-2026-00301/form", headers=h, json={"form": bad}).status_code == 422
    r = client.post("/api/applications/APP-2026-00301/submit", headers=h)
    assert r.status_code == 200 and r.json()["application"]["status"] == "UNDER_SCRUTINY"
    assert client.post("/api/applications/APP-2026-00301/submit", headers=h).status_code == 409


# --------------------------------------------------------------- scrutiny --
def test_scrutinizer_reviews_and_letter_goes_through_maker_checker(client, tokens):
    s, so = tokens["a.kulkarni"], tokens["r.menon"]
    detail = client.get("/api/applications/APP-2026-00045", headers=s).json()
    assert detail["permissions"]["draft_letter"]
    findings = {f["rule_id"]: f for f in detail["findings"]}
    fid = findings["FIRE-NOC-01"]["id"]
    assert client.post(f"/api/findings/{fid}/decision", headers=s, json={"action": "override", "note": "ok"}).status_code == 422
    r = client.post(f"/api/findings/{fid}/decision", headers=s, json={"action": "accept", "note": ""})
    assert r.status_code == 200 and r.json()["status"] == "ACCEPTED"
    for rule in ("CHECKLIST", "INTAKE-03", "FORENSIC-DUPLICATE"):
        client.post(f"/api/findings/{findings[rule]['id']}/decision", headers=s, json={"action": "accept"})
    letter = client.post("/api/applications/APP-2026-00045/letters", headers=s, json={"note": "Reply in 15 days"})
    assert letter.status_code == 200, letter.text
    letter = letter.json()
    assert any(i["title"].startswith("Verification of") for i in letter["items"])  # forensic items are worded neutrally
    assert client.post(f"/api/letters/{letter['id']}/submit", headers=s).status_code == 200
    assert client.post(f"/api/letters/{letter['id']}/review", headers=s, json={"approve": True}).status_code == 403
    r = client.post(f"/api/letters/{letter['id']}/review", headers=so, json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "ISSUED"
    STATE["letter"] = letter["id"]


def test_institution_replies_with_a_renewed_certificate(client, tokens):
    h = tokens["vce.pune"]
    detail = client.get("/api/applications/APP-2026-00045", headers=h).json()
    assert detail["application"]["status"] == "DEFICIENCY_ISSUED" and detail["letters"][0]["status"] == "ISSUED"
    assert detail["permissions"]["respond"]
    from app.seed import documents as D

    renewed = D.fire_noc(dict(state="Maharashtra", cert_no="FNOC/2026/PUN/55555", issue_date="2026-03-25",
                              premises_name="Vidyaprakash College of Engineering", address=detail["institution"]["address"],
                              built_up_area=10700, valid_from="2026-04-01", valid_till="2027-03-31", valid_label="Valid up to"))
    r = client.post("/api/applications/APP-2026-00045/documents", headers=h, data={"slot": "FIRE_NOC"},
                    files={"file": ("Fire_NOC_renewed.pdf", io.BytesIO(renewed), "application/pdf")})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/letters/{STATE['letter']}/respond", headers=h, json={"message": "Renewed Fire NOC uploaded."})
    assert r.status_code == 200 and r.json()["status"] == "RESPONDED"
    official = client.get("/api/applications/APP-2026-00045", headers=tokens["a.kulkarni"]).json()
    rules = {f["rule_id"] for f in official["findings"]}
    assert "FIRE-NOC-01" not in rules  # the renewed NOC is valid on the application date
    fire = {v["doc_type"]: v for v in official["verifications"]}["FIRE_NOC"]
    assert fire["status"] == "MISMATCH"  # not in the sandbox registry, so it cannot be confirmed


def test_decision_requires_every_blocking_finding_to_be_reviewed(client, tokens):
    s, so = tokens["a.kulkarni"], tokens["r.menon"]
    blocked = client.post("/api/applications/APP-2026-00045/decision", headers=so,
                          json={"decision": "APPROVED", "confirm": True})
    assert blocked.status_code == 409
    adverse = client.post("/api/applications/APP-2026-00045/decision", headers=so,
                          json={"decision": "NOT_APPROVED", "note": "too short", "confirm": True})
    assert adverse.status_code == 422
    detail = client.get("/api/applications/APP-2026-00045", headers=s).json()
    for f in detail["findings"]:
        if f["status"] == "OPEN" and f["severity"] in ("critical", "high"):
            r = client.post(f"/api/findings/{f['id']}/decision", headers=s,
                            json={"action": "override", "note": "Checked with the issuing office by phone"})
            assert r.status_code == 200
    r = client.post("/api/applications/APP-2026-00045/decision", headers=so,
                    json={"decision": "APPROVED_WITH_CONDITIONS", "note": "Renewed NOC to be verified on inspection", "confirm": True})
    assert r.status_code == 200 and r.json()["application"]["status"] == "DECIDED"
    alerts = client.get("/api/alerts", headers=tokens["vce.pune"]).json()
    assert any(a["kind"] == "decision" for a in alerts)


# --------------------------------------------------------------- rulebook --
def test_rulebook_draft_validation_dry_run_and_publish(client, tokens):
    admin, so = tokens["s.rao"], tokens["r.menon"]
    versions = client.get("/api/rulebook", headers=admin).json()
    live = next(v for v in versions if v["status"] == "PUBLISHED")
    draft = client.post("/api/rulebook", headers=admin, json={"base_id": live["id"], "change_note": ""})
    assert draft.status_code == 200
    draft = draft.json()
    assert client.post("/api/rulebook", headers=admin, json={"base_id": live["id"]}).status_code == 409
    content = draft["content"]
    broken = {"rules": [dict(content["rules"][0], rows=[{"when": [], "severity": "x", "category": "y", "title": ""}])]}
    r = client.put(f"/api/rulebook/{draft['id']}", headers=admin, json={"content": broken})
    assert r.status_code == 422 and r.json()["detail"]["problems"]
    rule = next(r_ for r_ in content["rules"] if r_["rule_id"] == "FAC-RATIO-01")
    rule["rows"][0]["when"][0]["value"] = 25
    r = client.put(f"/api/rulebook/{draft['id']}", headers=admin, json={"content": content,
                                                                         "change_note": "Ratio norm 1:25 for pharmacy"})
    assert r.status_code == 200
    tried = client.post(f"/api/rulebook/{draft['id']}/test", headers=admin, json={"application_id": "APP-2026-00112"}).json()
    assert not any(m["rule_id"] == "FAC-RATIO-01" for m in tried["matches"])
    assert client.post(f"/api/rulebook/{draft['id']}/dry-run", headers=admin).status_code == 200
    dry = client.get(f"/api/rulebook/{draft['id']}", headers=admin).json()["dry_run"]
    assert dry["applications"] >= 7 and dry["by_rule"]["FAC-RATIO-01"]["draft"] < dry["by_rule"]["FAC-RATIO-01"]["published"]
    assert client.post(f"/api/rulebook/{draft['id']}/submit", headers=admin).status_code == 200
    assert client.post(f"/api/rulebook/{draft['id']}/review", headers=admin, json={"approve": True}).status_code == 403
    r = client.post(f"/api/rulebook/{draft['id']}/review", headers=so, json={"approve": True, "note": "Agreed"})
    assert r.status_code == 200 and r.json()["status"] == "PUBLISHED"
    _, nvp = rules_of(client, tokens["r.iyer"], "APP-2026-00112")
    assert "FAC-RATIO-01" not in nvp  # every open application was re-checked against the new version


# ------------------------------------------------------------------ audit --
def test_dashboard_and_verification_log(client, tokens):
    d = client.get("/api/dashboard", headers=tokens["r.menon"]).json()
    assert d["kpis"]["received"] == 8 and d["kpis"]["decided"] >= 2
    assert len(d["daily"]) == 14 and d["verification_outcomes"]["VERIFIED"] > 10
    log = client.get("/api/verifications?status=SOURCE_UNAVAILABLE", headers=tokens["r.iyer"]).json()
    assert log and all(v["status"] == "SOURCE_UNAVAILABLE" for v in log)


def test_audit_chain_is_intact_then_detects_tampering(client, tokens):
    h = tokens["auditor"]
    ok = client.get("/api/audit/verify", headers=h).json()
    assert ok["valid"] and ok["events"] > 300
    events = client.get("/api/audit?application_id=APP-2026-00045&limit=500", headers=h).json()
    actions = {e["action"] for e in events}
    assert {"Document uploaded", "Text extracted", "Source response", "Finding accepted", "Letter issued",
            "Decision recorded"} <= actions
    csv = client.get("/api/audit/export.csv", headers=h)
    assert csv.status_code == 200 and csv.text.startswith("id,time_utc")

    from app.db import SessionLocal
    from app.models import AuditEvent

    with SessionLocal() as db:
        ev = db.get(AuditEvent, 5)
        original = dict(ev.details)
        ev.details = dict(original, file="changed.pdf")
        db.commit()
        broken = client.get("/api/audit/verify", headers=h).json()
        ev.details = original
        db.commit()
    assert broken == {"valid": False, "events": 5, "broken_at": 5, "reason": "event content changed"}
    assert client.get("/api/audit/verify", headers=h).json()["valid"]


@pytest.mark.parametrize("path", ["/api/health", "/sandbox/health"])
def test_health(client, path):
    assert client.get(path).status_code == 200


def test_demo_logins_can_be_hidden(client):
    from app.config import get_settings

    assert any(u["username"] == "a.kulkarni" for u in client.get("/api/auth/demo-users").json())
    settings = get_settings()
    settings.show_demo_logins = False
    try:
        assert client.get("/api/auth/demo-users").json() == []
    finally:
        settings.show_demo_logins = True
