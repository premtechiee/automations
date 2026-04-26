"""
stock_analyzer/recommender.py
==============================
Combine fundamentals + technicals + sentiment per stock, then bucket
into intraday / swing / long-term-holding / avoid-or-sell lists.

Scoring rubric
--------------
Each bucket gets its own tailored score so a "good long-term stock"
is not forced to also look good for intraday trading.
"""

from __future__ import annotations
import logging
import os
from typing import Any

from .config import (
    WEIGHT_FUNDAMENTAL, WEIGHT_TECHNICAL, WEIGHT_SENTIMENT,
    TOP_INTRADAY, TOP_SWING, TOP_HOLDING, TOP_SELL, TOP_MF,
)
from .indicators    import summarise_technicals
from .patterns      import detect_candles, find_support_resistance, predict_direction
from .fundamentals  import score_fundamentals
from .sentiment     import score_headlines_for
from .fetchers      import ticker_to_keyword

logger = logging.getLogger(__name__)


# ── Per-stock enrichment ────────────────────────────────────────────────────

def enrich_stock(pkg: dict[str, Any], headlines: list[str],
                 macro: dict | None = None,
                 nse_announcements: list[dict] | None = None) -> dict[str, Any]:
    tech     = summarise_technicals(pkg["history"])
    fund     = score_fundamentals(pkg["info"])
    senti    = score_headlines_for(ticker_to_keyword(pkg["symbol"]), headlines)
    patterns = detect_candles(pkg["history"])
    sr       = find_support_resistance(pkg["history"])

    # ── NSE corporate-announcements lookup (board meetings, results,
    # dividends, insider trades). Each match feeds the sentiment scorer
    # too so the learner attributes outcomes to filings.
    nse_filings: list[dict] = []
    if nse_announcements:
        try:
            from .nse import announcements_for
            nse_filings = announcements_for(pkg["symbol"], nse_announcements)
        except Exception as exc:
            logger.debug(f"NSE announcements lookup failed: {exc}")
        # Feed filing subjects through the same categorical sentiment scorer
        # so phrases like "buyback approved" / "board meeting" / "insider sell"
        # propagate into news_corp_action_pos / news_shareholder_neg etc.
        if nse_filings:
            extra = [f.get("subject", "") for f in nse_filings if f.get("subject")]
            if extra:
                kw = ticker_to_keyword(pkg["symbol"])
                # Re-score with both RSS headlines + filing subjects together
                senti = score_headlines_for(kw, list(headlines) + extra)
                senti["filings_seen"] = len(extra)

    # ── Per-stock NSE option-chain (PCR + max-pain) — only fetched for
    # F&O-eligible names, rate-limited so a 200-stock universe doesn't
    # hammer NSE. Default OFF; enable with STOCK_FETCH_PCR=1.
    option_chain: dict = {}
    if os.environ.get("STOCK_FETCH_PCR") == "1":
        try:
            from .nse import fetch_equity_option_chain
            option_chain = fetch_equity_option_chain(pkg["symbol"]) or {}
        except Exception as exc:
            logger.debug(f"NSE option chain fetch failed for {pkg['symbol']}: {exc}")

    pred = predict_direction(tech, patterns, sr, macro=macro, senti=senti)

    composite = (
        WEIGHT_FUNDAMENTAL * fund["score"] +
        WEIGHT_TECHNICAL   * _technical_quality(tech) +
        WEIGHT_SENTIMENT   * senti["score"]
    )

    return {
        "symbol":    pkg["symbol"],
        "name":      fund["name"],
        "sector":    fund["sector"],
        "price":     tech["price"],
        "tech":      tech,
        "fund":      fund,
        "senti":     senti,
        "patterns":  patterns,
        "sr":        sr,
        "predict":   pred,
        "filings":   nse_filings,
        "option_chain": option_chain,
        "composite": round(composite, 1),
    }


def _technical_quality(t: dict) -> float:
    """Generic 0..100 technical-health number (trend + momentum)."""
    score = 50.0
    if t["trend_up"]:               score += 15
    if t["macd_hist"] > 0:          score += 10
    if 40 <= t["rsi14"] <= 70:      score += 10
    if t["rsi14"] > 70:             score -= 10
    if t["rsi14"] < 30:             score -= 5   # oversold can be opportunity
    if t["chg_1m_pct"] > 5:         score += 5
    if t["chg_1m_pct"] < -10:       score -= 10
    if t["vol_ratio"] > 1.3:        score += 5
    return max(0.0, min(100.0, score))


