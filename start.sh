#!/usr/bin/env bash
# start.sh — bring up the car-recsys stack in one shot.
# Idempotent: anything already initialized / running is skipped.
#
# Order:
#   1. car-recsys-system .env  (copy from example if missing)
#   2. full stack              (postgres + qdrant + redis + postgrest + temporal
#                               + temporal-ui [+ backend + frontend])
#
# Orchestration is Temporal (self-hosted). The worker runs on the HOST, not in
# Docker — see crawler/temporal_app/README.md — because the crawler needs Chrome
# via Xvfb, which can't solve cars.com's Turnstile inside a container.
#
# Flags:
#   --skip-app   skip the backend + frontend containers (infra only)
#   -h, --help   this help
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

# ---- pretty output ---------------------------------------------------------
C_B='\033[1;34m'; C_G='\033[1;32m'; C_Y='\033[1;33m'; C_R='\033[1;31m'; C_O='\033[0m'
say()  { printf "\n${C_B}▸ %s${C_O}\n" "$*"; }
ok()   { printf "${C_G}  ✓ %s${C_O}\n" "$*"; }
warn() { printf "${C_Y}  ! %s${C_O}\n" "$*"; }
die()  { printf "${C_R}  ✗ %s${C_O}\n" "$*" >&2; exit 1; }

# ---- flags ----------------------------------------------------------------
SKIP_APP=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-app) SKIP_APP=1; shift ;;
        -h|--help)  sed -n '3,/^$/p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
        *) die "unknown flag: $1 (try --help)" ;;
    esac
done

# ---- 0. preflight ---------------------------------------------------------
say "preflight"
command -v docker >/dev/null            || die "docker not installed"
docker compose version >/dev/null 2>&1  || die "docker compose v2 not found"
docker info >/dev/null 2>&1             || die "docker daemon not reachable"
ok "docker $(docker version --format '{{.Client.Version}}') ok"

if [ ! -f "$HOME/.config/gcloud/application_default_credentials.json" ]; then
    warn "GCS ADC missing — load_bronze will fail until you run:"
    warn "    gcloud auth application-default login"
fi

# ---- 1. car-recsys-system .env --------------------------------------------
say "car-recsys-system/.env"
if [ ! -f "$REPO/car-recsys-system/.env" ]; then
    cp "$REPO/car-recsys-system/.env.example" "$REPO/car-recsys-system/.env"
    warn "created car-recsys-system/.env from example — set OPENAI_API_KEY + SECRET_KEY before chatbot/auth works"
else
    ok ".env present"
fi

# ---- 2. full backend stack -------------------------------------------------
# Default `docker compose up` brings up everything except the frontend (npm run
# dev) and bytebase (--profile tools): postgres, qdrant, redis, temporal,
# temporal-ui, postgrest, backend, pipeline-worker.
say "backend stack (db + cache + vectors + Temporal + worker + API)"
cd "$REPO/car-recsys-system"
if [ "$SKIP_APP" = 1 ]; then
    docker compose up -d postgres postgrest qdrant redis temporal temporal-ui pipeline-worker
else
    docker compose up -d
fi
printf '  waiting for postgres'
until docker compose exec -T postgres pg_isready -U admin >/dev/null 2>&1; do
    printf '.'; sleep 2
done
printf ' ready\n'
ok "backend stack up"

# ---- summary ---------------------------------------------------------------
cat <<EOF

═══════════════════════════════════════════════════════════
  BACKEND STACK READY (pipeline-worker included)
═══════════════════════════════════════════════════════════
  Temporal UI        http://localhost:8233
  Backend API docs   http://localhost:8000/docs
  PostgREST          http://localhost:3001
  Qdrant             http://localhost:6333

  frontend (host):   cd car-recsys-system/frontend && npm run dev   → :3000

  Transform / ML run in the Dockerized pipeline-worker. Trigger them:
    crawler/.venv/bin/python -m temporal_app.scripts.trigger_once transform
    crawler/.venv/bin/python -m temporal_app.scripts.trigger_once ml

  Crawling needs Chrome on the HOST (not Docker) — start its worker when needed:
    cd crawler && ./run_worker.sh
    crawler/.venv/bin/python -m temporal_app.scripts.trigger_once crawl

  Register weekly schedules (crawl + transform + ml):
    crawler/.venv/bin/python -m temporal_app.scripts.create_schedule

  see crawler/temporal_app/README.md for full details.

EOF
