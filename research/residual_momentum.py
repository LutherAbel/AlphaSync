"""Residual momentum (Blitz-Huij-Martens 2011) vs standard 12-1 momentum.

Spec: FactorSpec changelog trial #5. Timing convention (the look-ahead-critical part):
  - Holding month m. Formation uses information through end of m-1 ONLY.
  - FF3 regression window: monthly returns for months [m-36 .. m-1] (36 obs, all required).
  - Signal residuals: months [m-12 .. m-2] (11 obs, skips m-1), sum/std.
  - FF3 factors must exist through m-1, else month m is dropped.
Outputs comparison on the common window vs the standard sleeve.
"""

import io
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from build_factor import build_sleeve, bsc_weights, capm, load_prices, month_end_prices, stats_line

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
TOP_N = 20


def fetch_ff3():
    path = os.path.join(DATA, "ff3_monthly.csv")
    if os.path.exists(path):
        df = pd.read_csv(path, index_col=0)
        df.index = pd.PeriodIndex(df.index, freq="M")
        return df
    url = (
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
        "F-F_Research_Data_Factors_CSV.zip"
    )
    with urllib.request.urlopen(url) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    raw = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    rows = {}
    for line in raw:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 5 and len(parts[0]) == 6 and parts[0].isdigit():
            try:
                rows[parts[0]] = [float(v) for v in parts[1:5]]
            except ValueError:
                continue
    df = pd.DataFrame(
        rows.values(),
        index=pd.PeriodIndex([pd.Period(k, "M") for k in rows], freq="M"),
        columns=["MktRF", "SMB", "HML", "RF"],
    ).sort_index() / 100.0
    df.to_csv(path)
    return df


ff3 = fetch_ff3()
universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
px = load_prices()
etfs = ["QQQ", "SPY", "MTUM", "VTV"]
etf_m = month_end_prices(px[etfs]).pct_change()
stock_px = px.drop(columns=etfs)
me = month_end_prices(stock_px)
R = me.pct_change(fill_method=None)            # monthly returns, PeriodIndex
daily_ret = stock_px.pct_change(fill_method=None)

months = R.index
first_possible = 37  # need months[i-36 .. i-1] as returns => 37 prior price points

monthly, daily_parts, holdings_log = {}, [], {}
for i, m in enumerate(months):
    if i < first_possible or str(m) not in universe.index:
        continue
    est_months = months[i - 36 : i]            # [m-36 .. m-1]
    if not est_months.isin(ff3.index).all():
        continue                               # factors not yet available
    F = ff3.loc[est_months]
    X = np.column_stack([np.ones(36), F[["MktRF", "SMB", "HML"]].values])
    members = [t for t in universe.loc[str(m)].split(";") if t in R.columns]
    sig = {}
    for t in members:
        y = R.loc[est_months, t]
        if y.isna().any():
            continue                           # paper-strict: full 36m history
        resid = (y.values - F["RF"].values) - X @ np.linalg.lstsq(
            X, y.values - F["RF"].values, rcond=None
        )[0]
        sel = resid[-12:-1]                    # months [m-12 .. m-2], 11 obs
        sd = sel.std(ddof=1)
        if sd > 0:
            sig[t] = sel.sum() / sd
    if len(sig) < TOP_N:
        continue
    hold = sorted(sig, key=sig.get, reverse=True)[:TOP_N]
    holdings_log[m] = hold
    mask = daily_ret.index.to_period("M") == m
    sub = daily_ret.loc[mask, hold].fillna(0.0)
    d = sub.mean(axis=1)
    daily_parts.append(d)
    monthly[m] = float((1 + d).prod() - 1)

res_d = pd.concat(daily_parts)
res_m = pd.Series(monthly).sort_index()

# eligible-universe size check (recent IPOs drop out under the 36m rule)
n_elig = {m: len(universe.loc[str(m)].split(";")) for m in res_m.index}
print(f"residual sleeve: {res_m.index[0]} .. {res_m.index[-1]} ({len(res_m)} months)")

# standard sleeve, sliced to the common window
std_d, std_m, _, _ = build_sleeve(stock_px, universe)
common = std_m.index.intersection(res_m.index)
std_mc, res_mc = std_m[common], res_m[common]

# turnover of residual sleeve
tos = []
prev = None
for m in sorted(holdings_log):
    cur = set(holdings_log[m])
    if prev is not None:
        tos.append(len(cur - prev) / TOP_N)
    prev = cur

print("=" * 82)
print(f"COMMON WINDOW {common[0]} .. {common[-1]} (gross)")
print(stats_line(etf_m["QQQ"][common], "QQQ"))
print(stats_line(std_mc, "standard momentum top-20"))
print(stats_line(res_mc, "residual momentum top-20"))
print(f"  corr(standard, residual) = {std_mc.corr(res_mc):.2f}")
print(f"  residual sleeve turnover: mean {np.mean(tos)*100:.0f}%/mo (standard was ~25%)")
for label, (dd, mm) in {
    "standard + BSC(20%)": (std_d, std_mc),
    "residual + BSC(20%)": (res_d, res_mc),
}.items():
    w = bsc_weights(dd, 0.20)
    print(stats_line((w * mm).dropna(), label))

print()
print("ALPHA vs QQQ (common window)")
for label, s in [("standard", std_mc), ("residual", res_mc)]:
    a, t, b = capm(s, etf_m["QQQ"][common])
    print(f"  {label:<10} alpha {a*100:6.2f}%/yr (t {t:5.2f}), beta {b:.2f}")

print()
print("CRISIS MONTHS (monthly %, gross)")
rows = []
for m_str in ["2018-10", "2018-12", "2020-02", "2020-03", "2022-04", "2022-06", "2022-09"]:
    m = pd.Period(m_str, "M")
    if m in common:
        rows.append({"month": m_str, "QQQ": etf_m.loc[m, "QQQ"] * 100,
                     "standard": std_mc[m] * 100, "residual": res_mc[m] * 100})
print(pd.DataFrame(rows).set_index("month").round(1).to_string())
