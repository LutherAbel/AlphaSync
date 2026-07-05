"""Build ticker -> CIK mapping for the 208-ticker universe (+ETFs).

SEC's company_tickers.json only covers currently-registered filers, so many
delisted/acquired names (BRCM, LLTC, CELG, ...) will be missing. This script
does the mechanical lookup only; it does not try to backfill gaps by hand.
Output: research/data/ticker_cik_map.csv
"""

import json
import os
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

HEADERS = {"User-Agent": "AlphaSync research contact@alphasync.capital"}
SEC_URL = "https://www.sec.gov/files/company_tickers.json"


def load_universe_tickers():
    u = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"))
    all_t = sorted({t for row in u["tickers"] for t in row.split(";")})
    return all_t


def fetch_sec_map():
    req = urllib.request.Request(SEC_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read())
    # raw: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    by_ticker = {}
    for row in raw.values():
        by_ticker[row["ticker"].upper()] = {
            "cik": str(row["cik_str"]).zfill(10),
            "title": row["title"],
        }
    return by_ticker


def main():
    tickers = load_universe_tickers() + ["QQQ", "SPY", "MTUM", "VTV"]
    sec_map = fetch_sec_map()

    rows = []
    for t in tickers:
        hit = sec_map.get(t)
        rows.append(
            {
                "ticker": t,
                "cik": hit["cik"] if hit else "",
                "company_name": hit["title"] if hit else "",
                "found": bool(hit),
            }
        )

    df = pd.DataFrame(rows)
    out = os.path.join(DATA, "ticker_cik_map.csv")
    df.to_csv(out, index=False)

    missing = df.loc[~df["found"], "ticker"].tolist()
    print(f"{len(df)} tickers, {df['found'].sum()} matched, {len(missing)} not found in SEC company_tickers.json")
    print(f"saved: {out}")
    if missing:
        print("\nunmatched (mostly delisted/acquired, expected):")
        print(", ".join(missing))


if __name__ == "__main__":
    main()
