"""
generate_data.py — Generates bars.json, holdings.json, trades.json
for the Berkshire TradeBot web dashboard.
"""
import os
import json
import csv
import datetime
import math
from dataclasses import dataclass

import yfinance as yf
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
INPUT_DIR = os.path.join(ROOT, "output")
CACHE_DIR = os.path.join(ROOT, "cache")  # 價格快取已移出 output
def resolve_web_root(root: str) -> str:
    env_root = os.environ.get("WEB_ROOT")
    if env_root:
        web_root = os.path.abspath(env_root)
        if os.path.isdir(web_root):
            return web_root
        raise RuntimeError(f"WEB_ROOT does not exist: {web_root}")

    candidates = [
        os.path.join(root, "web"),
        os.path.join(root, ".worktrees", "web-phase1", "web"),
    ]
    for candidate in candidates:
        web_root = os.path.abspath(candidate)
        if os.path.isdir(web_root):
            return web_root

    searched = ", ".join(os.path.abspath(p) for p in candidates)
    raise RuntimeError(
        f"Web app directory not found. Searched: {searched}. "
        "Set WEB_ROOT to the web app path if it lives elsewhere."
    )


WEB_ROOT = resolve_web_root(ROOT)
OUTPUT_DIR = os.path.join(WEB_ROOT, "data")
PRICE_CACHE_DIR = os.path.join(CACHE_DIR, "price_cache")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def clean_json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json_value(v) for v in value]
    return value

# ── Inlined macro indicators (self-contained) ───────────────────────────────
_LOOKBACK_DAYS = 210
_JPY_ROC_ALERT = 4.0
_USD_ROC_ALERT = 3.0
_CREDIT_ROC_ALERT = -5.0


def _cache_symbol_name(ticker: str) -> str:
    s = str(ticker or "").upper().strip()
    if not s:
        return "UNKNOWN"
    return "".join(ch if ch.isalnum() else "_" for ch in s)


def _load_cached_close(ticker: str, start_date: str, end_date: str) -> pd.Series:
    path = os.path.join(PRICE_CACHE_DIR, f"{_cache_symbol_name(ticker)}__1d.csv")
    if not os.path.exists(path):
        return pd.Series(dtype=float, name=ticker)

    df = pd.read_csv(path, parse_dates=["Date"])
    if "Date" not in df.columns or "Close" not in df.columns:
        return pd.Series(dtype=float, name=ticker)

    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    close = close.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)]
    close.name = ticker
    return close


@dataclass
class MacroState:
    alert_vix: bool
    alert_jpy: bool
    alert_usd: bool
    alert_credit: bool
    macro_alert: bool
    spy_below_20w_ma: bool
    dual_gate: bool
    vix_clear: bool
    usd_clear: bool
    all_clear: bool


def roc_weekly(series: pd.Series, weeks: int) -> float:
    weekly = series.resample("W-FRI").last().dropna()
    if len(weekly) < weeks + 1:
        return 0.0
    return float(weekly.iloc[-1] / weekly.iloc[-(weeks + 1)] - 1) * 100.0


def _20w_sma(series: pd.Series) -> float:
    weekly = series.resample("W-FRI").last().dropna()
    if len(weekly) < 20:
        return float(weekly.mean()) if len(weekly) > 0 else 0.0
    return float(weekly.tail(20).mean())


