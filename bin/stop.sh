#!/usr/bin/env bash
# Stop the local portfolio tracker server started by bin/start.sh.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$HERE/.server.pid"

if [ ! -f "$PIDFILE" ]; then
  echo "[stop] not running (no PID file)"
  exit 0
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null || true
  # Give it a moment, then force if still alive.
  for _ in 1 2 3; do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
  done
  kill -9 "$PID" 2>/dev/null || true
  echo "[stop] stopped server (PID $PID)"
else
  echo "[stop] no live process for PID $PID (stale PID file)"
fi
rm -f "$PIDFILE"
