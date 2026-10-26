#!/usr/bin/env bash
# Set up PRAMAAN on an Ubuntu/Debian server with Docker. Run from the repository folder:
#
#   sudo bash deploy/setup.sh --domain pramaan-demo.centralindia.cloudapp.azure.com --demo
#
#   --domain HOST   serve https://HOST with an automatic certificate (ports 80 and 443 must be open
#                   and HOST must point at this server). Without it the site is plain http://SERVER-IP:8080
#   --demo          load the synthetic demo data (only into an empty database) and list the demo
#                   accounts on the sign-in page
#
# Safe to run again: secrets in .env are kept, and existing data is never wiped.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; }

DOMAIN=""
DEMO=false
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="${2:?--domain needs a hostname}"; shift 2 ;;
    --demo) DEMO=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo: sudo bash deploy/setup.sh $*" >&2
  exit 1
fi

step() { printf '\n==> %s\n' "$1"; }

# Docker -----------------------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  step "Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is missing. Install the docker-compose-plugin package and run this again." >&2
  exit 1
fi

# .env -------------------------------------------------------------------------------------------
set_env() {  # set_env KEY VALUE: replace the line for KEY in .env, or append it
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    echo "$1=$2" >> .env
  fi
}
get_env() { grep "^$1=" .env | tail -n1 | cut -d= -f2-; }

touch .env
chmod 600 .env
step "Writing settings to .env"
[ -n "$(get_env POSTGRES_PASSWORD)" ] || set_env POSTGRES_PASSWORD "$(openssl rand -hex 16)"
[ -n "$(get_env PRAMAAN_STORAGE_KEY)" ] || set_env PRAMAAN_STORAGE_KEY "$(openssl rand -base64 32 | tr '+/' '-_')"
[ -n "$(get_env PRAMAAN_JWT_SECRET)" ] || set_env PRAMAAN_JWT_SECRET "$(openssl rand -hex 32)"
if [ -n "$DOMAIN" ]; then
  set_env PRAMAAN_DOMAIN "$DOMAIN"
  set_env COMPOSE_PROFILES https
  set_env PRAMAAN_HTTP_PORT 127.0.0.1:8080   # only Caddy is reachable from outside
  set_env PRAMAAN_CORS_ORIGINS "https://$DOMAIN"
fi
if [ "$(get_env COMPOSE_PROFILES)" = "https" ] && [ -n "$(get_env PRAMAAN_DOMAIN)" ]; then
  URL="https://$(get_env PRAMAAN_DOMAIN)"
else
  port="$(get_env PRAMAAN_HTTP_PORT)"
  port="${port##*:}"
  URL="http://<this server's public IP>:${port:-8080}"
fi
if $DEMO; then set_env PRAMAAN_SHOW_DEMO_LOGINS true; fi

# Start ------------------------------------------------------------------------------------------
step "Building and starting PRAMAAN (the first build takes several minutes)"
docker compose up -d --build --wait

if $DEMO; then
  users="$(docker compose exec -T db psql -U pramaan -d pramaan -tAc 'SELECT count(*) FROM users' | tr -d '[:space:]')"
  if [ "$users" = "0" ]; then
    step "Loading the synthetic demo data (a few minutes)"
    bash deploy/reset-demo.sh
  else
    step "The database already has $users users: demo data not reloaded (use deploy/reset-demo.sh to start over)"
  fi
fi

step "Done"
echo "PRAMAAN is running at $URL"
if $DEMO; then
  echo "Demo accounts are listed on the sign-in page; the password for all of them is Pramaan@2026"
fi
if [ "${URL#https}" != "$URL" ]; then
  echo "If HTTPS does not work yet, check that the hostname points at this server and ports 80/443 are open: docker compose logs caddy"
fi
echo "Logs: docker compose logs -f api worker"
