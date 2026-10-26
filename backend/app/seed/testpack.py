"""Build a test pack of documents to upload as the demo institution `sit.dehradun` (draft APP-2026-00301).

    python -m app.seed.testpack OUTPUT_DIR

Writes:
  1-clean/                       the documents the draft is still missing (all consistent with the institution,
                                 its AICTE records and the sandbox issuers)
  1-clean/already-in-the-draft/  clean copies of the documents the draft already has, to put back after a test
  2-problems/                    one deliberate flaw per file
  README.md                      how to use the pack and what PRAMAAN reported for every file

The results are not hand-written: every file is uploaded into a throw-away copy of the demo data, the real pipeline
runs, and the findings it produces are recorded.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from ..pipeline.templates import DOC_TYPES

APP_ID = "APP-2026-00301"
INST_ID = "INST-SIT"
USERNAME = "sit.dehradun"
ALREADY = ["LAND_DEED", "BUILDING_COMPLETION", "FIRE_NOC", "AFFILIATION_LETTER", "TER_RECEIPT", "LAB_PHOTO:1"]

# (file name, slot, what is wrong with it)
PROBLEMS = [
    ("01_FIRE_NOC__expired.pdf", "FIRE_NOC", "Validity ended on 31-03-2026."),
    ("02_FIRE_NOC__date_hidden_under_white_box.pdf", "FIRE_NOC",
     "The real date (31-03-2026) is covered with a white box and 31-03-2027 is typed on top."),
    ("03_FIRE_NOC__fake_certificate_number.pdf", "FIRE_NOC", "The certificate number does not exist at the fire department."),
    ("04_FIRE_NOC__actually_a_land_deed.pdf", "FIRE_NOC", "A land deed uploaded in the Fire NOC slot."),
    ("05_BUILDING_COMPLETION__edited_after_signing.pdf", "BUILDING_COMPLETION",
     "Digitally signed, then the built-up area on it was changed (3,500 m2 added)."),
    ("06_BUILDING_COMPLETION__not_signed.pdf", "BUILDING_COMPLETION", "No digital signature."),
    ("07_AFFILIATION_LETTER__lower_intake.pdf", "AFFILIATION_LETTER",
     "The university allows 90 seats in B.Tech CSE, but the application asks for 120."),
    ("08_TER_RECEIPT__unknown_transaction.pdf", "TER_RECEIPT", "The transaction ID is not in the payment gateway's records."),
    ("09_FACULTY_LIST__unknown_faculty.pdf", "FACULTY_LIST", "Three faculty IDs are not in AICTE's faculty registry."),
    ("10_AFFIDAVIT__scanned_copy.pdf", "AFFIDAVIT", "A skewed, blurry scan with no text layer, so it has to be read by OCR."),
    ("11_LAB_PHOTO__taken_far_from_campus.jpg", "LAB_PHOTO", "The photo's GPS location is about 37 km from the campus."),
    ("12_LAB_PHOTO__copied_from_another_college.jpg", "LAB_PHOTO",
     "A re-saved copy of Wainganga Polytechnic's lab photo."),
    ("13_ANY_SLOT__not_really_a_pdf.pdf", "FIRE_NOC", "A text file renamed to .pdf."),
    ("14_LAB_PHOTO__pdf_instead_of_photo.pdf", "LAB_PHOTO", "A PDF uploaded in the photo slot."),
]


# ------------------------------------------------------------------------------------------------- generate --
def generate(out: Path) -> dict[str, tuple[str, str]]:
    """Write the files; returns {file name: (slot, relative path)} for the clean set."""
    from . import documents as D
    from . import pki
    from .__main__ import APPLICATIONS, INSTITUTIONS, build

    insts = {i["id"]: i for i in INSTITUTIONS}
    index = {inst["id"]: i for i, inst in enumerate(INSTITUTIONS, start=1)}
    inst, spec, idx = insts[INST_ID], APPLICATIONS[INST_ID], index[INST_ID]
    files = pki.create_pki(Path(tempfile.mkdtemp()) / "sandbox", Path(tempfile.mkdtemp()) / "trust")

    def variant(**changes):
        bank: dict = {}
        if changes.get("duplicate_photo_from"):
            wgp = changes["duplicate_photo_from"]
            build(insts[wgp], APPLICATIONS[wgp], index[wgp], files, bank)
        docs = build(inst, {**spec, **changes}, idx, files, bank)
        return docs[0], docs[3]

    clean, extra = variant()
    by_slot: dict[str, list[tuple[str, bytes]]] = {}
    for slot, name, data in clean:
        by_slot.setdefault(slot, []).append((name, data))

    shutil.rmtree(out, ignore_errors=True)
    (out / "1-clean" / "already-in-the-draft").mkdir(parents=True)
    (out / "2-problems").mkdir(parents=True)
    clean_index = {}
    already_photos = int(next(a.split(":")[1] for a in ALREADY if a.startswith("LAB_PHOTO")))
    for slot, items in by_slot.items():
        for k, (name, data) in enumerate(items):
            in_draft = slot in ALREADY or (slot == "LAB_PHOTO" and k < already_photos)
            rel = f"1-clean/already-in-the-draft/{name}" if in_draft else f"1-clean/{name}"
            (out / rel).write_bytes(data)
            clean_index[name] = (slot, rel)

    def pick(docs, slot, k=0):
        return [d for s, _, d in docs if s == slot][k]

    p = out / "2-problems"
    p.joinpath(PROBLEMS[0][0]).write_bytes(pick(variant(fire_till="2026-03-31")[0], "FIRE_NOC"))
    p.joinpath(PROBLEMS[1][0]).write_bytes(pick(variant(fire_till="2026-03-31", fire_tampered_to="2027-03-31")[0], "FIRE_NOC"))
    till = spec["fire_till"]
    frm = date.fromisoformat(till).replace(year=date.fromisoformat(till).year - 1)
    fake = dict(state=inst["state"], cert_no="FNOC/2025/DEH/40417", issue_date=(frm.replace(day=1)).isoformat(),
                premises_name=inst["name"], address=inst["address"], built_up_area=extra["area"],
                valid_from=frm.replace(day=1).isoformat(), valid_till=till, valid_label="Valid till")
    p.joinpath(PROBLEMS[2][0]).write_bytes(D.fire_noc(fake))
    p.joinpath(PROBLEMS[3][0]).write_bytes(by_slot["LAND_DEED"][0][1])
    p.joinpath(PROBLEMS[4][0]).write_bytes(pick(variant(bcc_modified=True)[0], "BUILDING_COMPLETION"))
    p.joinpath(PROBLEMS[5][0]).write_bytes(pick(variant(bcc_unsigned=True)[0], "BUILDING_COMPLETION"))
    p.joinpath(PROBLEMS[6][0]).write_bytes(
        pick(variant(affiliation_override={"B.Tech Computer Science and Engineering": 90})[0], "AFFILIATION_LETTER"))
    ter = dict(txn_id="TER-2026-00417", institution_name=inst["name"], amount_text="1,50,000", payment_date="2026-03-28")
    p.joinpath(PROBLEMS[7][0]).write_bytes(D.ter_receipt(ter))
    p.joinpath(PROBLEMS[8][0]).write_bytes(pick(variant(unknown_faculty=3)[0], "FACULTY_LIST"))
    p.joinpath(PROBLEMS[9][0]).write_bytes(pick(variant(scanned_affidavit=True)[0], "AFFIDAVIT"))
    p.joinpath(PROBLEMS[10][0]).write_bytes(pick(variant(photos_far=True)[0], "LAB_PHOTO", 1))
    p.joinpath(PROBLEMS[11][0]).write_bytes(pick(variant(duplicate_photo_from="INST-WGP")[0], "LAB_PHOTO", 1))
    p.joinpath(PROBLEMS[12][0]).write_bytes(b"This is a plain text file that was renamed to .pdf\n")
    p.joinpath(PROBLEMS[13][0]).write_bytes(by_slot["AFFIDAVIT"][0][1])
    return clean_index


# ------------------------------------------------------------------------------------------------- evaluate --
def evaluate(out: Path) -> dict:
    """Upload every file into a fresh copy of the demo data and record what PRAMAAN reports.
    Runs in its own process (see main) because settings are read from the environment at import time."""
    import io
    from contextlib import redirect_stdout

    from fastapi.testclient import TestClient

    from ..db import SessionLocal
    from ..models import Application
    from ..pipeline import verify
    from ..sandbox.main import app as sandbox_app
    from .__main__ import main as seed_main
    from .data import DEMO_PASSWORD

    from ..api.applications import current_findings

    sys.argv = ["seed"]
    with redirect_stdout(io.StringIO()):
        seed_main()
    verify.set_client(TestClient(sandbox_app, base_url="http://sandbox"))
    from ..main import app

    clean_index = json.loads((out / ".clean-index.json").read_text(encoding="utf-8"))
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": USERNAME, "password": DEMO_PASSWORD}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        def detail():
            return c.get(f"/api/applications/{APP_ID}", headers=h).json()

        def official_findings():
            with SessionLocal() as db:
                return [{"severity": f.severity, "title": f.title, "message": f.message, "rule_id": f.rule_id,
                         "visible_to_institution": f.visible_to_institution}
                        for f in current_findings(db, db.get(Application, APP_ID), False)]

        def upload(path: Path, slot: str):
            with path.open("rb") as fh:
                return c.post(f"/api/applications/{APP_ID}/documents", headers=h, data={"slot": slot},
                              files={"file": (path.name, fh)})

        # complete the draft with the clean files
        for name, (slot, rel) in clean_index.items():
            if not rel.startswith("1-clean/already"):
                r = upload(out / rel, slot)
                assert r.status_code == 200, (name, r.text)
        d = detail()
        baseline = {"risk": d["application"]["risk_score"], "status": d["application"]["overall_status"],
                    "institution": [(f["severity"], f["title"]) for f in d["findings"]],
                    "official": [(f["severity"], f["title"]) for f in official_findings()],
                    }
        base_keys = set(baseline["official"])

        results = []
        for fname, slot, problem in PROBLEMS:
            r = upload(out / "2-problems" / fname, slot)
            res = {"file": fname, "slot": slot, "problem": problem, "http": r.status_code}
            if r.status_code != 200:
                res["rejected"] = r.json().get("detail")
                results.append(res)
                continue
            doc = r.json()
            d = detail()
            doc = next(x for x in d["documents"] if x["id"] == doc["id"])
            res["document"] = {"status": doc["status"], "read_as": doc["detected_label"], "text_source": doc["text_source"],
                               "ocr_confidence": doc["ocr_confidence"],
                               "signature": (doc.get("signature") or {}).get("summary")}
            res["risk"], res["overall"] = d["application"]["risk_score"], d["application"]["overall_status"]
            new = [f for f in official_findings() if (f["severity"], f["title"]) not in base_keys]
            res["findings"] = new
            results.append(res)
            # put the clean document back
            if slot == "LAB_PHOTO":
                c.delete(f"/api/documents/{doc['id']}", headers=h)
            else:
                name = next(n for n, (s, _) in clean_index.items() if s == slot)
                assert upload(out / clean_index[name][1], slot).status_code == 200
        back = detail()["application"]
        after = {"risk": back["risk_score"], "status": back["overall_status"],
                 "official": [(f["severity"], f["title"]) for f in official_findings()]}
    return {"date": date.today().isoformat(), "baseline": baseline, "results": results, "after_restore": after}


# --------------------------------------------------------------------------------------------------- report --
SEV = {"critical": "Critical", "high": "High", "warning": "Warning", "info": "Info"}


def report(out: Path, clean_index: dict, ev: dict) -> str:
    when = date.fromisoformat(ev["date"]).strftime("%d-%m-%Y")
    b = ev["baseline"]
    missing = [f"`{n}` → **{DOC_TYPES[s]}**" for n, (s, rel) in clean_index.items() if not rel.startswith("1-clean/already")]
    lines = [
        "# PRAMAAN test pack",
        "",
        "Synthetic documents for trying PRAMAAN as an institution. Every certificate, name and number here is made up.",
        "",
        "## How to use it",
        "",
        "1. Sign in as **`sit.dehradun`** (password `Pramaan@2026`) and open application **APP-2026-00301**. It is a draft"
        " that still misses four documents.",
        "2. **Complete it with the files in `1-clean/`.** Use the **Upload** button next to each item:",
        "",
        *[f"   - {m}" for m in missing],
        "",
        f"   The pre-check runs after each upload. With all four, the application comes out **{b['status'].replace('_', ' ').title()}**"
        f" (risk {b['risk']}).",
        "3. **Try a problem file from `2-problems/`.** Upload it into the slot named below, then read the issues"
        " the page lists.",
        "   - **Undo it:** for a photo, remove it with the bin icon next to it. For any other document, upload the"
        " clean file from `1-clean/` or `1-clean/already-in-the-draft/` into the same slot, which replaces it.",
        "4. **See the official side.** Submit the application, then sign in as **`a.kulkarni`** and open it from the queue."
        " The scrutiny workspace shows every finding, with the evidence highlighted on the page.",
        "   - Some findings, such as suspected tampering, are shown **only to officials**. They are marked 🔒 below.",
        "   - After you submit, the application can't be edited. To start again, reload the demo data: restart the"
        " service on Render, run `python -m app.seed` locally, or run `sudo bash deploy/reset-demo.sh` on a server.",
        "",
        f"The results below were recorded on {when} by uploading each file into a fresh copy of the demo data."
        " Date checks use the day you test, so the dates in the messages will differ. A certificate close to expiry"
        " starts getting a warning 60 days before it ends.",
        "",
        "## Summary",
        "",
        "| File | Upload into | Result |",
        "|---|---|---|",
    ]
    details = ["", "## Details: what PRAMAAN says about each file", ""]
    for r in ev["results"]:
        label = DOC_TYPES[r["slot"]]
        details += [f"### `{r['file']}`", "", f"**Upload into:** {label}  ", f"**What is wrong:** {r['problem']}", ""]
        if r.get("rejected"):
            lines.append(f"| `{r['file']}` | {label} | Upload refused |")
            details += [f"The upload is refused with the message *“{r['rejected']}”*.", ""]
            continue
        top = r["findings"][0] if r["findings"] else None
        headline = f"{SEV[top['severity']]}: {top['title']}" if top else "No new finding"
        more = f" (+{len(r['findings']) - 1} more)" if len(r["findings"]) > 1 else ""
        lines.append(f"| `{r['file']}` | {label} | {'🔒 ' if top and not top['visible_to_institution'] else ''}{headline}{more}"
                     f" · risk {r['risk']} |")
        details.append(f"**Result:** risk {r['risk']}, {r['overall'].replace('_', ' ').lower()}.")
        details.append("")
        for f in r["findings"]:
            lock = "🔒 " if not f["visible_to_institution"] else ""
            details.append(f"- {lock}**{SEV[f['severity']]} · {f['title']}**: {f['message']} *(rule {f['rule_id']})*")
        doc = r["document"]
        if doc["text_source"] == "OCR" and doc["ocr_confidence"] is not None:
            details.append(f"- The file had no text layer, so it was read by OCR (confidence {doc['ocr_confidence']:.2f}).")
        if doc.get("signature"):
            details.append(f"- Digital signature: {doc['signature']}.")
        details.append("")
    lines += ["", "🔒 = shown to officials only, not to the institution.", ""]
    if b["official"]:
        lines += ["Even with the clean set, these documents have no online source to check against, so PRAMAAN asks"
                  " the officer to confirm them by hand:", ""]
        lines += [f"- **{SEV[sev]}** · {t}" for sev, t in b["official"]]
    return "\n".join(lines + details)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path)
    parser.add_argument("--evaluate-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = args.output.resolve()
    if args.evaluate_only:
        (out / ".results.json").write_text(json.dumps(evaluate(out), indent=1), encoding="utf-8")
        return

    clean_index = generate(out)
    (out / ".clean-index.json").write_text(json.dumps(clean_index), encoding="utf-8")
    work = Path(tempfile.mkdtemp(prefix="pramaan-testpack-"))
    env = {**os.environ, "PRAMAAN_DATA_DIR": str(work), "PRAMAAN_DATABASE_URL": f"sqlite:///{work / 'pramaan.db'}",
           "PRAMAAN_JOB_MODE": "sync", "PRAMAAN_ENV": "development"}
    print("Uploading every file into a fresh copy of the demo data (a few minutes)…")
    subprocess.run([sys.executable, "-m", "app.seed.testpack", str(out), "--evaluate-only"], env=env, check=True,
                   cwd=Path(__file__).resolve().parents[2])
    ev = json.loads((out / ".results.json").read_text(encoding="utf-8"))
    base, after = ev["baseline"], ev.pop("after_restore")
    if (after["risk"], after["status"], after["official"]) != (base["risk"], base["status"], base["official"]):
        raise SystemExit(f"Putting the clean files back did not restore the application: {after} != {base}")
    (out / "README.md").write_text(report(out, clean_index, ev), encoding="utf-8")
    (out / "results.json").write_text(json.dumps(ev, indent=1, ensure_ascii=False), encoding="utf-8")
    for tmp in (".results.json", ".clean-index.json"):
        (out / tmp).unlink()
    shutil.rmtree(work, ignore_errors=True)
    print(f"Test pack written to {out}")


if __name__ == "__main__":
    main()
