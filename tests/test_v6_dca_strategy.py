import importlib.util
import os
import shutil
import sys

import pandas as pd
import pytest


ROOT = os.path.dirname(os.path.dirname(__file__))
MODULE_PATH = os.path.join(ROOT, "python", "main.py")

spec = importlib.util.spec_from_file_location("v6_dca_strategy", MODULE_PATH)
v6 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = v6
spec.loader.exec_module(v6)


def make_price_df(n: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2024-01-05", periods=n, freq="W-FRI")
    close = pd.Series([100 + i * 1.5 for i in range(n)], index=dates, dtype=float)
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.01,
            "Low": close * 0.98,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=dates,
    )


@pytest.mark.parametrize(
    "model",
    ["traditional", "sharpe", "clenow"],
)
def test_compute_indicators_supports_all_momentum_models(model):
    cfg = v6.Config(momentum_model=model)
    out = v6.compute_indicators(make_price_df(), cfg)
    assert "momentum" in out.columns
    assert "score" in out.columns
    assert "vwma_mid" in out.columns
    assert out["score"].dropna().iloc[-1] > 0


def test_target_weights_respect_single_name_cap():
    cfg = v6.Config(max_long_positions=5, max_position_pct=0.19)
    engine = v6.MomentumEngine(cfg)
    ranked_scores = [
        ("AAA", 100.0),
        ("BBB", 80.0),
        ("CCC", 60.0),
        ("DDD", 40.0),
        ("EEE", 20.0),
    ]
    weights = engine._cap_and_normalize_weights(ranked_scores, total_long_pct=0.95)
    assert pytest.approx(sum(weights.values()), rel=1e-6) == 0.95
    assert max(weights.values()) <= 0.19 + 1e-9


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("A", "traditional"), ("traditional", "traditional"), ("B", "sharpe"), ("C", "clenow")],
)
def test_resolve_momentum_model_aliases(raw, expected):
    assert v6.resolve_momentum_model(raw) == expected


def test_parse_cli_args_supports_model_and_run_mode():
    args = v6.parse_cli_args(["--model", "C", "--run-mode", "full", "--monthly-add", "2500"])
    assert args.model == "C"
    assert args.run_mode == "full"
    assert args.monthly_add == pytest.approx(2500.0)
    assert args.refresh_web_data is True


def test_parse_cli_args_can_disable_web_refresh():
    args = v6.parse_cli_args(["--model", "A", "--no-refresh-web-data"])
    assert args.model == "A"
    assert args.refresh_web_data is False


def test_resolve_web_root_falls_back_to_web_phase_worktree(monkeypatch):
    monkeypatch.delenv("WEB_ROOT", raising=False)
    fake_root = os.path.join(ROOT, "tests", "_web_root_fixture")
    web_root = os.path.join(fake_root, ".worktrees", "web-phase1", "web")
    shutil.rmtree(fake_root, ignore_errors=True)
    os.makedirs(web_root, exist_ok=True)

    try:
        assert v6.resolve_web_root(fake_root) == os.path.abspath(web_root)
    finally:
        shutil.rmtree(fake_root, ignore_errors=True)


def test_yearly_snapshots_do_not_include_known_ipos_before_next_year():
    snapshots = {date: set(tickers) for date, tickers in v6.RAW_SNAPSHOTS}

    assert {"CRWD", "DDOG", "ZM"}.isdisjoint(snapshots["2019-01-01"])
    assert {"CRWD", "DDOG", "ZM"}.issubset(snapshots["2020-01-01"])
    assert "ALAB" not in snapshots["2023-01-01"]
    assert "ALAB" not in snapshots["2024-01-01"]
    assert "ALAB" in snapshots["2025-01-01"]



def _cache_test_config(name: str):
    output_dir = os.path.join(ROOT, "tests", "_price_cache_runtime", name)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    return v6.Config(
        output_dir=output_dir,
        price_cache_dir="cache",
        price_cache_enabled=True,
        price_cache_local_only=True,
    )


def test_weekly_price_data_keeps_monday_index():
    cfg = _cache_test_config("weekly_monday")
    try:
        weekly_cache = pd.DataFrame(
            {
                "Open": [157.353156],
                "High": [170.087647],
                "Low": [156.056222],
                "Close": [166.86409],
                "Volume": [15_694_500],
            },
            index=pd.to_datetime(["2022-10-03"]),
        )
        v6._write_cached_price(cfg, "CAT", "1wk", weekly_cache)

        weekly = v6.load_price_data(cfg, "CAT", "2022-10-03", "2022-10-10", "1wk", allow_network=False)

        assert list(weekly.index) == [pd.Timestamp("2022-10-03")]
        assert weekly.loc[pd.Timestamp("2022-10-03"), "Close"] == pytest.approx(166.86409)
    finally:
        shutil.rmtree(cfg.output_dir, ignore_errors=True)


