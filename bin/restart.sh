#!/usr/bin/env bash
# Restart the local portfolio tracker: stop, then start again.
# Passes any flags straight through to start.sh, e.g.:
#   bin/restart.sh --live --port=8137
#   bin/restart.sh --serve-only     # just bounce the server, skip rebuild
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
"$HERE/stop.sh" || true
exec "$HERE/start.sh" "$@"
