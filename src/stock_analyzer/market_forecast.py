"""
stock_analyzer/market_forecast.py
==================================
Aggregate breadth + macro + per-stock predictions into a single
*market-level* forecast for the next 1-5 sessions.

Outputs a dict:
    {
        "direction":   "UP" | "DOWN" | "SIDEWAYS",
        "confidence":  0-100,
        "band_pct":    (lo, hi),   # expected % range for Nifty
        "reasons":     [str, ...],
        "components":  {...}       # for transparency & debugging
    }

Not a neural net — a transparent weighted vote across breadth, macro,
prediction ensemble, and volatility regime. The confidence is calibrated
by `learner.calibrated_confidence()` so accuracy improves with data.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def forecast_market(
    enriched: list[dict],
    buckets: dict,
    macro: dict | None,
) -> dict[str, Any]:
    """Produce a single market-wide prediction from the full run context."""

    # ── 1. Breadth vote ─────────────────────────────────────────────
    adv = dec = flat = 0
    big_up = big_dn = 0
    atr_pcts: list[float] = []
    rsi_vals: list[float] = []
    trend_up_cnt = 0
    for e in enriched or []:
        t = e.get("tech") or {}
        v = t.get("chg_1d_pct")
        if v is None:
            continue
        if v > 0.2:   adv += 1
        elif v < -0.2: dec += 1
        else:          flat += 1
        if v >= 2.0:  big_up += 1
        if v <= -2.0: big_dn += 1
        if t.get("trend_up"):
            trend_up_cnt += 1
        atr_pcts.append(float(t.get("atr_pct") or 0))
        rsi_vals.append(float(t.get("rsi14") or 50))
    total = adv + dec + flat

    breadth_vote = 0.0
    if total:
        ad_ratio = (adv - dec) / total  # -1..+1
        breadth_vote = ad_ratio * 3.0
        # Strong-mover bias tilts the vote
        breadth_vote += (big_up - big_dn) * 0.3
        # % of universe trending up = structural bias
        breadth_vote += ((trend_up_cnt / total) - 0.5) * 2.0

    # ── 2. Per-stock prediction ensemble ────────────────────────────
    pred_score = 0.0
    n_pred = 0
    conf_sum = 0.0
    for key in ("intraday", "swing"):
        for p in (buckets.get(key) or []):
            pr = p.get("predict") or {}
            d  = pr.get("direction")
            c  = float(pr.get("confidence") or 0)
            if not d:
                continue
            n_pred += 1
            conf_sum += c
            if   d == "UP":   pred_score += c / 100.0
            elif d == "DOWN": pred_score -= c / 100.0
    pred_vote = 0.0
    if n_pred:
        # Normalise to roughly ±3 range
        pred_vote = (pred_score / n_pred) * 3.0

    # ── 3. Macro bias ───────────────────────────────────────────────
    macro_vote = 0.0
    regime = (macro or {}).get("regime", "neutral")
    macro_vote = int((macro or {}).get("bias") or 0) * 0.6
    if regime == "risk-on":  macro_vote += 1.0
    if regime == "risk-off": macro_vote -= 1.2

    # Opening-gap nudge
    opening = (macro or {}).get("opening") or {}
    op_dir  = opening.get("direction") or ""
    if   "GAP-UP"   in op_dir: macro_vote += 0.5
    elif "GAP-DOWN" in op_dir: macro_vote -= 0.5

    # ── 4. Volatility penalty (hi vol = lower confidence) ───────────
    median_atr = sorted(atr_pcts)[len(atr_pcts) // 2] if atr_pcts else 2.0
    vol_conf_penalty = max(0.0, (median_atr - 3.0)) * 5.0   # each point above 3% ATR cuts 5% conf

    # ── 5. Combine ───────────────────────────────────────────────────
    total_score = breadth_vote + pred_vote + macro_vote

    if   total_score >= 1.5:  direction = "UP"
    elif total_score <= -1.5: direction = "DOWN"
    else:                      direction = "SIDEWAYS"

    raw_conf = min(95, max(30, 55 + abs(total_score) * 8 - vol_conf_penalty))

    # Calibrate via learner if data available
    try:
        from .learner import calibrated_confidence
        conf = calibrated_confidence(raw_conf)
    except Exception:
        conf = int(raw_conf)

    # Expected Nifty range using median ATR
    atr_pct_band = max(median_atr, 0.8)
    if   direction == "UP":   band = (-atr_pct_band * 0.4,  atr_pct_band * 1.5)
    elif direction == "DOWN": band = (-atr_pct_band * 1.5,  atr_pct_band * 0.4)
    else:                      band = (-atr_pct_band,       atr_pct_band)

    reasons: list[str] = []
    if total:
        reasons.append(
            f"Breadth {adv}/{total} advancing ({adv / total * 100:.0f}%), "
            f"{trend_up_cnt / total * 100:.0f}% trending up."
        )
    if n_pred:
        avg_conf = conf_sum / n_pred
        reasons.append(
            f"{n_pred} per-stock predictions avg {avg_conf:.0f}% confidence, "
            f"net direction score {pred_vote:+.2f}."
        )
    reasons.append(f"Macro regime {regime.upper()}, bias {int((macro or {}).get('bias') or 0):+d}.")
    if op_dir:
        reasons.append(f"Nifty opening expectation: {op_dir}.")
    if vol_conf_penalty > 0:
        reasons.append(
            f"Median ATR {median_atr:.1f}% (elevated) — confidence reduced."
        )

    return {
        "direction":  direction,
        "confidence": int(conf),
        "band_pct":   (round(band[0], 2), round(band[1], 2)),
        "reasons":    reasons[:6],
        "components": {
            "breadth_vote": round(breadth_vote, 2),
            "pred_vote":    round(pred_vote, 2),
            "macro_vote":   round(macro_vote, 2),
            "total_score":  round(total_score, 2),
            "median_atr":   round(median_atr, 2),
            "advancing":    adv,
            "declining":    dec,
            "trending_up":  trend_up_cnt,
            "universe":     total,
        },
    }
