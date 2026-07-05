"""
daily_exit_monitor.py - Dual-Gate Daily Exit Monitor
=================================================
Runs every weekday after US market close.
Downloads previous day's closes, computes MacroState,
and reduces portfolio to 10% long (weakest momentum first) if dual_gate fires.

Usage:
    python python/momentum_strategy/deprecated_scripts/daily_exit_monitor.py
"""
from __future__ import annotations

import csv
import json
import os
import sys
import warnings
from datetime import date

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT      = os.path.join(_BASE_DIR, "..", "..")
_OUTPUT    = os.path.join(_ROOT, "output")
_STATE_FILE = os.path.join(_OUTPUT, "v6dca_state.json")
_EXEC_CSV   = os.path.join(_OUTPUT, "v6dca_executions.csv")

sys.path.insert(0, _BASE_DIR)
from macro_indicators import compute_macro_state
from daily_exit_utils import (
    DUAL_GATE_TARGET_LONG_PCT,
    compute_current_equity,
    compute_sells_to_reach_target_long_pct,
)

_EXEC_COLS = [
    "date", "ticker", "action", "shares", "price", "notional",
    "position_before", "position_after", "avg_price_before", "avg_price_after",
    "sleeve", "weight_before", "weight_after", "target_weight",
    "cash_after", "equity_after", "reason",
]


def _load_state() -> dict:
    with open(_STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False, default=str)
    print(f"State saved → {_STATE_FILE}")


def _fetch_prices_and_rocs(tickers: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """Single yfinance download for both prev close and 4w ROC. Uses 90d lookback."""
    if not tickers:
        return {}, {}
    from macro_indicators import roc_weekly
    raw = yf.download(tickers, period="90d", progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]]
        closes.columns = tickers[:1]

    prices = {}
    rocs = {}
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
        s = closes[ticker].dropna()
        if len(s) > 0:
            prices[ticker] = float(s.iloc[-1])
            rocs[ticker] = roc_weekly(s, 4)
    return prices, rocs


def _append_executions(records: list[dict]) -> None:
    """Append execution rows to v6dca_executions.csv (write header if file is new)."""
    file_exists = os.path.isfile(_EXEC_CSV)
    with open(_EXEC_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_EXEC_COLS)
        if not file_exists:
            writer.writeheader()
        for row in records:
            writer.writerow(row)
    print(f"Appended {len(records)} execution rows → {_EXEC_CSV}")


def run_daily_exit() -> None:
    print("=== daily_exit_monitor ===")

    # 1. Load current state
    if not os.path.isfile(_STATE_FILE):
        print(f"State file not found: {_STATE_FILE}  → nothing to do")
        return
    state = _load_state()
    positions = state.get("positions", {})
    if not positions:
        print("No open positions → nothing to do")
        return

    tickers = [t for t, p in positions.items() if p.get("sleeve", "long") == "long"]
    print(f"Open long positions: {tickers}")

    # 2. Compute MacroState
    ms = compute_macro_state()
    print(ms)

    if not ms.dual_gate:
        print("Dual-gate NOT triggered → no action")
        return

    # 3. Fetch previous closes + 4w ROCs (single download)
    prices, rocs = _fetch_prices_and_rocs(tickers)
    print(f"Prices: {prices}")
    print(f"4w ROCs: {rocs}")

    # 4. Check if already <= target pct
    equity, long_val = compute_current_equity(state, prices)
    current_pct = long_val / equity if equity > 0 else 0
    print(f"Current equity={equity:,.0f}  long={long_val:,.0f}  long_pct={current_pct:.1%}")

    if current_pct <= DUAL_GATE_TARGET_LONG_PCT:
        print(f"Already <= {DUAL_GATE_TARGET_LONG_PCT:.0%} long -> no action")
        return

    # 5. Determine sells
    sells = compute_sells_to_reach_target_long_pct(
        state, prices, rocs, target_long_pct=DUAL_GATE_TARGET_LONG_PCT
    )
    if not sells:
        print("Nothing to sell")
        return

    print(f"Will sell: {[(t, s) for t, s in sells]}")

    # 6. Execute sells: update state + build execution records
    today_str = date.today().isoformat()
    exec_records = []
    cash = float(state["cash"])
    remaining_long = long_val  # track as we sell

    for ticker, shares_to_sell in sells:
        pos  = positions[ticker]
        price = prices.get(ticker)
        if price is None:
            print(f"[daily_exit] WARNING: no price for {ticker}, skipping")
            continue
        notional = shares_to_sell * price
        remaining_long -= shares_to_sell * price
        pos_before = int(pos["shares"])
        pos_after  = pos_before - shares_to_sell
        avg_price  = float(pos["entry_price"])
        weight_before = (pos_before * price) / equity
        weight_after  = (pos_after  * price) / equity
        cash += notional
        equity_after_this_sell = round(cash + remaining_long, 4)

        # Update position in state
        if pos_after == 0:
            del state["positions"][ticker]
        else:
            state["positions"][ticker]["shares"] = pos_after

        exec_records.append({
            "date":              today_str,
            "ticker":            ticker,
            "action":            "REDUCE",
            "shares":            shares_to_sell,
            "price":             round(price, 4),
            "notional":          round(notional, 4),
            "position_before":   pos_before,
            "position_after":    pos_after,
            "avg_price_before":  round(avg_price, 4),
            "avg_price_after":   round(avg_price, 4) if pos_after > 0 else 0.0,
            "sleeve":            "long",
            "weight_before":     round(weight_before, 6),
            "weight_after":      round(weight_after, 6),
            "target_weight":     0.0,
            "cash_after":        round(cash, 4),
            "equity_after":      equity_after_this_sell,
            "reason":            "dual_gate_exit",
        })

    state["cash"] = round(cash, 4)
    state["equity"] = round(cash + remaining_long, 4)

    # 7. Persist
    _append_executions(exec_records)
    _save_state(state)
    print(f"Done. Sold {len(exec_records)} position(s). New cash={cash:,.0f}")


if __name__ == "__main__":
    run_daily_exit()
