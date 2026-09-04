"""Read the user's holdings and normalise them to the internal shape.

Users describe their portfolio as a **transaction ledger in CSV** - one row per
buy or sale - because that is the natural, spreadsheet-friendly way to keep it.
JSON stays purely internal (the generated data files). This module is the bridge:
it reads `config/holdings.csv` (preferred) or `config/holdings.json` (fallback)
and returns the list of holdings the pipeline works with:

    { "symbol", "name", "market", "lots": [ {date, action, quantity, price}, .. ] }

CSV columns (header row, case-insensitive; friendly aliases accepted):
    symbol,name,market,date,action,quantity,price
- One row per transaction. Repeat the symbol for each additional lot.
- `date` empty  -> an undated opening position (valued at today's FX).
- `action` empty -> "buy".
- `name`/`market` are taken from the first row that gives them for a symbol.
- A row whose symbol is blank or starts with "_" is ignored (comment/spacer).
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

CSV_COLUMNS = ["symbol", "name", "market", "date", "action", "quantity", "price"]

# Friendly header aliases -> canonical column.
_ALIASES = {
    "symbol": "symbol", "ticker": "symbol",
    "name": "name", "company": "name",
    "market": "market", "exchange": "market",
    "date": "date", "txn_date": "date", "trade_date": "date",
    "action": "action", "type": "action", "side": "action", "txn": "action",
    "quantity": "quantity", "qty": "quantity", "shares": "quantity", "units": "quantity",
    "price": "price", "cost": "price", "avg_cost": "price", "amount": "price",
    "rate": "price",
}


def _num(v: str) -> float:
    return float(str(v).replace(",", "").strip())


def parse_csv(text: str) -> list[dict]:
    """Parse ledger CSV text into the internal holdings list."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    colmap = {}
    for raw in reader.fieldnames:
        key = _ALIASES.get((raw or "").strip().lower().replace(" ", "_"))
        if key:
            colmap[raw] = key

    order: list[str] = []
    by_symbol: dict[str, dict] = {}
    for row in reader:
        rec = {colmap[k]: (v or "").strip() for k, v in row.items() if k in colmap}
        sym = rec.get("symbol", "").upper()
        if not sym or sym.startswith(("_", "#")):
            continue  # blank/commented row
        try:
            qty = _num(rec["quantity"])
            price = _num(rec["price"])
        except (KeyError, ValueError):
            continue  # skip a malformed row rather than break the whole build
        if sym not in by_symbol:
            by_symbol[sym] = {"symbol": sym, "name": sym, "market": "US", "lots": []}
            order.append(sym)
        h = by_symbol[sym]
        if rec.get("name"):
            h["name"] = rec["name"]
        if rec.get("market"):
            h["market"] = rec["market"].upper()
        h["lots"].append({
            "date": rec.get("date") or None,
            "action": (rec.get("action") or "buy").lower(),
            "quantity": abs(qty),
            "price": price,
        })
    return [by_symbol[s] for s in order]


def to_csv(holdings: list[dict]) -> str:
    """Serialise internal holdings back to canonical ledger CSV text.

    Legacy JSON holdings ({quantity, avg_cost}) become a single undated buy row.
    """
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(CSV_COLUMNS)
    for h in holdings:
        sym, name, market = h.get("symbol", ""), h.get("name", ""), h.get("market", "")
        lots = h.get("lots")
        if not lots:
            lots = [{"date": None, "action": "buy",
                     "quantity": h.get("quantity", 0), "price": h.get("avg_cost", 0)}]
        for lt in lots:
            w.writerow([sym, name, market, lt.get("date") or "",
                        lt.get("action", "buy"),
                        _fmt(lt.get("quantity", 0)), _fmt(lt.get("price", 0))])
    return out.getvalue()


def _fmt(x) -> str:
    f = float(x)
    return str(int(f)) if f == int(f) else f"{f:g}"


def read_holdings(config_dir: Path) -> tuple[list[dict], str]:
    """Load holdings, preferring CSV. Returns (holdings, source_filename)."""
    csv_path = config_dir / "holdings.csv"
    json_path = config_dir / "holdings.json"
    if csv_path.exists():
        return parse_csv(csv_path.read_text()), "holdings.csv"
    if json_path.exists():
        doc = json.loads(json_path.read_text())
        holdings = [h for h in doc.get("holdings", [])
                    if not str(h.get("symbol", "")).startswith("_")]
        return holdings, "holdings.json"
    return [], "(none)"
