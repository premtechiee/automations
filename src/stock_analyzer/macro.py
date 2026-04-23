"""
stock_analyzer/macro.py
========================
Global & macro context: US market overnight, VIX fear gauge, crude oil, US dollar,
gold, and geopolitical/war headline risk. Produces a "macro bias" applied to every
per-stock prediction so forecasts reflect the prevailing world regime.

No paid APIs. Uses yfinance for index/commodity snapshots and existing RSS feed list
for news scanning.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Risk / geopolitical keyword banks ───────────────────────────────────────

RISK_OFF_WORDS = {
    # War & conflict
    "war", "invasion", "attack", "strike", "missile", "drone",
    "ceasefire", "escalation", "conflict", "hostilities", "airstrike",
    # Terror / geopolitics
    "terror", "sanctions", "embargo", "coup", "protest", "riot",
    # Macro shocks
    "recession", "slowdown", "inflation", "hike", "default", "crisis",
    "downgrade", "crash", "plunge", "sell-off", "tariff", "trade-war",
    "shutdown", "layoffs", "bankruptcy", "fraud", "ban",
    # Oil & supply
    "opec+", "oil-surge", "supply-shock",
    # Pandemic / disaster
    "pandemic", "outbreak", "earthquake", "cyclone", "flood",
}

RISK_ON_WORDS = {
    "peace", "truce", "ceasefire-deal", "de-escalation", "dovish",
    "rate-cut", "cut-rates", "easing", "stimulus", "deal", "agreement",
    "upgrade", "surge", "rally", "record", "bullish", "boom",
    "accord", "resolution", "recovery", "rebound",
}


# Global RSS feeds layered on top of Indian ones (added into config dynamically).
GLOBAL_RSS_FEEDS: list[str] = [
    # US / global markets
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/reuters/worldNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",     # top news
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",      # world
    # Geopolitics / war
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]


# ── US market / VIX / commodity snapshots via yfinance ──────────────────────

def _pct_move(series) -> float | None:
    if series is None or len(series) < 2:
        return None
    try:
        last = float(series.iloc[-1])
        prev = float(series.iloc[-2])
        if prev == 0:
            return None
        return (last / prev - 1) * 100
    except Exception:
        return None


def fetch_macro_snapshot() -> dict[str, Any]:
    """
    Pull last-close prices for key global markers via yfinance.
    Returns dict of percentage moves + a 'regime' field: risk-on / risk-off / neutral.
    Non-fatal — returns {} on network failure.
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        logger.debug("yfinance unavailable for macro snapshot.")
        return {}

    tickers = {
        "SPY":  "SPY",         # S&P 500 ETF
        "QQQ":  "QQQ",         # Nasdaq 100 ETF
        "DJI":  "^DJI",        # Dow Jones
        "VIX":  "^VIX",        # CBOE volatility
        "OIL":  "CL=F",        # WTI crude futures
        "DXY":  "DX-Y.NYB",    # Dollar index
        "GOLD": "GC=F",        # Gold futures
        "NIFTY": "^NSEI",      # Indian benchmark
    }

    snap: dict[str, Any] = {}
    for key, tkr in tickers.items():
        try:
            hist = yf.Ticker(tkr).history(period="5d", interval="1d", auto_adjust=False)
            if hist.empty:
                continue
            close = hist["Close"]
            snap[key] = {
                "last":     round(float(close.iloc[-1]), 2),
                "chg_pct":  round(_pct_move(close) or 0.0, 2),
            }
        except Exception as exc:
            logger.debug(f"macro fetch failed {key}: {exc}")

    # Compute a regime classification from VIX + US indices
    snap["regime"] = _classify_regime(snap)
    return snap


def _classify_regime(snap: dict) -> str:
    vix = (snap.get("VIX") or {}).get("last")
    spy = (snap.get("SPY") or {}).get("chg_pct")
    dji = (snap.get("DJI") or {}).get("chg_pct")
    if vix is None and spy is None:
        return "neutral"
    vix = vix or 0
    us_move = ((spy or 0) + (dji or 0)) / 2

    if vix >= 25 or us_move <= -1.0:
        return "risk-off"
    if vix < 18 and us_move >= 0.4:
        return "risk-on"
    return "neutral"


