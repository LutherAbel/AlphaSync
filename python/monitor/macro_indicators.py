"""
macro_indicators.py — Dual-Gate Exit System: Macro Indicator Module
====================================================================
Computes MacroState from live yfinance data (previous day's close).

Usage:
    from macro_indicators import compute_macro_state
    ms = compute_macro_state()
    if ms.dual_gate:
        ...
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Lookback in calendar days — enough for 20w MA + 12w ROC
_LOOKBACK_DAYS = 210


@dataclass
class MacroState:
    # Gate 1 components
    alert_vix:    bool   # VIX > VIX3M
    alert_jpy:    bool   # FXY 4-week ROC > 4.0%
    alert_usd:    bool   # UUP 4-week ROC > 3.0%
    alert_credit: bool   # (HYG/IEF) 12-week ROC < -5.0%
    macro_alert:  bool   # any of the above

    # Gate 2
    spy_below_20w_ma: bool  # SPY close < 20-week SMA

    # Combined trigger
    dual_gate: bool      # macro_alert AND spy_below_20w_ma

    # Unlock conditions
    vix_clear: bool      # VIX < VIX3M
    usd_clear: bool      # UUP 4-week ROC < 0
    all_clear: bool      # vix_clear AND usd_clear

    def __str__(self) -> str:
        flags = []
        if self.alert_vix:    flags.append("VIX_INVERT")
        if self.alert_jpy:    flags.append("JPY_UNWIND")
        if self.alert_usd:    flags.append("USD_SQUEEZE")
        if self.alert_credit: flags.append("CREDIT_SPREAD")
        gate2 = "SPY<20wMA" if self.spy_below_20w_ma else "SPY_OK"
        status = "DUAL_GATE" if self.dual_gate else ("ALL_CLEAR" if self.all_clear else "WATCH")
        return f"MacroState({status} | alerts={flags} | {gate2})"


def roc_weekly(series: pd.Series, weeks: int) -> float:
    """N-week rate-of-change (%) using weekly resampled closes (W-FRI).

    Accepts any-frequency DatetimeIndex Series; resamples to W-FRI internally.
    """
    weekly = series.resample("W-FRI").last().dropna()
    if len(weekly) < weeks + 1:
        return 0.0
    return float(weekly.iloc[-1] / weekly.iloc[-(weeks + 1)] - 1) * 100.0


def _20w_sma(series: pd.Series) -> float:
    """20-week SMA of weekly resampled closes."""
    weekly = series.resample("W-FRI").last().dropna()
    if len(weekly) < 20:
        print(f"[macro_indicators] WARNING: only {len(weekly)} weekly bars for 20w SMA, using available mean")
        return float(weekly.mean()) if len(weekly) > 0 else 0.0
    return float(weekly.tail(20).mean())


def _download(tickers: list[str], days: int) -> pd.DataFrame:
    """Download daily closes for tickers; handle MultiIndex columns."""
    start = (pd.Timestamp.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    raw = yf.download(tickers, start=start, progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw["Close"]
    else:
        try:
            raw = raw[["Close"]]
        except KeyError:
            raise KeyError(f"yfinance did not return 'Close' column for {tickers}. Columns: {list(raw.columns)}")
        raw.columns = tickers[:1]
    return raw.ffill()


_JPY_ROC_ALERT    = 4.0   # FXY 4w ROC threshold (%)
_USD_ROC_ALERT    = 3.0   # UUP 4w ROC threshold (%)
_CREDIT_ROC_ALERT = -5.0  # (HYG/IEF) 12w ROC threshold (%)


def compute_macro_state_from_prices(
    vix: float,
    vix3m: float,
    fxy_weekly: pd.Series,
    uup_weekly: pd.Series,
    credit_weekly: pd.Series,
    spy_weekly: pd.Series,
) -> MacroState:
    """Pure-function core — accepts pre-built series. Testable without network."""
    uup_4w_roc   = roc_weekly(uup_weekly, 4)
    alert_vix    = vix > vix3m
    alert_jpy    = roc_weekly(fxy_weekly, 4) > _JPY_ROC_ALERT
    alert_usd    = uup_4w_roc > _USD_ROC_ALERT
    alert_credit = roc_weekly(credit_weekly, 12) < _CREDIT_ROC_ALERT
    macro_alert  = alert_vix or alert_jpy or alert_usd or alert_credit

    spy_sma20w       = _20w_sma(spy_weekly)
    spy_last         = float(spy_weekly.dropna().iloc[-1])
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


def compute_macro_state() -> MacroState:
    """Live version — downloads all required data from yfinance."""
    # Scalar VIX values (last close)
    vix_df  = _download(["^VIX"],  days=10)
    vix3m_df = _download(["^VIX3M"], days=10)
    vix   = float(vix_df.dropna().iloc[-1].iloc[0])
    vix3m = float(vix3m_df.dropna().iloc[-1].iloc[0])

    # Series for ROC / MA calculations
    multi = _download(["FXY", "UUP", "HYG", "IEF", "SPY"], days=_LOOKBACK_DAYS)
    fxy   = multi["FXY"]
    uup   = multi["UUP"]
    credit = multi["HYG"] / multi["IEF"]
    spy   = multi["SPY"]

    return compute_macro_state_from_prices(
        vix=vix, vix3m=vix3m,
        fxy_weekly=fxy, uup_weekly=uup,
        credit_weekly=credit, spy_weekly=spy,
    )


def build_macro_history(start_date: str, end_date: str) -> pd.DataFrame:
    """Download all macro indicator tickers for historical backtest.

    Returns a daily-indexed DataFrame with columns:
    VIX, VIX3M, FXY, UUP, HYG, IEF, SPY
    with _LOOKBACK_DAYS extra data prepended before start_date.
    """
    dl_start = (pd.Timestamp(start_date) - pd.Timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    tickers = ["^VIX", "^VIX3M", "FXY", "UUP", "HYG", "IEF", "SPY"]
    raw = yf.download(tickers, start=dl_start, end=end_date, progress=False, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw["Close"].copy()
    else:
        df = raw.copy()
    df = df.rename(columns={"^VIX": "VIX", "^VIX3M": "VIX3M"})
    return df.ffill()


def compute_macro_state_at_date(macro_df: pd.DataFrame, date: pd.Timestamp) -> MacroState:
    """Compute MacroState using historical data ending at date (lookback window)."""
    _all_clear = MacroState(False, False, False, False, False, False, False, True, True, True)
    window_start = date - pd.Timedelta(days=_LOOKBACK_DAYS)
    window = macro_df.loc[window_start:date]
    if window.empty or len(window) < 10:
        return _all_clear

    def _col(name: str) -> pd.Series:
        return window[name].dropna() if name in window.columns else pd.Series(dtype=float)

    vix_s   = _col("VIX");  vix3m_s = _col("VIX3M")
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


if __name__ == "__main__":
    ms = compute_macro_state()
    print(ms)
    print(f"  VIX alerts: vix={ms.alert_vix}, jpy={ms.alert_jpy}, usd={ms.alert_usd}, credit={ms.alert_credit}")
    print(f"  Unlock:     vix_clear={ms.vix_clear}, usd_clear={ms.usd_clear}, all_clear={ms.all_clear}")
