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
    Pull last-close prices for key global markers directly from Yahoo's
    chart endpoint (no yfinance dependency, hard requests timeouts).
    Returns dict of percentage moves + a 'regime' field. Non-fatal.
    """
    from .fetchers import _fetch_history_yahoo  # reuse hardened HTTP path

    tickers = {
        # ── Global / overnight cues ────────────────────────────────
        "SPY":  "SPY",         # S&P 500 ETF
        "QQQ":  "QQQ",         # Nasdaq 100 ETF
        "DJI":  "^DJI",        # Dow Jones
        "VIX":  "^VIX",        # CBOE volatility (US fear gauge)
        "OIL":  "CL=F",        # WTI crude futures
        "DXY":  "DX-Y.NYB",    # Dollar index
        "GOLD": "GC=F",        # Gold futures
        "INR":  "INR=X",       # USD-INR
        # ── Indian benchmark + broad-market indices ───────────────
        "NIFTY":      "^NSEI",       # Nifty 50
        "NIFTY_NEXT50": "^NSMIDCP",  # Nifty Next 50 fallback proxy
        "NIFTY100":   "^CNX100",     # Nifty 100
        "NIFTY200":   "^CNX200",     # Nifty 200
        "NIFTY500":   "^CRSLDX",     # Nifty 500
        "NIFTY_MIDCAP": "NIFTY_MIDCAP_100.NS",
        "NIFTY_SMALLCAP": "^CNXSC",
        "BANKNIFTY":  "^NSEBANK",    # Bank Nifty
        "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
        "NIFTY_IT":   "^CNXIT",
        "NIFTY_AUTO": "^CNXAUTO",
        "NIFTY_PHARMA": "^CNXPHARMA",
        "NIFTY_FMCG": "^CNXFMCG",
        "NIFTY_ENERGY": "^CNXENERGY",
        "NIFTY_METAL": "^CNXMETAL",
        "NIFTY_REALTY": "^CNXREALTY",
        "NIFTY_PSU_BANK": "^CNXPSUBANK",
        "INDIA_VIX":  "^INDIAVIX",   # Indian fear gauge
        "SENSEX":     "^BSESN",      # BSE Sensex
        "BSE500":     "BSE-500.BO",
    }

    snap: dict[str, Any] = {}
    for key, tkr in tickers.items():
        try:
            hist = _fetch_history_yahoo(tkr, "1mo", "1d")
            if hist is None or hist.empty:
                continue
            close = hist["Close"]
            snap[key] = {
                "last":     round(float(close.iloc[-1]), 2),
                "chg_pct":  round(_pct_move(close) or 0.0, 2),
            }
        except Exception as exc:
            logger.debug(f"macro fetch failed {key}: {exc}")

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

    # ── NSE FII/DII institutional flows + index PCR (free, no account) ─────
    flows: dict[str, Any] = {"available": False}
    pcr_idx: dict[str, Any] = {}
    try:
        from .nse import fetch_fii_dii, fetch_index_option_chain
        flows = fetch_fii_dii() or {"available": False}
        pcr_idx = {
            "NIFTY":     fetch_index_option_chain("NIFTY"),
            "BANKNIFTY": fetch_index_option_chain("BANKNIFTY"),
        }
        # strip empty entries so renderers can len()-check easily
        pcr_idx = {k: v for k, v in pcr_idx.items() if v}
    except Exception as exc:
        logger.debug(f"NSE flows/PCR fetch skipped: {exc}")

    if flows.get("available"):
        fn = float(flows.get("fii_net") or 0)
        dn = float(flows.get("dii_net") or 0)
        if fn >= 1500:
            bias += 2
            reasons.append(f"FII bought ₹{fn:,.0f}cr — strong institutional buying")
        elif fn >= 500:
            bias += 1
            reasons.append(f"FII net buyers (+₹{fn:,.0f}cr)")
        elif fn <= -1500:
            bias -= 2
            reasons.append(f"FII sold ₹{abs(fn):,.0f}cr — heavy outflow")
        elif fn <= -500:
            bias -= 1
            reasons.append(f"FII net sellers (₹{fn:,.0f}cr)")
        if dn >= 1500:
            bias += 1
            reasons.append(f"DII absorbing supply (+₹{dn:,.0f}cr)")
        elif dn <= -1500:
            bias -= 1
            reasons.append(f"DII also exiting (₹{dn:,.0f}cr)")

    # Index PCR overlay — heavy put-writing = bullish, heavy call-writing = bearish.
    nifty_pcr = (pcr_idx.get("NIFTY") or {}).get("pcr")
    if nifty_pcr is not None:
        if nifty_pcr >= 1.30:
            bias += 1; reasons.append(f"Nifty PCR {nifty_pcr:.2f} — option writers bullish")
        elif nifty_pcr <= 0.70:
            bias -= 1; reasons.append(f"Nifty PCR {nifty_pcr:.2f} — option writers bearish")

    return {
        "snapshot":   snap,
        "geo":        geo,
        "bias":       bias,       # integer typically -7..+7 now
        "regime":     regime,
        "reasons":    reasons,
        "flows":      flows,         # FII/DII institutional activity
        "pcr_index":  pcr_idx,       # index option-chain bias
        "opening":    _predict_india_open(snap, geo, bias),
    }


# ── Pre-open prediction for Indian market (from US overnight + Asian futures) ──

def _predict_india_open(snap: dict, geo: dict, bias: int) -> dict[str, Any]:
    """
    Predict Nifty's opening gap direction using overnight US close + Asian cues.
    Runs at 08:00 IST (market opens 09:15).
    """
    spy = (snap.get("SPY")  or {}).get("chg_pct", 0) or 0
    qqq = (snap.get("QQQ")  or {}).get("chg_pct", 0) or 0
    dji = (snap.get("DJI")  or {}).get("chg_pct", 0) or 0
    vix = (snap.get("VIX")  or {}).get("last")
    nif = (snap.get("NIFTY") or {}).get("chg_pct", 0) or 0

    us_avg = (spy + qqq + dji) / 3.0
    score  = 0
    notes: list[str] = []

    if us_avg >= 1.0:
        score += 2; notes.append(f"US closed strong (avg {us_avg:+.1f}%)")
    elif us_avg >= 0.3:
        score += 1; notes.append(f"US closed firm ({us_avg:+.1f}%)")
    elif us_avg <= -1.0:
        score -= 2; notes.append(f"US closed weak ({us_avg:+.1f}%)")
    elif us_avg <= -0.3:
        score -= 1; notes.append(f"US closed soft ({us_avg:+.1f}%)")

    if vix is not None:
        if vix >= 25:
            score -= 1; notes.append(f"VIX elevated ({vix:.0f}) — risk-off tone")
        elif vix < 15:
            score += 1; notes.append(f"VIX calm ({vix:.0f}) — risk-on tone")

    # Geopolitics / war overlay
    lvl = geo.get("level", 50)
    if lvl >= 65:
        score -= 2; notes.append("Geopolitical stress flagged in overnight news")
    elif lvl <= 35:
        score += 1; notes.append("Geopolitical mood improving overnight")

    # Gap size expectation (rough % of Nifty previous close)
    if score >= 3:
        direction, gap_pct = "GAP-UP", "+0.6% to +1.2%"
    elif score == 2:
        direction, gap_pct = "MILD GAP-UP", "+0.2% to +0.6%"
    elif score <= -3:
        direction, gap_pct = "GAP-DOWN", "−0.6% to −1.2%"
    elif score == -2:
        direction, gap_pct = "MILD GAP-DOWN", "−0.2% to −0.6%"
    else:
        direction, gap_pct = "FLAT OPEN", "±0.2%"

    # Confidence rises with magnitude of overlap between US & geo cues
    confidence = min(90, 50 + abs(score) * 10)

    return {
        "direction":    direction,
        "gap_pct":      gap_pct,
        "confidence":   confidence,
        "us_avg_pct":   round(us_avg, 2),
        "nifty_prev":   round(nif, 2),
        "vix":          vix,
        "notes":        notes,
    }
