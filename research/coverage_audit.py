"""Coverage audit: for every member-month, does a month-end price exist?

Catches delisted-data gaps AND ticker-reuse hazards (e.g. ALTR = Altera 2015
membership vs Altair 2017+ data) before they silently bias the backtest.
Output: research/data/coverage_audit.csv + console summary.
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")
DATA = os.path.join(ROOT, "data")

universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")[
    "tickers"
]

ranges = {}
for f in os.listdir(CACHE):
    t = f[:-4]
    df = pd.read_csv(os.path.join(CACHE, f), parse_dates=["date"])
    ranges[t] = (df["date"].min().to_period("M"), df["date"].max().to_period("M"))

rows = []
for month, tickers in universe.items():
    m = pd.Period(month, "M")
    for t in tickers.split(";"):
        if t not in ranges:
            rows.append({"month": month, "ticker": t, "issue": "no_data_file"})
        else:
            lo, hi = ranges[t]
            if not (lo <= m <= hi):
                rows.append({"month": month, "ticker": t, "issue": "outside_data_range"})

gaps = pd.DataFrame(rows)
total_mm = sum(len(v.split(";")) for v in universe)
print(f"member-months total: {total_mm}, missing: {len(gaps)} ({len(gaps)/total_mm*100:.1f}%)")
if len(gaps):
    print("\nworst tickers:")
    print(gaps.groupby("ticker").size().sort_values(ascending=False).head(15).to_string())
    gaps.to_csv(os.path.join(DATA, "coverage_audit.csv"), index=False)
    print("\nsaved: data/coverage_audit.csv")
