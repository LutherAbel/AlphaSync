"""Build the momentum sleeve + BSC vol layer + value combos, per docs/FactorSpec.md.

Gate order (FactorSpec §6): pipeline sanity checks first, performance last.
Outputs: research/output/{sleeve_returns.csv, holdings.csv, report.txt}
"""

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)

TOP_N = 20
SIGMA_TARGET_PRIMARY = 0.20
SIGMA_TARGET_ROBUST = [0.16, 0.24]
COST_PER_SIDE = 0.0010  # 10 bps


def load_prices():
    frames = {}
    for f in os.listdir(CACHE):
        t = f[:-4]
        df = pd.read_csv(os.path.join(CACHE, f), parse_dates=["date"])
        frames[t] = df.set_index("date")["adjClose"]
    px = pd.DataFrame(frames).sort_index()
    return px


def month_end_prices(px):
    grp = px.groupby(px.index.to_period("M"))
    return grp.last()


def build_sleeve(px, universe):
    me = month_end_prices(px)
    months = me.index
    daily_ret = px.pct_change()

    holding_rows, monthly, daily_parts, turnover = [], {}, [], {}
    prev_hold = set()
    first_holding = pd.Period("2015-01", "M")

    for i, m in enumerate(months):
        if m < first_holding or str(m) not in universe.index:
            continue
        f = i - 1  # formation month-end index (previous month)
        if f - 12 < 0:
            continue
        members = universe.loc[str(m)].split(";")
        members = [t for t in members if t in me.columns]
        p_lag1, p_lag12 = me.iloc[f - 1], me.iloc[f - 12]
        sig = {}
        for t in members:
            a, b = p_lag1.get(t), p_lag12.get(t)
            if pd.notna(a) and pd.notna(b) and b > 0:
                sig[t] = a / b - 1.0
        if len(sig) < TOP_N:
            continue
        hold = sorted(sig, key=sig.get, reverse=True)[:TOP_N]

        # turnover (one-way)
        new, old = set(hold), prev_hold
        turnover[m] = len(new - old) / TOP_N if old else 1.0
        prev_hold = new

        # daily EW returns during holding month m; missing (delisted) = 0 cash
        mask = daily_ret.index.to_period("M") == m
        sub = daily_ret.loc[mask, hold].fillna(0.0)
        daily_parts.append(sub.mean(axis=1))
        monthly[m] = float((1 + sub.mean(axis=1)).prod() - 1)
        holding_rows.append({"month": str(m), "holdings": ";".join(hold)})

    sleeve_d = pd.concat(daily_parts)
    sleeve_m = pd.Series(monthly).sort_index()
    holdings = pd.DataFrame(holding_rows)
    to = pd.Series(turnover).sort_index()
    return sleeve_d, sleeve_m, holdings, to


def bsc_weights(daily, sigma_target):
    sq = daily**2
    roll = sq.rolling(126).sum()
    me = roll.groupby(roll.index.to_period("M")).last()
    sigma_m = np.sqrt(21.0 * me / 126.0).shift(1)
    w = (sigma_target / np.sqrt(12.0)) / sigma_m
    return w.clip(upper=1.0)  # retail cap, FactorSpec S3


def maxdd(r):
    c = (1 + r).cumprod()
    return float((c / c.cummax() - 1).min())


def stats_line(x, label):
    x = x.dropna()
    ann = x.mean() * 12
    vol = x.std(ddof=1) * np.sqrt(12)
    sr = ann / vol if vol > 0 else np.nan
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return (
        f"  {label:<32} ann {ann*100:6.2f}%  vol {vol*100:5.2f}%  SR {sr:5.2f}"
        f"  t {t:5.2f}  skew {x.skew():5.2f}  worst_m {x.min()*100:6.1f}%"
        f"  maxDD {maxdd(x)*100:6.1f}%"
    )


def capm(y, x):
    y, x = y.align(x, join="inner")
    X = np.column_stack([np.ones(len(x)), x.values])
    b, *_ = np.linalg.lstsq(X, y.values, rcond=None)
    resid = y.values - X @ b
    se_b = np.sqrt(
        np.sum(resid**2) / (len(y) - 2) / np.sum((x - x.mean()) ** 2)
    )
    se_a = se_b * np.sqrt(np.mean(x.values**2))
    return b[0] * 12, b[0] / se_a, b[1]


