#!/usr/bin/env python3
"""Add a buy/sell transaction to config/holdings.csv from the terminal.

The same job as the app's "Add transaction" button, for people who prefer the
CLI. It only edits the ledger; run `python scripts/fetch.py` afterwards to
recompute with accurate purchase-date FX, average cost, and realized P&L.

Examples:
    python scripts/add_lot.py AAPL US buy  2026-02-10 3 205
    python scripts/add_lot.py NVDA US sell 2026-06-01 4 135 --rebuild
    python scripts/add_lot.py TCS  IN buy  2026-01-20 10 3800 --name "Tata Consultancy"

Add --rebuild to also run the pipeline + site build in one go. It then prints the
git commit/push command to publish (CI recomputes and redeploys on push).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from core import holdings_io  # noqa: E402


def _rebuild() -> int:
    """Run the pipeline + site assembly locally (accurate FX / avg cost / realized)."""
    steps = [
        ("fetch", [sys.executable, str(HERE / "fetch.py")]),
        ("build", ["bash", str(HERE / "build_site.sh")]),
    ]
    for name, cmd in steps:
        print(f"\n[rebuild] {name}: {' '.join(cmd)}")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"[rebuild] {name} failed (exit {r.returncode}). Fix the error and re-run.",
                  file=sys.stderr)
            return r.returncode
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    ap.add_argument("market", choices=["IN", "US"])
    ap.add_argument("action", choices=["buy", "sell"])
    ap.add_argument("date", help="YYYY-MM-DD")
    ap.add_argument("quantity", type=float)
    ap.add_argument("price", type=float, help="per share, in the holding's own currency")
    ap.add_argument("--name", default=None, help="display name (for a new holding)")
    ap.add_argument("--config", default=str(HERE.parent / "config"))
    ap.add_argument("--rebuild", action="store_true",
                    help="after editing, run fetch.py + build_site.sh locally")
    args = ap.parse_args()

    cfg_dir = Path(args.config)
    holdings, src = holdings_io.read_holdings(cfg_dir)

    sym = args.symbol.upper()
    lot = {"date": args.date, "action": args.action,
           "quantity": abs(args.quantity), "price": args.price}

    existing = next((h for h in holdings if str(h.get("symbol", "")).upper() == sym), None)
    if existing:
        existing.setdefault("lots", []).append(lot)
        existing["lots"].sort(key=lambda l: str(l.get("date") or ""))
        if args.name:
            existing["name"] = args.name
        where = "updated"
    else:
        holdings.append({"symbol": sym, "name": args.name or sym,
                         "market": args.market, "lots": [lot]})
        where = "added"

    out = cfg_dir / "holdings.csv"           # always write the canonical CSV
    out.write_text(holdings_io.to_csv(holdings))
    print(f"[ok] {where} {sym}: {args.action} {abs(args.quantity):g} @ {args.price:g} "
          f"on {args.date} -> {out}"
          + (f"  (migrated from {src})" if src != "holdings.csv" else ""))

    default_cfg = (HERE.parent / "config").resolve()
    if args.rebuild and cfg_dir.resolve() != default_cfg:
        # _rebuild drives the default project layout (fetch + build_site use fixed
        # project paths); a custom --config wouldn't line up, so don't pretend to.
        print("[rebuild] skipped: --rebuild only applies to the default project config.",
              file=sys.stderr)
        args.rebuild = False

    if args.rebuild:
        rc = _rebuild()
        if rc != 0:
            return rc
        print("\n[ok] rebuilt. Preview locally with:  bin/start.sh --serve-only")
    else:
        print("[next] run:  python scripts/fetch.py && bash scripts/build_site.sh"
              "   (or re-run with --rebuild)")

    # Per project rule, we never commit/push for you - here's the command to run.
    msg = f"txn: {args.action} {abs(args.quantity):g} {sym}"
    print("\n[deploy] to publish, commit the config change and push - CI recomputes & redeploys:")
    print(f'    git add config/holdings.csv && git commit -m "{msg}" && git push')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
