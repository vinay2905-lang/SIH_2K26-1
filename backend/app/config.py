"""Runtime settings, read from environment variables (prefix PRAMAAN_)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEV_STORAGE_KEY = "cHJhbWFhbi1kZXYta2V5LWNoYW5nZS1tZS0xMjM0NTY="
DEV_JWT_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRAMAAN_", env_file=".env", extra="ignore")

    # "production" refuses to start with the built-in development secrets
    env: str = "development"

    # Storage and database
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'pramaan.db'}"
    data_dir: Path = BACKEND_DIR / "data"
    # 32-byte key, base64 (urlsafe). Documents are encrypted at rest with AES-256-GCM.
    storage_key: str = DEV_STORAGE_KEY

    # Auth
    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_minutes: int = 12 * 60

    # Jobs: "worker" = a separate `python -m app.worker` process polls the jobs table;
    # "thread" = the API process runs jobs in a background thread (single-process dev mode);
    # "sync" = run immediately inside the request (tests).
    job_mode: str = "thread"

    # Issuer verification sandbox (mock issuing authorities)
    issuer_base_url: str = "http://127.0.0.1:8000/sandbox"
    mount_sandbox: bool = True
    issuer_timeout_s: float = 3.0
    issuer_retries: int = 3

    # Uploads
    max_upload_mb: int = 10
    ocr_languages: str = "eng+hin"
    # Path to tesseract(.exe) when it is not on PATH. On Windows the default install folder is found automatically.
    tesseract_cmd: str = ""

    # List the demo accounts on the sign-in page. Turn this off for any real deployment.
    show_demo_logins: bool = True

    # Rule/process defaults
    current_cycle: str = "2026-27"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Extra allowed origins as a regular expression, e.g. Vercel preview URLs: https://pramaan-[a-z0-9-]+\.vercel\.app
    cors_origin_regex: str = ""


    def check_production(self) -> None:
        if self.env != "production":
            return
        if self.storage_key == DEV_STORAGE_KEY or self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            raise RuntimeError("PRAMAAN_ENV=production needs your own PRAMAAN_STORAGE_KEY and a PRAMAAN_JWT_SECRET "
                               "of at least 32 characters (see .env.example)")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
