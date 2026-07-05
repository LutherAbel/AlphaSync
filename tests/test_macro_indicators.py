# tests/test_macro_indicators.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python", "monitor"))

import pandas as pd
import pytest
from macro_indicators import roc_weekly, MacroState, compute_macro_state_from_prices


def make_weekly_series(values: list) -> pd.Series:
    """Helper: weekly price series ending today."""
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=len(values), freq="W-FRI")
    return pd.Series(values, index=idx)


def test_roc_weekly_4w():
    # 4 weeks ago = 100, now = 104 → ROC = 4.0%
    s = make_weekly_series([100, 101, 102, 103, 104])
    assert abs(roc_weekly(s, 4) - 4.0) < 0.01


def test_roc_weekly_insufficient_data():
    s = make_weekly_series([100, 101])
    assert roc_weekly(s, 4) == 0.0


def test_macro_state_dual_gate_true():
    # VIX > VIX3M triggers alert; SPY below 20w MA triggers price gate
    spy_weekly = make_weekly_series([200] * 19 + [170])  # 20w MA ~= 198, last = 170
    ms = compute_macro_state_from_prices(
        vix=25.0, vix3m=20.0,        # VIX > VIX3M → alert_vix = True
        fxy_weekly=make_weekly_series([22.0] * 5),  # flat → alert_jpy = False
        uup_weekly=make_weekly_series([27.0] * 5),  # flat → alert_usd = False
        credit_weekly=make_weekly_series([1.0] * 13),  # flat → alert_credit = False
        spy_weekly=spy_weekly,
    )
    assert ms.alert_vix is True
    assert ms.macro_alert is True
    assert ms.spy_below_20w_ma is True
    assert ms.dual_gate is True


def test_macro_state_dual_gate_false_price_ok():
    # Alert fires but SPY still above 20w MA → no dual gate
    spy_weekly = make_weekly_series([190] * 19 + [210])  # last > MA
    ms = compute_macro_state_from_prices(
        vix=25.0, vix3m=20.0,
        fxy_weekly=make_weekly_series([22.0] * 5),
        uup_weekly=make_weekly_series([27.0] * 5),
        credit_weekly=make_weekly_series([1.0] * 13),
        spy_weekly=spy_weekly,
    )
    assert ms.macro_alert is True
    assert ms.spy_below_20w_ma is False
    assert ms.dual_gate is False


def test_macro_state_all_clear():
    # VIX < VIX3M and UUP ROC < 0 → all_clear
    ms = compute_macro_state_from_prices(
        vix=18.0, vix3m=22.0,         # VIX < VIX3M → vix_clear
        fxy_weekly=make_weekly_series([22.0] * 5),
        uup_weekly=make_weekly_series([28.0, 27.5, 27.0, 26.5, 26.0]),  # declining → usd_clear
        credit_weekly=make_weekly_series([1.0] * 13),
        spy_weekly=make_weekly_series([200] * 20),
    )
    assert ms.vix_clear is True
    assert ms.usd_clear is True
    assert ms.all_clear is True