def test_entry_execution_price_uses_same_monday_daily_close():
    cfg = v6.Config()
    engine = v6.DCAEngine(cfg)
    date = pd.Timestamp("2022-10-03")
    weekly_row = pd.Series(
        {
            "Open": 157.353156,
            "High": 170.087647,
            "Low": 156.056222,
            "Close": 166.86409,
            "Volume": 15_694_500,
            "atr": 5.0,
        }
    )
    weekly = pd.DataFrame([weekly_row], index=[date])
    daily = pd.DataFrame(
        {
            "Open": [157.353140],
            "High": [162.935641],
            "Low": [156.056206],
            "Close": [160.924438],
            "Volume": [3_444_700],
        },
        index=[date],
    )
    daily_data = {"CAT": daily}
    engine._daily_execution_price_data = daily_data

    engine._enter_position(
        "CAT", date, weekly_row, budget=10_000.0, intended_budget=10_000.0,
        bar_idx=0, sleeve="long",
        all_data={"CAT": weekly}, daily_price_data=daily_data,
    )

    assert engine.positions["CAT"].entry_date == date
    assert engine.positions["CAT"].entry_price == pytest.approx(160.924438)
    assert engine.executions[-1].date == date
    assert engine.executions[-1].price == pytest.approx(160.924438)


def test_target_weights_use_previous_completed_weekly_bar():
    cfg = v6.Config(timeframe="1wk", max_long_positions=5, max_position_pct=0.19)
    engine = v6.DCAEngine(cfg)
    dates = pd.to_datetime(["2024-01-01", "2024-01-08"])

    def frame(previous_score: float | None, current_score: float | None) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "score": [previous_score, current_score],
                "momentum": [previous_score, current_score],
                "ema": [100.0, 100.0],
                "ema_prev": [99.0, 99.0],
                "atr": [5.0, 5.0],
                "Open": [100.0, 100.0],
                "Close": [101.0, 101.0],
                "full_range": [2.0, 2.0],
                "body": [1.0, 1.0],
            },
            index=dates,
        )

    stock_data = {
        "AAA": frame(10.0, None),
        "BBB": frame(None, 100.0),
    }

    weights = engine._compute_target_weights(pd.Timestamp("2024-01-08"), stock_data, total_long_pct=0.50)

    assert set(weights) == {"AAA"}


def test_sampled_daily_bars_roll_forward_and_execute_next_trading_day():
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-04", "2024-01-05",
        "2024-01-08", "2024-01-10", "2024-01-11",
    ])
    close = pd.Series([100, 102, 103, 104, 110, 111], index=dates, dtype=float)
    daily = pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=dates,
    )

    sampled = v6.build_sampled_daily_bars(
        daily, start="2024-01-01", end="2024-01-12", decision_weekday=2
    )

    assert list(sampled.index) == [pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-11")]
    assert sampled.iloc[0]["signal_date"] == "2024-01-04"
    assert sampled.iloc[0]["execution_date"] == "2024-01-05"
    assert sampled.iloc[1]["signal_date"] == "2024-01-10"
    assert sampled.iloc[1]["execution_date"] == "2024-01-11"
    assert sampled.iloc[0]["Close"] == pytest.approx(102.0)


def test_target_weights_use_current_sampled_daily_signal_row():
    cfg = v6.Config(timeframe="1d_7d", max_long_positions=5, max_position_pct=0.19)
    engine = v6.DCAEngine(cfg)
    dates = pd.to_datetime(["2024-01-05", "2024-01-11"])

    def frame(previous_score: float | None, current_score: float | None) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "score": [previous_score, current_score],
                "momentum": [previous_score, current_score],
                "ema": [100.0, 100.0],
                "ema_prev": [99.0, 99.0],
                "atr": [5.0, 5.0],
                "Open": [100.0, 100.0],
                "Close": [101.0, 101.0],
                "full_range": [2.0, 2.0],
                "body": [1.0, 1.0],
            },
            index=dates,
        )

    stock_data = {
        "AAA": frame(10.0, None),
        "BBB": frame(None, 100.0),
    }

    weights = engine._compute_target_weights(pd.Timestamp("2024-01-11"), stock_data, total_long_pct=0.50)

    assert set(weights) == {"BBB"}


def test_target_weights_use_rank_buckets_for_new_entries():
    cfg = v6.Config()
    engine = v6.DCAEngine(cfg)
    dates = pd.to_datetime(["2024-01-05"])

    def frame(score: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "score": [score],
                "momentum": [score],
                "ema": [100.0],
                "ema_prev": [99.0],
                "atr": [5.0],
                "Open": [100.0],
                "Close": [101.0],
                "High": [102.0],
                "Low": [99.0],
                "Volume": [1_000_000],
            },
            index=dates,
        )

    stock_data = {
        "AAA": frame(10.0),
        "BBB": frame(9.0),
        "CCC": frame(8.0),
        "DDD": frame(7.0),
        "EEE": frame(6.0),
        "FFF": frame(5.0),
        "GGG": frame(4.0),
        "HHH": frame(3.0),
    }

    weights = engine._compute_target_weights(pd.Timestamp("2024-01-05"), stock_data, total_long_pct=0.90)

    assert weights == {
        "AAA": pytest.approx(0.18),
        "BBB": pytest.approx(0.18),
        "CCC": pytest.approx(0.18),
        "DDD": pytest.approx(0.09),
        "EEE": pytest.approx(0.09),
        "FFF": pytest.approx(0.09),
    }


