"""
Momentum Rotation v6-DCA — 定期定額版（自包含）
================================================
單檔自包含：不依賴本專案其他 Python 檔案，只使用 numpy / pandas / yfinance。

功能：
  1. 日 K 每 7 天抽樣的動能輪動引擎（regime score、cross-sectional collapse、VIX 避險閘門）
  2. 月初定額注資 (monthly_add，預設 $1,000)
  3. TWR (Time-Weighted Return) 追蹤：注資不改變 NAV，僅增加 units
  4. Dual-gate 宏觀退場：週線觸發時模擬週內最早日線觸發日出場
  5. 週五宏觀 safety net（避免漏接當日 monitor）
  6. Append-Only 輸出：全量模式覆寫、增量模式只 append
"""

from __future__ import annotations

import argparse
import os
import sys
import io
import subprocess
# 只在直接執行（非被 import，例如測試）時重設 stdout 編碼，避免破壞 pytest 的輸出捕捉
if __name__ == "__main__" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import json
import warnings
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


# ============================================================
# Annual Universe Snapshots (yearly rotation)
# ------------------------------------------------------------
# 每年 1/1 生效的股池，同一年內所有月份共用該年的 tickers。
# 結構：(生效日, [tickers])；月初會往前找最近一筆生效快照。
# ============================================================
RAW_SNAPSHOTS = [
    ("2016-01-01", ["AAPL", "MSFT", "XOM", "JNJ", "AMZN", "GOOGL", "BRK-B", "GE", "T", "NVDA", "TSLA", "NOW", "WDAY", "ILMN", "EA", "ADBE", "ISRG", "LRCX", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2017-01-01", ["AAPL", "MSFT", "AMZN", "GOOGL", "BRK-B", "XOM", "JNJ", "T", "META", "NVDA", "TSLA", "NOW", "WDAY", "ILMN", "ISRG", "LRCX", "SNPS", "ADSK", "EA", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2018-01-01", ["AAPL", "MSFT", "AMZN", "GOOGL", "BRK-B", "META", "JPM", "JNJ", "XOM", "NVDA", "TSLA", "NOW", "WDAY", "ISRG", "ILMN", "SNPS", "CDNS", "ADSK", "LRCX", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2019-01-01", ["MSFT", "AAPL", "AMZN", "GOOGL", "BRK-B", "META", "JPM", "JNJ", "XOM", "TSLA", "NOW", "NVDA", "WDAY", "OKTA", "TEAM", "MDB", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2020-01-01", ["MSFT", "AAPL", "AMZN", "GOOGL", "META", "BRK-B", "JNJ", "V", "JPM", "ZM", "CRWD", "DDOG", "OKTA", "MDB", "DOCU", "TSLA", "NOW", "ZS", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2021-01-01", ["AAPL", "MSFT", "AMZN", "META", "GOOGL", "BRK-B", "TSLA", "JPM", "JNJ", "ON", "ENTG", "FTNT", "DDOG", "CRWD", "MDB", "OKTA", "DXCM", "EBAY", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2022-01-01", ["AAPL", "MSFT", "AMZN", "GOOGL", "BRK-B", "TSLA", "NVDA", "UNH", "JPM", "DXCM", "IDXX", "EBAY", "ON", "EXPE", "VRSN", "ENTG", "NTRA", "FTNT", "MDB", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2023-01-01", ["AAPL", "MSFT", "AMZN", "GOOGL", "BRK-B", "NVDA", "TSLA", "UNH", "XOM", "TER", "LITE", "ON", "NTRA", "DXCM", "MDB", "ENTG", "EBAY", "IDXX", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2024-01-01", ["MSFT", "AAPL", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "AVGO", "TER", "LITE", "ON", "EBAY", "DXCM", "NTRA", "ENTG", "MDB", "IDXX", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2025-01-01", ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "BRK-B", "AVGO", "META", "TSLA", "STX", "WDC", "ALNY", "MPWR", "EBAY", "TER", "LITE", "ON", "DXCM", "ALAB", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
    ("2026-01-01", ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "META", "TSLA", "BRK-B", "SNDK", "LITE", "TER", "EBAY", "CRWV", "ESLT", "KMB", "NBIS", "UAL", "GLD", "SLV", "CPER", "USO", "UNG", "UUP"]),
]

def _build_yearly_snapshots():
    out = []
    seen_per_snapshot = []
    for date_text, names in RAW_SNAPSHOTS:
        uniq = []
        seen = set()
        for t in names:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        out.append((pd.Timestamp(date_text), uniq))
        seen_per_snapshot.append(seen)
    return out


def _build_monthly_universe_from_snapshots(snapshots, start: str, end: str) -> dict:
    if not snapshots:
        return {}
    months = pd.period_range(
        pd.Timestamp(start).to_period("M"),
        pd.Timestamp(end).to_period("M"),
        freq="M",
    )
    monthly = {}
    for month in months:
        month_start = month.to_timestamp()
        active = snapshots[0][1]
        for effective_date, tickers in snapshots:
            if effective_date <= month_start:
                active = tickers
            else:
                break
        monthly[str(month)] = active
    return monthly


# ============================================================
# Config
# ============================================================
@dataclass
class Config:
    # --- Universe ---
    universe: list = field(default_factory=lambda: [
        # 1. 絕對核心 (Tech Titans)
        "MSFT", "AAPL", "GOOGL", "AMZN", "META",
        # 2. 算力與半導體 (Semiconductors)
        "NVDA", "AVGO", "TSM", "ASML", "AMD", "LRCX", "AMAT", "QCOM",
        # 3. 企業軟體 (Enterprise SaaS)
        "CRM", "ADBE", "NOW", "INTU", "ORCL",
        # 4. 支付與金融 (Payments & Financials)
        "V", "MA", "AXP", "JPM", "BX",
        # 5. 醫療與生技 (Healthcare)
        "LLY", "UNH", "ABBV", "ISRG",
        # 6. 消費與基建 (Consumer & Industrials)
        "COST", "WMT", "NFLX", "HD", "CAT",
        # 7. Macro / commodity sleeves
        "GLD", "SLV", "CPER", "USO", "UNG", "UUP",
    ])
    dynamic_universe_enabled: bool = False
    dynamic_top_n: int = 10
    dynamic_append_max: int = 10
    dynamic_source_russell2000: bool = True
    dynamic_source_nasdaq_composite: bool = True
    dynamic_scan_cap: int = 2800
    dynamic_download_batch: int = 200
    dynamic_request_timeout_sec: int = 25
    dynamic_monthly_cache_enabled: bool = True
    dynamic_monthly_cache_force_refresh: bool = False
    dynamic_monthly_cache_json: str = "v6dca_dynamic_universe_monthly.json"
    dynamic_min_history: int = 200
    dynamic_momentum_lookback: int = 126
    dynamic_min_price: float = 5.0
    dynamic_min_dollar_volume: float = 10_000_000.0
    dynamic_52w_floor_ratio: float = 0.85
    dynamic_ignition_vol_mult: float = 2.0
    dynamic_ignition_recent_weeks: int = 4
    dynamic_output_json: str = "v6dca_dynamic_universe.json"
    hedge_universe: list = field(default_factory=lambda: [
        "SQQQ", "VIXY",
    ])
    leverage_map: dict = field(default_factory=lambda: {
        "SQQQ": 3.0, "TQQQ": 3.0, "UPRO": 3.0, "SPXU": 3.0,
        "QLD": 2.0, "QID": 2.0, "UVXY": 1.5, "VIXY": 1.0,
    })

    start_date: str = "2016-01-04"
    end_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    timeframe: str       = "1d_7d"
    hedge_timeframe: str = "1d"
    decision_weekday: int = 2  # Monday=0, Wednesday=2. If closed, roll forward.

    # --- Capital ---
    initial_capital: float   = 10_000
    max_long_positions: int  = 8
    max_hedge_positions: int = 2
    risk_per_trade: float    = 0.02
    max_position_pct: float  = 0.20
    force_target_long_allocation: bool = True
    long_fill_target_ratio: float = 0.98
    min_rebalance_shares: int = 2
    momentum_entry_rank: int = 6
    momentum_hold_rank: int = 8
    momentum_rank_weights: tuple[float, ...] = (0.18, 0.18, 0.18, 0.09, 0.09, 0.09, 0.045, 0.045)
    target_long_total_pct: float = 0.90
    extreme_fear_vix: float = 30.0
    pine_hedge_enabled: bool = True
    pine_hedge_ticker: str = "VIXY"
    pine_hedge_vix_gate: float = 15.0
    pine_hedge_first_entry_pct: float = 0.10
    pine_hedge_add_on_pct: float = 0.05
    pine_hedge_max_adds: int = 3
    pine_hedge_add_atr_interval: float = 1.0
    pine_hedge_add_size_ratio: float = 0.5

    # --- Indicators ---
    ema_len: int          = 30
    atr_len: int          = 14
    vol_ma_len: int       = 20
    momentum_weeks: int   = 12
    bb_len: int           = 26
    min_bars: int         = 100
    momentum_model: str   = "traditional"
    clenow_window_weeks: int = 26
    sharpe_vol_floor: float = 1e-6
    score_smooth_span: int = 3
    conviction_exit_score_floor: float = 0.0

    # --- Exits ---
    stop_atr_mult: float     = 2.0
    trail_atr_mult: float    = 3.0
    max_loss_pct: float      = 11.0
    blowoff_bb_mult: float   = 4.5
    blowoff_vol_mult: float  = 2.5

    # --- Regime ---
    spy_ema_len: int          = 30
    spy_momentum_weeks: int   = 12
    bear_entry_thresh: float  = -0.2
    bear_exit_thresh: float   = 0.3
    regime_sigmoid_k: float   = 12.0
    regime_sigmoid_mid: float = 0.10
    regime_long_floor: float  = 0.20
    regime_long_ceiling: float = 0.99

    # --- Early Warning ---
    ew_lookback: int          = 4
    ew_velocity_thresh: float = -0.15
    ew_confirm_bars: int      = 2
    hedge_min_hold: int       = 3

    # --- Hard Gates ---
    ema_crash_thresh: float    = -0.08
    bearish_body_thresh: float = 0.70

    # --- Health Exit ---
    health_exit_thresh: float  = 0.25

    # --- v6: Cross-sectional Collapse ---
    cs_top_n: int               = 5
    cs_mom_delta_thresh: float  = -3.0
    cs_disp_delta_thresh: float = -3.0
    cs_early_scale: float       = 0.8
    cs_avg_mom_thresh: float    = 5.0
    cs_dispersion_thresh: float = 10.0
    cs_full_scale: float        = 0.6

    # --- VIX-based Hedge Gate ---
    vix_term_inv_thresh: float    = 1.05
    vix_contrarian_thresh: float  = 30.0
    tlt_stagflation_thresh: float = -8.0
    contrarian_long_mult: float   = 1.4

    # --- DCA ---
    monthly_add: float = 1_000.0

    # --- Output files ---
    state_file: str     = "v6dca_state.json"
    equity_csv: str     = "v6dca_equity_curve.csv"
    trades_csv: str     = "v6dca_trades.csv"
    executions_csv: str = "v6dca_executions.csv"
    regime_debug_csv: str = "v6dca_regime_debug.csv"
    output_dir: str     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
    # --- Cache root (與 output 分離；快取不是執行結果) ---
    cache_dir: str      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cache")
    # --- Local price cache ---
    price_cache_enabled: bool = True
    price_cache_local_only: bool = True
    price_cache_prefetch_daily: bool = True
    price_cache_dir: str = "price_cache"  # cache_dir 下的子資料夾
    # --- Market data provider ---
    data_provider_primary: str = "tiingo"
    data_provider_fallback: str = "yahoo"
    tiingo_api_key: str = os.environ.get("TIINGO_API_KEY", "")
    tiingo_timeout_sec: int = 20


def DCAConfig(monthly_add: float = 1_000) -> Config:
    """工廠函式：回傳套用 DCA 預設參數的 Config 實例。"""
    cfg = Config()
    cfg.monthly_add = monthly_add
    return cfg


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Momentum Rotation v6 DCA runner."
    )
    parser.add_argument(
        "-m", "--model",
        default="A",
        help="Momentum model: A/traditional, B/sharpe, C/clenow.",
    )
    parser.add_argument(
        "--run-mode",
        choices=["auto", "full", "incremental"],
        default="auto",
        help="Execution mode. auto follows state file, full ignores state, incremental requires state.",
    )
    parser.add_argument(
        "--monthly-add",
        type=float,
        default=1_000.0,
        help="Monthly DCA injection amount.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow downloading missing price data instead of using local cache only.",
    )
    parser.add_argument(
        "--refresh-web-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Regenerate web JSON data after the strategy run completes.",
    )
    return parser.parse_args(argv)


def resolve_momentum_model(model_arg: str) -> str:
    normalized = str(model_arg or "A").strip().lower()
    alias_map = {
        "a": "traditional",
        "traditional": "traditional",
        "point": "traditional",
        "point_to_point": "traditional",
        "b": "sharpe",
        "sharpe": "sharpe",
        "sharpe_like": "sharpe",
        "information_ratio": "sharpe",
        "ir": "sharpe",
        "c": "clenow",
        "clenow": "clenow",
    }
    if normalized not in alias_map:
        raise ValueError(
            f"Unsupported model '{model_arg}'. Use A/B/C or traditional/sharpe/clenow."
        )
    return alias_map[normalized]


def resolve_web_root(root_dir: str) -> str:
    env_root = os.environ.get("WEB_ROOT")
    if env_root:
        web_root = os.path.abspath(env_root)
        if os.path.isdir(web_root):
            return web_root
        raise FileNotFoundError(f"WEB_ROOT does not exist: {web_root}")

    candidates = [
        os.path.join(root_dir, "web"),
        os.path.join(root_dir, ".worktrees", "web-phase1", "web"),
    ]
    for candidate in candidates:
        web_root = os.path.abspath(candidate)
        if os.path.isdir(web_root):
            return web_root

    searched = ", ".join(os.path.abspath(p) for p in candidates)
    raise FileNotFoundError(f"Web app directory not found. Searched: {searched}")


def configure_yfinance_cache(cache_root: str) -> None:
    tz_cache_dir = os.path.join(cache_root, "yf_tz_cache")
    os.makedirs(tz_cache_dir, exist_ok=True)
    if hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(tz_cache_dir)


def refresh_web_data() -> None:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script_path = os.path.join(root_dir, "scripts", "generate_data.py")
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"generate_data.py not found: {script_path}")

    web_root = resolve_web_root(root_dir)
    env = os.environ.copy()
    env["WEB_ROOT"] = web_root

    print(f"Refreshing web data via {script_path} ...")
    print(f"WEB_ROOT={web_root}")
    subprocess.run([sys.executable, script_path], cwd=root_dir, env=env, check=True)
    print("Web data refresh complete.")


def _dedupe_keep_order(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _extract_ohlcv(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw is None or len(raw) == 0:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        lv0 = raw.columns.get_level_values(0)
        lv1 = raw.columns.get_level_values(1)
        if ticker in lv0:
            sub = raw[ticker].copy()
        elif ticker in lv1:
            sub = raw.xs(ticker, axis=1, level=1).copy()
        else:
            return pd.DataFrame()
    else:
        sub = raw.copy()

    required = ["Open", "High", "Low", "Close", "Volume"]
    for col in required:
        if col not in sub.columns:
            return pd.DataFrame()
    sub = sub[required].dropna()
    if sub.index.tz is not None:
        sub.index = sub.index.tz_localize(None)
    return sub


def _cache_symbol_name(ticker: str) -> str:
    s = str(ticker or "").upper().strip()
    if not s:
        return "UNKNOWN"
    return "".join(ch if ch.isalnum() else "_" for ch in s)


def _price_cache_path(cfg: Config, ticker: str, interval: str) -> str:
    cache_root = os.path.join(cfg.cache_dir, cfg.price_cache_dir)
    os.makedirs(cache_root, exist_ok=True)
    sym = _cache_symbol_name(ticker)
    tf = str(interval or "1d").replace("/", "_")
    return os.path.join(cache_root, f"{sym}__{tf}.csv")


def _is_sampled_daily_timeframe(interval: str) -> bool:
    return str(interval or "").strip().lower() in {
        "1d_7d",
        "1d-7d",
        "daily_7d",
        "sampled_daily_7d",
        "7d_daily",
    }


def _bars_per_year(cfg: Config) -> int:
    tf = str(getattr(cfg, "timeframe", "1d_7d")).lower()
    return 52 if tf == "1wk" or _is_sampled_daily_timeframe(tf) else 252


def _read_cached_price(cfg: Config, ticker: str, interval: str) -> pd.DataFrame:
    p = _price_cache_path(cfg, ticker, interval)
    if not os.path.exists(p):
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, parse_dates=["Date"])
        if "Date" not in df.columns:
            return pd.DataFrame()
        df = df.set_index("Date")
        need_cols = ["Open", "High", "Low", "Close", "Volume"]
        for c in need_cols:
            if c not in df.columns:
                return pd.DataFrame()
        df = df[need_cols].dropna()
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df.sort_index()
    except Exception:
        return pd.DataFrame()


def _write_cached_price(cfg: Config, ticker: str, interval: str, df: pd.DataFrame) -> None:
    if df is None or len(df) == 0:
        return
    out = df.copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.sort_index()
    out.index.name = "Date"
    p = _price_cache_path(cfg, ticker, interval)
    out.to_csv(p, encoding="utf-8")


def _normalize_ohlcv_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)
    need_cols = ["Open", "High", "Low", "Close", "Volume"]
    if len(raw) == 0 or any(c not in raw.columns for c in need_cols):
        return pd.DataFrame()
    df = raw[need_cols].dropna()
    if len(df) == 0:
        return pd.DataFrame()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def _download_price_yahoo(ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
    raw = yf.download(
        ticker, start=start, end=end, interval=interval,
        progress=False, auto_adjust=True
    )
    return _normalize_ohlcv_frame(raw)


def _tiingo_symbol_candidates(ticker: str) -> list[str]:
    t = str(ticker).upper()
    out = [t]
    if "-" in t:
        out.append(t.replace("-", "."))
    seen = set()
    uniq = []
    for sym in out:
        if sym in seen:
            continue
        seen.add(sym)
        uniq.append(sym)
    return uniq


def _download_price_tiingo(cfg: Config, ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
    # Tiingo daily endpoint does not support Yahoo index symbols like ^VIX.
    if str(ticker).startswith("^"):
        return pd.DataFrame()
    if interval not in {"1d", "1wk"}:
        return pd.DataFrame()
    token = str(getattr(cfg, "tiingo_api_key", "") or "").strip()
    if not token:
        return pd.DataFrame()

    end_inclusive = (pd.Timestamp(end) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if pd.Timestamp(end_inclusive) < pd.Timestamp(start):
        return pd.DataFrame()
    freq = "weekly" if interval == "1wk" else "daily"

    for symbol in _tiingo_symbol_candidates(ticker):
        params = {
            "startDate": start,
            "endDate": end_inclusive,
            "resampleFreq": freq,
            "token": token,
        }
        url = (
            "https://api.tiingo.com/tiingo/daily/"
            f"{urllib.parse.quote(symbol)}/prices?"
            f"{urllib.parse.urlencode(params)}"
        )
        try:
            with urllib.request.urlopen(url, timeout=int(getattr(cfg, "tiingo_timeout_sec", 20))) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if not isinstance(payload, list) or len(payload) == 0:
                continue

            rows = []
            for item in payload:
                d = pd.to_datetime(item.get("date"), errors="coerce")
                if pd.isna(d):
                    continue
                if getattr(d, "tzinfo", None) is not None:
                    d = d.tz_localize(None)
                rows.append({
                    "Date": pd.Timestamp(d).normalize(),
                    "Open": float(item.get("adjOpen", item.get("open", np.nan))),
                    "High": float(item.get("adjHigh", item.get("high", np.nan))),
                    "Low": float(item.get("adjLow", item.get("low", np.nan))),
                    "Close": float(item.get("adjClose", item.get("close", np.nan))),
                    "Volume": float(item.get("adjVolume", item.get("volume", np.nan))),
                })
            if not rows:
                continue
            df = pd.DataFrame(rows).set_index("Date").sort_index()
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(df):
                return df
        except Exception:
            continue
    return pd.DataFrame()


def _download_price(cfg: Config, ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
    # Keep Yahoo index semantics for ^VIX / ^VIX3M (and other ^ symbols).
    if str(ticker).startswith("^"):
        return _download_price_yahoo(ticker=ticker, start=start, end=end, interval=interval)

    providers = [
        str(getattr(cfg, "data_provider_primary", "tiingo")).strip().lower(),
        str(getattr(cfg, "data_provider_fallback", "yahoo")).strip().lower(),
    ]
    seen = set()
    ordered = []
    for p in providers:
        if not p or p in seen:
            continue
        seen.add(p)
        ordered.append(p)

    for provider in ordered:
        if provider == "tiingo":
            df = _download_price_tiingo(cfg, ticker=ticker, start=start, end=end, interval=interval)
        elif provider == "yahoo":
            df = _download_price_yahoo(ticker=ticker, start=start, end=end, interval=interval)
        else:
            continue
        if len(df):
            return df
    return pd.DataFrame()


def load_price_data(
    cfg: Config,
    ticker: str,
    start: str,
    end: str,
    interval: str,
    allow_network: bool = True,
) -> pd.DataFrame:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    cached = _read_cached_price(cfg, ticker, interval) if cfg.price_cache_enabled else pd.DataFrame()

    # Fix #12: Only return cache if it completely covers the required range up to the requested 'end'
    # If cache ends earlier than end_ts, we must allow network download to fill the gap.
    if len(cached):
        cache_start = cached.index.min()
        cache_end   = cached.index.max()
        if cache_start <= start_ts and cache_end >= (end_ts - pd.Timedelta(days=1)):
            in_range = cached[(cached.index >= start_ts) & (cached.index < end_ts)]
            if not in_range.empty:
                return in_range

    if not allow_network:
        # If network not allowed, return whatever we have in range
        if not cached.empty:
            return cached[(cached.index >= start_ts) & (cached.index < end_ts)]
        return pd.DataFrame()

    dl = _download_price(cfg=cfg, ticker=ticker, start=start, end=end, interval=interval)
    if len(dl) == 0:
        return pd.DataFrame()

    if len(cached):
        merged = pd.concat([cached, dl]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
    else:
        merged = dl

    if cfg.price_cache_enabled:
        _write_cached_price(cfg, ticker, interval, merged)

    return merged[(merged.index >= start_ts) & (merged.index < end_ts)]


def build_sampled_daily_bars(
    daily_df: pd.DataFrame,
    start: str,
    end: str,
    decision_weekday: int = 2,
) -> pd.DataFrame:
    """
    Build one strategy bar every 7 calendar days from daily OHLCV.

    The target decision day is Wednesday by default. If that day is not a
    trading day, the signal rolls forward to the next available trading day.
    The row index is the next trading day after the signal day, so the engine
    can execute after the completed daily signal is known.
    """
    if daily_df is None or daily_df.empty:
        return pd.DataFrame()

    need_cols = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in daily_df.columns for c in need_cols):
        return pd.DataFrame()

    daily = daily_df[need_cols].dropna().copy()
    if daily.empty:
        return pd.DataFrame()
    daily.index = pd.to_datetime(daily.index).tz_localize(None).normalize()
    daily = daily.sort_index()
    daily = daily[~daily.index.duplicated(keep="last")]

    start_ts = max(pd.Timestamp(start).normalize(), daily.index.min())
    end_ts = min(pd.Timestamp(end).normalize(), daily.index.max() + pd.Timedelta(days=1))
    if start_ts >= end_ts:
        return pd.DataFrame()

    weekday = int(decision_weekday) % 7
    offset_days = (weekday - start_ts.weekday()) % 7
    first_target = start_ts + pd.Timedelta(days=offset_days)
    target_dates = pd.date_range(first_target, end_ts, freq="7D")

    rows = []
    idx = []
    daily_index = daily.index
    for target in target_dates:
        signal_pos = daily_index.searchsorted(target, side="left")
        if signal_pos >= len(daily_index):
            continue
        signal_date = daily_index[signal_pos]
        if signal_date > target + pd.Timedelta(days=6):
            continue

        trade_pos = signal_pos + 1
        if trade_pos >= len(daily_index):
            continue
        execution_date = daily_index[trade_pos]
        if execution_date >= pd.Timestamp(end).normalize():
            continue

        row = daily.loc[signal_date].copy()
        row["signal_date"] = signal_date.strftime("%Y-%m-%d")
        row["execution_date"] = execution_date.strftime("%Y-%m-%d")
        row["data_frequency"] = "daily_7d"
        rows.append(row)
        idx.append(execution_date)

    if not rows:
        return pd.DataFrame(columns=need_cols + ["signal_date", "execution_date", "data_frequency"])

    out = pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name=daily.index.name))
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


def load_strategy_price_data(
    cfg: Config,
    ticker: str,
    start: str,
    end: str,
    allow_network: bool = True,
) -> pd.DataFrame:
    if _is_sampled_daily_timeframe(cfg.timeframe):
        daily = load_price_data(
            cfg, ticker=ticker, start=start, end=end,
            interval="1d", allow_network=allow_network,
        )
        return build_sampled_daily_bars(
            daily, start=start, end=end,
            decision_weekday=getattr(cfg, "decision_weekday", 2),
        )

    return load_price_data(
        cfg, ticker=ticker, start=start, end=end,
        interval=cfg.timeframe, allow_network=allow_network,
    )


def _load_cached_close_series(
    cfg: Config,
    ticker: str,
    start: str,
    end: str,
    interval: str = "1d",
    allow_network: bool = False,
) -> pd.Series:
    df = load_price_data(
        cfg, ticker=ticker, start=start, end=end,
        interval=interval, allow_network=allow_network,
    )
    if df is None or df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    close = df["Close"].copy()
    close.name = ticker
    return close


def prefetch_pool_prices(
    cfg: Config,
    tickers: list,
    start: str,
    end: str,
    include_daily: bool = True,
) -> None:
    uniq = _dedupe_keep_order([str(t).upper() for t in tickers if str(t).strip()])
    if not uniq:
        print("[price-cache] no tickers to prefetch")
        return
    print(f"[price-cache] prefetch {len(uniq)} tickers ({start} → {end})")
    ok = 0
    for t in uniq:
        try:
            has_weekly = False
            if not _is_sampled_daily_timeframe(cfg.timeframe):
                wk = load_price_data(cfg, t, start=start, end=end, interval="1wk", allow_network=True)
                has_weekly = len(wk) > 0
            has_daily = False
            if include_daily:
                d1 = load_price_data(cfg, t, start=start, end=end, interval="1d", allow_network=True)
                has_daily = len(d1) > 0
            if has_weekly or has_daily:
                ok += 1
        except Exception as e:
            print(f"[price-cache] {t} prefetch failed: {e}")
    print(f"[price-cache] done, cached tickers={ok}/{len(uniq)}")


# ============================================================
# State Manager
# ============================================================
class StateManager:
    """讀寫 state JSON，實現 stateful 增量執行。"""

    def __init__(self, path: str = ".", filename: str = "v6dca_state.json"):
        self.state_path = os.path.join(path, filename)

    def exists(self) -> bool:
        return os.path.exists(self.state_path)

    def load(self) -> dict:
        if not self.exists():
            return {}
        with open(self.state_path, "r") as f:
            return json.load(f)

    def save(
        self,
        cash: float,
        equity: float,
        positions: dict,
        last_processed_date,
        initial_capital: float,
        nav_units: float | None = None,
        total_injected: float | None = None,
        dca_prev_month: str | None = None,
        long_entry_block_active: bool = False,
    ):
        if self.exists():
            old = self.load()
            ic = old.get("initial_capital", initial_capital)
        else:
            ic = initial_capital

        pos_dict = {}
        for ticker, pos in positions.items():
            pos_dict[ticker] = {
                "ticker":              pos.ticker,
                "entry_price":         pos.entry_price,
                "entry_date":          str(pos.entry_date.date()) if hasattr(pos.entry_date, "date") else str(pos.entry_date),
                "shares":              pos.shares,
                "stop_price":          pos.stop_price,
                "highest_since_entry": pos.highest_since_entry,
                "trailing_stop":       pos.trailing_stop,
                "sleeve":              pos.sleeve,
                "entry_bar_idx":       -9999,
                "momentum_at_entry":   pos.momentum_at_entry,
                "entry_alloc_pct":     getattr(pos, "entry_alloc_pct", 0.0),
                "target_weight":       float(getattr(pos, "target_weight", 0.0)),
                "hedge_add_count":     int(getattr(pos, "hedge_add_count", 0)),
                "hedge_last_add_price": float(getattr(pos, "hedge_last_add_price", np.nan)),
                "hedge_has_scaled_out": bool(getattr(pos, "hedge_has_scaled_out", False)),
                "hedge_has_scaled_out_purple": bool(getattr(pos, "hedge_has_scaled_out_purple", False)),
            }

        state = {
            "initial_capital":     ic,
            "last_processed_date": str(last_processed_date.date()) if hasattr(last_processed_date, "date") else str(last_processed_date),
            "cash":                round(cash, 4),
            "equity":              round(equity, 4),
            "nav_units":           round(float(nav_units), 4) if nav_units is not None else None,
            "total_injected":      round(float(total_injected), 2) if total_injected is not None else None,
            "dca_prev_month":      dca_prev_month,
            "long_entry_block_active": bool(long_entry_block_active),
            "positions":           pos_dict,
        }
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        print(f"state saved: {self.state_path}")
        print(f"  last={state['last_processed_date']}, cash={cash:,.2f}, "
              f"equity={equity:,.2f}, positions={len(pos_dict)}")

    def restore_positions(self, state: dict) -> dict:
        positions = {}
        for ticker, d in state.get("positions", {}).items():
            positions[ticker] = Position(
                ticker=ticker,
                entry_price=float(d["entry_price"]),
                entry_date=pd.Timestamp(d["entry_date"]),
                shares=int(d["shares"]),
                stop_price=float(d["stop_price"]),
                highest_since_entry=float(d.get("highest_since_entry", d["entry_price"])),
                trailing_stop=float(d.get("trailing_stop", 0.0)),
                sleeve=str(d.get("sleeve", "long")),
                entry_bar_idx=int(d.get("entry_bar_idx", -9999)),
                momentum_at_entry=float(d.get("momentum_at_entry", 0.0)),
                entry_alloc_pct=float(d.get("entry_alloc_pct", 0.0)),
                target_weight=float(d.get("target_weight", 0.0)),
                hedge_add_count=int(d.get("hedge_add_count", 0)),
                hedge_last_add_price=float(d.get("hedge_last_add_price", np.nan)),
                hedge_has_scaled_out=bool(d.get("hedge_has_scaled_out", False)),
                hedge_has_scaled_out_purple=bool(d.get("hedge_has_scaled_out_purple", False)),
            )
        return positions


# ============================================================
# Indicators & signals
# ============================================================
def compute_indicators(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    c, h, l, o, v = df["Close"], df["High"], df["Low"], df["Open"], df["Volume"]

    df["ema"]      = c.ewm(span=cfg.ema_len, adjust=False).mean()
    df["ema_prev"] = df["ema"].shift(1)

    tr         = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    df["atr"]    = tr.rolling(cfg.atr_len).mean()
    df["vol_ma"] = v.rolling(cfg.vol_ma_len).mean()

    df["bb_mid"] = c.rolling(cfg.bb_len).mean()
    vol_sum = v.rolling(cfg.bb_len).sum()
    px_vol_sum = (c * v).rolling(cfg.bb_len).sum()
    df["vwma_mid"] = (px_vol_sum / vol_sum.replace(0, np.nan))
    _ = c.rolling(cfg.bb_len).std()

    bars_per_year = _bars_per_year(cfg)
    lookback = max(int(cfg.momentum_weeks), 1)
    clenow_window = max(int(cfg.clenow_window_weeks), lookback + 2)

    def _calc_point_to_point(prices, lb):
        if len(prices) < lb + 1:
            return np.nan
        base = float(prices[-(lb + 1)])
        if base <= 0:
            return np.nan
        return (float(prices[-1]) / base - 1.0) * 100.0

    def _calc_sharpe_like(prices, lb, bpy):
        if len(prices) < lb + 1:
            return np.nan
        series = pd.Series(prices[-(lb + 1):], dtype=float)
        rets = series.pct_change().dropna()
        if len(rets) < max(lb // 2, 3):
            return np.nan
        vol = float(rets.std(ddof=0))
        if not np.isfinite(vol) or vol < float(cfg.sharpe_vol_floor):
            return np.nan
        return float(rets.mean() / vol) * np.sqrt(bpy)

    def _calc_clenow(prices, window, bpy):
        if len(prices) < window:
            return np.nan
        y = np.log(np.asarray(prices[-window:], dtype=float))
        x = np.arange(window)
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        ss_res = np.sum((y - y_pred) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return ((np.exp(slope) ** bpy) - 1.0) * r2 * 100.0

    model = str(getattr(cfg, "momentum_model", "traditional") or "traditional").lower().strip()
    c_vals = c.values.astype(float)
    momentum_vals = []
    for i in range(len(c_vals)):
        window = c_vals[: i + 1]
        if model in {"a", "traditional", "point", "point_to_point"}:
            val = _calc_point_to_point(window, lookback)
        elif model in {"b", "sharpe", "sharpe_like", "information_ratio", "ir"}:
            val = _calc_sharpe_like(window, lookback, bars_per_year)
        elif model in {"c", "clenow"}:
            val = _calc_clenow(window, clenow_window, bars_per_year)
        else:
            raise ValueError(f"Unsupported momentum_model: {cfg.momentum_model}")
        momentum_vals.append(val)

    df["momentum"] = momentum_vals
    df["body"]       = (c - o).abs()
    df["full_range"] = h - l

    df["ret_1"] = c.pct_change()
    df["vol_12"] = df["ret_1"].rolling(12).std()
    df["vol_12_floor"] = df["vol_12"].clip(lower=0.02)

    df["score_raw"] = df["momentum"].where(df["momentum"] > 0.0, 0.0)
    df["score"] = df["score_raw"].ewm(span=max(int(cfg.score_smooth_span), 1), adjust=False).mean()

    wma_fast = c.rolling(12).apply(lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True)
    wma_slow = c.rolling(26).apply(lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True)
    df["macd"]      = (wma_fast - wma_slow).ewm(span=9, adjust=False).mean()
    df["macd_prev"] = df["macd"].shift(1)

    return df


def fetch_vix_signals(start_date: str, end_date: str, cfg) -> pd.DataFrame:
    signals = pd.DataFrame()
    try:
        allow_network = not bool(getattr(cfg, "price_cache_local_only", False))
        vix_close = _load_cached_close_series(cfg, "^VIX", start_date, end_date, allow_network=allow_network)
        vix3m_close = _load_cached_close_series(cfg, "^VIX3M", start_date, end_date, allow_network=allow_network)
        tlt_close = _load_cached_close_series(cfg, "TLT", start_date, end_date, allow_network=allow_network)

        tlt_mom = tlt_close.pct_change(60) * 100

        signals = pd.concat([
            vix_close.rename("vix"),
            vix3m_close.rename("vix3m"),
        ], axis=1).dropna(subset=["vix"])
        signals["tlt_mom"]        = tlt_mom
        signals["term_inverted"]  = signals["vix"] > signals["vix3m"] * cfg.vix_term_inv_thresh
        signals["stagflation"]    = signals["tlt_mom"] < cfg.tlt_stagflation_thresh
        signals["contrarian_boost"] = (
            (signals["vix"] > cfg.vix_contrarian_thresh) & (~signals["stagflation"])
        )
        if signals.index.tz is not None:
            signals.index = signals.index.tz_localize(None)
        print(f"  ^VIX/^VIX3M/TLT loaded: {len(signals)} daily bars")
    except Exception as e:
        print(f"  VIX signals fetch error: {e}，使用空訊號")
    return signals


def load_historical_macro_signals(csv_path: str = None) -> pd.Series:
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "macro_signals_historical.csv")
    if not os.path.exists(csv_path):
        return pd.Series(dtype=str)
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").set_index("date")
    return df["tradebot_action"]


def lookup_historical_macro(signals: pd.Series, date: pd.Timestamp) -> dict:
    if signals.empty:
        return {"tradebot_action": "normal"}
    idx = signals.index.searchsorted(date, side="right") - 1
    if idx < 0:
        return {"tradebot_action": "normal"}
    return {"tradebot_action": signals.iloc[idx]}


def fetch_macro_signal(url: str = "http://localhost:3000/api/signal") -> dict:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        action = data.get("tradebot_action", "normal")
        print(f"  MacroSignal: {data.get('regime','?')} / {data.get('recovery_type','?')} "
              f"/ {data.get('confidence','?')} → {action}")
        return data
    except Exception as e:
        print(f"  MacroSignal fetch failed ({e})，使用 normal")
        return {"tradebot_action": "normal"}


def _lookup_vix(vix_signals: pd.DataFrame, date: pd.Timestamp) -> dict:
    if vix_signals is None or vix_signals.empty:
        return {"term_inverted": True, "contrarian_boost": False, "vix": np.nan}
    idx = vix_signals.index.searchsorted(date, side="right") - 1
    if idx < 0:
        return {"term_inverted": True, "contrarian_boost": False, "vix": np.nan}
    row = vix_signals.iloc[idx]
    return {
        "term_inverted":    bool(row.get("term_inverted", True)),
        "contrarian_boost": bool(row.get("contrarian_boost", False)),
        "vix":              float(row.get("vix", np.nan)),
    }


def compute_regime_score(spy_df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    df = spy_df.copy()
    c = df["Close"]
    df["spy_ema"] = c.ewm(span=cfg.spy_ema_len, adjust=False).mean()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - c.shift(1)).abs(),
                    (df["Low"] - c.shift(1)).abs()], axis=1).max(axis=1)
    df["spy_atr"]    = tr.rolling(cfg.atr_len).mean()
    df["sig_pos"]    = ((c - df["spy_ema"]) / df["spy_atr"] / 2).clip(-1, 1)
    df["sig_mom"]    = (c.pct_change(cfg.spy_momentum_weeks) * 100 / 20).clip(-1, 1)
    df["sig_slope"]  = (df["spy_ema"].diff() / df["spy_atr"] / 0.3).clip(-1, 1)
    df["regime_score"] = ((df["sig_pos"] + df["sig_mom"] + df["sig_slope"]) / 3).clip(-1, 1)
    return df


def passes_long_gate(row, cfg):
    if pd.isna(row.get("ema")) or pd.isna(row.get("ema_prev")) or pd.isna(row.get("atr")):
        return False
    if row["atr"] == 0:
        return False
    ema_slope = (row["ema"] - row["ema_prev"]) / row["atr"]
    if ema_slope < cfg.ema_crash_thresh:
        return False
    if row["full_range"] > 0 and row["Close"] < row["Open"]:
        if row["body"] / row["full_range"] > cfg.bearish_body_thresh:
            return False
    return True


def compute_health_score(row):
    if pd.isna(row.get("macd")) or pd.isna(row.get("atr")) or row["atr"] == 0:
        return 0.5

    macd, mp = row["macd"], row.get("macd_prev", np.nan)
    s_macd = (1.0 if macd > mp else 0.0) if not pd.isna(mp) else 0.5

    ema, ep = row.get("ema", np.nan), row.get("ema_prev", np.nan)
    if not pd.isna(ema) and not pd.isna(ep):
        slope = (ema - ep) / row["atr"]
        s_ema = 1.0 if slope > 0.01 else 0.5 if slope > -0.03 else 0.0
    else:
        s_ema = 0.5

    vm = row.get("vol_ma", np.nan)
    if not pd.isna(vm) and vm > 0:
        vr = row["Volume"] / vm
        s_vol = 1.0 if vr > 1.2 else 0.5 if vr > 0.7 else 0.0
    else:
        s_vol = 0.5

    return round((s_macd + s_ema + s_vol) / 3, 3)


def score_hedge(row, cfg):
    if pd.isna(row.get("ema")) or pd.isna(row.get("atr")) or row["atr"] == 0:
        return 0.0
    c, ema, mom = row["Close"], row["ema"], row.get("momentum", 0)
    if pd.isna(mom):
        mom = 0
    s_trend = 0.5 if c > ema else 0.1
    s_mom   = min(max(mom / 20, -0.5), 0.5) + 0.5
    return round((s_trend + s_mom) * 2.5, 3)


def compute_cross_sectional(
    long_momentums: dict,
    cfg: Config,
    prev_avg_mom: float,
    prev_dispersion: float,
) -> tuple:
    if len(long_momentums) < 2:
        return np.nan, np.nan, np.nan, np.nan, 1.0, 0

    top_moms   = sorted(long_momentums.values(), reverse=True)[:cfg.cs_top_n]
    avg_mom    = float(np.mean(top_moms))
    dispersion = float(np.std(top_moms))

    mom_delta  = avg_mom    - prev_avg_mom    if not np.isnan(prev_avg_mom)    else 0.0
    disp_delta = dispersion - prev_dispersion if not np.isnan(prev_dispersion) else 0.0

    stage1 = (mom_delta < cfg.cs_mom_delta_thresh) or (disp_delta < cfg.cs_disp_delta_thresh)
    stage2 = avg_mom < cfg.cs_avg_mom_thresh and dispersion < cfg.cs_dispersion_thresh

    cs_scale = 1.0
    if stage1:
        cs_scale *= cfg.cs_early_scale
    if stage2:
        cs_scale *= cfg.cs_full_scale

    cs_stage = (1 if stage1 else 0) + (2 if stage2 else 0)

    return avg_mom, dispersion, mom_delta, disp_delta, cs_scale, cs_stage


# ============================================================
# Macro dual-gate (inlined from macro_indicators.py)
# ============================================================
_MACRO_LOOKBACK_DAYS = 300
_JPY_ROC_ALERT       = 4.0
_USD_ROC_ALERT       = 3.0
_CREDIT_ROC_ALERT    = -5.0
_EXTREME_FEAR_VIX    = 30.0


@dataclass
class MacroState:
    alert_vix:    bool
    alert_jpy:    bool
    alert_usd:    bool
    alert_credit: bool
    macro_alert:  bool
    spy_below_20w_ma: bool
    dual_gate: bool
    vix_clear: bool
    usd_clear: bool
    all_clear: bool
    shock_warning: bool
    confirmed_deterioration: bool
    state_recovery: bool
    extreme_fear: bool
    structural_weakness: bool # Fix: 20W < 40W SMA

    def __str__(self) -> str:
        flags = []
        if self.alert_vix:    flags.append("VIX_INVERT")
        if self.alert_jpy:    flags.append("JPY_UNWIND")
        if self.alert_usd:    flags.append("USD_SQUEEZE")
        if self.alert_credit: flags.append("CREDIT_SPREAD")
        if self.structural_weakness: flags.append("STRUCTURAL_WEAK")
        if self.confirmed_deterioration:
            status = "BLOCK_LONGS"
        elif self.shock_warning:
            status = "SHOCK_WARNING"
        elif self.state_recovery:
            status = "RECOVERY"
        else:
            status = "WATCH"
        gate2 = "SPY<20wMA" if self.spy_below_20w_ma else "SPY_OK"
        return f"MacroState({status} | alerts={flags} | {gate2})"


def roc_weekly(series: pd.Series, weeks: int) -> float:
    weekly = series.resample("W-FRI").last().dropna()
    if len(weekly) < weeks + 1:
        return 0.0
    return float(weekly.iloc[-1] / weekly.iloc[-(weeks + 1)] - 1) * 100.0


def _weekly_sma(series: pd.Series, weeks: int) -> float:
    weekly = series.resample("W-FRI").last().dropna()
    if len(weekly) < weeks:
        return float(weekly.mean()) if len(weekly) > 0 else 0.0
    return float(weekly.tail(weeks).mean())


def _macro_download(tickers: list, days: int, cfg: Config | None = None) -> pd.DataFrame:
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if cfg is not None:
        allow_network = not bool(getattr(cfg, "price_cache_local_only", False))
        cols = {
            t: _load_cached_close_series(cfg, t, start, end, allow_network=allow_network)
            for t in tickers
        }
        cached = pd.concat(cols.values(), axis=1)
        cached.columns = list(cols.keys())
        if not cached.dropna(how="all").empty:
            return cached.ffill()
    raw = yf.download(tickers, start=start, progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw["Close"]
    else:
        raw = raw[["Close"]]
        raw.columns = tickers[:1]
    return raw.ffill()


def compute_macro_state_from_prices(
    vix: float, vix3m: float,
    fxy_weekly: pd.Series, uup_weekly: pd.Series,
    credit_weekly: pd.Series, spy_weekly: pd.Series,
) -> MacroState:
    spy_weekly = spy_weekly.dropna()
    if spy_weekly.empty:
        return MacroState(
            alert_vix=False, alert_jpy=False, alert_usd=False,
            alert_credit=False, macro_alert=False,
            spy_below_20w_ma=False, dual_gate=False,
            vix_clear=True, usd_clear=True, all_clear=True,
            shock_warning=False,
            confirmed_deterioration=False,
            state_recovery=True,
            extreme_fear=False,
            structural_weakness=False,
        )
    uup_4w_roc   = roc_weekly(uup_weekly, 4)
    alert_vix    = vix > vix3m
    alert_jpy    = roc_weekly(fxy_weekly, 4) > _JPY_ROC_ALERT
    alert_usd    = uup_4w_roc > _USD_ROC_ALERT
    alert_credit = roc_weekly(credit_weekly, 12) < _CREDIT_ROC_ALERT
    macro_alert  = alert_vix or alert_jpy or alert_usd or alert_credit

    spy_sma20w       = _weekly_sma(spy_weekly, 20)
    spy_sma40w       = _weekly_sma(spy_weekly, 40)
    spy_last         = float(spy_weekly.iloc[-1])
    spy_below_20w_ma = spy_last < spy_sma20w
    spy_below_40w_ma = spy_last < spy_sma40w

    shock_warning = alert_vix and (alert_usd or alert_jpy)
    confirmed_deterioration = spy_below_20w_ma and alert_credit
    state_recovery = not spy_below_20w_ma
    dual_gate = confirmed_deterioration
    vix_clear = vix < vix3m
    usd_clear = uup_4w_roc < 0.0
    all_clear = vix_clear and usd_clear
    extreme_fear = vix >= _EXTREME_FEAR_VIX
    
    # Structural bear market:
    # 20W < 40W and SPY is below either 20W or 40W MA.
    structural_weakness = (spy_sma20w < spy_sma40w) and (spy_below_20w_ma or spy_below_40w_ma)

    return MacroState(
        alert_vix=alert_vix, alert_jpy=alert_jpy, alert_usd=alert_usd,
        alert_credit=alert_credit, macro_alert=macro_alert,
        spy_below_20w_ma=spy_below_20w_ma, dual_gate=dual_gate,
        vix_clear=vix_clear, usd_clear=usd_clear, all_clear=all_clear,
        shock_warning=shock_warning,
        confirmed_deterioration=confirmed_deterioration,
        state_recovery=state_recovery,
        extreme_fear=extreme_fear,
        structural_weakness=structural_weakness,
    )


def compute_macro_state(cfg: Config | None = None) -> MacroState:
    vix_df  = _macro_download(["^VIX"],  days=10, cfg=cfg)
    vix3m_df = _macro_download(["^VIX3M"], days=10, cfg=cfg)
    vix   = float(vix_df.dropna().iloc[-1].iloc[0])
    vix3m = float(vix3m_df.dropna().iloc[-1].iloc[0])

    multi = _macro_download(["FXY", "UUP", "HYG", "IEF", "SPY"], days=_MACRO_LOOKBACK_DAYS, cfg=cfg)
    fxy    = multi["FXY"]
    uup    = multi["UUP"]
    credit = multi["HYG"] / multi["IEF"]
    spy    = multi["SPY"]

    return compute_macro_state_from_prices(
        vix=vix, vix3m=vix3m,
        fxy_weekly=fxy, uup_weekly=uup,
        credit_weekly=credit, spy_weekly=spy,
    )


def build_macro_history(start_date: str, end_date: str, cfg: Config | None = None) -> pd.DataFrame:
    dl_start = (pd.Timestamp(start_date) - pd.Timedelta(days=_MACRO_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    tickers = ["^VIX", "^VIX3M", "FXY", "UUP", "HYG", "IEF", "SPY"]
    if cfg is not None:
        allow_network = not bool(getattr(cfg, "price_cache_local_only", False))
        cols = {
            t: _load_cached_close_series(cfg, t, dl_start, end_date, allow_network=allow_network)
            for t in tickers
        }
        df = pd.concat(cols.values(), axis=1)
        df.columns = list(cols.keys())
    else:
        raw = yf.download(tickers, start=dl_start, end=end_date, progress=False, auto_adjust=True)
        if isinstance(raw.columns, pd.MultiIndex):
            df = raw["Close"].copy()
        else:
            df = raw.copy()
    df = df.rename(columns={"^VIX": "VIX", "^VIX3M": "VIX3M"})
    return df.dropna(how="all").ffill()


def compute_macro_state_at_date(macro_df: pd.DataFrame, date: pd.Timestamp) -> MacroState:
    _all_clear = MacroState(
        False, False, False, False, False, False, False, True, True, True,
        False, False, True, False, False,
    )
    window_start = date - pd.Timedelta(days=_MACRO_LOOKBACK_DAYS)
    window = macro_df.loc[window_start:date]
    if window.empty or len(window) < 10:
        return _all_clear

    def _col(name: str) -> pd.Series:
        return window[name].dropna() if name in window.columns else pd.Series(dtype=float)

    vix_s   = _col("VIX")
    vix3m_s = _col("VIX3M")
    if vix_s.empty or vix3m_s.empty:
        return _all_clear

    vix   = float(vix_s.iloc[-1])
    vix3m = float(vix3m_s.iloc[-1])
    hyg_s, ief_s = _col("HYG"), _col("IEF")
    credit_s = (hyg_s / ief_s.reindex(hyg_s.index, method="ffill")).dropna() \
               if not hyg_s.empty and not ief_s.empty else pd.Series(dtype=float)

    return compute_macro_state_from_prices(
        vix=vix, vix3m=vix3m,
        fxy_weekly=_col("FXY"),
        uup_weekly=_col("UUP"),
        credit_weekly=credit_s,
        spy_weekly=_col("SPY"),
    )


# ============================================================
# Dual-gate sell helper (inlined from daily_exit_utils.py)
# ============================================================
DUAL_GATE_TARGET_LONG_PCT = 0.30


def _compute_current_equity(state: dict, prices: dict) -> tuple:
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


def _rank_positions_by_momentum(state: dict, rocs: dict) -> list:
    result = []
    for ticker, pos in state.get("positions", {}).items():
        if pos.get("sleeve", "long") != "long":
            continue
        roc = rocs.get(ticker, 0.0)
        result.append((ticker, roc))
    return sorted(result, key=lambda x: x[1])


def compute_sells_to_reach_target_long_pct(
    state: dict,
    prices: dict,
    rocs: dict,
    target_long_pct: float = DUAL_GATE_TARGET_LONG_PCT,
) -> list:
    equity, long_val = _compute_current_equity(state, prices)
    if equity <= 0:
        return []
    target_long = equity * target_long_pct
    if long_val <= target_long:
        return []

    ranked = _rank_positions_by_momentum(state, rocs)
    need_to_sell = long_val - target_long

    sells = []
    sold_value = 0.0
    for ticker, _roc in ranked:
        if sold_value >= need_to_sell:
            break
        shares = int(state["positions"][ticker]["shares"])
        price  = prices.get(ticker, 0.0)
        if price <= 0:
            continue
        pos_value = shares * price
        remaining = need_to_sell - sold_value
        if pos_value <= remaining:
            sells.append((ticker, shares))
            sold_value += pos_value
        else:
            shares_to_sell = int(remaining / price)
            if shares_to_sell > 0:
                sells.append((ticker, shares_to_sell))
            sold_value += shares_to_sell * price
            break
    return sells


# ============================================================
# Position / TradeRecord / ExecutionRecord
# ============================================================
@dataclass
class Position:
    ticker: str
    entry_price: float
    entry_date: pd.Timestamp
    shares: int
    stop_price: float
    highest_since_entry: float = 0.0
    trailing_stop: float       = 0.0
    sleeve: str                = "long"
    entry_bar_idx: int         = 0
    momentum_at_entry: float   = 0.0
    entry_alloc_pct: float     = 0.0
    target_weight: float       = 0.0
    hedge_add_count: int       = 0
    hedge_last_add_price: float = np.nan
    hedge_has_scaled_out: bool = False
    hedge_has_scaled_out_purple: bool = False

    def update_trailing_long(self, high, atr, trail_mult):
        self.highest_since_entry = max(self.highest_since_entry, high)
        new_trail = self.highest_since_entry - atr * trail_mult
        self.trailing_stop = max(self.trailing_stop, new_trail)


@dataclass
class TradeRecord:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    exit_reason: str
    hold_bars: int
    sleeve: str              = "long"
    momentum_at_entry: float = 0.0
    entry_alloc_pct: float   = 0.0


@dataclass
class ExecutionRecord:
    date: pd.Timestamp
    ticker: str
    action: str
    shares: int
    price: float
    notional: float
    position_before: int
    position_after: int
    avg_price_before: float
    avg_price_after: float
    sleeve: str
    weight_before: float
    weight_after: float
    target_weight: float
    cash_after: float
    equity_after: float
    reason: str


@dataclass
class TargetState:
    eligible: bool
    base_weight: float
    weight_cap: float
    final_target_weight: float
    primary_reason: str
    rank: int | None = None
    score: float = np.nan


# ============================================================
# CSV append-only helpers
# ============================================================
_EQUITY_COLS = [
    "date", "equity", "cash", "positions", "long_n", "hedge_n",
    "invested_pct", "long_pct", "hedge_pct",
    "regime_score", "regime_velocity", "early_warning",
    "cs_avg_mom", "cs_dispersion", "cs_mom_delta", "cs_disp_delta", "cs_stage",
]
_DCA_EQUITY_COLS = _EQUITY_COLS + [
    "nav", "nav_units", "total_injected",
    "signal_date", "execution_date", "data_frequency",
]

_TRADES_COLS = [
    "ticker", "entry_date", "exit_date", "entry_price", "exit_price",
    "shares", "pnl", "pnl_pct", "exit_reason", "hold_bars",
    "sleeve", "momentum_at_entry", "entry_alloc_pct",
]

_EXECUTIONS_COLS = [
    "date", "ticker", "action", "shares", "price", "notional",
    "position_before", "position_after",
    "avg_price_before", "avg_price_after", "sleeve",
    "weight_before", "weight_after", "target_weight",
    "cash_after", "equity_after", "reason",
]

_REGIME_DEBUG_COLS = [
    "date", "equity_before", "regime_score", "regime_velocity",
    "base_long_pct", "base_hedge_pct",
    "rs_lock_before", "rs_lock_after", "rs_gate_action", "after_rs_long_pct",
    "cs_scale", "cs_stage", "after_cs_long_pct", "cs_applied",
    "contrarian_boost", "after_vix_long_pct",
    "macro_action", "after_macro_long_pct",
    "dual_gate", "daily_exit_scanned", "daily_exit_triggered",
    "dual_gate_exit_date", "after_dual_gate_long_pct",
    "final_target_long_pct", "actual_long_pct_after",
    "macro_alert", "alert_vix", "alert_jpy", "alert_usd", "alert_credit",
    "spy_below_20w_ma",
]


def save_trades(trades: list, csv_path: str, is_incremental: bool):
    if not trades:
        return
    new_rows = []
    for t in trades:
        new_rows.append({
            "ticker":            t.ticker,
            "entry_date":        str(t.entry_date.date()) if hasattr(t.entry_date, "date") else str(t.entry_date),
            "exit_date":         str(t.exit_date.date())  if hasattr(t.exit_date, "date")  else str(t.exit_date),
            "entry_price":       round(t.entry_price, 4),
            "exit_price":        round(t.exit_price, 4),
            "shares":            t.shares,
            "pnl":               round(t.pnl, 2),
            "pnl_pct":           round(t.pnl_pct, 4),
            "exit_reason":       t.exit_reason,
            "hold_bars":         t.hold_bars,
            "sleeve":            t.sleeve,
            "momentum_at_entry": round(t.momentum_at_entry, 4),
            "entry_alloc_pct":   round(t.entry_alloc_pct, 2),
        })
    new_df = pd.DataFrame(new_rows)[_TRADES_COLS]

    if is_incremental and os.path.exists(csv_path):
        existing = pd.read_csv(csv_path, parse_dates=["entry_date"])
        existing_keys = set(zip(existing["ticker"].astype(str), existing["entry_date"].astype(str)))
        new_df["_key"] = list(zip(new_df["ticker"], new_df["entry_date"].astype(str)))
        new_df = new_df[~new_df["_key"].isin(existing_keys)].drop(columns=["_key"])
        if len(new_df) == 0:
            print("trades: 無新 trades 需要 append")
            return
        new_df.to_csv(csv_path, mode="a", index=False, header=False)
        print(f"trades: appended {len(new_df)} rows → {csv_path}")
    else:
        new_df.to_csv(csv_path, index=False)
        print(f"trades: written {len(new_df)} rows → {csv_path}")


def save_executions(executions: list, csv_path: str, is_incremental: bool):
    if not executions:
        return
    new_rows = []
    for e in executions:
        new_rows.append({
            "date": str(e.date.date()) if hasattr(e.date, "date") else str(e.date),
            "ticker": e.ticker,
            "action": e.action,
            "shares": int(e.shares),
            "price": round(float(e.price), 6),
            "notional": round(float(e.notional), 6),
            "position_before": int(e.position_before),
            "position_after": int(e.position_after),
            "avg_price_before": round(float(e.avg_price_before), 6),
            "avg_price_after": round(float(e.avg_price_after), 6),
            "sleeve": str(getattr(e, "sleeve", "")),
            "weight_before": round(float(e.weight_before), 10),
            "weight_after": round(float(e.weight_after), 10),
            "target_weight": round(float(e.target_weight), 10),
            "cash_after": round(float(e.cash_after), 6),
            "equity_after": round(float(e.equity_after), 6),
            "reason": e.reason,
        })
    new_df = pd.DataFrame(new_rows)[_EXECUTIONS_COLS]

    if is_incremental and os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        existing_keys = set(tuple(row) for row in existing[_EXECUTIONS_COLS].itertuples(index=False, name=None))
        keys = [tuple(row) for row in new_df[_EXECUTIONS_COLS].itertuples(index=False, name=None)]
        mask = [k not in existing_keys for k in keys]
        new_df = new_df[mask]
        if len(new_df) == 0:
            print("executions: 無新 rows 需要 append")
            return
        new_df.to_csv(csv_path, mode="a", index=False, header=False)
        print(f"executions: appended {len(new_df)} rows → {csv_path}")
    else:
        new_df.to_csv(csv_path, index=False)
        print(f"executions: written {len(new_df)} rows → {csv_path}")


def load_resume_twr_state(output_dir: str, equity_csv: str, state: dict) -> dict:
    resume = {
        "nav_units": state.get("nav_units", None),
        "total_injected": state.get("total_injected", None),
        "dca_prev_month": state.get("dca_prev_month", None),
    }
    if all(resume[k] not in (None, "") for k in resume):
        return resume

    equity_path = os.path.join(output_dir, equity_csv)
    if not os.path.exists(equity_path):
        return resume

    try:
        eq = pd.read_csv(equity_path, usecols=["date", "nav_units", "total_injected"])
    except Exception:
        return resume
    if eq.empty:
        return resume

    eq["date"] = pd.to_datetime(eq["date"], errors="coerce")
    eq["nav_units"] = pd.to_numeric(eq["nav_units"], errors="coerce")
    eq["total_injected"] = pd.to_numeric(eq["total_injected"], errors="coerce")
    eq = eq.dropna(subset=["date"])
    state_last_date = state.get("last_processed_date", None)
    if state_last_date:
        eq = eq[eq["date"] <= pd.Timestamp(state_last_date)]
    if eq.empty:
        return resume

    stable = eq.copy()
    stable["inj_cummax"] = stable["total_injected"].cummax()
    stable = stable[
        stable["total_injected"].notna()
        & stable["nav_units"].notna()
        & (stable["nav_units"] > 0)
        & (stable["total_injected"] >= 0)
        & (stable["total_injected"] >= stable["inj_cummax"] - 1e-9)
    ]
    last = stable.iloc[-1] if not stable.empty else eq.iloc[-1]
    if resume["nav_units"] in (None, ""):
        val = pd.to_numeric(last.get("nav_units", np.nan), errors="coerce")
        if pd.notna(val) and float(val) > 0:
            resume["nav_units"] = float(val)
    if resume["total_injected"] in (None, ""):
        val = pd.to_numeric(last.get("total_injected", np.nan), errors="coerce")
        if pd.notna(val) and float(val) >= 0:
            resume["total_injected"] = float(val)
    if resume["dca_prev_month"] in (None, ""):
        date_val = last.get("date", None)
        if pd.notna(date_val):
            resume["dca_prev_month"] = pd.Timestamp(date_val).strftime("%Y-%m")

    return resume


# ============================================================
# Base momentum engine
# ============================================================
class MomentumEngine:

    def __init__(self, cfg: Config, initial_positions: dict = None, initial_cash: float = None):
        self.cfg       = cfg
        self.positions: dict = dict(initial_positions) if initial_positions else {}
        self.cash      = initial_cash if initial_cash is not None else cfg.initial_capital
        # Fix #7: Initialize equity correctly by including existing position values (if price is known)
        # or at least using the cost basis as a proxy until first price update.
        pos_value = sum(p.shares * p.entry_price for p in self.positions.values())
        self.equity    = self.cash + pos_value
        self.trades: list          = []
        self.equity_curve: list    = []
        self.executions: list      = []
        self.regime_debug: list    = []
        self._last_price: dict     = {t: p.entry_price for t, p in self.positions.items()}
        self._regime_history: list = []
        self._ew_active_count: int = 0
        self._prev_cs_avg_mom: float    = np.nan
        self._prev_cs_dispersion: float = np.nan
        self.nav_units: float = 1.0 # Will be overridden or recalculated
        self.total_injected: float = 0.0
        self.dca_prev_month: str | None = None
        self._long_entry_block_active: bool = False

    def fetch_data(self, fetch_start: str = None, extra_tickers: list = None):
        extra_tickers = extra_tickers or []
        all_t = list(set(self.cfg.universe + self.cfg.hedge_universe + extra_tickers))
        allow_network = not bool(getattr(self.cfg, "price_cache_local_only", False))

        if fetch_start is not None:
            lookback_days  = self.cfg.min_bars * 7
            download_start = (pd.Timestamp(fetch_start) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            print(f"增量模式：下載起點 {download_start}，交易迴圈起點 {fetch_start}")
        else:
            warmup_days = 26 * 7 + 30
            download_start = (pd.Timestamp(self.cfg.start_date) - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
            print(f"全量回測模式：下載起點 {download_start}（含 Clenow warmup）")

        print(f"Downloading {len(all_t)} tickers → {self.cfg.end_date}...")
        stock_data, hedge_data, exit_only_data = {}, {}, {}

        for t in all_t:
            try:
                is_hedge = t in self.cfg.hedge_universe
                interval = self.cfg.hedge_timeframe if is_hedge else self.cfg.timeframe
                if is_hedge:
                    df = load_price_data(
                        self.cfg, ticker=t, start=download_start, end=self.cfg.end_date,
                        interval=interval, allow_network=allow_network
                    )
                else:
                    df = load_strategy_price_data(
                        self.cfg, ticker=t, start=download_start, end=self.cfg.end_date,
                        allow_network=allow_network,
                    )
                if len(df) == 0:
                    print(f"  {t}: 0 bars, skipped"); continue
                if fetch_start is None and len(df) < self.cfg.min_bars:
                    print(f"  {t}: {len(df)} bars (< {self.cfg.min_bars}), skipped"); continue
                df = compute_indicators(df, self.cfg)
                if t in extra_tickers and t not in self.cfg.universe and t not in self.cfg.hedge_universe:
                    exit_only_data[t] = df
                elif is_hedge:
                    hedge_data[t] = df
                if t in self.cfg.universe:
                    stock_data[t] = df
                print(f"  {t}: {len(df)} bars [{interval}]")
            except Exception as e:
                print(f"  {t}: error - {e}")

        return stock_data, hedge_data, exit_only_data

    # ---- 內部工具 ----
    def _lookup_daily_close(self, ticker, date, daily_price_data=None):
        daily_price_data = daily_price_data if daily_price_data is not None else getattr(
            self, "_daily_execution_price_data", {}
        )
        if not daily_price_data or ticker not in daily_price_data:
            return None
        df = daily_price_data.get(ticker)
        if df is None or len(df) == 0 or "Close" not in df.columns:
            return None

        date_ts = pd.Timestamp(date).normalize()
        if date_ts in df.index:
            price = df.loc[date_ts, "Close"]
        else:
            window = df[(df.index > date_ts) & (df.index <= date_ts + pd.Timedelta(days=6))]
            if window.empty:
                return None
            price = window.iloc[0]["Close"]

        if pd.isna(price) or float(price) <= 0:
            return None
        return float(price)

    def _get_price(self, ticker, date, all_data):
        daily_price = self._lookup_daily_close(ticker, date)
        if daily_price is not None:
            self._last_price[ticker] = daily_price
            return daily_price
        if ticker in all_data and date in all_data[ticker].index:
            p = float(all_data[ticker].loc[date, "Close"])
            self._last_price[ticker] = p
            return p
        return self._last_price.get(ticker, 0.0)

    def _execution_price(self, ticker, date, row, daily_price_data=None):
        daily_price = self._lookup_daily_close(ticker, date, daily_price_data=daily_price_data)
        if daily_price is not None:
            return daily_price
        return float(row["Close"])

    def _previous_completed_row(self, df: pd.DataFrame, date):
        if df is None or len(df) == 0 or date not in df.index:
            return None
        idx = df.index.get_loc(date)
        if isinstance(idx, slice):
            idx = idx.start
        elif isinstance(idx, np.ndarray):
            matches = np.flatnonzero(idx)
            idx = int(matches[0]) if len(matches) else -1
        elif not isinstance(idx, (int, np.integer)):
            idx = int(idx)
        if idx < 1:
            return None
        return df.iloc[int(idx) - 1]

    def _current_indexed_signal_row(self, df: pd.DataFrame, date):
        if df is None or len(df) == 0 or date not in df.index:
            return None
        row = df.loc[date]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return row

    def _completed_signal_row(self, df: pd.DataFrame, date):
        if _is_sampled_daily_timeframe(self.cfg.timeframe):
            return self._current_indexed_signal_row(df, date)
        return self._previous_completed_row(df, date)

    def _signal_row(self, data: dict, ticker: str, date):
        if data is None or ticker not in data:
            return None
        return self._completed_signal_row(data[ticker], date)

    def _bar_metadata(self, data: dict, date) -> tuple[str, str, str]:
        execution_date = pd.Timestamp(date).strftime("%Y-%m-%d")
        signal_date = execution_date
        data_frequency = "weekly" if str(self.cfg.timeframe).lower() == "1wk" else str(self.cfg.timeframe)

        for df in (data or {}).values():
            if df is None or date not in df.index:
                continue
            row = df.loc[date]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            raw_signal = row.get("signal_date", None)
            raw_exec = row.get("execution_date", None)
            raw_freq = row.get("data_frequency", None)
            if raw_signal not in (None, "") and not pd.isna(raw_signal):
                signal_date = str(raw_signal)[:10]
            if raw_exec not in (None, "") and not pd.isna(raw_exec):
                execution_date = str(raw_exec)[:10]
            if raw_freq not in (None, "") and not pd.isna(raw_freq):
                data_frequency = str(raw_freq)
            break

        return signal_date, execution_date, data_frequency

    def _get_leverage(self, t):
        return self.cfg.leverage_map.get(t, 1.0)

    def _effective_pos_pct(self, sleeve):
        n = {"long": self.cfg.max_long_positions, "hedge": self.cfg.max_hedge_positions}.get(sleeve, 5)
        return min(self.cfg.max_position_pct, 0.95 / max(n, 1))

    def _equity_at(self, date, all_data) -> float:
        lv = 0.0
        for t, pos in self.positions.items():
            lv += float(pos.shares) * float(self._get_price(t, date, all_data))
        return float(self.cash) + float(lv)

    def _log_execution(self, date, ticker, action, shares, price,
                       position_before, position_after,
                       avg_price_before, avg_price_after, sleeve,
                       weight_before, weight_after, target_weight,
                       cash_after, equity_after, reason):
        notional = float(shares) * float(price)
        self.executions.append(ExecutionRecord(
            date=date, ticker=ticker, action=action,
            shares=int(shares), price=float(price), notional=float(notional),
            position_before=int(position_before), position_after=int(position_after),
            avg_price_before=float(avg_price_before), avg_price_after=float(avg_price_after),
            sleeve=str(sleeve),
            weight_before=float(weight_before), weight_after=float(weight_after),
            target_weight=float(target_weight),
            cash_after=float(cash_after), equity_after=float(equity_after),
            reason=str(reason),
        ))

    def _map_execution_reason(self, raw_reason: str) -> str:
        r = str(raw_reason or "")
        if r in {"rebalance_add", "rebalance_reduce", "entry"}:
            return r
        if r in {"initial_stop", "hedge_stop"}:
            return "stop"
        if r.startswith("structural_bear"):
            return "macro_block"
        if r.startswith("macro_block"):
            return "macro_block"
        if r.startswith("rank_exit"):
            return "rank_exit"
        if r.startswith("hold_missing_signal"):
            return "hold_missing_signal"
        return r

    def _rank_weight_for_rank(self, rank: int) -> float:
        weights = tuple(float(w) for w in getattr(self.cfg, "momentum_rank_weights", ()))
        if rank <= 0 or rank > len(weights):
            return 0.0
        return max(weights[rank - 1], 0.0)

    def _scale_rank_weight(self, base_weight: float, total_long_pct: float) -> float:
        target_total = float(getattr(self.cfg, "target_long_total_pct", 0.90))
        if target_total <= 0 or total_long_pct <= 0:
            return 0.0
        return float(base_weight) * float(total_long_pct) / target_total

    def _build_long_target_states(
        self,
        date,
        stock_data,
        total_long_pct: float,
        current_positions: dict | None = None,
        allowed_tickers: set | None = None,
        long_block_active: bool = False,
        block_new_entries: bool = False,
    ) -> dict[str, TargetState]:
        current_positions = current_positions or {}
        current_longs = {t: p for t, p in current_positions.items() if getattr(p, "sleeve", "long") == "long"}

        if total_long_pct <= 0 or long_block_active:
            return {
                t: TargetState(
                    eligible=False,
                    base_weight=0.0,
                    weight_cap=0.0,
                    final_target_weight=0.0,
                    primary_reason="macro_block_exit",
                    rank=None,
                    score=np.nan,
                )
                for t in current_longs
            }

        scored = []
        for ticker, df in stock_data.items():
            if allowed_tickers is not None and ticker not in allowed_tickers:
                continue
            if date not in df.index:
                continue
            row = self._completed_signal_row(df, date)
            if row is None:
                continue
            score = row.get("score", row.get("momentum", np.nan))
            if pd.isna(score):
                continue
            score_f = float(score)
            if score_f <= 0:
                continue
            scored.append((ticker, score_f))

        if not scored:
            return {
                t: TargetState(
                    eligible=False,
                    base_weight=0.0,
                    weight_cap=0.0,
                    final_target_weight=0.0,
                    primary_reason="rank_exit_no_positive_score",
                    rank=None,
                    score=np.nan,
                )
                for t in current_longs
            }

        ranked = sorted(scored, key=lambda item: item[1], reverse=True)
        decisions: dict[str, TargetState] = {}
        for rank, (ticker, score_f) in enumerate(ranked, start=1):
            base_weight = self._rank_weight_for_rank(rank)
            is_current = ticker in current_longs
            
            if base_weight <= 0:
                decisions[ticker] = TargetState(
                    eligible=False,
                    base_weight=0.0,
                    weight_cap=0.0,
                    final_target_weight=0.0,
                    primary_reason="rank_exit_below_9",
                    rank=rank,
                    score=score_f,
                )
                continue

            # Check for new entry block (VIX > 30 and Structural Weakness)
            if block_new_entries and not is_current:
                decisions[ticker] = TargetState(
                    eligible=False,
                    base_weight=0.0,
                    weight_cap=0.0,
                    final_target_weight=0.0,
                    primary_reason="panic_entry_block",
                    rank=rank,
                    score=score_f,
                )
                continue

            if rank <= int(self.cfg.momentum_entry_rank):
                scaled_weight = self._scale_rank_weight(base_weight, total_long_pct)
                decisions[ticker] = TargetState(
                    eligible=True,
                    base_weight=scaled_weight,
                    weight_cap=scaled_weight,
                    final_target_weight=scaled_weight,
                    primary_reason="rank_entry_zone",
                    rank=rank,
                    score=score_f,
                )
            elif is_current and rank <= int(self.cfg.momentum_hold_rank):
                scaled_weight = self._scale_rank_weight(base_weight, total_long_pct)
                decisions[ticker] = TargetState(
                    eligible=True,
                    base_weight=scaled_weight,
                    weight_cap=scaled_weight,
                    final_target_weight=scaled_weight,
                    primary_reason="rank_hold_zone",
                    rank=rank,
                    score=score_f,
                )
            else:
                decisions[ticker] = TargetState(
                    eligible=False,
                    base_weight=0.0,
                    weight_cap=0.0,
                    final_target_weight=0.0,
                    primary_reason="rank_exit_below_9" if not is_current else "rank_hold_zone_exit",
                    rank=rank,
                    score=score_f,
                )

        for ticker, pos in current_longs.items():
            if ticker in decisions:
                continue
            decisions[ticker] = TargetState(
                eligible=True,
                base_weight=float(getattr(pos, "target_weight", 0.0)),
                weight_cap=float(getattr(pos, "target_weight", 0.0)),
                final_target_weight=float(getattr(pos, "target_weight", 0.0)),
                primary_reason="hold_missing_signal",
                rank=None,
                score=np.nan,
            )

        return decisions

    def _regime_to_allocation(self, rs, velocity):
        # Regime sigmoid (configurable):
        # target behavior: regime > 0.3 should be close to full long exposure.
        sig = 1.0 / (1.0 + np.exp(-self.cfg.regime_sigmoid_k * (rs - self.cfg.regime_sigmoid_mid)))
        span = max(0.0, self.cfg.regime_long_ceiling - self.cfg.regime_long_floor)
        long_pct = self.cfg.regime_long_floor + sig * span

        if velocity < self.cfg.ew_velocity_thresh and rs <= 0.3:
            intensity = min(abs(velocity / self.cfg.ew_velocity_thresh), 2.0)
            hedge_pct = 0.15 * intensity
            long_pct *= 0.85
        elif rs < self.cfg.bear_entry_thresh:
            hedge_pct = 0.30
            long_pct  = min(long_pct, 0.25)
        else:
            hedge_pct = 0.0

        total = long_pct + hedge_pct
        if total > 1.0:
            long_pct  /= total
            hedge_pct /= total

        return round(long_pct, 3), round(hedge_pct, 3)

    def _close_position(self, ticker, date, exit_price, reason, bar_idx, dates, all_data=None):
        pos = self.positions[ticker]
        price = float(exit_price)
        
        # Fix: Capture all needed data BEFORE modifying state
        position_before = int(pos.shares)
        avg_before = float(pos.entry_price)
        entry_date = pos.entry_date
        sleeve = pos.sleeve
        momentum_at_entry = pos.momentum_at_entry
        entry_alloc_pct = getattr(pos, "entry_alloc_pct", 0.0)
        target_weight = float(getattr(pos, "target_weight", 0.0))

        # Update cash and DELETE position before calculating equity_after
        self.cash += position_before * price
        del self.positions[ticker]
        self._last_price[ticker] = price # Ensure next equity_at call sees this price

        if all_data is not None:
            equity_after = self._equity_at(date, all_data)
            # For logging purposes, we estimate weight_before using equity_after + sold value
            equity_est_before = equity_after 
            value_before = float(position_before) * price
            weight_before = (value_before / (equity_est_before)) if equity_est_before > 0 else 0.0
        else:
            equity_after = float(self.equity)
            weight_before = 0.0

        pnl     = (price - avg_before) * position_before
        pnl_pct = (price / avg_before - 1) * 100 if avg_before > 0 else 0

        ei = dates.index(entry_date) if entry_date in dates else 0
        self.trades.append(TradeRecord(
            ticker=ticker, entry_date=entry_date, exit_date=date,
            entry_price=avg_before, exit_price=price,
            shares=position_before, pnl=pnl, pnl_pct=pnl_pct,
            exit_reason=reason, hold_bars=bar_idx - ei,
            sleeve=sleeve, momentum_at_entry=momentum_at_entry,
            entry_alloc_pct=entry_alloc_pct,
        ))

        if all_data is not None:
            self._log_execution(
                date=date, ticker=ticker, action="SELL",
                shares=int(position_before), price=float(price),
                position_before=position_before, position_after=0,
                avg_price_before=avg_before, avg_price_after=0.0,
                sleeve=("hedge" if ticker in self.cfg.hedge_universe else "long"),
                weight_before=weight_before, weight_after=0.0,
                target_weight=target_weight,
                cash_after=float(self.cash), equity_after=float(equity_after),
                reason=self._map_execution_reason(reason),
            )

    def _enter_position(self, ticker, date, row, budget, intended_budget, bar_idx, sleeve,
                        momentum=0.0, all_data=None, target_weight: float = 0.0,
                        reason: str = "entry", daily_price_data=None, execution_price: float | None = None):
        price = float(execution_price) if execution_price is not None else self._execution_price(ticker, date, row, daily_price_data=daily_price_data)
        atr = row["atr"]
        if pd.isna(atr) or atr == 0 or price == 0 or budget <= 0:
            return

        if all_data is not None:
            equity_before = self._equity_at(date, all_data)
        else:
            equity_before = float(self.equity)

        lev        = self._get_leverage(ticker)
        stop_dist  = atr * self.cfg.stop_atr_mult
        if self.cfg.force_target_long_allocation and sleeve == "long":
            shares = int(min(budget, self.cash) / price)
        else:
            eff_pct    = self._effective_pos_pct(sleeve) / lev
            max_shares = int(self.equity * eff_pct / price)
            shares     = min(int(budget / price), max_shares)
        if shares <= 0:
            return
        cost = shares * price
        if cost > self.cash:
            shares = int(self.cash / price); cost = shares * price
        if shares <= 0:
            return
        if sleeve == "long" and intended_budget > 0:
            fill_ratio = float(cost) / float(intended_budget)
            if fill_ratio < float(getattr(self.cfg, "long_fill_target_ratio", 0.98)):
                return

        entry_value = shares * price
        total_capital = self.cash + sum(p.shares * p.entry_price for p in self.positions.values())
        entry_alloc_pct = (entry_value / total_capital * 100) if total_capital > 0 else 0.0

        self.cash -= cost
        self._last_price[ticker] = price
        max_loss_floor = price * (1 - self.cfg.max_loss_pct / 100)
        init_stop = max(price - stop_dist, max_loss_floor)
        self.positions[ticker] = Position(
            ticker=ticker, entry_price=price, entry_date=date,
            shares=shares, stop_price=init_stop,
            highest_since_entry=row["High"], sleeve=sleeve,
            entry_bar_idx=bar_idx, momentum_at_entry=momentum,
            entry_alloc_pct=entry_alloc_pct,
            target_weight=float(target_weight),
        )

        if all_data is not None:
            equity_after = self._equity_at(date, all_data)
            position_after = int(self.positions[ticker].shares)
            avg_after = float(self.positions[ticker].entry_price)
            value_after = float(position_after) * float(price)
            weight_after = (value_after / equity_after) if equity_after > 0 else 0.0
            self._log_execution(
                date=date, ticker=ticker, action="BUY",
                shares=int(position_after), price=float(price),
                position_before=0, position_after=position_after,
                avg_price_before=0.0, avg_price_after=avg_after,
                sleeve=("hedge" if ticker in self.cfg.hedge_universe else "long"),
                weight_before=0.0, weight_after=weight_after,
                target_weight=float(target_weight),
                cash_after=float(self.cash), equity_after=float(equity_after),
                reason=str(reason),
            )

    def _position_value(self, ticker, date, all_data) -> float:
        if ticker not in self.positions:
            return 0.0
        p = self._get_price(ticker, date, all_data)
        return float(self.positions[ticker].shares) * float(p)

    def _current_weight(self, ticker, date, all_data) -> float:
        if self.equity <= 0:
            return 0.0
        return self._position_value(ticker, date, all_data) / self.equity

    def _current_signal_score(self, ticker: str, date, all_data=None, fallback: float = 0.0) -> float:
        if all_data is not None and ticker in all_data and date in all_data[ticker].index:
            row = self._completed_signal_row(all_data[ticker], date)
            if row is None:
                row = all_data[ticker].loc[date]
            score = row.get("score", row.get("momentum", np.nan))
            if not pd.isna(score):
                return float(score)
        if ticker in self.positions:
            return float(getattr(self.positions[ticker], "momentum_at_entry", fallback))
        return float(fallback)

    def _fund_hedge_from_weakest_longs(
        self,
        date,
        required_cash: float,
        bar_idx: int,
        dates,
        stock_data: dict | None,
        all_data=None,
        daily_price_data=None,
    ) -> None:
        shortfall = float(required_cash) - float(self.cash)
        if shortfall <= 1e-9:
            return

        self.equity = self._equity_at(date, all_data) if all_data is not None else float(self.equity)
        current_longs = [t for t, p in self.positions.items() if p.sleeve == "long"]
        ranked = sorted(
            current_longs,
            key=lambda t: self._current_signal_score(t, date, stock_data, fallback=0.0),
        )

        for ticker in ranked:
            if self.cash >= required_cash - 1e-9:
                break
            if ticker not in self.positions or ticker not in all_data or date not in all_data[ticker].index:
                continue
            price = self._get_price(ticker, date, all_data)
            if price <= 0:
                continue
            pos_value = self._position_value(ticker, date, all_data)
            if pos_value <= 0:
                continue

            remaining_shortfall = required_cash - self.cash
            size_pct = min(remaining_shortfall / max(float(self.equity), 1e-9), pos_value / max(float(self.equity), 1e-9))
            row = self._signal_row(stock_data, ticker, date)
            if row is None:
                row = all_data[ticker].loc[date]
            self._reduce_position(
                ticker, date, row, size_pct, bar_idx, dates,
                reason="hedge_funding_reduce", all_data=all_data,
                target_weight=float(getattr(self.positions.get(ticker), "target_weight", 0.0)),
                daily_price_data=daily_price_data,
            )
            self.equity = self._equity_at(date, all_data) if all_data is not None else float(self.equity)

    def _cap_and_normalize_weights(self, ranked_scores: list[tuple[str, float]], total_long_pct: float, sleeve: str = "long") -> dict:
        if total_long_pct <= 0 or not ranked_scores:
            return {}
        cap = self._effective_pos_pct(sleeve)
        if cap <= 0:
            return {}

        remaining = min(float(total_long_pct), cap * len(ranked_scores))
        active = {t: max(float(s), 1e-9) for t, s in ranked_scores}
        weights = {t: 0.0 for t, _ in ranked_scores}

        while remaining > 1e-9 and active:
            score_sum = float(sum(active.values()))
            if score_sum <= 0:
                break
            saturated = []
            distributed = 0.0
            for ticker, score in list(active.items()):
                room = cap - weights[ticker]
                if room <= 1e-9:
                    saturated.append(ticker)
                    continue
                alloc = remaining * (score / score_sum)
                alloc = min(alloc, room)
                if alloc > 0:
                    weights[ticker] += alloc
                    distributed += alloc
                if cap - weights[ticker] <= 1e-9:
                    saturated.append(ticker)
            if distributed <= 1e-9:
                break
            remaining -= distributed
            for ticker in saturated:
                active.pop(ticker, None)

        return {t: w for t, w in weights.items() if w > 1e-9}

    def _compute_target_weights(
        self,
        date,
        stock_data,
        total_long_pct: float,
        allowed_tickers: set | None = None,
        current_positions: dict | None = None,
        long_block_active: bool = False,
    ) -> dict:
        decisions = self._build_long_target_states(
            date=date,
            stock_data=stock_data,
            total_long_pct=total_long_pct,
            current_positions=current_positions or self.positions,
            allowed_tickers=allowed_tickers,
            long_block_active=long_block_active,
        )
        return {
            ticker: decision.final_target_weight
            for ticker, decision in decisions.items()
            if decision.final_target_weight > 1e-9
        }

    def _add_position(self, ticker, date, row, size_pct: float, bar_idx: int, sleeve: str,
                      momentum: float = 0.0, all_data=None, target_weight: float = 0.0,
                      reason: str = "rebalance_add", daily_price_data=None, execution_price: float | None = None):
        if size_pct <= 0 or self.equity <= 0:
            return

        price = float(execution_price) if execution_price is not None else self._execution_price(ticker, date, row, daily_price_data=daily_price_data)
        if price <= 0:
            return

        intended_budget = float(self.equity) * float(size_pct)
        budget = float(intended_budget)
        budget = min(budget, float(self.cash))
        if budget <= 0:
            return

        if ticker not in self.positions:
            self._enter_position(
                ticker, date, row, budget, intended_budget, bar_idx, sleeve,
                momentum=momentum, all_data=all_data,
                target_weight=target_weight,
                reason="entry" if reason == "rebalance_add" else reason,
                daily_price_data=daily_price_data,
                execution_price=execution_price,
            )
            return

        pos = self.positions[ticker]
        price_f = float(price)
        if all_data is not None:
            equity_before = self._equity_at(date, all_data)
            position_before = int(pos.shares)
            avg_before = float(pos.entry_price)
            value_before = float(position_before) * price_f
            weight_before = (value_before / equity_before) if equity_before > 0 else 0.0
        else:
            position_before = int(pos.shares)
            avg_before = float(pos.entry_price)
            weight_before = 0.0

        shares_to_buy = int(budget / price)
        if shares_to_buy <= 0:
            return

        cost = shares_to_buy * price
        if cost > self.cash:
            shares_to_buy = int(self.cash / price)
            cost = shares_to_buy * price
        if shares_to_buy <= 0:
            return
        if sleeve == "long" and intended_budget > 0:
            fill_ratio = float(cost) / float(intended_budget)
            if fill_ratio < float(getattr(self.cfg, "long_fill_target_ratio", 0.98)):
                return
        if (
            sleeve == "long"
            and reason in {"rebalance_add", "entry"}
            and shares_to_buy < int(getattr(self.cfg, "min_rebalance_shares", 2))
        ):
            return

        old_value = pos.shares * pos.entry_price
        add_value = shares_to_buy * price
        new_shares = pos.shares + shares_to_buy
        if new_shares <= 0:
            return

        pos.entry_price = (old_value + add_value) / new_shares
        pos.shares = new_shares
        pos.highest_since_entry = max(pos.highest_since_entry, float(row["High"]))
        self.cash -= cost
        self._last_price[ticker] = price
        pos.target_weight = float(target_weight)

        if all_data is not None:
            equity_after = self._equity_at(date, all_data)
            position_after = int(pos.shares)
            avg_after = float(pos.entry_price)
            value_after = float(position_after) * price_f
            weight_after = (value_after / equity_after) if equity_after > 0 else 0.0
            self._log_execution(
                date=date, ticker=ticker, action="ADD",
                shares=int(shares_to_buy), price=price_f,
                position_before=position_before, position_after=position_after,
                avg_price_before=avg_before, avg_price_after=avg_after,
                sleeve=("hedge" if ticker in self.cfg.hedge_universe else "long"),
                weight_before=weight_before, weight_after=weight_after,
                target_weight=float(target_weight),
                cash_after=float(self.cash), equity_after=float(equity_after),
                reason=str(reason),
            )

    def _reduce_position(self, ticker, date, row, size_pct: float, bar_idx: int, dates,
                         reason: str = "rebalance_reduce", all_data=None, target_weight: float = 0.0,
                         daily_price_data=None):
        if ticker not in self.positions or size_pct <= 0 or self.equity <= 0:
            return

        price = self._execution_price(ticker, date, row, daily_price_data=daily_price_data)
        if price <= 0:
            return

        pos = self.positions[ticker]
        price_f = float(price)
        
        # Fix #1: Capture state BEFORE modification
        position_before = int(pos.shares)
        avg_before = float(pos.entry_price)

        if all_data is not None:
            equity_before = self._equity_at(date, all_data)
            value_before = float(position_before) * price_f
            weight_before = (value_before / equity_before) if equity_before > 0 else 0.0
        else:
            equity_before = float(self.equity)
            weight_before = 0.0

        target_value = float(self.equity) * float(size_pct)
        shares_to_sell = int(target_value / price)
        shares_to_sell = min(shares_to_sell, position_before)
        if shares_to_sell <= 0:
            return
        if (
            reason == "rebalance_reduce"
            and shares_to_sell < int(getattr(self.cfg, "min_rebalance_shares", 2))
        ):
            return

        if shares_to_sell >= position_before:
            self._close_position(ticker, date, price, reason, bar_idx, dates, all_data=all_data)
            return

        proceeds = shares_to_sell * price
        pos.shares -= shares_to_sell
        self.cash += proceeds
        self._last_price[ticker] = price
        pos.target_weight = float(target_weight)

        if all_data is not None:
            equity_after = self._equity_at(date, all_data)
            position_after = int(pos.shares)
            value_after = float(position_after) * price_f
            weight_after = (value_after / equity_after) if equity_after > 0 else 0.0
            self._log_execution(
                date=date, ticker=ticker, action="REDUCE",
                shares=int(shares_to_sell), price=price_f,
                position_before=position_before, position_after=position_after,
                avg_price_before=avg_before, avg_price_after=avg_before,
                sleeve=("hedge" if ticker in self.cfg.hedge_universe else "long"),
                weight_before=weight_before, weight_after=weight_after,
                target_weight=float(target_weight),
                cash_after=float(self.cash), equity_after=float(equity_after),
                reason=str(reason),
            )

    def _check_exit_long(self, pos, row):
        c, atr = row["Close"], row["atr"]
        if pd.isna(atr) or atr == 0:
            return None
        if c <= pos.stop_price:
            return "initial_stop"
        return None

    def _reset_pine_hedge_state(self, pos: Position) -> None:
        pos.hedge_add_count = 0
        pos.hedge_last_add_price = np.nan
        pos.hedge_has_scaled_out = False
        pos.hedge_has_scaled_out_purple = False
        pos.trailing_stop = 0.0
        pos.highest_since_entry = max(float(getattr(pos, "highest_since_entry", 0.0)), float(pos.entry_price))

    def _check_exit_pine_hedge(self, pos: Position, row: pd.Series, prev_row: pd.Series | None) -> dict | None:
        if pos.sleeve != "hedge":
            return None
        atr = row.get("atr", np.nan)
        bb_mid = row.get("bb_mid", np.nan)
        vol_ma = row.get("vol_ma", np.nan)
        if pd.isna(atr) or atr <= 0 or pd.isna(bb_mid):
            return None

        close = float(row["Close"])
        high = float(row["High"])
        open_ = float(row["Open"])
        volume = float(row["Volume"])
        ema_trend = row.get("ema_trend", row.get("ema", np.nan))
        prev_ema = prev_row.get("ema_trend", prev_row.get("ema", np.nan)) if prev_row is not None else np.nan

        pos.highest_since_entry = max(float(getattr(pos, "highest_since_entry", pos.entry_price)), high)
        pos.trailing_stop = pos.highest_since_entry - float(atr) * float(self.cfg.trail_atr_mult)

        is_ema_up = False
        if not pd.isna(ema_trend) and not pd.isna(prev_ema):
            is_ema_up = float(ema_trend) > float(prev_ema)
        current_stop_pct = 0.10 if is_ema_up else 0.05
        stop_loss_price = float(pos.entry_price) * (1 - current_stop_pct)

        is_over_extended = close > float(bb_mid) + 4.5 * float(atr)
        is_volume_climax = (not pd.isna(vol_ma)) and float(vol_ma) > 0 and volume > float(vol_ma) * 2.5
        is_rejection = (high - max(open_, close)) > abs(open_ - close) * 2.0
        is_blowoff_top = bool(is_over_extended and (is_volume_climax or is_rejection))

        if (not bool(getattr(pos, "hedge_has_scaled_out", False))) and close <= stop_loss_price:
            return {"kind": "full_exit", "reason": "pine_hedge_stop_loss"}
        if bool(getattr(pos, "hedge_has_scaled_out", False)) and (
            close < float(pos.trailing_stop) or close <= float(pos.entry_price) * 1.05
        ):
            return {"kind": "full_exit", "reason": "pine_hedge_trailing_stop"}
        if (not bool(getattr(pos, "hedge_has_scaled_out_purple", False))) and is_blowoff_top:
            return {"kind": "reduce", "size_pct": 0.40, "reason": "pine_hedge_blowoff_40pct"}
        if (not bool(getattr(pos, "hedge_has_scaled_out", False))) and close >= float(pos.entry_price) * 1.10:
            return {"kind": "reduce", "size_pct": 0.20, "reason": "pine_hedge_take_profit_20pct"}
        return None

    def _run_pine_hedge_sleeve(
        self,
        date,
        stock_data: dict | None,
        hedge_data: dict | None,
        vix_info: dict,
        bar_idx: int,
        all_dates,
        all_data=None,
        daily_price_data=None,
    ) -> None:
        if not bool(getattr(self.cfg, "pine_hedge_enabled", False)):
            return

        hedge_ticker = str(getattr(self.cfg, "pine_hedge_ticker", "VIXY") or "VIXY").upper()
        if hedge_data is None or hedge_ticker not in hedge_data or date not in hedge_data[hedge_ticker].index:
            return

        row = self._current_indexed_signal_row(hedge_data[hedge_ticker], date)
        signal_row = self._previous_completed_row(hedge_data[hedge_ticker], date)
        prev_row = self._previous_completed_row(hedge_data[hedge_ticker], signal_row.name) if signal_row is not None else None
        if row is None:
            return

        pos = self.positions.get(hedge_ticker)
        if pos is not None and pos.sleeve == "hedge":
            exit_signal = self._check_exit_pine_hedge(pos, row, prev_row)
            if exit_signal is not None:
                if exit_signal["kind"] == "full_exit":
                    self._close_position(
                        hedge_ticker, date, self._get_price(hedge_ticker, date, all_data),
                        exit_signal["reason"], bar_idx, all_dates, all_data=all_data,
                    )
                    pos = None
                elif exit_signal["kind"] == "reduce":
                    self._reduce_position(
                        hedge_ticker, date, row, float(exit_signal["size_pct"]), bar_idx, all_dates,
                        reason=exit_signal["reason"], all_data=all_data, target_weight=0.0,
                        daily_price_data=daily_price_data,
                    )
                    pos = self.positions.get(hedge_ticker)
                    if pos is not None and pos.sleeve == "hedge":
                        if exit_signal["reason"] == "pine_hedge_take_profit_20pct":
                            pos.hedge_has_scaled_out = True
                        if exit_signal["reason"] == "pine_hedge_blowoff_40pct":
                            pos.hedge_has_scaled_out_purple = True

        gate_active = float(vix_info.get("vix", np.nan)) > float(getattr(self.cfg, "pine_hedge_vix_gate", 15.0))
        if not gate_active:
            return

        if signal_row is None or prev_row is None:
            return

        execution_price = float(row.get("Open", np.nan))
        if pd.isna(execution_price) or execution_price <= 0:
            return

        macd_now = signal_row.get("macd", np.nan)
        macd_prev = prev_row.get("macd", np.nan)
        bb_mid = signal_row.get("bb_mid", np.nan)
        vwma_mid = signal_row.get("vwma_mid", np.nan)
        prev_vwma_mid = prev_row.get("vwma_mid", np.nan)
        atr = signal_row.get("atr", np.nan)
        if any(pd.isna(x) for x in [macd_now, macd_prev, bb_mid, vwma_mid, prev_vwma_mid, atr]) or float(atr) <= 0:
            return

        close = float(signal_row["Close"])
        prev_close = float(prev_row["Close"])
        low = float(signal_row["Low"])
        high = float(signal_row["High"])
        prev_bb_mid = prev_row.get("bb_mid", np.nan)
        if pd.isna(prev_bb_mid):
            return

        is_macd_under_zero = float(macd_now) < 0.0
        is_macd_rising = float(macd_now) > float(macd_prev)
        is_vwma_up = float(vwma_mid) > float(prev_vwma_mid)
        touch_or_cross_mid = ((low <= float(bb_mid) <= high) or (prev_close <= float(prev_bb_mid) and close > float(bb_mid)))
        entry_condition = is_macd_under_zero and (is_macd_rising or is_vwma_up)

        if pos is None:
            if entry_condition and touch_or_cross_mid:
                hedge_budget = float(self.equity) * float(getattr(self.cfg, "pine_hedge_first_entry_pct", 0.10))
                self._fund_hedge_from_weakest_longs(
                    date, hedge_budget, bar_idx, all_dates, stock_data,
                    all_data=all_data, daily_price_data=daily_price_data,
                )
                self._add_position(
                    hedge_ticker, date, signal_row, float(getattr(self.cfg, "pine_hedge_first_entry_pct", 0.10)),
                    bar_idx, "hedge", momentum=float(macd_now), all_data=all_data,
                    target_weight=0.0, reason="pine_hedge_buy", daily_price_data=daily_price_data,
                    execution_price=execution_price,
                )
                pos = self.positions.get(hedge_ticker)
                if pos is not None and pos.sleeve == "hedge":
                    self._reset_pine_hedge_state(pos)
                    pos.hedge_last_add_price = close
            return

        if pos.sleeve != "hedge":
            return

        max_adds = int(getattr(self.cfg, "pine_hedge_max_adds", 3))
        add_interval = float(getattr(self.cfg, "pine_hedge_add_atr_interval", 1.0))
        if int(getattr(pos, "hedge_add_count", 0)) >= max_adds:
            return
        last_add_price = float(getattr(pos, "hedge_last_add_price", np.nan))
        if np.isnan(last_add_price):
            last_add_price = float(pos.entry_price)
        if close > last_add_price + float(atr) * add_interval:
            hedge_budget = float(self.equity) * float(getattr(self.cfg, "pine_hedge_add_on_pct", 0.05))
            self._fund_hedge_from_weakest_longs(
                date, hedge_budget, bar_idx, all_dates, stock_data,
                all_data=all_data, daily_price_data=daily_price_data,
            )
            self._add_position(
                hedge_ticker, date, signal_row, float(getattr(self.cfg, "pine_hedge_add_on_pct", 0.05)),
                bar_idx, "hedge", momentum=float(macd_now), all_data=all_data,
                target_weight=0.0, reason="pine_hedge_add", daily_price_data=daily_price_data,
                execution_price=execution_price,
            )
            pos = self.positions.get(hedge_ticker)
            if pos is not None and pos.sleeve == "hedge":
                pos.hedge_add_count = int(getattr(pos, "hedge_add_count", 0)) + 1
                pos.hedge_last_add_price = close


# ============================================================
# DCA Engine
# ============================================================
class DCAEngine(MomentumEngine):
    """
    DCA 引擎：週線動能輪動 + 月初定額注資 + TWR 追蹤 + Dual-gate 週內日線模擬退場。

    TWR：
      NAV = equity / nav_units
      注資只增加 units，不改變 NAV
    """



    def run(self, stock_data, hedge_data=None, spy_df=None,
            start_from: pd.Timestamp = None,
            exit_only_data: dict = None,
            vix_signals: pd.DataFrame = None,
            macro_signal: dict = None,
            macro_signals_historical: pd.Series = None,
            macro_history: pd.DataFrame = None,
            daily_stock_data: dict = None,
            dynamic_monthly_universe: dict = None,
            core_universe: list = None):

        nav_units = float(self.nav_units if self.nav_units > 0 else (self.equity if self.equity > 0 else self.cfg.initial_capital))
        total_inj = float(self.total_injected)
        prev_month = self.dca_prev_month

        exit_only_data = exit_only_data or {}
        self._daily_execution_price_data = daily_stock_data or {}
        all_data = {**stock_data, **(hedge_data or {}), **exit_only_data}
        all_dates = sorted(set().union(*(df.index for df in all_data.values())))

        if start_from is not None:
            all_dates = [d for d in all_dates if d > start_from]
            if not all_dates:
                print("No new bars to process.")
                return

        spy_regime = compute_regime_score(spy_df, self.cfg) if spy_df is not None else None
        print(
            f"Running DCA (monthly_add=${self.cfg.monthly_add:,.0f}): "
            f"{all_dates[0].date()} -> {all_dates[-1].date()}  ({len(all_dates)} bars)"
        )

        for i, date in enumerate(all_dates):
            month_key = f"{date.year:04d}-{date.month:02d}"
            dynamic_allowed = dynamic_monthly_universe.get(month_key, []) if dynamic_monthly_universe else []
            allowed_set = set(core_universe or []) | set(dynamic_allowed) if dynamic_monthly_universe else None

            curr_month = (date.year, date.month)
            if prev_month is not None and curr_month != prev_month:
                injection = float(self.cfg.monthly_add)
                nav_before = self.equity / nav_units if nav_units > 0 else 1.0
                nav_units += injection / nav_before
                self.cash += injection
                total_inj += injection
                print(
                    f"  DCA inject ${injection:,.0f} @ {date.date()}  "
                    f"total_injected=${total_inj:,.0f}  nav={nav_before:.4f}"
                )
            prev_month = curr_month

            rs = 0.5
            if spy_regime is not None and date in spy_regime.index:
                regime_row = self._completed_signal_row(spy_regime, date)
                if regime_row is not None:
                    val = regime_row["regime_score"]
                    if not pd.isna(val):
                        rs = float(val)

            self._regime_history.append(rs)
            lb = self.cfg.ew_lookback
            rv = rs - self._regime_history[-(lb + 1)] if len(self._regime_history) >= lb + 1 else 0.0
            equity_before_regime = float(self.equity)

            if macro_history is not None and not macro_history.empty:
                macro_state = compute_macro_state_at_date(macro_history, date)
            else:
                macro_state = MacroState(
                    False, False, False, False, False, False, False, True, True, True,
                    False, False, False, False,
                )
            vix_info = _lookup_vix(vix_signals, date)

            rs_lock_before = bool(self._long_entry_block_active)
            if macro_state.structural_weakness:
                self._long_entry_block_active = True
            else:
                self._long_entry_block_active = False
            rs_lock_after = bool(self._long_entry_block_active)

            # Structural bear gate: block NEW long entries.
            block_new_long_entries = bool(macro_state.structural_weakness)

            base_long_pct = float(self.cfg.target_long_total_pct)
            base_hedge_pct = 0.0
            long_pct = 0.0 if self._long_entry_block_active else base_long_pct
            rs_gate_action = "macro_block" if self._long_entry_block_active else "normal"
            after_rs_long_pct = float(long_pct)
            after_cs_long_pct = float(long_pct)
            after_vix_long_pct = float(long_pct)
            after_macro_long_pct = float(long_pct)
            after_dual_gate_long_pct = float(long_pct)
            cs_avg_mom = np.nan
            cs_dispersion = np.nan
            cs_mom_delta = np.nan
            cs_disp_delta = np.nan
            cs_scale = 1.0
            cs_stage = 0
            cs_applied = False
            contrarian_boost = bool(macro_state.extreme_fear)
            macro_action = (
                "structural_bear_block" if macro_state.structural_weakness
                else "shock_warning" if macro_state.shock_warning
                else "normal"
            )
            daily_exit_scanned = False
            daily_exit_triggered = False
            dual_gate_exit_date = ""

            for ticker in list(self.positions.keys()):
                pos = self.positions[ticker]
                if pos.sleeve != "long":
                    continue
                if ticker not in all_data or date not in all_data[ticker].index:
                    continue
                row = self._completed_signal_row(all_data[ticker], date)
                if row is None:
                    continue
                reason = self._check_exit_long(pos, row)
                if reason:
                    self._close_position(
                        ticker, date, self._get_price(ticker, date, all_data),
                        reason, i, all_dates, all_data=all_data,
                    )

            # In structural bear market, liquidate all remaining positions (all sleeves).
            if self._long_entry_block_active and self.positions:
                for ticker in list(self.positions.keys()):
                    if ticker not in all_data or date not in all_data[ticker].index:
                        continue
                    px = self._get_price(ticker, date, all_data)
                    if px <= 0:
                        continue
                    self._close_position(
                        ticker, date, px,
                        "structural_bear_liquidation", i, all_dates, all_data=all_data,
                    )

            self.equity = self._equity_at(date, all_data)
            self._run_pine_hedge_sleeve(
                date=date,
                stock_data=stock_data,
                hedge_data=hedge_data,
                vix_info=vix_info,
                bar_idx=i,
                all_dates=all_dates,
                all_data=all_data,
                daily_price_data=daily_stock_data,
            )

            hedge_value_pre_long = sum(
                p.shares * self._get_price(t, date, all_data)
                for t, p in self.positions.items()
                if p.sleeve == "hedge"
            )
            self.equity = self._equity_at(date, all_data)
            hedge_weight_pre_long = hedge_value_pre_long / self.equity if self.equity > 0 else 0.0
            long_pct = max(0.0, float(long_pct) - float(hedge_weight_pre_long))

            current_longs = {t: p for t, p in self.positions.items() if p.sleeve == "long"}
            decisions = self._build_long_target_states(
                date=date,
                stock_data=stock_data,
                total_long_pct=long_pct,
                current_positions=current_longs,
                allowed_tickers=allowed_set,
                long_block_active=self._long_entry_block_active,
                block_new_entries=block_new_long_entries,
            )

            for ticker, pos in list(self.positions.items()):
                if pos.sleeve != "long":
                    continue
                if ticker not in all_data or date not in all_data[ticker].index:
                    continue
                row = self._signal_row(all_data, ticker, date)
                if row is None:
                    continue

                decision = decisions.get(ticker)
                if decision is None:
                    continue

                tw = float(decision.final_target_weight)
                pos.target_weight = tw
                if tw <= 0.0:
                    self._close_position(
                        ticker, date, self._get_price(ticker, date, all_data),
                        decision.primary_reason, i, all_dates, all_data=all_data,
                    )
                    continue

                cw = self._current_weight(ticker, date, all_data)
                min_shares = int(getattr(self.cfg, "min_rebalance_shares", 2))
                if (
                    pos.sleeve == "long"
                    and int(pos.shares) < min_shares
                    and cw < (tw * 0.25)
                ):
                    self._close_position(
                        ticker, date, self._get_price(ticker, date, all_data),
                        "dust_position_cleanup", i, all_dates, all_data=all_data,
                    )
                    continue
                gap = tw - cw
                if gap > 1e-3:
                    self._add_position(
                        ticker, date, row, gap, i, "long",
                        momentum=self._current_signal_score(ticker, date, stock_data, fallback=decision.score),
                        all_data=all_data, target_weight=tw, reason="rebalance_add",
                        daily_price_data=daily_stock_data,
                    )
                elif gap < -1e-3:
                    self._reduce_position(
                        ticker, date, row, -gap, i, all_dates,
                        reason="rebalance_reduce", all_data=all_data, target_weight=tw,
                        daily_price_data=daily_stock_data,
                    )

            current_long_names = {t for t, p in self.positions.items() if p.sleeve == "long"}
            ranked_decisions = sorted(
                decisions.items(),
                key=lambda item: ((item[1].rank if item[1].rank is not None else 999), item[0]),
            )
            for ticker, decision in ranked_decisions:
                if decision.final_target_weight <= 0:
                    continue
                if ticker in current_long_names or ticker in exit_only_data:
                    continue
                if ticker not in stock_data or date not in stock_data[ticker].index:
                    continue
                row = self._signal_row(stock_data, ticker, date)
                if row is None:
                    continue
                mom = row.get("momentum", np.nan)
                self._add_position(
                    ticker, date, row, float(decision.final_target_weight), i, "long",
                    momentum=float(mom) if not pd.isna(mom) else float(decision.score),
                    all_data=all_data,
                    target_weight=float(decision.final_target_weight),
                    reason="entry",
                    daily_price_data=daily_stock_data,
                )
                current_long_names.add(ticker)

            long_value = sum(
                p.shares * self._get_price(t, date, all_data)
                for t, p in self.positions.items()
                if p.sleeve == "long"
            )
            hedge_value = sum(
                p.shares * self._get_price(t, date, all_data)
                for t, p in self.positions.items()
                if p.sleeve == "hedge"
            )
            total_value = long_value + hedge_value
            self.equity = self.cash + total_value

            curr_nav = self.equity / nav_units if nav_units > 0 else 1.0
            actual_long_pct_after = long_value / self.equity if self.equity > 0 else 0.0
            signal_date, execution_date, data_frequency = self._bar_metadata(stock_data, date)

            self.regime_debug.append({
                "date": date,
                "equity_before": equity_before_regime,
                "regime_score": rs,
                "regime_velocity": rv,
                "base_long_pct": base_long_pct,
                "base_hedge_pct": base_hedge_pct,
                "rs_lock_before": rs_lock_before,
                "rs_lock_after": rs_lock_after,
                "rs_gate_action": rs_gate_action,
                "after_rs_long_pct": after_rs_long_pct,
                "cs_scale": cs_scale,
                "cs_stage": cs_stage,
                "after_cs_long_pct": after_cs_long_pct,
                "cs_applied": cs_applied,
                "contrarian_boost": contrarian_boost,
                "after_vix_long_pct": after_vix_long_pct,
                "macro_action": macro_action,
                "after_macro_long_pct": after_macro_long_pct,
                "dual_gate": bool(macro_state.confirmed_deterioration),
                "daily_exit_scanned": daily_exit_scanned,
                "daily_exit_triggered": daily_exit_triggered,
                "dual_gate_exit_date": dual_gate_exit_date,
                "after_dual_gate_long_pct": after_dual_gate_long_pct,
                "final_target_long_pct": float(long_pct),
                "actual_long_pct_after": actual_long_pct_after,
                "macro_alert": bool(macro_state.macro_alert),
                "alert_vix": bool(macro_state.alert_vix),
                "alert_jpy": bool(macro_state.alert_jpy),
                "alert_usd": bool(macro_state.alert_usd),
                "alert_credit": bool(macro_state.alert_credit),
                "spy_below_20w_ma": bool(macro_state.spy_below_20w_ma),
                "extreme_fear": bool(macro_state.extreme_fear),
                "structural_weakness": bool(macro_state.structural_weakness),
                })


            long_n = sum(1 for p in self.positions.values() if p.sleeve == "long")
            hedge_n = sum(1 for p in self.positions.values() if p.sleeve == "hedge")
            self.equity_curve.append({
                "date": date,
                "equity": self.equity,
                "cash": self.cash,
                "positions": len(self.positions),
                "long_n": long_n,
                "hedge_n": hedge_n,
                "invested_pct": total_value / self.equity * 100 if self.equity > 0 else 0.0,
                "long_pct": long_value / self.equity * 100 if self.equity > 0 else 0.0,
                "hedge_pct": hedge_value / self.equity * 100 if self.equity > 0 else 0.0,
                "regime_score": rs,
                "regime_velocity": rv,
                "early_warning": bool(macro_state.shock_warning),
                "cs_avg_mom": cs_avg_mom,
                "cs_dispersion": cs_dispersion,
                "cs_mom_delta": cs_mom_delta,
                "cs_disp_delta": cs_disp_delta,
                "cs_stage": cs_stage,
                "nav": round(curr_nav, 6),
                "nav_units": round(nav_units, 4),
                "total_injected": round(total_inj, 2),
                "signal_date": signal_date,
                "execution_date": execution_date,
                "data_frequency": data_frequency,
            })

        print(f"Done: {len(self.trades)} trades closed, {len(self.positions)} open.  Total injected: ${total_inj:,.0f}")
        self.nav_units = float(nav_units)
        self.total_injected = float(total_inj)
        self.dca_prev_month = prev_month

    def save_outputs(self, state_mgr: StateManager, is_incremental: bool, output_dir: str = "."):
        if not self.equity_curve:
            print("沒有任何 bar 被處理，略過輸出。")
            return

        last_date = self.equity_curve[-1]["date"]

        state_mgr.save(
            cash=self.cash, equity=self.equity, positions=self.positions,
            last_processed_date=last_date, initial_capital=self.cfg.initial_capital,
            nav_units=self.nav_units,
            total_injected=self.total_injected,
            dca_prev_month=self.dca_prev_month,
            long_entry_block_active=self._long_entry_block_active,
        )

        if self.equity_curve:
            new_df = pd.DataFrame(self.equity_curve)[_DCA_EQUITY_COLS]
            equity_path = os.path.join(output_dir, self.cfg.equity_csv)
            if is_incremental and os.path.exists(equity_path):
                existing = pd.read_csv(equity_path, parse_dates=["date"])
                if list(existing.columns) != _DCA_EQUITY_COLS:
                    for col in _DCA_EQUITY_COLS:
                        if col not in existing.columns:
                            existing[col] = ""
                    combined = pd.concat([existing[_DCA_EQUITY_COLS], new_df], ignore_index=True)
                    combined["_d"] = combined["date"].astype(str)
                    combined = combined.drop_duplicates("_d", keep="last").drop(columns=["_d"])
                    combined.to_csv(equity_path, index=False)
                    print(f"equity_curve: schema upgraded and written {len(combined)} rows → {equity_path}")
                else:
                    existing_dates = set(existing["date"].astype(str))
                    new_df["_d"] = new_df["date"].astype(str)
                    new_df = new_df[~new_df["_d"].isin(existing_dates)].drop(columns=["_d"])
                    if len(new_df):
                        new_df.to_csv(equity_path, mode="a", index=False, header=False)
                        print(f"equity_curve: appended {len(new_df)} rows → {equity_path}")
            else:
                new_df.to_csv(equity_path, index=False)
                print(f"equity_curve: written {len(new_df)} rows → {equity_path}")

        save_trades(self.trades, os.path.join(output_dir, self.cfg.trades_csv), is_incremental)
        save_executions(self.executions, os.path.join(output_dir, self.cfg.executions_csv), is_incremental)
        if self.regime_debug:
            debug_df = pd.DataFrame(self.regime_debug)[_REGIME_DEBUG_COLS]
            debug_path = os.path.join(output_dir, self.cfg.regime_debug_csv)
            if is_incremental and os.path.exists(debug_path):
                existing = pd.read_csv(debug_path, parse_dates=["date"])
                existing_dates = set(existing["date"].astype(str))
                debug_df["_d"] = debug_df["date"].astype(str)
                debug_df = debug_df[~debug_df["_d"].isin(existing_dates)].drop(columns=["_d"])
                if len(debug_df):
                    debug_df.to_csv(debug_path, mode="a", index=False, header=False)
                    print(f"regime_debug: appended {len(debug_df)} rows → {debug_path}")
            else:
                debug_df.to_csv(debug_path, index=False)
                print(f"regime_debug: written {len(debug_df)} rows → {debug_path}")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    cli_args = parse_cli_args()
    cfg = DCAConfig(monthly_add=cli_args.monthly_add)
    cfg.momentum_model = resolve_momentum_model(cli_args.model)
    cfg.price_cache_local_only = not bool(cli_args.allow_network)
    configure_yfinance_cache(cfg.cache_dir)
    print(f"DCA Config: start={cfg.start_date}, end={cfg.end_date}, "
          f"initial=${cfg.initial_capital:,.0f}, monthly_add=${cfg.monthly_add:,.0f}")
    print(
        f"CLI options: model={cfg.momentum_model}, run_mode={cli_args.run_mode}, "
        f"refresh_web_data={cli_args.refresh_web_data}, allow_network={cli_args.allow_network}"
    )
    # 使用年度快照 RAW_SNAPSHOTS 取代固定 Config.universe
    _yearly_snapshots = _build_yearly_snapshots()
    _all_snapshot_tickers = []
    _seen = set()
    for _, _tickers in _yearly_snapshots:
        for _t in _tickers:
            if _t in _seen:
                continue
            _seen.add(_t)
            _all_snapshot_tickers.append(_t)
    cfg.universe = list(_all_snapshot_tickers)
    core_universe = []  # 動態年度池，無固定核心
    print(f"Annual rotation pool: {len(cfg.universe)} unique tickers across {len(_yearly_snapshots)} yearly snapshots")

    state_mgr = StateManager(path=cfg.output_dir, filename=cfg.state_file)
    state = state_mgr.load()

    if cli_args.run_mode == "full":
        state = {}
    elif cli_args.run_mode == "incremental" and not state:
        raise RuntimeError("Incremental mode requested but no saved state file was found.")

    is_incr = bool(state)

    if is_incr:
        open_positions = state_mgr.restore_positions(state)
        saved_cash     = float(state.get("cash", cfg.initial_capital))
        last_run_date  = pd.Timestamp(state["last_processed_date"])
        fetch_start    = (last_run_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"增量模式: last={last_run_date.date()}, fetch_start={fetch_start}")
    else:
        open_positions = {}
        saved_cash     = None
        last_run_date  = None
        fetch_start    = None
        print("全量回測模式")

    if fetch_start is not None:
        dyn_start = pd.Timestamp(fetch_start).to_period("M").to_timestamp().strftime("%Y-%m-%d")
    else:
        dyn_start = cfg.start_date
    dynamic_monthly_map = _build_monthly_universe_from_snapshots(
        _yearly_snapshots, dyn_start, cfg.end_date,
    )
    cfg.universe = list(_all_snapshot_tickers)
    print(f"Universe: {len(cfg.universe)} tickers (annual rotation, monthly map built {dyn_start} → {cfg.end_date})")

    extra_tickers = [t for t in open_positions if t not in set(cfg.universe)]
    cache_seed_tickers = _dedupe_keep_order(
        cfg.universe + cfg.hedge_universe + extra_tickers + ["SPY"]
    )
    prefetch_start = fetch_start if fetch_start is not None else cfg.start_date
    prefetch_pool_prices(
        cfg,
        tickers=cache_seed_tickers,
        start=prefetch_start,
        end=cfg.end_date,
        include_daily=bool(cfg.price_cache_prefetch_daily),
    )

    engine = DCAEngine(cfg, initial_positions=open_positions, initial_cash=saved_cash)
    if is_incr:
        resume_twr = load_resume_twr_state(cfg.output_dir, cfg.equity_csv, state)
        saved_nav_units = resume_twr.get("nav_units", None)
        saved_total_injected = resume_twr.get("total_injected", None)
        engine.nav_units = float(saved_nav_units) if saved_nav_units not in (None, "", 0, 0.0) else float(
            engine.equity if engine.equity > 0 else cfg.initial_capital
        )
        engine.total_injected = float(saved_total_injected) if saved_total_injected not in (None, "") else 0.0
        engine.dca_prev_month = resume_twr.get("dca_prev_month", None) or f"{last_run_date.year:04d}-{last_run_date.month:02d}"
        engine._long_entry_block_active = bool(state.get("long_entry_block_active", False))

    stock_data, _hedge_data, exit_only_data = engine.fetch_data(
        fetch_start=fetch_start, extra_tickers=extra_tickers,
    )

    if fetch_start is not None:
        spy_dl_start = (pd.Timestamp(fetch_start) - timedelta(days=cfg.min_bars * 7)).strftime("%Y-%m-%d")
    else:
        spy_dl_start = cfg.start_date

    spy = load_price_data(
        cfg, ticker="SPY", start=spy_dl_start, end=cfg.end_date,
        interval="1d" if _is_sampled_daily_timeframe(cfg.timeframe) else cfg.timeframe,
        allow_network=not cfg.price_cache_local_only
    )
    if _is_sampled_daily_timeframe(cfg.timeframe):
        spy = build_sampled_daily_bars(
            spy, start=spy_dl_start, end=cfg.end_date,
            decision_weekday=cfg.decision_weekday,
        )
    if len(spy) == 0:
        raise RuntimeError("SPY 資料不可用：請先完成本地價格快取後再執行。")

    print("Fetching VIX signals...")
    vix_signals = fetch_vix_signals(spy_dl_start, cfg.end_date, cfg)

    print("Fetching macro history for dual-gate backtest...")
    macro_hist_df = build_macro_history(spy_dl_start, cfg.end_date, cfg=cfg)
    print(f"Macro history: {len(macro_hist_df)} rows, {list(macro_hist_df.columns)}")

    if is_incr:
        macro_signal      = fetch_macro_signal()
        macro_signals_hist = None
    else:
        macro_signal      = None
        macro_signals_hist = load_historical_macro_signals()
        if not macro_signals_hist.empty:
            print(f"Historical macro signals: {len(macro_signals_hist)} entries")

    # ── 日線資料：用於 dual-gate 週內最早觸發日模擬出場 ────────────────────
    _use_daily_exit_sim = len(cfg.universe) <= 120
    daily_stock_data = {}
    if _use_daily_exit_sim:
        print("Downloading daily data for dual-gate intra-week simulation...")
        for _t in list(set(cfg.universe)):
            try:
                _df_d = load_price_data(
                    cfg, ticker=_t, start=spy_dl_start, end=cfg.end_date,
                    interval="1d", allow_network=not cfg.price_cache_local_only
                )
                if len(_df_d) > 0:
                    daily_stock_data[_t] = _df_d
            except Exception:
                pass
        print(f"Daily data loaded: {len(daily_stock_data)} tickers")
    else:
        print(f"Daily dual-gate simulation skipped (universe too large: {len(cfg.universe)})")

    engine.run(stock_data, hedge_data=_hedge_data, spy_df=spy,
               start_from=last_run_date, exit_only_data=exit_only_data,
               vix_signals=vix_signals, macro_signal=macro_signal,
               macro_signals_historical=macro_signals_hist,
               macro_history=macro_hist_df,
               daily_stock_data=daily_stock_data if _use_daily_exit_sim else None,
               dynamic_monthly_universe=dynamic_monthly_map,
               core_universe=core_universe)

    # Final macro snapshot for visibility after the run.
    try:
        _ms = compute_macro_state(cfg=cfg)
        print(f"Final macro snapshot: {_ms} | long_block_active={engine._long_entry_block_active}")
    except Exception as _e:
        print(f"[macro snapshot] skipped: {_e}")

    engine.save_outputs(state_mgr, is_incremental=is_incr, output_dir=cfg.output_dir)
    if cli_args.refresh_web_data:
        refresh_web_data()
