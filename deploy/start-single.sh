#!/bin/sh
# Entry point of the single-container image (root Dockerfile).
set -e
PORT="${PORT:-8000}"
# Issuer checks call the sandbox served by this same process.
export PRAMAAN_ISSUER_BASE_URL="${PRAMAAN_ISSUER_BASE_URL:-http://127.0.0.1:$PORT/sandbox}"
# A new token-signing secret on every start unless one is provided (signed-in users sign in again).
if [ -z "${PRAMAAN_JWT_SECRET:-}" ]; then
  PRAMAAN_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  export PRAMAAN_JWT_SECRET
fi
# One process: background jobs run on a thread inside it and SQLite has a single writer.
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 --proxy-headers --forwarded-allow-ips '*'