def test_existing_positions_can_remain_in_hold_zone_ranks_7_and_8():
    cfg = v6.Config()
    hold_positions = {
        "GGG": v6.Position(
            ticker="GGG", entry_price=100.0, entry_date=pd.Timestamp("2024-01-05"),
            shares=10, stop_price=89.0, sleeve="long",
        ),
        "HHH": v6.Position(
            ticker="HHH", entry_price=100.0, entry_date=pd.Timestamp("2024-01-05"),
            shares=10, stop_price=89.0, sleeve="long",
        ),
    }
    engine = v6.DCAEngine(cfg, initial_positions=hold_positions)
    dates = pd.to_datetime(["2024-01-05"])

    def frame(score: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "score": [score],
                "momentum": [score],
                "ema": [100.0],
                "ema_prev": [99.0],
                "atr": [5.0],
                "Open": [100.0],
                "Close": [101.0],
                "High": [102.0],
                "Low": [99.0],
                "Volume": [1_000_000],
            },
            index=dates,
        )

    stock_data = {
        "AAA": frame(10.0),
        "BBB": frame(9.0),
        "CCC": frame(8.0),
        "DDD": frame(7.0),
        "EEE": frame(6.0),
        "FFF": frame(5.0),
        "GGG": frame(4.0),
        "HHH": frame(3.0),
    }

    weights = engine._compute_target_weights(
        pd.Timestamp("2024-01-05"),
        stock_data,
        total_long_pct=0.90,
        current_positions=engine.positions,
    )

    assert weights["GGG"] == pytest.approx(0.045)
    assert weights["HHH"] == pytest.approx(0.045)


def test_pine_hedge_buy_uses_vix_gate_and_next_day_execution():
    cfg = v6.Config()
    engine = v6.DCAEngine(cfg, initial_cash=50_000.0)
    dates = pd.to_datetime(["2020-02-20", "2020-02-21", "2020-02-24"])
    hedge_data = {
        "VIXY": pd.DataFrame(
            {
                "Open": [896.8, 951.2, 1128.0],
                "High": [952.8, 1005.6, 1165.6],
                "Low": [888.0, 942.4, 1075.2],
                "Close": [920.8, 980.8, 1160.8],
                "Volume": [1_000_000, 1_200_000, 1_500_000],
                "macd": [-8.2, -10.0, -7.0],
                "bb_mid": [930.9, 934.0, 944.0],
                "vwma_mid": [953.8, 956.9, 980.0],
                "atr": [40.0, 42.0, 45.0],
                "ema": [900.0, 910.0, 930.0],
                "signal_date": ["2020-02-20", "2020-02-21", "2020-02-24"],
                "execution_date": ["2020-02-21", "2020-02-24", "2020-02-25"],
                "data_frequency": ["1d", "1d", "1d"],
            },
            index=dates,
        )
    }
    daily_data = {
        "VIXY": pd.DataFrame(
            {
                "Open": [1128.0],
                "High": [1165.6],
                "Low": [1075.2],
                "Close": [1160.8],
                "Volume": [1_500_000],
            },
            index=[pd.Timestamp("2020-02-24")],
        )
    }

    engine.equity = 50_000.0
    engine._run_pine_hedge_sleeve(
        date=pd.Timestamp("2020-02-24"),
        stock_data={},
        hedge_data=hedge_data,
        vix_info={"vix": 17.08},
        bar_idx=0,
        all_dates=list(dates),
        all_data=hedge_data,
        daily_price_data=daily_data,
    )

    assert "VIXY" in engine.positions
    assert engine.positions["VIXY"].sleeve == "hedge"
    assert engine.positions["VIXY"].entry_price == pytest.approx(1128.0)


def test_state_manager_persists_twr_fields():
    runtime_dir = os.path.join(ROOT, "tests", "_state_runtime")
    shutil.rmtree(runtime_dir, ignore_errors=True)
    os.makedirs(runtime_dir, exist_ok=True)
    mgr = v6.StateManager(path=runtime_dir, filename="state.json")

    try:
        mgr.save(
            cash=12_345.67,
            equity=98_765.43,
            positions={},
            last_processed_date=pd.Timestamp("2026-04-20"),
            initial_capital=10_000.0,
            nav_units=51_760.5585,
            total_injected=123_000.0,
            dca_prev_month="2026-04",
        )
        state = mgr.load()
        assert state["nav_units"] == pytest.approx(51_760.5585)
        assert state["total_injected"] == pytest.approx(123_000.0)
        assert state["dca_prev_month"] == "2026-04"
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
