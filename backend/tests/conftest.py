"""Test setup: a throwaway data folder and database, jobs run synchronously, the issuer sandbox runs in-process.

Set PRAMAAN_TEST_DATABASE_URL (e.g. postgresql+psycopg://...) to run the whole suite against PostgreSQL.
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="pramaan-test-"))
os.environ["PRAMAAN_DATA_DIR"] = str(TMP)
os.environ["PRAMAAN_DATABASE_URL"] = os.environ.get("PRAMAAN_TEST_DATABASE_URL", f"sqlite:///{TMP / 'test.db'}")
os.environ["PRAMAAN_JOB_MODE"] = "sync"
os.environ["PRAMAAN_ISSUER_RETRIES"] = "2"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PASSWORD = "Pramaan@2026"


@pytest.fixture(scope="session")
def seeded():
    from app.seed.__main__ import main as seed_main
    from app.pipeline import verify
    from app.sandbox.main import app as sandbox_app

    sys.argv = ["seed"]
    seed_main()
    verify.set_client(TestClient(sandbox_app, base_url="http://sandbox"))
    yield TMP


@pytest.fixture(scope="session")
def client(seeded):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    out = {}
    for username in ("a.kulkarni", "r.iyer", "r.menon", "s.rao", "auditor", "sit.dehradun", "vce.pune", "ksm.kochi"):
        r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        out[username] = {"Authorization": f"Bearer {r.json()['token']}"}
    return out
