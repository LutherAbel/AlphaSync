"""Daniel-Moskowitz (2016) bear-state gate on top of BSC. See FactorSpec changelog
entry 2026-07-04 (trial #4) for the declared implementation choices.

Question: does conditioning on market state add anything OVER BSC in this sample?
All state variables are point-in-time (use info only through end of prior month).
"""

import os

import numpy as np
import pandas as pd

from build_factor import build_sleeve, capm, load_prices, month_end_prices, stats_line

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
px = load_prices()
qqq_d = px["QQQ"].dropna()
qqq_me = month_end_prices(px[["QQQ"]])["QQQ"]
etf_m = month_end_prices(px[["QQQ", "SPY"]]).pct_change()
sleeve_d, sleeve_m, _, _ = build_sleeve(px.drop(columns=["QQQ", "SPY", "MTUM", "VTV"]), universe)


def bsc_w(daily, sigma_target=0.20, cap=1.0):
    sq = daily**2
    roll = sq.rolling(126).sum()
    me = roll.groupby(roll.index.to_period("M")).last()
    sigma_m = np.sqrt(21.0 * me / 126.0).shift(1)
    return ((sigma_target / np.sqrt(12.0)) / sigma_m).clip(upper=cap)


# --- market state, all shifted to use info through end of prior month ---
# bear24: QQQ trailing 24m cumulative return < 0
months = qqq_me.index
bear24 = pd.Series(index=months, dtype=float)
bear12 = pd.Series(index=months, dtype=float)
for i, m in enumerate(months):
    bear24[m] = (qqq_me.iloc[i - 1] / qqq_me.iloc[i - 25] - 1) if i >= 25 else np.nan
    bear12[m] = (qqq_me.iloc[i - 1] / qqq_me.iloc[i - 13] - 1) if i >= 13 else np.nan

# high-vol: 63d annualized realized vol at end of prior month > expanding median
qret = qqq_d.pct_change()
rv = qret.rolling(63).std() * np.sqrt(252)
rv_me = rv.groupby(rv.index.to_period("M")).last().shift(1)
rv_med = rv_me.expanding(min_periods=12).median()
highvol = rv_me > rv_med

is_bear24 = (bear24 < 0).reindex(sleeve_m.index).fillna(False)
is_bear12 = (bear12 < 0).reindex(sleeve_m.index).fillna(False)
is_hv = highvol.reindex(sleeve_m.index).fillna(False)
panic = is_bear24 & is_hv

print("=" * 80)
print("STATE FIRING FREQUENCY (fraction of held months)")
print(f"  bear24 (24m QQQ ret<0): {is_bear24.mean()*100:4.0f}%")
print(f"  bear12 (12m QQQ ret<0): {is_bear12.mean()*100:4.0f}%")
print(f"  high-vol:               {is_hv.mean()*100:4.0f}%")
print(f"  panic (bear24 & hv):    {panic.mean()*100:4.0f}%   ({int(panic.sum())} months)")
if panic.sum():
    print(f"  panic months: {[str(m) for m in sleeve_m.index[panic.values]]}")

w_bsc = bsc_w(sleeve_d)
bsc_m = (w_bsc * sleeve_m).dropna()

print("\n" + "=" * 80)
print("PERFORMANCE (gross)")
print(stats_line(sleeve_m, "plain sleeve"))
print(stats_line(bsc_m, "BSC only"))
for k in [0.5, 0.0]:
    gate = pd.Series(1.0, index=sleeve_m.index)
    gate[panic.values] = k
    dm_m = (w_bsc * gate * sleeve_m).dropna()
    a, t, b = capm(dm_m, etf_m["QQQ"].dropna())
    print(stats_line(dm_m, f"BSC + DM gate (panic->x{k})"))

# also a pure bear12 gate (more responsive) for comparison
for k in [0.0]:
    gate = pd.Series(1.0, index=sleeve_m.index)
    gate[is_bear12.values] = k
    dm_m = (w_bsc * gate * sleeve_m).dropna()
    print(stats_line(dm_m, f"BSC + bear12 gate (->x{k})"))

print("\nCrisis months (monthly %): plain / BSC / BSC+DM(panic->0)")
gate0 = pd.Series(1.0, index=sleeve_m.index)
gate0[panic.values] = 0.0
rows = []
for m_str in ["2018-12", "2020-02", "2020-03", "2022-04", "2022-06", "2022-09", "2022-10", "2022-12"]:
    m = pd.Period(m_str, "M")
    if m in sleeve_m.index:
        rows.append({
            "month": m_str,
            "plain": sleeve_m[m] * 100,
            "BSC": (w_bsc.get(m, np.nan) * sleeve_m[m]) * 100,
            "BSC+DM": (w_bsc.get(m, np.nan) * gate0[m] * sleeve_m[m]) * 100,
            "bear24?": bool(is_bear24[m]),
            "hv?": bool(is_hv[m]),
        })
print(pd.DataFrame(rows).set_index("month").round(2).to_string())
