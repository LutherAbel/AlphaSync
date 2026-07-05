# tests/test_daily_exit.py
import sys, os, json, csv, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python", "monitor"))

import pytest
from daily_exit_utils import (
    compute_current_equity,
    rank_positions_by_momentum,
    compute_sells_to_reach_target_long_pct,
)


def make_state(positions: dict, cash: float) -> dict:
    return {"cash": cash, "equity": 0.0, "last_processed_date": "2026-04-18",
            "positions": positions}


def make_pos(shares: int, entry_price: float, momentum: float = 10.0) -> dict:
    return {"shares": shares, "entry_price": entry_price, "entry_date": "2026-01-01",
            "stop_price": entry_price * 0.9, "highest_since_entry": entry_price,
            "trailing_stop": entry_price * 0.9, "sleeve": "long",
            "entry_bar_idx": 0, "momentum_at_entry": momentum,
            "entry_alloc_pct": 0.15, "target_weight": 0.15}


def test_compute_current_equity():
    state = make_state({"AAPL": make_pos(10, 150.0)}, cash=5000.0)
    prices = {"AAPL": 200.0}
    equity, long_val = compute_current_equity(state, prices)
    assert equity == pytest.approx(7000.0)   # 5000 + 10*200
    assert long_val == pytest.approx(2000.0) # 10*200


def test_rank_positions_by_momentum():
    state = make_state({
        "AAA": make_pos(10, 100.0, momentum=5.0),
        "BBB": make_pos(10, 100.0, momentum=25.0),
        "CCC": make_pos(10, 100.0, momentum=-3.0),
    }, cash=0.0)
    rocs = {"AAA": 3.0, "BBB": 20.0, "CCC": -5.0}
    ranked = rank_positions_by_momentum(state, rocs)
    assert [t for t, _ in ranked] == ["CCC", "AAA", "BBB"]


def test_compute_sells_exact_threshold():
    # equity=100k, long=80k (80%), cash=20k → need to sell down to 10k long
    # positions: A=40k, B=25k, C=15k sorted by ROC asc: C(ROC=-2), A(ROC=1), B(ROC=5)
    state = make_state({
        "A": make_pos(400, 100.0),
        "B": make_pos(250, 100.0),
        "C": make_pos(150, 100.0),
    }, cash=20_000.0)
    prices = {"A": 100.0, "B": 100.0, "C": 100.0}
    rocs   = {"A": 1.0, "B": 5.0, "C": -2.0}
    sells = compute_sells_to_reach_target_long_pct(state, prices, rocs, target_long_pct=0.10)
    # Must sell C (15k), A (40k), then B partial 15k to reach 10k long target.
    tickers_sold = [t for t, _ in sells]
    assert "C" in tickers_sold
    assert "A" in tickers_sold
    assert "B" in tickers_sold


def test_compute_sells_partial_last():
    # equity=100k, cash=10k, long=90k → target long = 10k → sell 80k worth
    # only one position: 900 shares @ 100 = 90k
    # sell 800 shares → remaining 100 shares = 10k = 10% ✓
    state = make_state({"X": make_pos(900, 100.0)}, cash=10_000.0)
    prices = {"X": 100.0}
    rocs   = {"X": 5.0}
    sells = compute_sells_to_reach_target_long_pct(state, prices, rocs, target_long_pct=0.10)
    assert len(sells) == 1
    ticker, shares_to_sell = sells[0]
    assert ticker == "X"
    assert shares_to_sell == 800  # sell 800, keep 100
