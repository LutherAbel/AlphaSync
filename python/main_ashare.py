"""
A-share ETF rotation prototype.

This is intentionally separate from the v6 DCA engine: it tests the
AlphaSync-style idea for A-shares, where allocation starts from a cross-section
of ETFs and a market regime gate instead of one ticker's entry signal.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


ETF_NAMES = {
    "510300.SS": "CSI 300 ETF",
    "510500.SS": "CSI 500 ETF",
    "159915.SZ": "ChiNext ETF",
    "588000.SS": "STAR 50 ETF",
    "512480.SS": "Semiconductor ETF",
    "512880.SS": "Securities ETF",
    "512660.SS": "Defense ETF",
    "512010.SS": "Pharma ETF",
    "510880.SS": "Dividend ETF",
    "518880.SS": "Gold ETF",
    "511010.SS": "Treasury Bond ETF",
}


@dataclass
class RotationConfig:
    start_date: str = "2020-01-01"
    end_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    initial_capital: float = 100_000.0
    top_n: int = 3
    rebalance_days: int = 20
    transaction_cost_bps: float = 8.0
    min_history: int = 130
    lookbacks: tuple[int, ...] = (20, 60, 120)
    output_dir: str = "output"
    run_name: str = "a_share_rotation"
    risk_symbols: tuple[str, ...] = ("510300.SS", "159915.SZ")
    fallback_symbols: tuple[str, ...] = ("518880.SS", "511010.SS")
    universe: tuple[str, ...] = (
        "510300.SS",
        "510500.SS",
        "159915.SZ",
        "588000.SS",
        "512480.SS",
        "512880.SS",
        "512660.SS",
        "512010.SS",
        "510880.SS",
    )

    @property
    def all_symbols(self) -> list[str]:
        symbols = list(self.universe) + list(self.fallback_symbols)
        return list(dict.fromkeys(symbols))


def _clean_yfinance_panel(raw: pd.DataFrame, field: str, symbols: list[str]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        if field not in raw.columns.get_level_values(0):
            return pd.DataFrame(index=raw.index)
        out = raw[field].copy()
    else:
        out = raw[[field]].copy() if field in raw.columns else pd.DataFrame(index=raw.index)
        if len(symbols) == 1:
            out.columns = symbols
    out = out.reindex(columns=symbols)
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return out.sort_index().dropna(how="all")


def download_prices(symbols: list[str], start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = yf.download(
        tickers=symbols,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    close = _clean_yfinance_panel(raw, "Close", symbols)
    volume = _clean_yfinance_panel(raw, "Volume", symbols)
    return close, volume


def _percentile_rank(series: pd.Series, ascending: bool = True) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(dtype=float)
    ranked = valid.rank(pct=True, ascending=ascending)
    return ranked.reindex(series.index)


def score_assets(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    symbols: list[str],
    date: pd.Timestamp,
    lookbacks: tuple[int, ...] = (20, 60, 120),
) -> pd.DataFrame:
    """Score assets at a rebalance date using bars strictly before that date."""
    history = close.loc[close.index < pd.Timestamp(date), symbols].dropna(how="all")
    vol_history = volume.loc[volume.index < pd.Timestamp(date), symbols].reindex(history.index)
    if len(history) < max(lookbacks) + 1:
        return pd.DataFrame(columns=["score", "momentum", "drawdown", "volatility", "liquidity", "trend_ok"])

    last = history.iloc[-1]
    momentum_parts = []
    for lookback in lookbacks:
        base = history.shift(lookback).iloc[-1]
        momentum_parts.append(last / base - 1.0)
    momentum = pd.concat(momentum_parts, axis=1).mean(axis=1)

    rolling_high = history.tail(max(lookbacks)).max()
    drawdown = last / rolling_high - 1.0
    volatility = history.pct_change(fill_method=None).tail(60).std()
    liquidity = (history * vol_history).tail(20).mean()
    ma120 = history.rolling(120).mean().iloc[-1]
    trend_ok = last > ma120

    score = (
        0.55 * _percentile_rank(momentum, ascending=True)
        + 0.20 * _percentile_rank(drawdown, ascending=True)
        + 0.15 * _percentile_rank(volatility, ascending=False)
        + 0.10 * _percentile_rank(liquidity, ascending=True)
    )
    out = pd.DataFrame(
        {
            "score": score,
            "momentum": momentum,
            "drawdown": drawdown,
            "volatility": volatility,
            "liquidity": liquidity,
            "trend_ok": trend_ok,
        }
    ).dropna(subset=["score"]).sort_values("score", ascending=False)
    return out


def regime_is_risk_on(close: pd.DataFrame, date: pd.Timestamp, risk_symbols: tuple[str, ...]) -> bool:
    history = close.loc[close.index < pd.Timestamp(date), list(risk_symbols)].dropna(how="all")
    if len(history) < 121:
        return False
    votes = []
    for symbol in risk_symbols:
        series = history[symbol].dropna()
        if len(series) < 121:
            continue
        last = series.iloc[-1]
        ma120 = series.rolling(120).mean().iloc[-1]
        mom60 = last / series.shift(60).iloc[-1] - 1.0
        votes.append(bool(last > ma120 and mom60 > -0.02))
    return any(votes)


def select_targets(
    scores: pd.DataFrame,
    risk_on: bool,
    top_n: int,
    fallback_symbols: list[str],
) -> list[str]:
    if not risk_on:
        return fallback_symbols
    eligible = scores[scores["trend_ok"]].head(top_n)
    if eligible.empty:
        return fallback_symbols
    return list(eligible.index)


def _target_weights(targets: list[str]) -> dict[str, float]:
    if not targets:
        return {}
    weight = 1.0 / len(targets)
    return {symbol: weight for symbol in targets}


def _portfolio_return(weights: dict[str, float], returns: pd.Series) -> float:
    invested = sum(weights.values())
    weighted = sum(weight * float(returns.get(symbol, 0.0) or 0.0) for symbol, weight in weights.items())
    return weighted + max(0.0, 1.0 - invested) * 0.0


def run_backtest(close: pd.DataFrame, volume: pd.DataFrame, cfg: RotationConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    close = close.dropna(how="all")
    returns = close.pct_change(fill_method=None).fillna(0.0)
    dates = close.loc[pd.Timestamp(cfg.start_date) : pd.Timestamp(cfg.end_date)].index
    if len(dates) < cfg.min_history:
        raise ValueError("Not enough price history for the requested period.")

    equity = float(cfg.initial_capital)
    weights: dict[str, float] = {}
    next_rebalance_idx = 0
    rows = []
    trades = []

    fee_rate = cfg.transaction_cost_bps / 10_000.0
    for i, date in enumerate(dates):
        if i > 0:
            daily_return = _portfolio_return(weights, returns.loc[date])
            equity *= 1.0 + daily_return
        else:
            daily_return = 0.0

        risk_on = regime_is_risk_on(close, date, cfg.risk_symbols)
        did_rebalance = i >= next_rebalance_idx and i >= cfg.min_history
        if did_rebalance:
            scores = score_assets(close, volume, list(cfg.universe), date, cfg.lookbacks)
            targets = select_targets(scores, risk_on, cfg.top_n, list(cfg.fallback_symbols))
            new_weights = _target_weights(targets)
            turnover = sum(abs(new_weights.get(s, 0.0) - weights.get(s, 0.0)) for s in set(new_weights) | set(weights))
            cost = equity * turnover * fee_rate
            equity -= cost
            weights = new_weights
            next_rebalance_idx = i + cfg.rebalance_days
            trades.append(
                {
                    "date": date,
                    "risk_on": risk_on,
                    "targets": "|".join(targets),
                    "turnover": turnover,
                    "transaction_cost": cost,
                    "equity_after": equity,
                    "top_scores": json.dumps(scores.head(8)["score"].round(4).to_dict(), ensure_ascii=True),
                }
            )

        rows.append(
            {
                "date": date,
                "equity": equity,
                "daily_return": daily_return,
                "risk_on": risk_on,
                "holdings": "|".join(weights.keys()),
                "gross_exposure": sum(weights.values()),
            }
        )

    equity_df = pd.DataFrame(rows)
    trades_df = pd.DataFrame(trades)
    summary = compute_summary(equity_df, trades_df, cfg)
    return equity_df, trades_df, summary


def compute_summary(equity_df: pd.DataFrame, trades_df: pd.DataFrame, cfg: RotationConfig) -> dict:
    start_equity = float(equity_df["equity"].iloc[0])
    end_equity = float(equity_df["equity"].iloc[-1])
    start_date = pd.Timestamp(equity_df["date"].iloc[0])
    end_date = pd.Timestamp(equity_df["date"].iloc[-1])
    years = max((end_date - start_date).days / 365.25, 1e-9)
    cagr = (end_equity / start_equity) ** (1.0 / years) - 1.0
    running_max = equity_df["equity"].cummax()
    drawdown = equity_df["equity"] / running_max - 1.0
    daily = equity_df["equity"].pct_change().dropna()
    sharpe = math.nan
    if daily.std() > 0:
        sharpe = float((daily.mean() / daily.std()) * math.sqrt(252))
    return {
        "run_name": cfg.run_name,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "initial_capital": cfg.initial_capital,
        "final_equity": round(end_equity, 2),
        "total_return_pct": round((end_equity / start_equity - 1.0) * 100.0, 2),
        "cagr_pct": round(cagr * 100.0, 2),
        "max_drawdown_pct": round(float(drawdown.min()) * 100.0, 2),
        "sharpe": None if math.isnan(sharpe) else round(sharpe, 2),
        "rebalance_count": int(len(trades_df)),
        "risk_on_days_pct": round(float(equity_df["risk_on"].mean()) * 100.0, 2),
    }


def write_outputs(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    equity_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    summary: dict,
    cfg: RotationConfig,
) -> dict[str, str]:
    os.makedirs(cfg.output_dir, exist_ok=True)
    prefix = os.path.join(cfg.output_dir, cfg.run_name)
    paths = {
        "equity": f"{prefix}_equity_curve.csv",
        "trades": f"{prefix}_trades.csv",
        "prices": f"{prefix}_prices.csv",
        "summary": f"{prefix}_summary.json",
    }
    equity_df.to_csv(paths["equity"], index=False)
    trades_df.to_csv(paths["trades"], index=False)
    price_panel = pd.concat({"close": close, "volume": volume}, axis=1)
    price_panel.to_csv(paths["prices"])
    with open(paths["summary"], "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an A-share ETF rotation backtest.")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--rebalance-days", type=int, default=20)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=8.0)
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--run-name", default="a_share_rotation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = RotationConfig(
        start_date=args.start,
        end_date=args.end,
        top_n=args.top_n,
        rebalance_days=args.rebalance_days,
        initial_capital=args.initial_capital,
        transaction_cost_bps=args.transaction_cost_bps,
        output_dir=args.output_dir,
        run_name=args.run_name,
    )
    warmup_start = (pd.Timestamp(cfg.start_date) - timedelta(days=260)).strftime("%Y-%m-%d")
    close, volume = download_prices(cfg.all_symbols, warmup_start, cfg.end_date)
    close = close.dropna(axis=1, how="all")
    volume = volume.reindex(columns=close.columns)

    missing = [symbol for symbol in cfg.all_symbols if symbol not in close.columns]
    if missing:
        print(f"Skipped symbols without Yahoo data: {', '.join(missing)}")

    equity_df, trades_df, summary = run_backtest(close, volume, cfg)
    paths = write_outputs(close, volume, equity_df, trades_df, summary, cfg)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("Outputs:")
    for key, path in paths.items():
        print(f"  {key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
