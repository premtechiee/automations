"""
stock_analyzer/indicators.py
=============================
Pure-python / pandas technical indicators — no TA-Lib dependency.
All functions take a pandas DataFrame with columns: Open/High/Low/Close/Volume.
"""

from __future__ import annotations
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line   = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist        = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat(
        [(high - low),
         (high - close.shift()).abs(),
         (low  - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(close: pd.Series, period: int = 20, mult: float = 2.0):
    mid = close.rolling(period).mean()
    sd  = close.rolling(period).std()
    return mid - mult * sd, mid, mid + mult * sd


def summarise_technicals(df: pd.DataFrame) -> dict:
    """Return a dict of last-bar indicator values + momentum ratios."""
    close = df["Close"]
    vol   = df["Volume"]
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema200 = ema(close, 200) if len(close) >= 200 else pd.Series([close.mean()] * len(close), index=close.index)
    rsi14 = rsi(close, 14)
    macd_l, sig_l, hist_l = macd(close)
    atr14 = atr(df, 14)
    bb_lo, bb_mid, bb_hi = bollinger(close)

    last = -1
    cp  = float(close.iloc[last])
    chg_1d = (cp / float(close.iloc[-2]) - 1) * 100 if len(close) > 1 else 0.0
    chg_5d = (cp / float(close.iloc[-6]) - 1) * 100 if len(close) > 5 else 0.0
    chg_1m = (cp / float(close.iloc[-22]) - 1) * 100 if len(close) > 22 else 0.0
    chg_3m = (cp / float(close.iloc[-66]) - 1) * 100 if len(close) > 66 else 0.0

    avg_vol_20 = float(vol.tail(20).mean()) if len(vol) >= 20 else float(vol.mean())
    vol_ratio  = (float(vol.iloc[last]) / avg_vol_20) if avg_vol_20 else 1.0

    return {
        "price":      cp,
        "chg_1d_pct": chg_1d,
        "chg_5d_pct": chg_5d,
        "chg_1m_pct": chg_1m,
        "chg_3m_pct": chg_3m,
        "ema20":      float(ema20.iloc[last]),
        "ema50":      float(ema50.iloc[last]),
        "ema200":     float(ema200.iloc[last]),
        "rsi14":      float(rsi14.iloc[last]),
        "macd":       float(macd_l.iloc[last]),
        "macd_sig":   float(sig_l.iloc[last]),
        "macd_hist":  float(hist_l.iloc[last]),
        "atr14":      float(atr14.iloc[last]),
        "atr_pct":    float(atr14.iloc[last]) / cp * 100 if cp else 0.0,
        "bb_low":     float(bb_lo.iloc[last])  if not pd.isna(bb_lo.iloc[last])  else cp,
        "bb_high":    float(bb_hi.iloc[last])  if not pd.isna(bb_hi.iloc[last])  else cp,
        "vol_ratio":  vol_ratio,
        "trend_up":   cp > float(ema50.iloc[last]) > float(ema200.iloc[last]),
    }
