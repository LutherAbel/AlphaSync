"""Post-hoc diagnostics (analysis only, no strategy config change):
1. EW all-NDX benchmark: isolates momentum-selection value vs equal-weighting effect.
2. Crisis table: sleeve behavior in the 10 worst SPY months.
"""

import os

import numpy as np
import pandas as pd

from build_factor import bsc_weights, load_prices, month_end_prices, stats_line

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")

universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
px = load_prices()
etfs = ["QQQ", "SPY", "MTUM", "VTV"]
etf_m = month_end_prices(px[etfs]).pct_change()
stock_px = px.drop(columns=etfs)
daily_ret = stock_px.pct_change(fill_method=None)

# --- EW all-NDX: hold every member EW, monthly, same machinery as the sleeve ---
monthly, daily_parts = {}, []
for m_str, tickers in universe.items():
    m = pd.Period(m_str, "M")
    members = [t for t in tickers.split(";") if t in daily_ret.columns]
    mask = daily_ret.index.to_period("M") == m
    sub = daily_ret.loc[mask, members]
    # keep only names with data this month; no cash drag from never-listed names
    sub = sub.dropna(axis=1, how="all").fillna(0.0)
    if sub.empty:
        continue
    d = sub.mean(axis=1)
    daily_parts.append(d)
    monthly[m] = float((1 + d).prod() - 1)

ewndx_d = pd.concat(daily_parts)
ewndx_m = pd.Series(monthly).sort_index()

res = pd.read_csv(os.path.join(OUT, "sleeve_returns.csv"), index_col=0)
res.index = pd.PeriodIndex(res.index, freq="M")
common = res.index.intersection(ewndx_m.index)
sleeve = res.loc[common, "sleeve_plain"]
managed = res.loc[common, "sleeve_managed"]
ewndx = ewndx_m[common]

print("=" * 78)
print("1) MOMENTUM SELECTION vs EQUAL-WEIGHTING (same window, gross)")
print(stats_line(res.loc[common, "QQQ"], "QQQ (cap-weight NDX)"))
print(stats_line(ewndx, "EW all-NDX (no selection)"))
print(stats_line(sleeve, "momentum top-20 EW (sleeve)"))
sel = sleeve - ewndx
print(stats_line(sel, "selection effect (sleeve-EWNDX)"))
print(f"  corr(sleeve, EW all-NDX) = {sleeve.corr(ewndx):.2f}")

# EW all-NDX with BSC layer, for the risk-product comparison
w_ew = bsc_weights(ewndx_d, 0.20).clip(upper=1.0)
ew_managed = (w_ew * ewndx_m).dropna()
print(stats_line(ew_managed[common.intersection(ew_managed.index)], "EW all-NDX + BSC(20%)"))

print()
print("=" * 78)
print("2) TEN WORST SPY MONTHS: does the product earn its keep in crises?")
spy = res["SPY"].dropna()
worst = spy.nsmallest(10).index
rows = []
for m in sorted(worst):
    rows.append({
        "month": str(m),
        "SPY": res.loc[m, "SPY"],
        "QQQ": res.loc[m, "QQQ"],
        "sleeve": res.loc[m, "sleeve_plain"],
        "managed": res.loc[m, "sleeve_managed"],
        "50/50 w VTV": 0.5 * res.loc[m, "sleeve_managed"] + 0.5 * res.loc[m, "VTV"],
    })
df = pd.DataFrame(rows).set_index("month")
print((df * 100).round(1).to_string())
print("\n  mean across the 10 months:")
print((df.mean() * 100).round(1).to_string())