def main():
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    universe = pd.read_csv(
        os.path.join(DATA, "universe_monthly.csv"), index_col="month"
    )["tickers"]
    px = load_prices()
    etf_m = month_end_prices(px[["QQQ", "SPY", "MTUM", "VTV"]]).pct_change()

    sleeve_d, sleeve_m, holdings, to = build_sleeve(
        px.drop(columns=["QQQ", "SPY", "MTUM", "VTV"]), universe
    )
    holdings.to_csv(os.path.join(OUT, "holdings.csv"), index=False)

    # ---- Gate 1: known-event spot checks (FactorSpec S6.1) ----
    emit("=" * 78)
    emit("GATE 1: spot checks")
    h = holdings.set_index("month")["holdings"].str.split(";")
    nvda_2324 = np.mean(
        [("NVDA" in h[m]) for m in h.index if m >= "2023-01" and m <= "2024-12"]
    )
    tsla_2020h2 = np.mean(
        [("TSLA" in h[m]) for m in h.index if m >= "2020-07" and m <= "2020-12"]
    )
    emit(f"  NVDA in top-20, 2023-2024: {nvda_2324*100:.0f}% of months (expect high)")
    emit(f"  TSLA in top-20, 2020H2:    {tsla_2020h2*100:.0f}% of months (expect high)")

    # ---- Gate 2: correlations / beta (FactorSpec S6.2) ----
    emit("GATE 2: correlation structure")
    for etf in ["QQQ", "SPY", "MTUM"]:
        c = sleeve_m.corr(etf_m[etf])
        emit(f"  corr(sleeve, {etf}) = {c:.2f}")
    a_q, t_q, b_q = capm(sleeve_m, etf_m["QQQ"].dropna())
    emit(f"  beta vs QQQ = {b_q:.2f} (expect ~1)")

    # ---- Gate 3: turnover (FactorSpec S6.3) ----
    emit("GATE 3: turnover")
    emit(
        f"  monthly one-way turnover: mean {to.mean()*100:.0f}%,"
        f" median {to.median()*100:.0f}% (literature momentum: high)"
    )

    # ---- Performance (only meaningful if gates pass) ----
    emit("=" * 78)
    emit(f"PERFORMANCE {sleeve_m.index[0]} .. {sleeve_m.index[-1]} (gross)")
    w = bsc_weights(sleeve_d, SIGMA_TARGET_PRIMARY)
    managed_m = (w * sleeve_m).dropna()
    emit(stats_line(etf_m["SPY"], "SPY"))
    emit(stats_line(etf_m["QQQ"], "QQQ"))
    emit(stats_line(etf_m["MTUM"], "MTUM"))
    emit(stats_line(sleeve_m, "momentum sleeve (plain)"))
    emit(stats_line(managed_m, f"sleeve + BSC(20%, cap 1)"))
    for st in SIGMA_TARGET_ROBUST:
        wr = bsc_weights(sleeve_d, st)
        emit(stats_line((wr * sleeve_m).dropna(), f"sleeve + BSC({int(st*100)}%, cap 1)"))
    emit(f"  BSC weight: median {w.median():.2f}, months at cap {np.mean(w>=0.999)*100:.0f}%")

    emit("")
    emit("VALUE COMBOS (managed momentum + unmanaged VTV, monthly rebalance)")
    vtv = etf_m["VTV"]
    for wm in [0.75, 0.50]:
        combo = (wm * managed_m + (1 - wm) * vtv).dropna()
        emit(stats_line(combo, f"{int(wm*100)}/{int((1-wm)*100)} mom/value"))

    emit("")
    emit("ALPHA REGRESSIONS (monthly)")
    for label, series in [
        ("sleeve plain", sleeve_m),
        ("sleeve managed", managed_m),
    ]:
        for bench in ["QQQ", "SPY"]:
            a, t, b = capm(series, etf_m[bench].dropna())
            emit(f"  {label:<16} vs {bench}: alpha {a*100:6.2f}%/yr (t {t:5.2f}), beta {b:.2f}")

    emit("")
    emit("NET OF COSTS (10 bps per side x turnover)")
    net = sleeve_m - to.reindex(sleeve_m.index).fillna(0) * 2 * COST_PER_SIDE
    emit(stats_line(net, "momentum sleeve (net)"))
    net_mgd = (w * net).dropna()
    emit(stats_line(net_mgd, "sleeve + BSC (net)"))

    sleeve_m.rename("sleeve_plain").to_frame().join(
        managed_m.rename("sleeve_managed"), how="left"
    ).join(etf_m[["QQQ", "SPY", "MTUM", "VTV"]], how="left").to_csv(
        os.path.join(OUT, "sleeve_returns.csv")
    )
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nsaved: output/report.txt, sleeve_returns.csv, holdings.csv")


if __name__ == "__main__":
    main()