def compute_macro_state_from_prices(
    vix: float,
    vix3m: float,
    fxy_weekly: pd.Series,
    uup_weekly: pd.Series,
    credit_weekly: pd.Series,
    spy_weekly: pd.Series,
) -> MacroState:
    uup_4w_roc = roc_weekly(uup_weekly, 4)
    alert_vix = vix > vix3m
    alert_jpy = roc_weekly(fxy_weekly, 4) > _JPY_ROC_ALERT
    alert_usd = uup_4w_roc > _USD_ROC_ALERT
    alert_credit = roc_weekly(credit_weekly, 12) < _CREDIT_ROC_ALERT
    macro_alert = alert_vix or alert_jpy or alert_usd or alert_credit

    spy_sma20w = _20w_sma(spy_weekly)
    spy_last = float(spy_weekly.dropna().iloc[-1])
    spy_below_20w_ma = spy_last < spy_sma20w

    dual_gate = macro_alert and spy_below_20w_ma
    vix_clear = vix < vix3m
    usd_clear = uup_4w_roc < 0.0
    all_clear = vix_clear and usd_clear

    return MacroState(
        alert_vix=alert_vix,
        alert_jpy=alert_jpy,
        alert_usd=alert_usd,
        alert_credit=alert_credit,
        macro_alert=macro_alert,
        spy_below_20w_ma=spy_below_20w_ma,
        dual_gate=dual_gate,
        vix_clear=vix_clear,
        usd_clear=usd_clear,
        all_clear=all_clear,
    )


