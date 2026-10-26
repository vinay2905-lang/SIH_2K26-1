"""Verification adapters: confirm documents with the authority that issued them.

Each adapter returns one of: VERIFIED, MISMATCH, EXPIRED, PENDING, SOURCE_UNAVAILABLE, MANUAL_REVIEW, with
the source, method, the fields compared and the raw response, so every result is traceable.
"""
import time
from dataclasses import dataclass, field
from datetime import date

import httpx
from rapidfuzz import fuzz

from ..config import get_settings
from .rules_engine import _norm_text

STATUSES = ("VERIFIED", "MISMATCH", "EXPIRED", "PENDING", "SOURCE_UNAVAILABLE", "MANUAL_REVIEW")
QR_PREFIX = "PRAMAAN-SANDBOX|"


@dataclass
class VResult:
    doc_type: str
    source: str
    method: str
    status: str
    reference: str | None = None
    compared: list = field(default_factory=list)
    response: dict | None = None
    note: str = ""
    attempts: int = 1
    latency_ms: int | None = None


class SourceUnavailable(Exception):
    def __init__(self, msg: str, attempts: int, latency_ms: int):
        super().__init__(msg)
        self.attempts, self.latency_ms = attempts, latency_ms


_client: httpx.Client | None = None


def set_client(c: httpx.Client | None) -> None:
    """Tests inject an in-process client; production uses ISSUER_BASE_URL."""
    global _client
    _client = c


def client() -> httpx.Client:
    global _client
    if _client is None:
        s = get_settings()
        _client = httpx.Client(base_url=s.issuer_base_url, timeout=s.issuer_timeout_s)
    return _client


def call(path: str, params: dict) -> tuple[int, dict | None, int, int]:
    s = get_settings()
    attempts, start, last_err = 0, time.monotonic(), ""
    for attempt in range(1, max(1, s.issuer_retries) + 1):
        attempts = attempt
        try:
            r = client().get(path, params=params)
            if r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
            else:
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
                return r.status_code, body, attempts, int((time.monotonic() - start) * 1000)
        except httpx.HTTPError as exc:
            last_err = type(exc).__name__
        time.sleep(0.15 * attempt)
    raise SourceUnavailable(last_err, attempts, int((time.monotonic() - start) * 1000))


def _cmp(name: str, registry, submitted, kind: str = "text") -> dict:
    if submitted in (None, ""):
        return {"field": name, "registry": registry, "submitted": None, "match": None}
    if kind == "fuzzy":
        ok = fuzz.token_set_ratio(_norm_text(registry), _norm_text(submitted)) >= 85
    elif kind == "number":
        try:
            ok = abs(float(str(registry).replace(",", "")) - float(str(submitted).replace(",", ""))) < 0.5
        except ValueError:
            ok = False
    else:
        ok = _norm_text(registry) == _norm_text(submitted)
    return {"field": name, "registry": registry, "submitted": submitted, "match": ok}


def _reference(qr: str | None, doc_type: str, fields: dict, field_name: str) -> tuple[str | None, str]:
    if qr and qr.startswith(QR_PREFIX):
        parts = qr.split("|")
        if len(parts) >= 3 and parts[1] == doc_type:
            return parts[2], "QR code"
    value = fields.get(field_name)
    return (value, "Reference number") if value else (None, "Reference number")


def _registry_check(doc_type, source, path, param, ref, method, compare_fn, as_of: date, expiry_key=None) -> VResult:
    if not ref:
        return VResult(doc_type, source, method, "MANUAL_REVIEW", note="Reference number could not be read; confirm manually.")
    try:
        code, body, attempts, ms = call(path, {param: ref})
    except SourceUnavailable as exc:
        return VResult(doc_type, source, method, "SOURCE_UNAVAILABLE", ref, attempts=exc.attempts, latency_ms=exc.latency_ms,
                       note=f"{source} did not respond ({exc}) after {exc.attempts} attempts; routed to manual review.")
    if code == 404:
        return VResult(doc_type, source, method, "MISMATCH", ref, attempts=attempts, latency_ms=ms,
                       note=f"{source} has no record for {ref}.")
    if code != 200 or body is None:
        return VResult(doc_type, source, method, "MANUAL_REVIEW", ref, attempts=attempts, latency_ms=ms,
                       note=f"Unexpected answer from {source} (HTTP {code}).")
    compared = compare_fn(body)
    bad = [c for c in compared if c["match"] is False]
    if bad:
        detail = "; ".join(f"{c['field']}: issuer has {c['registry']}, document shows {c['submitted']}" for c in bad)
        return VResult(doc_type, source, method, "MISMATCH", ref, compared, body, f"Differs from {source}: {detail}.", attempts, ms)
    if expiry_key and body.get(expiry_key):
        try:
            if date.fromisoformat(body[expiry_key]) < as_of:
                return VResult(doc_type, source, method, "EXPIRED", ref, compared, body,
                               f"{source} confirms the document, but it expired on "
                               f"{date.fromisoformat(body[expiry_key]):%d-%m-%Y}.", attempts, ms)
        except ValueError:
            pass
    return VResult(doc_type, source, method, "VERIFIED", ref, compared, body, f"Matches {source}.", attempts, ms)


