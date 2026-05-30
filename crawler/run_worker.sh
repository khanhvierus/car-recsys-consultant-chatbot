#!/usr/bin/env bash
# Run the Temporal worker on the local host against a SELF-HOSTED Temporal
# server (see car-recsys-system/docker-compose.yml: temporal + temporal-ui).
#
# Connection (no TLS for local self-host):
#   TEMPORAL_ADDRESS    default localhost:7233
#   TEMPORAL_NAMESPACE  default "default"
#
# Pipeline env (only needed for transform/ml workflows — crawler ignores them):
#   WAREHOUSE_DSN       postgresql://admin:admin123@localhost:5432/car_recsys
#   DBT_DIR             /abs/path/to/car-recsys-system/dbt
#   MATVIEWS_SQL        /abs/path/to/car-recsys-system/database/matviews.sql
#   QDRANT_URL          http://localhost:6333
#   OPENAI_API_KEY      sk-...   (embed_vehicles skips if unset)
#   GOOGLE_APPLICATION_CREDENTIALS  /abs/path/to/gcp-sa.json (load_bronze/upload)
set -euo pipefail

cd "$(dirname "$0")"

# Load .env if present.
if [ -f temporal_app/.env ]; then
  set -a; . temporal_app/.env; set +a
fi

# venv shared with run_local.sh + pipeline/worker deps.
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi
.venv/bin/pip install -q -r requirements.txt -r temporal_app/requirements.txt

# Data layout — same as run_local.sh.
export DATA_ROOT="${DATA_ROOT:-$PWD/local_data}"
export LINK_FOLDER="$DATA_ROOT/car_links"
export RAW_DATA_DIR="$DATA_ROOT/raw_data"
export IMG_BASE_DIR="$DATA_ROOT/downloaded_images"
mkdir -p "$LINK_FOLDER" "$RAW_DATA_DIR" "$IMG_BASE_DIR"

# Browser mode — xvfb by default (no window, works on headless laptops too).
export BROWSER_MODE="${BROWSER_MODE:-xvfb}"
case "$BROWSER_MODE" in
  xvfb)     export HEADLESS=false; export USE_XVFB=true ;;
  gui)      export HEADLESS=false; export USE_XVFB=false ;;
  headless) export HEADLESS=true;  export USE_XVFB=false ;;
esac

# Single browser only.
export MAX_BROWSER_WORKERS=1
export CHROME_BINARY="${CHROME_BINARY:-/usr/bin/google-chrome}"
export PYTHONPATH="$PWD"

# Corporate CA bundle (for googlechromelabs.github.io + others).
if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi

exec .venv/bin/python -m temporal_app.worker