# ── Bucket-specific scorers ─────────────────────────────────────────────────

def _intraday_score(s: dict) -> float:
    """High volatility + volume surge + recent momentum."""
    t = s["tech"]
    sc = 0.0
    sc += min(t["atr_pct"] * 15, 35)                # volatility
    sc += min(t["vol_ratio"] * 15, 30)              # volume surge
    sc += max(min(t["chg_1d_pct"] * 3, 15), -15)    # today's drift
    sc += 10 if t["macd_hist"] > 0 else -5
    sc += 10 if 45 <= t["rsi14"] <= 75 else -5
    return round(sc + 50, 1)


def _swing_score(s: dict) -> float:
    """Uptrend + pullback-to-EMA setup; RSI not overbought."""
    t = s["tech"]
    sc = 50.0
    if t["trend_up"]:                 sc += 15
    if t["macd_hist"] > 0:            sc += 10
    # proximity-to-ema20 bonus: closer ≈ better pullback entry
    if t["price"] and t["ema20"]:
        dist = abs(t["price"] - t["ema20"]) / t["price"] * 100
        sc += max(0, 10 - dist)
    if 50 <= t["rsi14"] <= 65:        sc += 10
    if t["rsi14"] > 75:               sc -= 15
    sc += min(t["chg_1m_pct"] * 0.5, 10)
    return round(max(0, min(100, sc)), 1)


def _holding_score(s: dict) -> float:
    """Fundamentals dominate; require not-broken long-term trend."""
    t = s["tech"]
    base = 0.70 * s["fund"]["score"] + 0.20 * _technical_quality(t) + 0.10 * s["senti"]["score"]
    if not t["trend_up"]:
        base -= 10
    if t["chg_3m_pct"] < -20:
        base -= 10
    return round(max(0, min(100, base)), 1)


def _sell_score(s: dict) -> float:
    """Weak fundamentals + bearish technicals + negative news."""
    t = s["tech"]
    sc = 50.0
    sc += (50 - s["fund"]["score"]) * 0.6
    if not t["trend_up"]:             sc += 10
    if t["macd_hist"] < 0:            sc += 10
    if t["rsi14"] > 75:               sc += 10        # overbought → mean revert
    if t["chg_1m_pct"] < -10:         sc += 10
    sc += (50 - s["senti"]["score"]) * 0.3
    return round(max(0, min(100, sc)), 1)


# ── Targets (very naive SL / target using ATR) ──────────────────────────────

