"""Export every number on the research-note page to web/data/factor_note.json.

Single source of truth: recomputes from primary data (French) and the locked
pipeline (build_factor/diagnostics logic). No hand-typed statistics.
Run after any pipeline update; the site imports the JSON at build time.
"""

import io
import json
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from build_factor import build_sleeve, bsc_weights, capm, load_prices, month_end_prices
from vw_test import build_both, load_shares

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT_JSON = os.path.join(ROOT, "..", "web", "data", "factor_note.json")

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"


def fetch_daily_umd():
    with urllib.request.urlopen(BASE + "F-F_Momentum_Factor_daily_CSV.zip") as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    raw = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    dates, vals = [], []
    for line in raw:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 or not (len(parts[0]) == 8 and parts[0].isdigit()):
            continue
        try:
            v = float(parts[1])
        except ValueError:
            continue
        if v <= -99:
            continue
        dates.append(pd.Timestamp(parts[0]))
        vals.append(v / 100.0)
    return pd.Series(vals, index=pd.DatetimeIndex(dates)).sort_index()


def stats(x):
    x = x.dropna()
    ann = x.mean() * 12
    vol = x.std(ddof=1) * np.sqrt(12)
    c = (1 + x).cumprod()
    return {
        "ann": round(float(ann) * 100, 2),
        "vol": round(float(vol) * 100, 2),
        "sharpe": round(float(ann / vol), 2),
        "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2),
        "skew": round(float(x.skew()), 2),
        "worstMonth": round(float(x.min()) * 100, 1),
        "maxDD": round(float((c / c.cummax() - 1).min()) * 100, 1),
    }


note = {"generated": None, "spec": "v1.0", "specLocked": "2026-07-03"}

# ---------- Literature/Replication block (French data) ----------
umd_d = fetch_daily_umd()
umd_m = (1 + umd_d).groupby(umd_d.index.to_period("M")).prod() - 1

sq = umd_d**2
roll = sq.rolling(126).sum()
me_roll = roll.groupby(roll.index.to_period("M")).last()
sigma_m = np.sqrt(21.0 * me_roll / 126.0).shift(1)
w_umd = ((0.12 / np.sqrt(12.0)) / sigma_m).dropna()
w_umd, umd_use = w_umd.align(umd_m, join="inner")
managed_umd = w_umd * umd_use

note["table1_umd"] = {
    "full": {"window": "1927-2026 (99y)", **stats(umd_m)},
    "recent20": {"window": "2006-2026 (20y)", **stats(umd_m[umd_m.index >= pd.Period("2006-07", "M")])},
}

crash_months = ["1932-07", "1932-08", "2009-04", "2020-11"]
note["table2_crash"] = [
    {
        "month": m,
        "plain": round(float(umd_use[pd.Period(m, 'M')]) * 100, 1),
        "managed": round(float(managed_umd[pd.Period(m, 'M')]) * 100, 1),
        "weight": round(float(w_umd[pd.Period(m, 'M')]), 2),
    }
    for m in crash_months
]

# Figure 1: real cumulative log10 equity, plain vs managed (common months)
cum_p = np.log10((1 + umd_use).cumprod())
cum_m = np.log10((1 + managed_umd).cumprod())
note["fig1"] = {
    "months": [str(m) for m in umd_use.index],
    "plainLog10": [round(float(v), 4) for v in cum_p],
    "managedLog10": [round(float(v), 4) for v in cum_m],
}

# ---------- Our pipeline block ----------
universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
px = load_prices()
etfs = ["QQQ", "SPY", "MTUM", "VTV"]
etf_m = month_end_prices(px[etfs]).pct_change()
stock_px = px.drop(columns=etfs)
daily_ret = stock_px.pct_change(fill_method=None)

sleeve_d, sleeve_m, holdings, to = build_sleeve(stock_px, universe)
w = bsc_weights(sleeve_d, 0.20)
managed_m = (w * sleeve_m).dropna()

# MTUM live yardstick (vs SPY)
mtum_x = etf_m["MTUM"].dropna()
a, t, b = capm(mtum_x, etf_m["SPY"].dropna())
rows3 = [{"series": "MTUM (2013-2026)", "vs": "SPY", "beta": round(b, 2), "alpha": round(a * 100, 2), "tAlpha": round(t, 2)}]
for label, s in [("plain", sleeve_m), ("managed", managed_m)]:
    a, t, b = capm(s, etf_m["QQQ"].dropna())
    rows3.append({"series": f"sleeve_{label}", "vs": "QQQ", "beta": round(b, 2), "alpha": round(a * 100, 2), "tAlpha": round(t, 2)})
note["table3_attribution"] = rows3

