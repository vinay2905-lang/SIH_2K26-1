"""Document reading, extraction and forensic checks on the synthetic samples produced by the seed."""
from datetime import date

import pytest

from app.pipeline import classify, extract, forensics, ingest, qr, signatures, verify
from app.pipeline.templates import DOC_TYPES
from app.seed import documents as D
from app.seed import pki

FIRE = dict(state="Rajasthan", cert_no="FNOC/2025/JAI/20411", issue_date="2025-03-20", premises_name="Gulmohar Institute of Technology",
            address="Plot 7, Sitapura Institutional Area, Jaipur 302022", built_up_area=15200, valid_from="2025-04-01",
            valid_till="2026-03-31")


def read(data, doc_type=None, state="RJ"):
    ing = ingest.ingest(data)
    detected, conf, _ = classify.classify(ing)
    fields = {f.name: f for f in extract.extract(ing, doc_type or detected, state)}
    return ing, detected, conf, fields


def test_fire_noc_fields_and_qr():
    pdf = D.fire_noc(FIRE)
    ing, detected, conf, fields = read(pdf)
    assert detected == "FIRE_NOC" and conf > 0.6
    assert fields["valid_till"].normalized == "2026-03-31"
    assert fields["premises_name"].value == FIRE["premises_name"]
    assert fields["valid_till"].bbox and fields["valid_till"].confidence > 0.9
    assert qr.read_qr(pdf) == "PRAMAAN-SANDBOX|FIRE_NOC|FNOC/2025/JAI/20411"
    assert forensics.pdf_signals(ing, list(fields.values()), None) == []


def test_state_template_variant():
    pdf = D.fire_noc(dict(FIRE, state="Maharashtra", valid_label="Valid up to"))
    _, _, _, fields = read(pdf, state="MH")
    assert fields["valid_till"].normalized == "2026-03-31"


def test_white_box_forgery_is_detected_and_visible_value_is_read():
    forged = D.tamper_cover_text(D.fire_noc(FIRE), "31-03-2026", "31-03-2027")
    ing, _, _, fields = read(forged)
    assert fields["valid_till"].normalized == "2027-03-31"  # what a reader sees
    codes = {s["code"] for s in forensics.pdf_signals(ing, list(fields.values()), None)}
    assert {"TEXT_COVERED", "EDITING_TOOL", "EDITED_LATER"} <= codes
    assert ing.hidden_text[0]["hidden_text"] == "31-03-2026"


def test_digital_signature_states(tmp_path):
    files = pki.create_pki(tmp_path / "pki", tmp_path / "trust")
    from app.config import get_settings

    trust = get_settings().data_dir / "trust"
    trust.mkdir(parents=True, exist_ok=True)
    (trust / "test-root.pem").write_bytes(files["ca_cert"].read_bytes())
    pdf = D.building_completion(dict(city="Pune", cert_no="BCC/2003/PUN/101", issue_date="2003-06-12",
                                     premises_name="Test College", address="Pune", built_up_area=12000))
    assert signatures.check_signature(pdf) == {"present": False}
    signed = pki.sign_pdf(pdf, files)
    ok = signatures.check_signature(signed)
    assert ok["present"] and ok["intact"] and ok["trusted"] and not ok["modified_after_signing"]
    changed = signatures.check_signature(pki.modify_after_signing(signed, "12,000 m2", "15,500 m2"))
    assert changed["modified_after_signing"] is True
    v = verify.verify_document("BUILDING_COMPLETION", {}, None, changed, date(2026, 4, 1))
    assert v.status == "MISMATCH"


def test_scanned_document_needs_ocr():
    scan = D.scanned(D.affidavit(dict(deponent="Dr. Test Person", institution_name="Test College", date="2026-04-02",
                                      notary_reg_no="MP/NOT/2231")))
    ing, detected, _, _ = read(scan)
    if not ingest.ocr_available():
        pytest.skip("Tesseract not installed")
    assert ing.text_source == "OCR"
    assert detected == "AFFIDAVIT"
    assert ing.ocr_confidence is not None and ing.ocr_confidence < 0.8


def test_every_sample_document_is_classified_correctly(seeded):
    root = seeded / "samples"
    checked = 0
    for slot_dir in root.glob("*/*"):
        for f in slot_dir.iterdir():
            ing = ingest.ingest(f.read_bytes())
            if ing.text_source == "NONE" and not ingest.ocr_available():
                continue  # a scan without Tesseract goes to manual review instead (covered above)
            detected, _, _ = classify.classify(ing)
            assert detected == slot_dir.name, f"{f} read as {detected}"
            checked += 1
    assert checked >= 60
    assert set(p.name for p in root.glob("*/*")) <= set(DOC_TYPES)


def test_photo_metadata_and_duplicate_hash():
    from datetime import datetime

    import imagehash

    a = D.lab_photo(11, (18.59, 73.74), datetime(2026, 3, 10, 11, 20))
    b = D.lab_photo(12, (18.59, 73.74), datetime(2026, 3, 10, 11, 20))
    copy = D.recapture(a, (10.0, 76.3), datetime(2026, 3, 12))
    info_a, _ = forensics.photo_info(ingest.ingest(a).image, a)
    info_b, _ = forensics.photo_info(ingest.ingest(b).image, b)
    info_c, _ = forensics.photo_info(ingest.ingest(copy).image, copy)
    assert abs(info_a["gps_lat"] - 18.59) < 0.001 and info_a["taken_at"].startswith("2026-03-10")
    h = imagehash.hex_to_hash
    assert h(info_a["phash"]) - h(info_c["phash"]) <= 6
    assert h(info_a["phash"]) - h(info_b["phash"]) > 6


def test_signature_check_inside_a_running_event_loop(seeded):
    # Jobs run inline (sync mode) are called from async endpoints; pyHanko's sync API must still work there.
    import asyncio

    pdf = (seeded / "samples" / "INST-SIT" / "BUILDING_COMPLETION" / "Building_completion_certificate.pdf").read_bytes()

    async def check():
        return signatures.check_signature(pdf)

    result = asyncio.run(check())
    assert result["intact"] and result["trusted"] and not result["modified_after_signing"], result
