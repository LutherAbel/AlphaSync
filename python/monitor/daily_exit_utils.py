"""
daily_exit_utils.py — Pure utility functions for dual-gate exit logic.
No I/O, no network. Testable in isolation.
"""
from __future__ import annotations


def compute_current_equity(state: dict, prices: dict[str, float]) -> tuple[float, float]:
    """
    Returns (total_equity, total_long_value) using current prices.
    state: loaded state JSON dict
    prices: {ticker: prev_close_price}
    """
    cash = float(state["cash"])
    long_val = 0.0
    for ticker, pos in state.get("positions", {}).items():
        if pos.get("sleeve", "long") != "long":
            continue
        price = prices.get(ticker)
        if price is None:
            continue
        long_val += int(pos["shares"]) * price
    return cash + long_val, long_val


def rank_positions_by_momentum(
    state: dict, rocs: dict[str, float]
) -> list[tuple[str, float]]:
    """
    Returns positions sorted ascending by 4-week ROC (weakest first).
    rocs: {ticker: 4_week_roc_pct}
    """
    result = []
    for ticker, pos in state.get("positions", {}).items():
        if pos.get("sleeve", "long") != "long":
            continue
        roc = rocs.get(ticker, 0.0)
        result.append((ticker, roc))
    return sorted(result, key=lambda x: x[1])


DUAL_GATE_TARGET_LONG_PCT = 0.10


def compute_sells_to_reach_target_long_pct(
    state: dict,
    prices: dict[str, float],
    rocs: dict[str, float],
    target_long_pct: float = DUAL_GATE_TARGET_LONG_PCT,
) -> list[tuple[str, int]]:
    """
    Returns list of (ticker, shares_to_sell) to reduce long exposure to target pct.
    Sells weakest-momentum positions first (whole positions).
    Last position may be partial to land exactly at target.

    Returns empty list if already ≤ target.
    """
    equity, long_val = compute_current_equity(state, prices)
    if equity <= 0:
        return []
    target_long = equity * target_long_pct
    if long_val <= target_long:
        return []

    ranked = rank_positions_by_momentum(state, rocs)
    need_to_sell = long_val - target_long

    sells: list[tuple[str, int]] = []
    sold_value = 0.0

    for ticker, _roc in ranked:
        if sold_value >= need_to_sell:
            break
        shares = int(state["positions"][ticker]["shares"])
        price  = prices.get(ticker, 0.0)
        if price <= 0:
            continue  # skip positions with no valid price
        pos_value = shares * price
        remaining_to_sell = need_to_sell - sold_value

        if pos_value <= remaining_to_sell:
            # Sell entire position
            sells.append((ticker, shares))
            sold_value += pos_value
        else:
            # Partial sell: sell just enough shares (floor)
            shares_to_sell = int(remaining_to_sell / price)
            if shares_to_sell > 0:
                sells.append((ticker, shares_to_sell))
            sold_value += shares_to_sell * price
            break

    return sells


def compute_sells_to_reach_30pct(
    state: dict,
    prices: dict[str, float],
    rocs: dict[str, float],
) -> list[tuple[str, int]]:
    """Backward-compatible alias."""
    return compute_sells_to_reach_target_long_pct(state, prices, rocs)
