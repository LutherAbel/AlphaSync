"""Fetch point-in-time shares outstanding from SEC EDGAR companyfacts.

Per FactorSpec trial #6. For each CIK in data/ticker_cik_map.csv, pull
dei:EntityCommonStockSharesOutstanding (cover-page fact, filed with every
10-K/10-Q). Multi-class companies report one fact per class with the same
filed date; we sum distinct (end, val) pairs per filed date (approximation,
logged). Output: data/shares_outstanding.csv (ticker, filed, end, shares).
"""

import json
import os
import time
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT_CSV = os.path.join(DATA, "shares_outstanding.csv")

UA = {"User-Agent": "AlphaSync research chamberblue@gmail.com"}
TAGS = [
    ("dei", "EntityCommonStockSharesOutstanding"),
    ("us-gaap", "CommonStockSharesOutstanding"),
    # Multi-class issuers report cover-page shares per class WITH a dimension,
    # and companyfacts drops dimensioned facts entirely (META, ABNB, ZM ...).
    # Basic weighted-average shares is undimensioned and class-aggregated;
    # period-average instead of point-in-time, acceptable for a weighting
    # robustness check (logged in FactorSpec trial #6).
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),
]


def fetch_cik(cik: str):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def extract(facts: dict):
    for ns, tag in TAGS:
        node = facts.get("facts", {}).get(ns, {}).get(tag)
        if not node:
            continue
        units = node.get("units", {}).get("shares", [])
        if not units:
            continue
        df = pd.DataFrame(units)
        if df.empty or "filed" not in df:
            continue
        # dedupe exact duplicates (amendments), then sum classes per filed date
        df = df.drop_duplicates(subset=["end", "val"])
        agg = df.groupby("filed").agg(end=("end", "max"), shares=("val", "sum"))
        return agg.reset_index(), f"{ns}:{tag}"
    return None, None


def main():
    cmap = pd.read_csv(os.path.join(DATA, "ticker_cik_map.csv"), dtype={"cik": str})
    rows, misses = [], []
    cmap = cmap[cmap["cik"].notna()].reset_index(drop=True)  # skip ETFs (MTUM/VTV)
    for i, rec in cmap.iterrows():
        t, cik = rec["ticker"], rec["cik"].zfill(10)
        try:
            agg, src = extract(fetch_cik(cik))
        except Exception as e:
            agg, src = None, f"error:{e}"
        if agg is None or agg.empty:
            misses.append((t, src))
        else:
            for _, r in agg.iterrows():
                rows.append({"ticker": t, "filed": r["filed"], "end": r["end"], "shares": int(r["shares"]), "source": src})
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{len(cmap)} done, rows={len(rows)}, misses={len(misses)}")
        time.sleep(0.13)  # stay under SEC 10 req/s

    out = pd.DataFrame(rows).sort_values(["ticker", "filed"])
    out.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_CSV}: {len(out)} rows, {out['ticker'].nunique()} tickers")
    if misses:
        print("MISSING:", misses)


if __name__ == "__main__":
    main()
