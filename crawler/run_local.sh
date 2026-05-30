#!/usr/bin/env bash
# Run the crawler on the host (no Docker, no Airflow).
# Uses real X display when available — best Cloudflare-bypass rate, lowest RAM.
#
# Usage:
#   ./run_local.sh crawl-links   --page 1
#   ./run_local.sh scrape-detail --page 1
#   ./run_local.sh full          --page 1
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating .venv..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install seleniumbase beautifulsoup4 requests lxml google-cloud-storage
fi

# Local data layout (host, not /data).
export DATA_ROOT="${DATA_ROOT:-$PWD/local_data}"
export LINK_FOLDER="$DATA_ROOT/car_links"
export RAW_DATA_DIR="$DATA_ROOT/raw_data"
export IMG_BASE_DIR="$DATA_ROOT/downloaded_images"
mkdir -p "$LINK_FOLDER" "$RAW_DATA_DIR" "$IMG_BASE_DIR"

# Browser mode — choose one (override with env var):
#   BROWSER_MODE=xvfb     virtual display, no window pops up, best for Cloudflare (default)
#   BROWSER_MODE=gui      real GUI on $DISPLAY, window visible — best bypass rate
#   BROWSER_MODE=headless no display at all, lightest but easier for sites to detect
BROWSER_MODE="${BROWSER_MODE:-xvfb}"
case "$BROWSER_MODE" in
  xvfb)
    if ! command -v Xvfb >/dev/null; then
      echo "Xvfb not installed. Run: sudo apt install -y xvfb"; exit 1
    fi
    echo "Using Xvfb (hidden virtual display)"
    export HEADLESS=false
    export USE_XVFB=true
    ;;
  gui)
    if [ -z "${DISPLAY:-}" ] || ! xset q >/dev/null 2>&1; then
      echo "No real DISPLAY available — set BROWSER_MODE=xvfb or headless"; exit 1
    fi
    echo "Using real X display: $DISPLAY (window will appear)"
    export HEADLESS=false
    export USE_XVFB=false
    ;;
  headless)
    echo "Using headless mode (no display)"
    export HEADLESS=true
    export USE_XVFB=false
    ;;
  *)
    echo "Unknown BROWSER_MODE=$BROWSER_MODE (expected: xvfb|gui|headless)"; exit 1
    ;;
esac

export CHROME_BINARY="${CHROME_BINARY:-/usr/bin/google-chrome}"
export PYTHONPATH="$PWD"

# Trust system CA bundle (handles corporate SSL-inspection proxies).
if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi

# Local = single-threaded, single browser. Keeps RAM low and avoids any
# threading / staggered-launch complexity.
export MAX_BROWSER_WORKERS=1

exec .venv/bin/python -m crawler.main "$@"
