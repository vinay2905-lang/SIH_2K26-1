"""Database engine and session helpers (PostgreSQL in deployment, SQLite for local dev/tests)."""
from contextlib import contextmanager
from importlib import import_module

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

try:
    import fcntl
except ImportError:  # Windows: single-process SQLite only
    fcntl = None


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def is_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    import_module(f"{__package__}.models")  # registers the tables on Base

    # API processes and the worker can start together on an empty database: serialise table creation.
    if is_postgres():
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(424243)"))
            Base.metadata.create_all(conn)
        return
    with open(get_settings().data_dir / "init.lock", "a") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        Base.metadata.create_all(engine)
