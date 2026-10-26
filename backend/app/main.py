"""PRAMAAN API: AI-assisted pre-scrutiny for AICTE approval applications."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import jobs
from .api import applications, auth, insights, rules
from .config import get_settings
from .db import SessionLocal, init_db
from .pipeline.ingest import ocr_available
from .pipeline.orchestrator import published_rulebook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().check_production()
    init_db()
    db = SessionLocal()
    try:
        published_rulebook(db, get_settings().current_cycle)
    finally:
        db.close()
    if get_settings().job_mode == "thread":
        jobs.start_thread_worker()
    yield
    jobs.stop_thread_worker()


app = FastAPI(title="PRAMAAN API", version="1.0.0", lifespan=lifespan,
              description="Evidence-linked AI pre-scrutiny for AICTE approval applications. Decision support only.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


for r in (auth.router, applications.router, insights.router, rules.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "ocr": ocr_available(),
            "job_mode": get_settings().job_mode}


if get_settings().mount_sandbox:
    from .sandbox.main import app as sandbox_app

    app.mount("/sandbox", sandbox_app)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "sandbox/")):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        file = FRONTEND_DIST / path
        if path and file.is_file() and FRONTEND_DIST in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
