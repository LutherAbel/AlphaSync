import importlib.util
import os
import sys

import pandas as pd
import pytest


ROOT = os.path.dirname(os.path.dirname(__file__))
MODULE_PATH = os.path.join(ROOT, "python", "main_ashare.py")

spec = importlib.util.spec_from_file_location("main_ashare", MODULE_PATH)
ashare = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = ashare
spec.loader.exec_module(ashare)


def test_score_assets_uses_only_prior_bars_for_rebalance_date():
    dates = pd.date_range("2024-01-01", periods=140, freq="D")
    close = pd.DataFrame(
        {
            "AAA": [100.0 + i for i in range(140)],
            "BBB": [100.0 for _ in range(139)] + [1000.0],
        },
        index=dates,
    )
    volume = pd.DataFrame(1_000_000, index=dates, columns=close.columns)

    scores = ashare.score_assets(
        close=close,
        volume=volume,
        symbols=["AAA", "BBB"],
        date=dates[-1],
        lookbacks=(20, 60, 120),
    )

    assert list(scores.index) == ["AAA", "BBB"]
    assert scores.loc["AAA", "score"] > scores.loc["BBB", "score"]


def test_select_targets_prefers_fallback_when_regime_is_off():
    scores = pd.DataFrame(
        {"score": [3.0, 2.0], "trend_ok": [True, True]},
        index=["510300.SS", "510500.SS"],
    )

    targets = ashare.select_targets(
        scores=scores,
        risk_on=False,
        top_n=3,
        fallback_symbols=["518880.SS", "511010.SS"],
    )

    assert targets == ["518880.SS", "511010.SS"]