def _levels(s: dict, horizon: str) -> dict:
    t  = s["tech"]
    sr = s.get("sr") or {}
    price = s["price"]
    atr_r = max(t["atr14"], price * 0.005)

    if horizon == "intraday":
        sl_atr   = price - atr_r * 1.0
        tgt_atr  = price + atr_r * 1.5
    elif horizon == "swing":
        sl_atr   = price - atr_r * 1.8
        tgt_atr  = price + atr_r * 3.0
    else:  # holding
        sl_atr   = price * 0.90
        tgt_atr  = price * 1.25

    # Tighten SL to just below nearest support, target to just below nearest resistance.
    support    = sr.get("support")
    resistance = sr.get("resistance")
    sl     = sl_atr
    target = tgt_atr
    if support and support < price:
        # Use max(atr SL, support*0.995) so SL is the less-aggressive of the two
        sl = max(sl_atr, support * 0.995)
    if resistance and resistance > price:
        # Stop short of resistance on intraday/swing; long-term can overshoot
        if horizon in ("intraday", "swing"):
            target = min(tgt_atr, resistance * 0.998)

    # ── Forecast metrics (expected profit, risk, hold duration) ──────────
    expected_profit_pct = (target - price) / price * 100 if price else 0.0
    risk_pct            = (price - sl) / price * 100 if price else 0.0
    rr                  = (target - price) / (price - sl) if (price - sl) > 0 else 0.0

    # Hold-duration estimate = distance-to-target / typical daily move (ATR)
    daily_move = max(atr_r * 0.6, price * 0.003)
    est_days   = max(1, int(round((target - price) / daily_move))) if price else 1
    if horizon == "intraday":
        est_days  = 0
        hold_hint = "Same trading day — exit by 3:20 PM"
    elif horizon == "swing":
        est_days  = min(est_days, 15)
        hold_hint = f"~{est_days} trading days (max 15)"
    else:
        est_days  = 252
        hold_hint = "6–12 months+ ; review quarterly"

    if horizon == "intraday":
        buy_window = "After 09:30 IST on dip to entry — avoid first 15-min chaos"
    elif horizon == "swing":
        buy_window = "Stagger: 50% now, 50% on pullback toward support"
    else:
        buy_window = "Accumulate on any 3–5% dip; SIP-style monthly adds"

    # Near-term forecast bands (ATR-based, 1/3/5 trading-day expectation)
    band_1d = (price - atr_r,       price + atr_r)
    band_3d = (price - atr_r * 1.7, price + atr_r * 1.7)
    band_5d = (price - atr_r * 2.2, price + atr_r * 2.2)

    return {
        "entry":               round(price, 2),
        "sl":                  round(sl, 2),
        "target":              round(target, 2),
        "support":             round(support, 2)    if support    else None,
        "resistance":          round(resistance, 2) if resistance else None,
        "expected_profit_pct": round(expected_profit_pct, 2),
        "risk_pct":            round(risk_pct, 2),
        "rr":                  round(rr, 2),
        "est_hold_days":       est_days,
        "hold_hint":           hold_hint,
        "buy_window":          buy_window,
        "forecast_1d":         [round(band_1d[0], 2), round(band_1d[1], 2)],
        "forecast_3d":         [round(band_3d[0], 2), round(band_3d[1], 2)],
        "forecast_5d":         [round(band_5d[0], 2), round(band_5d[1], 2)],
    }


# ── Bucket builder ──────────────────────────────────────────────────────────

def build_buckets(enriched: list[dict]) -> dict[str, list[dict]]:
    def _pick(scorer, horizon, n, reverse=True):
        scored = [{**s, "bucket_score": scorer(s), **{"levels": _levels(s, horizon)}}
                  for s in enriched]
        scored.sort(key=lambda x: x["bucket_score"], reverse=reverse)
        return scored[:n]

    return {
        "intraday": _pick(_intraday_score, "intraday", TOP_INTRADAY),
        "swing":    _pick(_swing_score,    "swing",    TOP_SWING),
        "holding":  _pick(_holding_score,  "holding",  TOP_HOLDING),
        "sell":     _pick(_sell_score,     "holding",  TOP_SELL),
    }


# ── Mutual-fund ranking ─────────────────────────────────────────────────────

def rank_mutual_funds(mfs: list[dict]) -> list[dict]:
    """
    Rank funds by a blended return score: 1Y (weight 0.5) + 3M (0.3) + 1M (0.2).
    Uses NAV history from mfapi.in (daily).
    """
    ranked: list[dict] = []
    for mf in mfs:
        if not mf:
            continue
        series = mf["series"]
        if len(series) < 30:
            continue
        latest = series[-1][1]

        def _ret(days: int) -> float | None:
            if len(series) <= days:
                return None
            past = series[-days - 1][1]
            return (latest / past - 1) * 100 if past else None

        r_1m, r_3m, r_1y, r_3y = _ret(21), _ret(63), _ret(252), _ret(756)
        parts = [(r, w) for r, w in [(r_1m, 0.2), (r_3m, 0.3), (r_1y, 0.5)] if r is not None]
        score = sum(r * w for r, w in parts) / sum(w for _, w in parts) if parts else 0.0

        ranked.append({
            "code":   mf["code"],
            "name":   mf["meta"].get("scheme_name") or mf["meta"].get("fund_house", mf["code"]),
            "cat":    mf["meta"].get("scheme_category", "—"),
            "nav":    round(latest, 4),
            "r_1m":   round(r_1m, 2) if r_1m is not None else None,
            "r_3m":   round(r_3m, 2) if r_3m is not None else None,
            "r_1y":   round(r_1y, 2) if r_1y is not None else None,
            "r_3y":   round(r_3y, 2) if r_3y is not None else None,
            "score":  round(score, 2),
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:TOP_MF]
