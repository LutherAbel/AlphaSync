"""Compare TOP_N=20 (locked primary) vs TOP_N=10 (2026-07-04 exploratory add-on).

Per FactorSpec.md changelog: both must be reported regardless of which looks
better. This script does not alter build_factor.py's primary TOP_N=20 output.
"""

import os

import numpy as np
import pandas as pd

from build_factor import (
    bsc_weights,
    build_sleeve,
    capm,
    load_prices,
    month_end_prices,
    stats_line,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
px = load_prices()
etfs = ["QQQ", "SPY", "MTUM", "VTV"]
etf_m = month_end_prices(px[etfs]).pct_change()
stock_px = px.drop(columns=etfs)


def run(top_n):
    import build_factor as m
    orig = m.TOP_N
    m.TOP_N = top_n
    try:
        sleeve_d, sleeve_m, holdings, to = m.build_sleeve(stock_px, universe)
    finally:
        m.TOP_N = orig
    return sleeve_d, sleeve_m, holdings, to


for top_n in [20, 10]:
    sleeve_d, sleeve_m, holdings, to = run(top_n)
    w = bsc_weights(sleeve_d, 0.20).clip(upper=1.0)
    managed_m = (w * sleeve_m).dropna()

    print("=" * 78)
    print(f"TOP_N = {top_n}")
    print("=" * 78)
    print(stats_line(sleeve_m, f"sleeve plain (top-{top_n})"))
    print(stats_line(managed_m, f"sleeve + BSC(20%) (top-{top_n})"))
    a_q, t_q, b_q = capm(sleeve_m, etf_m["QQQ"].dropna())
    print(f"  alpha vs QQQ: {a_q*100:.2f}%/yr (t {t_q:.2f}), beta {b_q:.2f}")
    print(f"  monthly one-way turnover: mean {to.mean()*100:.0f}%")
    corr = sleeve_m.corr(etf_m["QQQ"].reindex(sleeve_m.index))
    print(f"  corr vs QQQ: {corr:.2f}")
    print()
