"""Fetch point-in-time NDX membership + Tiingo daily prices (incl. delisted).

Spec: docs/FactorSpec.md (locked 2026-07-03).
Idempotent: cached tickers are skipped; safe to re-run after rate limits.
"""

import json
import os
import time
import urllib.error
import urllib.request

import pandas as pd
from nasdaq_100_ticker_history import tickers_as_of

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")
DATA = os.path.join(ROOT, "data")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

TIINGO_KEY = os.environ.get("TIINGO_API_KEY")
if not TIINGO_KEY:
    raise SystemExit("TIINGO_API_KEY not set (env var or GitHub secret)")
START = "2013-10-01"          # 12m signal history buffer before 2015-01
ETFS = ["QQQ", "SPY", "MTUM", "VTV"]

# FactorSpec §1: one share class per company
DROP_CLASSES = {"GOOG", "FOX", "NWS", "LBTYK", "LBTYB", "LILAK"}
# FactorSpec §1: ticker renames (membership symbol -> Tiingo symbol)
ALIASES = {"FB": "META"}


def build_universe():
    months = pd.period_range("2015-01", pd.Timestamp.today().to_period("M"), freq="M")
    rows = []
    for m in months:
        ts = m.to_timestamp()
        tickers = tickers_as_of(ts.year, ts.month, 1)
        keep = sorted(
            ALIASES.get(t, t) for t in tickers if t not in DROP_CLASSES
        )
        rows.append({"month": str(m), "tickers": ";".join(keep)})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(DATA, "universe_monthly.csv"), index=False)
    all_tickers = sorted({t for r in rows for t in r["tickers"].split(";")})
    print(f"universe: {len(df)} months, {len(all_tickers)} unique tickers")
    return all_tickers


def fetch_ticker(ticker, force=False):
    out = os.path.join(CACHE, f"{ticker}.csv")
    if os.path.exists(out) and not force:
        return "cached"
    url = (
        f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
        f"?startDate={START}&token={TIINGO_KEY}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return f"http {e.code}"
    except Exception as e:  # noqa: BLE001 - log and continue, resume later
        return f"error {type(e).__name__}"
    if not data:
        return "empty"
    df = pd.DataFrame(data)[["date", "adjClose"]]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df.to_csv(out, index=False)
    return f"ok {len(df)}"


def main(refresh=False):
    all_tickers = build_universe()
    # --refresh: re-download current members + ETFs in full (extends history
    # to today); delisted names keep their frozen cached files.
    universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"))
    current = set(universe.iloc[-1]["tickers"].split(";")) | set(ETFS)
    tickers = all_tickers + ETFS
    gaps = []
    for i, t in enumerate(tickers, 1):
        status = fetch_ticker(t, force=refresh and t in current)
        if status != "cached":
            print(f"[{i}/{len(tickers)}] {t:6} {status}", flush=True)
            time.sleep(0.3)
        if status.startswith(("http", "empty", "error")):
            gaps.append(f"{t},{status}")
        if "429" in status:
            print("rate limited - stopping; re-run to resume")
            break
    with open(os.path.join(DATA, "coverage_gaps.txt"), "w") as f:
        f.write("\n".join(gaps))
    print(f"done. gaps: {len(gaps)} -> data/coverage_gaps.txt")


if __name__ == "__main__":
    import sys

    main(refresh="--refresh" in sys.argv)
