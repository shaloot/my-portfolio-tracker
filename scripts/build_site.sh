#!/usr/bin/env bash
# Assemble the deployable static site into ./public
# This is the exact step CI runs, so local preview output == production output.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/public"

rm -rf "$OUT"
mkdir -p "$OUT/data"
cp "$ROOT/site/"*.html "$ROOT/site/"*.css "$ROOT/site/"*.js "$OUT/"
cp "$ROOT/data/"*.json "$OUT/data/" 2>/dev/null || {
  echo "No data/*.json yet - run: python scripts/fetch.py --mock" >&2; exit 1; }

echo "Built site -> $OUT"
ls -1 "$OUT" "$OUT/data"
