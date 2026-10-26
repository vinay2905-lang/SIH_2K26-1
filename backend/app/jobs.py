"""A small, durable job queue stored in the database.

Jobs survive restarts and are visible to the UI. PostgreSQL claims jobs with
`FOR UPDATE SKIP LOCKED`, so several workers can run safely side by side.
"""
import logging
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from .config import get_settings
from .db import SessionLocal, is_postgres
from .models import Job

log = logging.getLogger("pramaan.jobs")
MAX_ATTEMPTS = 3
_wake = threading.Event()
_thread: threading.Thread | None = None
_stop = threading.Event()


def handlers():
    from .pipeline import orchestrator

    return {
        "process_document": orchestrator.process_document_job,
        "run_precheck": orchestrator.run_precheck_job,
        "dry_run": orchestrator.dry_run_job,
    }


def enqueue(kind: str, **payload) -> int:
    db = SessionLocal()
    try:
        job = Job(kind=kind, payload=payload)
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()
    mode = get_settings().job_mode
    if mode == "sync":
        run_job(job_id)
    elif mode == "thread":
        start_thread_worker()
        _wake.set()
    return job_id


def _claim_next() -> int | None:
    db = SessionLocal()
    try:
        if is_postgres():
            job = db.execute(
                select(Job).where(Job.status == "QUEUED").order_by(Job.id).limit(1).with_for_update(skip_locked=True)
            ).scalar()
            if job is None:
                db.rollback()
                return None
            job.status, job.started_at = "RUNNING", datetime.now(timezone.utc)
            db.commit()
            return job.id
        for job_id in db.execute(select(Job.id).where(Job.status == "QUEUED").order_by(Job.id).limit(5)).scalars():
            res = db.execute(update(Job).where(Job.id == job_id, Job.status == "QUEUED")
                             .values(status="RUNNING", started_at=datetime.now(timezone.utc)))
            db.commit()
            if res.rowcount == 1:
                return job_id
        return None
    finally:
        db.close()


def run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status, job.attempts = "RUNNING", job.attempts + 1
        job.started_at = job.started_at or datetime.now(timezone.utc)
        db.commit()
        kind, payload = job.kind, dict(job.payload or {})
    finally:
        db.close()
    try:
        handlers()[kind](**payload)
        status, error = "DONE", None
    except Exception as exc:  # recorded on the job row and retried
        log.error("job %s (%s) failed: %s", job_id, kind, exc)
        status, error = "FAILED", traceback.format_exc()[-4000:]
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if status == "FAILED" and job.attempts < MAX_ATTEMPTS and get_settings().job_mode != "sync":
            status = "QUEUED"
        job.status, job.error, job.finished_at = status, error, datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def requeue_stale(minutes: int = 10) -> None:
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        db.execute(update(Job).where(Job.status == "RUNNING", Job.started_at < cutoff).values(status="QUEUED"))
        db.commit()
    finally:
        db.close()


def work_forever(poll_seconds: float = 1.0) -> None:
    requeue_stale()
    while not _stop.is_set():
        job_id = _claim_next()
        if job_id is None:
            _wake.wait(poll_seconds)
            _wake.clear()
            continue
        run_job(job_id)


def start_thread_worker() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=work_forever, name="pramaan-jobs", daemon=True)
        _thread.start()


def stop_thread_worker() -> None:
    _stop.set()
    _wake.set()


def wait_idle(timeout: float = 120.0) -> bool:
    """Block until no queued or running jobs remain (used by seeding and tests)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        db = SessionLocal()
        try:
            busy = db.execute(select(Job.id).where(Job.status.in_(["QUEUED", "RUNNING"])).limit(1)).scalar()
        finally:
            db.close()
        if busy is None:
            return True
        time.sleep(0.3)
    return False