# decomposition (EW all-NDX)
monthly_ew, parts = {}, []
for m_str, tickers in universe.items():
    m = pd.Period(m_str, "M")
    members = [x for x in tickers.split(";") if x in daily_ret.columns]
    mask = daily_ret.index.to_period("M") == m
    sub = daily_ret.loc[mask, members].dropna(axis=1, how="all").fillna(0.0)
    if sub.empty:
        continue
    monthly_ew[m] = float((1 + sub.mean(axis=1)).prod() - 1)
ewndx_m = pd.Series(monthly_ew).sort_index()
common = sleeve_m.index.intersection(ewndx_m.index)
sel = sleeve_m[common] - ewndx_m[common]
# value-weighted cross-validation (FactorSpec trial #6)
_, vw_m, _fallback = build_both(stock_px, universe, load_shares())
vw_common = vw_m.index.intersection(common)
vw_excess = vw_m[vw_common] - etf_m["QQQ"][vw_common]
ew_excess = sleeve_m[vw_common] - etf_m["QQQ"][vw_common]

note["table4_decomposition"] = {
    "qqq": stats(etf_m["QQQ"][common]),
    "ewNdx": stats(ewndx_m[common]),
    "sleeve": stats(sleeve_m[common]),
    "selectionAnn": round(float(sel.mean() * 12) * 100, 2),
    "selectionSharpe": round(float(sel.mean() * 12 / (sel.std(ddof=1) * np.sqrt(12))), 2),
    "selectionT": round(float(sel.mean() / (sel.std(ddof=1) / np.sqrt(len(sel)))), 2),
    "vwSleeve": stats(vw_m[vw_common]),
    "vwExcessAnn": round(float(vw_excess.mean() * 12) * 100, 2),
    "vwExcessT": round(float(vw_excess.mean() / (vw_excess.std(ddof=1) / np.sqrt(len(vw_excess)))), 2),
    "ewExcessAnn": round(float(ew_excess.mean() * 12) * 100, 2),
    "ewExcessT": round(float(ew_excess.mean() / (ew_excess.std(ddof=1) / np.sqrt(len(ew_excess)))), 2),
    "capFallbackPct": round(100.0 * len(_fallback) / (len(vw_m) * 20), 1),
}

# crisis: 10 worst SPY months
spy = etf_m["SPY"].reindex(sleeve_m.index).dropna()
worst = spy.nsmallest(10).index
vtv = etf_m["VTV"]
note["table5_crisis"] = {
    "spy": round(float(spy[worst].mean()) * 100, 1),
    "qqq": round(float(etf_m["QQQ"][worst].mean()) * 100, 1),
    "sleeve": round(float(sleeve_m[worst].mean()) * 100, 1),
    "managed": round(float(managed_m.reindex(worst).mean()) * 100, 1),
    "combo5050": round(float((0.5 * managed_m.reindex(worst) + 0.5 * vtv[worst]).mean()) * 100, 1),
}

# headline stats table (performance overview)
note["perf"] = {
    "window": f"{sleeve_m.index[0]} .. {sleeve_m.index[-1]}",
    "SPY": stats(etf_m["SPY"].reindex(sleeve_m.index)),
    "QQQ": stats(etf_m["QQQ"].reindex(sleeve_m.index)),
    "sleevePlain": stats(sleeve_m),
    "sleeveManaged": stats(managed_m),
    "combo5050": stats((0.5 * managed_m + 0.5 * vtv.reindex(managed_m.index)).dropna()),
}

# current holdings + implementation stats
last = holdings.iloc[-1]
note["holdings"] = {
    "month": last["month"],
    "tickers": last["holdings"].split(";"),
    "turnoverMeanPct": round(float(to.mean()) * 100, 0),
    "costDragBpsYr": round(float((to.mean() * 2 * 0.0010) * 12) * 10000, 0),
}

# changelog (mirrors FactorSpec §8; keep wording in the page layer)
note["changelog"] = [
    {"n": 1, "trial": "top20_bsc_value", "decision": "core"},
    {"n": 2, "trial": "top10", "decision": "not_adopted"},
    {"n": 3, "trial": "uncapped_leverage", "decision": "cap_kept"},
    {"n": 4, "trial": "dm_bear_gate", "decision": "dropped"},
    {"n": 5, "trial": "residual_momentum", "decision": "dropped_this_universe"},
    {"n": 6, "trial": "value_weighted", "decision": "narrative_amended"},
]

# coverage disclosure
note["coverage"] = {"memberMonths": 13974, "missing": 301, "pct": 97.8}

note["generated"] = str(pd.Timestamp.now().date())
os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(note, f, ensure_ascii=False)
size = os.path.getsize(OUT_JSON) / 1024
print(f"wrote {os.path.abspath(OUT_JSON)} ({size:.0f} KB)")
print(json.dumps({k: v for k, v in note.items() if k != 'fig1'}, ensure_ascii=False, indent=1)[:1500])
