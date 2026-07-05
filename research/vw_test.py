"""Trial #6 (FactorSpec changelog 2026-07-05): value-weighted top-20.

Signal, selection, monthly rebalance identical to build_factor.build_sleeve.
Only the within-month weighting changes:
  EW  : daily equal weight (no drift), per locked spec
  VW  : formation-date market-cap weights, buy-and-hold within month (drift)
Market cap = point-in-time shares (latest SEC filing with filed <= formation
month-end) x formation month-end adjClose. Holdings lacking shares data get
the month's median cap (neutral placement, counted and reported).

Outputs comparison stats + correlation/beta vs QQQ for both variants.
"""

import os

import numpy as np
import pandas as pd

from build_factor import TOP_N, capm, load_prices, maxdd, month_end_prices

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")


def load_shares():
    df = pd.read_csv(os.path.join(DATA, "shares_outstanding.csv"), parse_dates=["filed"])
    return df.sort_values("filed")


def pit_shares(shares_df, ticker, asof):
    sub = shares_df[(shares_df["ticker"] == ticker) & (shares_df["filed"] <= asof)]
    if sub.empty:
        return None
    return float(sub.iloc[-1]["shares"])


def build_both(px, universe, shares_df):
    me = month_end_prices(px)
    me_dates = px.groupby(px.index.to_period("M")).apply(lambda d: d.index.max())
    months = me.index
    daily_ret = px.pct_change(fill_method=None)

    first_holding = pd.Period("2015-01", "M")
    ew_m, vw_m = {}, {}
    fallback_events = []

    for i, m in enumerate(months):
        if m < first_holding or str(m) not in universe.index:
            continue
        f = i - 1
        if f - 12 < 0:
            continue
        members = [t for t in universe.loc[str(m)].split(";") if t in me.columns]
        p_lag1, p_lag12 = me.iloc[f - 1], me.iloc[f - 12]
        sig = {}
        for t in members:
            a, b = p_lag1.get(t), p_lag12.get(t)
            if pd.notna(a) and pd.notna(b) and b > 0:
                sig[t] = a / b - 1.0
        if len(sig) < TOP_N:
            continue
        hold = sorted(sig, key=sig.get, reverse=True)[:TOP_N]

        mask = daily_ret.index.to_period("M") == m
        sub = daily_ret.loc[mask, hold].fillna(0.0)

        # EW (locked spec): daily equal weight
        ew_m[m] = float((1 + sub.mean(axis=1)).prod() - 1)

        # VW: formation-date caps, buy-and-hold drift within month
        formation_date = me_dates.iloc[f]
        f_px = me.iloc[f]
        caps = {}
        for t in hold:
            sh = pit_shares(shares_df, t, formation_date)
            p = f_px.get(t)
            if sh is not None and pd.notna(p):
                caps[t] = sh * float(p)
        if len(caps) < TOP_N:
            med = np.median(list(caps.values())) if caps else np.nan
            for t in hold:
                if t not in caps:
                    caps[t] = med
                    fallback_events.append((str(m), t))
        w0 = pd.Series({t: caps[t] for t in hold})
        w0 = w0 / w0.sum()
        cum = (1 + sub).cumprod()
        port_value = cum.mul(w0, axis=1).sum(axis=1)  # starts near 1
        vw_m[m] = float(port_value.iloc[-1] - 1)

    return pd.Series(ew_m).sort_index(), pd.Series(vw_m).sort_index(), fallback_events


def stats(x):
    ann = x.mean() * 12
    vol = x.std(ddof=1) * np.sqrt(12)
    return ann, vol, ann / vol, maxdd(x)


def main():
    universe = pd.read_csv(os.path.join(DATA, "universe_monthly.csv"), index_col="month")["tickers"]
    px = load_prices()
    etf_m = month_end_prices(px[["QQQ", "SPY"]]).pct_change()
    stock_px = px.drop(columns=[c for c in ["QQQ", "SPY", "MTUM", "VTV"] if c in px.columns])
    shares_df = load_shares()

    ew, vw, fallback = build_both(stock_px, universe, shares_df)
    common = ew.index.intersection(vw.index)
    ew, vw = ew[common], vw[common]
    qqq = etf_m["QQQ"][common]

    print(f"window: {common[0]} .. {common[-1]}  ({len(common)} months)")
    print(f"cap fallback events (median-cap placement): {len(fallback)}")
    if fallback:
        from collections import Counter
        print("  by ticker:", Counter(t for _, t in fallback).most_common(8))

    print(f"\n{'':22} {'ann':>8} {'vol':>7} {'SR':>6} {'maxDD':>8}")
    for label, s in [("QQQ", qqq), ("EW sleeve (spec)", ew), ("VW sleeve (trial 6)", vw)]:
        a, v, sr, dd = stats(s)
        print(f"{label:22} {a*100:7.2f}% {v*100:6.2f}% {sr:6.2f} {dd*100:7.1f}%")

    for label, s in [("EW", ew), ("VW", vw)]:
        alpha, t, beta = capm(s, qqq)
        excess = s - qqq
        t_ex = excess.mean() / (excess.std(ddof=1) / np.sqrt(len(excess)))
        print(f"\n{label} vs QQQ: corr {s.corr(qqq):.2f}  beta {beta:.2f}  "
              f"alpha {alpha*100:+.2f}%/yr (t {t:.2f})  "
              f"excess {excess.mean()*12*100:+.2f}%/yr (t {t_ex:.2f})")

    gap = ew - vw
    print(f"\nEW-minus-VW (weighting effect): {gap.mean()*12*100:+.2f}%/yr  "
          f"(t {gap.mean()/(gap.std(ddof=1)/np.sqrt(len(gap))):.2f})")
    print(f"EW/VW monthly correlation: {ew.corr(vw):.3f}")


if __name__ == "__main__":
    main()
