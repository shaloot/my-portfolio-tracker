#!/usr/bin/env bash
# Start the portfolio tracker locally: build the data, assemble the static
# site, and serve public/ in the background.
#
# Usage:
#   bin/start.sh                 # mock data (no network/keys), port 8000
#   bin/start.sh --live          # live data (needs deps; uses .venv if present)
#   bin/start.sh --port=8137     # serve on a different port
#   bin/start.sh --serve-only    # skip fetch+build, just (re)serve existing public/
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PIDFILE="$HERE/.server.pid"
LOGFILE="$HERE/server.log"

PORT="${PORT:-8000}"
MODE="auto"          # auto: live if deps are installed, else mock
SERVE_ONLY=0
for a in "$@"; do
  case "$a" in
    --live)       MODE="live" ;;
    --mock)       MODE="mock" ;;
    --serve-only) SERVE_ONLY=1 ;;
    --port=*)     PORT="${a#*=}" ;;
    *) echo "[start] unknown option: $a" >&2; exit 2 ;;
  esac
done

PY="${PYTHON:-python3}"

# Use the project venv if present, so auto-detection sees the installed deps.
if [ -f "$ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

# auto: pick live when the price library is importable (so you get real data +
# real news), otherwise fall back to the keyless offline mock.
if [ "$MODE" = "auto" ]; then
  if "$PY" -c "import yfinance" >/dev/null 2>&1; then
    MODE="live"; echo "[start] deps detected -> using live data (real prices + news)"
  else
    MODE="mock"; echo "[start] no deps -> using offline mock (run pip install for live data)"
  fi
fi

# Already running (our own server)? Do nothing.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[start] already running (PID $(cat "$PIDFILE")) at http://localhost:$PORT"
  exit 0
fi

# Preflight: if the requested port is taken, auto-advance to the next free one
# (scan up to +50). This runs before the possibly-slow live fetch.
port_free() {
  "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1',$1))==0 else 0)" 2>/dev/null
}
REQUESTED_PORT="$PORT"
tries=0
while ! port_free "$PORT"; do
  tries=$((tries + 1))
  if [ "$tries" -gt 50 ]; then
    echo "[start] no free port found in range $REQUESTED_PORT-$((REQUESTED_PORT + 50))" >&2
    exit 1
  fi
  PORT=$((PORT + 1))
done
if [ "$PORT" != "$REQUESTED_PORT" ]; then
  echo "[start] port $REQUESTED_PORT in use; using next free port $PORT"
fi

if [ "$SERVE_ONLY" -eq 0 ]; then
  echo "[start] building data ($MODE)..."
  if [ "$MODE" = "live" ]; then
    "$PY" "$ROOT/scripts/fetch.py"
  else
    "$PY" "$ROOT/scripts/fetch.py" --mock
  fi

  echo "[start] assembling site..."
  bash "$ROOT/scripts/build_site.sh" >/dev/null
fi

if [ ! -d "$ROOT/public" ]; then
  echo "[start] no public/ to serve - run without --serve-only first" >&2
  exit 1
fi

echo "[start] serving public/ on :$PORT"
nohup "$PY" -m http.server "$PORT" --directory "$ROOT/public" >"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
sleep 1

if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[start] up -> http://localhost:$PORT  (PID $(cat "$PIDFILE"), logs: bin/server.log)"
else
  echo "[start] server failed to start (is port $PORT already in use?); see $LOGFILE" >&2
  rm -f "$PIDFILE"
  exit 1
fi