# ── Geopolitical / headline risk scanner ────────────────────────────────────

def score_geopolitical_risk(headlines: list[str]) -> dict[str, Any]:
    """
    Tokenise headlines and count hits against risk-off and risk-on banks.
    Returns {level, risk_off_hits, risk_on_hits, samples[]}.
    level = 0..100, 50 = neutral, higher = more risk-off.
    """
    off_hits = on_hits = 0
    off_samples: list[str] = []
    on_samples:  list[str] = []

    def _tokens(h: str) -> set[str]:
        return {w.strip(".,:;!?\"'()[]").lower().replace(" ", "-")
                for w in h.split()}

    for h in headlines:
        toks = _tokens(h)
        if toks & RISK_OFF_WORDS:
            off_hits += 1
            if len(off_samples) < 4:
                off_samples.append(h)
        if toks & RISK_ON_WORDS:
            on_hits += 1
            if len(on_samples) < 4:
                on_samples.append(h)

    total = off_hits + on_hits
    if total == 0:
        level = 50.0
    else:
        # More off → pushes 50 → 100; more on → pushes 50 → 0.
        level = 50 + (off_hits - on_hits) / total * 50

    return {
        "level":          round(level, 1),
        "risk_off_hits":  off_hits,
        "risk_on_hits":   on_hits,
        "off_samples":    off_samples,
        "on_samples":     on_samples,
    }


# ── Combine into a single macro context ─────────────────────────────────────

def build_macro_context(headlines: list[str]) -> dict[str, Any]:
    snap = fetch_macro_snapshot()
    geo  = score_geopolitical_risk(headlines)

    regime = snap.get("regime", "neutral")
    # Bias: positive shifts predictions upward, negative downward.
    bias = 0
    reasons: list[str] = []

    if regime == "risk-on":
        bias += 2; reasons.append("Global markets risk-on (US indices up, volatility low)")
    elif regime == "risk-off":
        bias -= 3; reasons.append("Global markets risk-off (US down or VIX elevated)")

    spy = (snap.get("SPY") or {}).get("chg_pct", 0) or 0
    if spy >= 1.0:
        bias += 1; reasons.append(f"S&P 500 closed strong ({spy:+.1f}%) — positive cue")
    elif spy <= -1.0:
        bias -= 1; reasons.append(f"S&P 500 closed weak ({spy:+.1f}%) — negative cue")

    vix = (snap.get("VIX") or {}).get("last")
    if vix is not None:
        if vix >= 25:
            bias -= 1; reasons.append(f"Fear gauge (VIX {vix:.0f}) elevated — caution")
        elif vix < 15:
            bias += 1; reasons.append(f"Fear gauge (VIX {vix:.0f}) calm — supportive")

    oil = (snap.get("OIL") or {}).get("chg_pct", 0) or 0
    if oil >= 3:
        bias -= 1; reasons.append(f"Crude spiked {oil:+.1f}% — inflation risk")
    elif oil <= -3:
        bias += 1; reasons.append(f"Crude fell {oil:+.1f}% — inflation relief")

    dxy = (snap.get("DXY") or {}).get("chg_pct", 0) or 0
    if dxy >= 0.6:
        bias -= 1; reasons.append(f"Dollar strengthening ({dxy:+.1f}%) — headwind for EMs")
    elif dxy <= -0.6:
        bias += 1; reasons.append(f"Dollar weakening ({dxy:+.1f}%) — tailwind for EMs")

    # Geopolitical / war
    if geo["level"] >= 65:
        bias -= 2
        samp = geo["off_samples"][0] if geo["off_samples"] else "war/geopolitical stress"
        reasons.append(f"Geopolitical risk high: “{samp[:90]}”")
    elif geo["level"] <= 35:
        bias += 1
        samp = geo["on_samples"][0] if geo["on_samples"] else "de-escalation signals"
        reasons.append(f"Geopolitical mood positive: “{samp[:90]}”")

    return {
        "snapshot":   snap,
        "geo":        geo,
        "bias":       bias,       # integer typically -5..+5
        "regime":     regime,
        "reasons":    reasons,
    }
