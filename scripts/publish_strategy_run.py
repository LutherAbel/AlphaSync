"""
publish_strategy_run.py — wrapper that takes the v6_dca strategy outputs
(`output/v6dca_executions.csv` + `output/v6dca_state.json`) and writes the
latest rebalance snapshot into Supabase tables `strategy_runs` /
`strategy_targets`.

Reads strategy outputs only. Does NOT modify the main strategy script.

Env required:
    SUPABASE_URL                e.g. https://xxxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   service_role JWT (NOT the anon key)

Usage:
    python scripts/publish_strategy_run.py
    python scripts/publish_strategy_run.py --run-date 2026-04-23
    python scripts/publish_strategy_run.py --output-dir path/to/output

Idempotency: `strategy_runs` has a unique (source, run_date) constraint.
Re-running the same date upserts cleanly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests

SOURCE = "v6_dca"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output"

# Search for .env.local in known locations (web app dir + repo root) and load
# any keys not already in os.environ. Keeps env management to one file for the
# user, while letting CI override via real env vars.
_DOTENV_CANDIDATES = [
    REPO_ROOT / ".worktrees" / "web-phase1" / "web" / ".env.local",
    REPO_ROOT / "web" / ".env.local",
    REPO_ROOT / ".env.local",
]


def _load_dotenv_files() -> None:
    for path in _DOTENV_CANDIDATES:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_dotenv_files()
EXECUTIONS_CSV = "v6dca_executions.csv"
STATE_JSON = "v6dca_state.json"


def _env(name: str, fallback: str | None = None) -> str:
    val = os.environ.get(name) or (os.environ.get(fallback) if fallback else None)
    if not val:
        sys.exit(f"missing env var: {name}")
    return val


def _post(url: str, headers: dict, payload: Any) -> requests.Response:
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code >= 400:
        sys.exit(f"supabase POST {url} failed [{r.status_code}]: {r.text}")
    return r


def _fetch_prices(tickers: list[str], run_date: str) -> dict[str, float]:
    """Pull adjusted close on run_date via yfinance. Returns {ticker: price}."""
    import yfinance as yf

    end = pd.Timestamp(run_date) + pd.Timedelta(days=1)
    start = pd.Timestamp(run_date) - pd.Timedelta(days=10)
    data = yf.download(
        tickers=tickers,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    out: dict[str, float] = {}
    target_ts = pd.Timestamp(run_date)
    for t in tickers:
        try:
            df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            close = df["Close"].dropna()
            if close.empty:
                continue
            on_or_before = close.loc[close.index <= target_ts]
            if on_or_before.empty:
                continue
            out[t] = float(on_or_before.iloc[-1])
        except Exception as e:  # noqa: BLE001
            print(f"  ! price fetch failed for {t}: {e}", file=sys.stderr)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--run-date",
        default=None,
        help="YYYY-MM-DD execution date (Thursday). Defaults to latest date in executions.csv.",
    )
    parser.add_argument(
        "--signal-date",
        default=None,
        help="YYYY-MM-DD signal date (Wednesday). Defaults to run_date - 1 day.",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    state_path = out_dir / STATE_JSON
    exec_path = out_dir / EXECUTIONS_CSV
    if not state_path.exists():
        sys.exit(f"state file not found: {state_path}")
    if not exec_path.exists():
        sys.exit(f"executions file not found: {exec_path}")

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    run_date = args.run_date or state.get("last_processed_date")
    if not run_date:
        sys.exit("could not determine run_date (pass --run-date)")

    positions: dict[str, dict] = state.get("positions") or {}
    if not positions:
        sys.exit("state.json has no positions — nothing to publish")

    # Latest rebalance prices: prefer the price recorded in executions for
    # this run_date; fall back to yfinance close for anything still held but
    # untraded.
    execs = pd.read_csv(exec_path)
    today_execs = execs[execs["date"] == run_date]
    exec_price_by_ticker: dict[str, float] = {}
    for _, row in today_execs.iterrows():
        exec_price_by_ticker[str(row["ticker"])] = float(row["price"])

    tickers = sorted(positions.keys())
    missing = [t for t in tickers if t not in exec_price_by_ticker]
    yf_prices: dict[str, float] = {}
    if missing:
        print(f"fetching prices for {len(missing)} held-but-untraded tickers on {run_date}")
        yf_prices = _fetch_prices(missing, run_date)

    targets: list[dict] = []
    for t in tickers:
        pos = positions[t]
        weight = float(pos.get("target_weight") or 0.0)
        sleeve = str(pos.get("sleeve") or "long")
        price = exec_price_by_ticker.get(t) or yf_prices.get(t)
        if price is None:
            print(f"  ! no price for {t}; skipping", file=sys.stderr)
            continue
        targets.append(
            {"ticker": t, "target_weight": weight, "price": float(price), "sleeve": sleeve}
        )

    if not targets:
        sys.exit("no resolvable targets — aborting")

    supabase_url = _env("SUPABASE_URL", fallback="NEXT_PUBLIC_SUPABASE_URL").rstrip("/")
    service_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    # Upsert run row.
    runs_url = f"{supabase_url}/rest/v1/strategy_runs?on_conflict=source,run_date"
    run_payload = [{"source": SOURCE, "run_date": run_date, "signal_date": run_date}]
    resp = _post(runs_url, headers, run_payload)
    run_row = resp.json()[0]
    run_id = run_row["id"]
    print(f"strategy_runs upserted: id={run_id} run_date={run_date}")

    # Replace targets for this run: delete existing rows then insert.
    del_url = f"{supabase_url}/rest/v1/strategy_targets?run_id=eq.{run_id}"
    del_resp = requests.delete(del_url, headers=headers, timeout=30)
    if del_resp.status_code >= 400 and del_resp.status_code != 404:
        sys.exit(f"strategy_targets delete failed [{del_resp.status_code}]: {del_resp.text}")

    insert_url = f"{supabase_url}/rest/v1/strategy_targets"
    rows = [{"run_id": run_id, **t} for t in targets]
    _post(insert_url, headers, rows)
    print(f"strategy_targets written: {len(rows)} rows")


if __name__ == "__main__":
    main()
