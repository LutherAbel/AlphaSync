"""Uncapped BSC test: is the 'BSC lowers Sharpe' result just an artifact of cap=1.0?

Runs the sleeve with BSC weights at several caps (1.0 = current retail spec,
up to uncapped = paper-native). Analysis only; does not change the locked spec.
"""

import os

import numpy as np
import pandas as pd

from build_factor import build_sleeve, load_prices, month_end_prices, stats_line, capm

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
px = load_prices()
etf_m = month_end_prices(px[["QQQ", "SPY", "VTV"]]).pct_change()
sleeve_d, sleeve_m, _, _ = build_sleeve(px.drop(columns=["QQQ", "SPY", "MTUM", "VTV"]), universe)


def bsc_w(daily, sigma_target, cap):
    sq = daily**2
    roll = sq.rolling(126).sum()
    me = roll.groupby(roll.index.to_period("M")).last()
    sigma_m = np.sqrt(21.0 * me / 126.0).shift(1)
    w = (sigma_target / np.sqrt(12.0)) / sigma_m
    return w.clip(upper=cap)


print("=" * 82)
print("BSC(20%) at increasing leverage caps (gross)")
print("=" * 82)
print(stats_line(sleeve_m, "plain sleeve (no BSC)"))
for cap in [1.0, 1.3, 1.5, 2.0, np.inf]:
    w = bsc_w(sleeve_d, 0.20, cap)
    managed = (w * sleeve_m).dropna()
    tag = f"BSC cap={cap}"
    a, t, b = capm(managed, etf_m["QQQ"].dropna())
    print(stats_line(managed, tag))
    print(
        f"      -> median w {w.median():.2f}, max w {w.max():.2f}, "
        f"months levered>1: {np.mean(w > 1.0) * 100:.0f}%, alpha vs QQQ {a*100:.2f}% (t {t:.2f})"
    )

print("\nCrisis months: does leverage keep the crash protection? (monthly %)")
crisis = ["2020-02", "2020-03", "2022-04", "2022-06", "2022-09", "2022-12"]
w1 = bsc_w(sleeve_d, 0.20, 1.0)
winf = bsc_w(sleeve_d, 0.20, np.inf)
rows = []
for m_str in crisis:
    m = pd.Period(m_str, "M")
    if m in sleeve_m.index:
        rows.append({
            "month": m_str,
            "plain": sleeve_m[m] * 100,
            "cap1.0": (w1.get(m, np.nan) * sleeve_m[m]) * 100,
            "uncapped": (winf.get(m, np.nan) * sleeve_m[m]) * 100,
            "weight_uncapped": winf.get(m, np.nan),
        })
print(pd.DataFrame(rows).set_index("month").round(2).to_string())
