#!/usr/bin/env bash
# Wipe every application, document and audit event and reload the synthetic demo data.
# Run from anywhere: sudo bash deploy/reset-demo.sh   (a nightly cron entry works too, see docs/DEPLOY.md)
set -euo pipefail
cd "$(dirname "$0")/.."

# The worker is paused so it does not pick up jobs while the seed rebuilds the database.
docker compose stop worker
trap 'docker compose start worker >/dev/null' EXIT
docker compose run --rm -T api python -m app.seed --yes
echo "Demo data reloaded."