def verify_document(doc_type: str, fields: dict, qr: str | None, signature: dict | None, as_of: date,
                    faculty_ids_on_record: set[str] | None = None) -> VResult | None:
    """`fields` maps field name -> normalised value for this document."""
    if doc_type == "FIRE_NOC":
        ref, method = _reference(qr, doc_type, fields, "cert_no")
        return _registry_check(doc_type, "State fire NOC registry", "/fire-noc", "cert_no", ref, method, lambda b: [
            _cmp("valid till", b.get("valid_till"), fields.get("valid_till")),
            _cmp("premises", b.get("premises_name"), fields.get("premises_name"), "fuzzy"),
        ], as_of, "valid_till")
    if doc_type == "LAND_DEED":
        ref, method = _reference(qr, doc_type, fields, "registration_no")
        return _registry_check(doc_type, "State e-registration", "/land", "registration_no", ref, method, lambda b: [
            _cmp("purchaser", b.get("owner_name"), fields.get("owner_name"), "fuzzy"),
            _cmp("survey no.", b.get("survey_no"), fields.get("survey_no")),
        ], as_of)
    if doc_type == "AFFILIATION_LETTER":
        ref, method = _reference(qr, doc_type, fields, "letter_no")

        def compare(b):
            rows = [_cmp("academic year", b.get("academic_year"), fields.get("academic_year"))]
            for p in b.get("programmes", []):
                rows.append(_cmp(f"intake {p['programme']}", p["approved_intake"], fields.get(f"intake::{p['programme']}"), "number"))
            return rows

        return _registry_check(doc_type, "Affiliating-university API", "/affiliations", "letter_no", ref, method, compare, as_of)
    if doc_type == "NBA_ACCREDITATION":
        ref, method = _reference(qr, doc_type, fields, "accreditation_no")
        return _registry_check(doc_type, "NBA", "/nba", "accreditation_no", ref, method, lambda b: [
            _cmp("valid till", b.get("valid_till"), fields.get("valid_till")),
        ], as_of, "valid_till")
    if doc_type == "TER_RECEIPT":
        ref, method = _reference(qr, doc_type, fields, "txn_id")

        def compare(b):
            rows = [_cmp("amount", b.get("amount"), fields.get("amount"), "number")]
            rows.append({"field": "payment status", "registry": b.get("status"), "submitted": "paid",
                         "match": b.get("status") == "SUCCESS"})
            return rows

        return _registry_check(doc_type, "Payment gateway", "/payments", "txn_id", ref, method, compare, as_of)
    if doc_type in ("BUILDING_COMPLETION", "STRUCTURAL_STABILITY"):
        source = "Municipal Corporation" if doc_type == "BUILDING_COMPLETION" else "Structural engineer"
        sig = signature or {}
        if not sig.get("present"):
            return VResult(doc_type, source, "Digital signature", "MANUAL_REVIEW",
                           note="Not digitally signed and no online source; confirm with the issuing office.")
        compared = [{"field": "signature intact", "registry": True, "submitted": sig.get("intact"), "match": sig.get("intact")},
                    {"field": "unchanged since signing", "registry": True,
                     "submitted": not sig.get("modified_after_signing"), "match": not sig.get("modified_after_signing")},
                    {"field": "trusted signer", "registry": True, "submitted": sig.get("trusted"), "match": sig.get("trusted")}]
        if not sig.get("intact") or sig.get("modified_after_signing"):
            status = "MISMATCH"
        elif not sig.get("trusted"):
            status = "MANUAL_REVIEW"
        else:
            status = "VERIFIED"
        return VResult(doc_type, source, "Digital signature (PKI)", status, sig.get("signer"), compared, sig,
                       sig.get("summary", ""))
    if doc_type == "AFFIDAVIT":
        return VResult(doc_type, "Notarised paper", "Manual", "MANUAL_REVIEW",
                       note="Notarised affidavit has no online source; check the notary seal and registration number.")
    if doc_type == "FACULTY_LIST":
        listed = sorted(set(fields.get("faculty_ids") or []))
        if not listed:
            return VResult(doc_type, "AICTE faculty records", "Record match", "MANUAL_REVIEW",
                           note="No faculty IDs could be read from the list.")
        known = faculty_ids_on_record or set()
        missing = [f for f in listed if f not in known]
        compared = [{"field": "faculty IDs found", "registry": len(listed) - len(missing), "submitted": len(listed),
                     "match": not missing}]
        if missing:
            return VResult(doc_type, "AICTE faculty records", "Record match", "MISMATCH", None, compared, None,
                           f"{len(missing)} of {len(listed)} faculty IDs are not in AICTE records: {', '.join(missing)}.")
        return VResult(doc_type, "AICTE faculty records", "Record match", "VERIFIED", None, compared, None,
                       f"All {len(listed)} faculty IDs found in AICTE records.")
    return None