def build_macro_history(start_date: str, end_date: str) -> pd.DataFrame:
    dl_start = (pd.Timestamp(start_date) - pd.Timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    tickers = ["^VIX", "^VIX3M", "FXY", "UUP", "HYG", "IEF", "SPY"]
    cached = pd.concat(
        [_load_cached_close(ticker, dl_start, end_date) for ticker in tickers],
        axis=1,
    ).rename(columns={"^VIX": "VIX", "^VIX3M": "VIX3M"})

    required = ["VIX", "VIX3M", "FXY", "UUP", "HYG", "IEF", "SPY"]
    if all(col in cached.columns and not cached[col].dropna().empty for col in required):
        return cached.ffill()

    try:
        raw = yf.download(tickers, start=dl_start, end=end_date, progress=False, auto_adjust=True)
    except Exception as exc:
        print(f"macro history download failed; using cached prices where available: {exc}")
        raw = pd.DataFrame()

    if raw.empty:
        df = cached
    elif isinstance(raw.columns, pd.MultiIndex):
        df = raw["Close"].copy()
    else:
        df = raw.copy()

    df = df.rename(columns={"^VIX": "VIX", "^VIX3M": "VIX3M"})
    df = cached.combine_first(df)
    return df.ffill()


def compute_macro_state_at_date(macro_df: pd.DataFrame, date: pd.Timestamp) -> MacroState:
    _all_clear = MacroState(False, False, False, False, False, False, False, True, True, True)
    window_start = date - pd.Timedelta(days=_LOOKBACK_DAYS)
    window = macro_df.loc[window_start:date]
    if window.empty or len(window) < 10:
        return _all_clear

    def _col(name: str) -> pd.Series:
        return window[name].dropna() if name in window.columns else pd.Series(dtype=float)

    vix_s = _col("VIX")
    vix3m_s = _col("VIX3M")
    if vix_s.empty or vix3m_s.empty:
        return _all_clear

    vix = float(vix_s.iloc[-1])
    vix3m = float(vix3m_s.iloc[-1])
    hyg_s, ief_s = _col("HYG"), _col("IEF")
    credit_s = (hyg_s / ief_s.reindex(hyg_s.index, method="ffill")).dropna() \
        if not hyg_s.empty and not ief_s.empty else pd.Series(dtype=float)

    return compute_macro_state_from_prices(
        vix=vix,
        vix3m=vix3m,
        fxy_weekly=_col("FXY"),
        uup_weekly=_col("UUP"),
        credit_weekly=credit_s,
        spy_weekly=_col("SPY"),
    )

EQUITY_CSV   = os.path.join(INPUT_DIR, "v6dca_equity_curve.csv")
STATE_JSON   = os.path.join(INPUT_DIR, "v6dca_state.json")
TRADES_CSV   = os.path.join(INPUT_DIR, "v6dca_trades.csv")
EXEC_CSV     = os.path.join(INPUT_DIR, "v6dca_executions.csv")

# ── 1. Load equity curve ───────────────────────────────────────────────────
eq_rows = []
with open(EQUITY_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        eq_rows.append(row)

dates           = [r["date"] for r in eq_rows]
signal_dates    = [r.get("signal_date") or r["date"] for r in eq_rows]
execution_dates = [r.get("execution_date") or r["date"] for r in eq_rows]
data_frequency  = [r.get("data_frequency") or "weekly" for r in eq_rows]
equity          = [float(r["equity"]) for r in eq_rows]
nav             = [float(r["nav"]) if r.get("nav") not in ("", None) else None for r in eq_rows]
total_injected  = [float(r["total_injected"]) for r in eq_rows]
regime_score    = [float(r["regime_score"]) if r["regime_score"] not in ("", None) else None for r in eq_rows]
long_n          = [int(r["long_n"]) if r["long_n"] not in ("", None) else 0 for r in eq_rows]
long_pct        = [round(float(r["long_pct"]), 4) if r.get("long_pct") not in ("", None) else 0.0 for r in eq_rows]
cs_stage        = [str(r["cs_stage"]) if r["cs_stage"] not in ("", None) else "" for r in eq_rows]

# ── 2. Load SPY daily prices aligned to strategy execution dates ───────────
start_dt = datetime.datetime.strptime(dates[0], "%Y-%m-%d")
end_dt   = datetime.datetime.strptime(dates[-1], "%Y-%m-%d") + datetime.timedelta(days=14)

spy_cache_path = os.path.join(PRICE_CACHE_DIR, "SPY__1d.csv")
if os.path.exists(spy_cache_path):
    spy_raw = pd.read_csv(spy_cache_path, parse_dates=["Date"]).set_index("Date").sort_index()
else:
    spy_raw = yf.download(
        "SPY",
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

    # Handle MultiIndex columns from yfinance
    if isinstance(spy_raw.columns, pd.MultiIndex):
        spy_raw.columns = spy_raw.columns.droplevel(1)

if "Close" not in spy_raw.columns or spy_raw["Close"].dropna().empty:
    raise RuntimeError("SPY daily close data is unavailable; cannot generate a correct benchmark.")

# Build a Series of SPY close indexed by date string
spy_close = spy_raw["Close"].dropna().copy()
# Ensure spy_close is a Series, not a DataFrame
if isinstance(spy_close, pd.DataFrame):
    spy_close = spy_close.squeeze()
spy_close.index = pd.to_datetime(spy_close.index).strftime("%Y-%m-%d")

# Build a daily-indexed SPY series spanning all equity dates, ffill
date_range = pd.date_range(start=dates[0], end=dates[-1], freq="D")
spy_daily = pd.Series(dtype=float, index=date_range.strftime("%Y-%m-%d"))
for d, v in spy_close.items():
    if d in spy_daily.index:
        spy_daily[d] = float(v)
spy_daily = spy_daily.ffill().bfill()

# Compute SPY return aligned to each strategy execution date
spy_returns = {}
prev_spy = None
for d in dates:
    cur = spy_daily.get(d, None)
    if cur is None or pd.isna(cur) or (prev_spy is None):
        spy_returns[d] = 0.0
    else:
        spy_returns[d] = float(cur / prev_spy - 1) if prev_spy != 0 else 0.0
    if cur is not None and not pd.isna(cur):
        prev_spy = cur

# ── 3. Build bars ─────────────────────────────────────────────────────────
macro_hist = build_macro_history(dates[0], dates[-1])
bars = []
for t, row in enumerate(eq_rows):
    date = dates[t]
    if t == 0:
        bar_ret = 0.0
        injection = 0.0
    else:
        injection = total_injected[t] - total_injected[t - 1]
        denom = equity[t - 1] + injection
        bar_ret = float(equity[t] / denom - 1) if denom != 0 else 0.0

    rs = regime_score[t]
    ms = compute_macro_state_at_date(macro_hist, pd.Timestamp(date))
    spy_ret = spy_returns.get(date, 0.0)
    if pd.isna(spy_ret):
        raise RuntimeError(f"SPY return is NaN at {date}; cannot generate a correct benchmark.")
    bars.append({
        "date":           date,
        "signal_date":    signal_dates[t],
        "execution_date": execution_dates[t],
        "data_frequency": data_frequency[t],
        "equity":         round(equity[t], 4),
        "nav":            round(nav[t], 6) if nav[t] is not None else None,
        "bar_return":     round(bar_ret, 6),
        "is_injection":   injection > 0,
        "spy_return":     round(spy_ret, 6),
        "dual_gate":      bool(ms.dual_gate),
        "regime_score":   round(rs, 4) if rs is not None else None,
        "long_pct":       long_pct[t],
        "long_n":         long_n[t],
        "cs_stage":       cs_stage[t],
        "total_injected": total_injected[t],
    })

out_path = os.path.join(OUTPUT_DIR, "bars.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(clean_json_value(bars), f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
print(f"bars.json: {len(bars)} rows")

# ── 4. Build holdings ─────────────────────────────────────────────────────
with open(STATE_JSON, encoding="utf-8") as f:
    state = json.load(f)

holdings = []
asof_date = pd.Timestamp(state.get("last_processed_date")).normalize()
equity_now = float(state.get("equity", 0.0))
for ticker, pos in state["positions"].items():
    close_s = _load_cached_close(ticker, "1990-01-01", asof_date.strftime("%Y-%m-%d"))
    current_price = float(close_s.iloc[-1]) if len(close_s) else float(pos["entry_price"])
    shares = float(pos["shares"])
    market_value = current_price * shares
    weight = (market_value / equity_now) if equity_now > 0 else 0.0
    holdings.append({
        "ticker":            ticker,
        "first_entry_date":  pos["entry_date"],
        "avg_cost":          round(float(pos["entry_price"]), 4),
        "current_price":     round(current_price, 4),
        "position_value":    round(market_value, 2),
        "weight":            round(weight, 6),
        "shares":            pos["shares"],
        "sleeve":            pos["sleeve"],
    })

out_path = os.path.join(OUTPUT_DIR, "holdings.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(holdings, f, ensure_ascii=False, separators=(",", ":"))
print(f"holdings.json: {len(holdings)} positions")

# ── 5. Build trades ───────────────────────────────────────────────────────
trades = []
with open(TRADES_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        trades.append({
            "ticker":      row["ticker"],
            "entry_date":  row["entry_date"],
            "exit_date":   row["exit_date"],
            "entry_price": round(float(row["entry_price"]), 4),
            "exit_price":  round(float(row["exit_price"]), 4),
            "shares":      int(row["shares"]) if row["shares"] else 0,
            "pnl":         round(float(row["pnl"]), 2),
            "pnl_pct":     round(float(row["pnl_pct"]), 4),
            "exit_reason": row["exit_reason"],
            "hold_bars":   int(row["hold_bars"]) if row["hold_bars"] else 0,
        })

out_path = os.path.join(OUTPUT_DIR, "trades.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(trades, f, ensure_ascii=False, separators=(",", ":"))
print(f"trades.json: {len(trades)} trades")

# ── 6. Build executions ───────────────────────────────────────────────────
executions = []
with open(EXEC_CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        avg_before = float(row["avg_price_before"]) if row["avg_price_before"] not in ("", None, "0", "0.0") else None
        price = float(row["price"])
        shares = int(float(row["shares"])) if row["shares"] else 0
        action = row["action"]
        pnl_pct = None
        pnl_dollar = None
        if action in ("SELL", "REDUCE") and avg_before and avg_before > 0:
            pnl_pct = round((price - avg_before) / avg_before, 4)
            pnl_dollar = round((price - avg_before) * shares, 2)
        executions.append({
            "date":             row["date"],
            "ticker":           row["ticker"],
            "action":           action,
            "shares":           shares,
            "price":            round(price, 4),
            "avg_price_before": round(avg_before, 4) if avg_before else None,
            "sleeve":           row["sleeve"],
            "reason":           row["reason"],
            "pnl_pct":          pnl_pct,
            "pnl_dollar":       pnl_dollar,
        })

out_path = os.path.join(OUTPUT_DIR, "executions.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(executions, f, ensure_ascii=False, separators=(",", ":"))
print(f"executions.json: {len(executions)} rows")

print("Done.")
