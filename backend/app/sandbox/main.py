"""Issuer sandbox: stands in for issuing authorities (fire services, universities, NBA, payment gateway,
land registry) so verification can be demonstrated end to end with synthetic records.

In a real deployment each adapter in `app.pipeline.verify` points at the authority's authorised API
(for example through API Setu / DigiLocker) instead of this service.
"""
import json
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from ..config import get_settings

app = FastAPI(title="PRAMAAN issuer sandbox", description="Synthetic issuing-authority records for demos and tests")


def registry_path() -> Path:
    return get_settings().data_dir / "sandbox" / "registry.json"


@lru_cache(maxsize=1)
def _load(mtime: float) -> dict:
    path = registry_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def registry() -> dict:
    path = registry_path()
    return _load(path.stat().st_mtime if path.exists() else 0.0)


def _get(section: str, key: str) -> dict:
    record = registry().get(section, {}).get(key)
    if record is None:
        raise HTTPException(404, "No record for this reference number")
    return record


@app.get("/health")
def health():
    return {"status": "ok", "records": {k: len(v) for k, v in registry().items() if isinstance(v, dict)}}


@app.get("/fire-noc")
def fire_noc(cert_no: str = Query(..., max_length=60)):
    return _get("fire_noc", cert_no)


@app.get("/land")
def land(registration_no: str = Query(..., max_length=60)):
    return _get("land", registration_no)


@app.get("/affiliations")
def affiliation(letter_no: str = Query(..., max_length=60)):
    record = _get("affiliations", letter_no)
    if record.get("university") in registry().get("outages", []):
        time.sleep(0.05)
        raise HTTPException(503, "University service temporarily unavailable")
    return record


@app.get("/nba")
def nba(accreditation_no: str = Query(..., max_length=60)):
    return _get("nba", accreditation_no)


@app.get("/payments")
def payments(txn_id: str = Query(..., max_length=60)):
    return _get("payments", txn_id)
