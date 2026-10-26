"""API processes and the worker start together on an empty database: none of them may crash."""
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[1]
STARTUP = """
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.pipeline.orchestrator import published_rulebook
init_db()
with SessionLocal() as db:
    published_rulebook(db, get_settings().current_cycle)
"""


def test_concurrent_startup_on_empty_database():
    data_dir = Path(tempfile.mkdtemp(prefix="pramaan-startup-"))
    base_url = os.environ.get("PRAMAAN_TEST_DATABASE_URL")
    schema = None
    if base_url:  # PostgreSQL: a throwaway schema stands in for an empty database
        schema = f"startup_{uuid.uuid4().hex[:8]}"
        with create_engine(base_url).begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        url = f"{base_url}{'&' if '?' in base_url else '?'}options=-csearch_path%3D{schema}"
    else:
        url = f"sqlite:///{data_dir / 'startup.db'}"
    env = {**os.environ, "PRAMAAN_DATABASE_URL": url, "PRAMAAN_DATA_DIR": str(data_dir)}
    try:
        procs = [subprocess.Popen([sys.executable, "-c", STARTUP], cwd=BACKEND, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(6)]
        results = [(p.wait(timeout=120), p.stderr.read()) for p in procs]
        for code, err in results:
            assert code == 0, err[-1500:]
        with create_engine(url).connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM rulebook_versions WHERE status = 'PUBLISHED'")).scalar() == 1
    finally:
        if schema:
            with create_engine(base_url).begin() as conn:
                conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))


def test_production_refuses_development_secrets():
    from app.config import Settings

    Settings(env="development").check_production()
    with pytest.raises(RuntimeError):
        Settings(env="production").check_production()
    with pytest.raises(RuntimeError):
        Settings(env="production", storage_key="a2V5LWtleS1rZXkta2V5LWtleS1rZXkta2V5LWtleS0=", jwt_secret="short").check_production()
    Settings(env="production", storage_key="a2V5LWtleS1rZXkta2V5LWtleS1rZXkta2V5LWtleS0=", jwt_secret="x" * 40).check_production()
