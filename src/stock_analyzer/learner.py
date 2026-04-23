"""
stock_analyzer/learner.py
==========================
Self-learning weight tuner — the closest a free / no-API automation can get
to "training an LLM" without burning credits.

How it works
------------
1. Every run, we already persist full recommendations to `data/stock_reports/`.
2. On each subsequent run we walk through every prior report, join it with the
   *current* live prices, and decide whether each prediction was correct.
3. We attribute the win / loss to the *features that were active* at the time
   (e.g. "trend_up=True, RSI<30, bullish engulfing, macro=risk-off").
4. Each feature's running hit-rate becomes its *weight* the next time the
   predictor runs.  Features that have been historically wrong shrink toward
   zero; features that are consistently right amplify.

The learned weights are saved to `data/learned_weights.json` and re-used by
`patterns.predict_direction` via `apply_learned_weights()`.

This is rule-based machine-learning (online logistic-style updates), NOT a
neural model — but it adapts daily and turns the tool into a genuine
"market expert advisor" whose conviction grows with experience.
"""

from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from typing import Any

from .config import REPORTS_DIR

logger = logging.getLogger(__name__)

WEIGHTS_FILE = os.path.join(os.path.dirname(REPORTS_DIR), "learned_weights.json")

# Default neutral weight for every feature
_DEFAULT = {
    "min_samples":   5,     # below this we keep weight = 1.0
    "smoothing":     3,     # Bayesian smoothing — keeps weight rational with low data
    "max_weight":    1.5,   # cap so a lucky streak can't dominate
    "min_weight":    0.3,
}


# ── Feature attribution ─────────────────────────────────────────────────────

def _features_at_pick(pick: dict, macro: dict | None = None) -> list[str]:
    """Return list of feature tags that were active when this pick was made."""
    tags: list[str] = []
    t = pick.get("tech") or {}
    sr = pick.get("sr") or {}
    pr = pick.get("predict") or {}

    if t.get("trend_up"):              tags.append("trend_up")
    else:                              tags.append("trend_down")
    if t.get("macd_hist", 0) > 0:      tags.append("macd_pos")
    else:                              tags.append("macd_neg")
    rsi = t.get("rsi14") or 50
    if rsi > 70:                       tags.append("rsi_overbought")
    elif rsi < 30:                     tags.append("rsi_oversold")
    elif 45 <= rsi <= 65:              tags.append("rsi_strong")
    if (t.get("vol_ratio") or 0) > 1.4: tags.append("vol_surge")

    for pat in pick.get("patterns", []):
        pl = pat.lower()
        if "bullish" in pl or "hammer" in pl or "morning" in pl:
            tags.append("candle_bullish")
        elif "bearish" in pl or "shooting" in pl or "evening" in pl:
            tags.append("candle_bearish")

    # Macro snapshot (optional)
    macro = macro or pr.get("macro") or {}
    regime = macro.get("regime") if isinstance(macro, dict) else None
    if regime in ("risk-on", "risk-off"):
        tags.append(f"macro_{regime.replace('-', '_')}")

    # S/R proximity
    price = pick.get("price") or t.get("price") or 0
    if price and sr.get("support"):
        if (price - sr["support"]) / price * 100 < 1.0:
            tags.append("near_support")
    if price and sr.get("resistance"):
        if (sr["resistance"] - price) / price * 100 < 1.0:
            tags.append("near_resistance")

    return tags


def _is_win(pick: dict, current_price: float, bucket: str) -> bool | None:
    """Was this pick correct given today's price?"""
    entry = (pick.get("levels") or {}).get("entry")
    if entry is None or not current_price:
        return None
    ret = (current_price / entry - 1) * 100
    return ret < 0 if bucket == "sell" else ret > 0


# ── Learning: scan history, update tallies ──────────────────────────────────

def update_learned_weights(current_prices: dict[str, float],
                            window_runs: int = 30) -> dict[str, Any]:
    """
    Walk the last `window_runs` saved reports, score every pick against
    today's price, attribute wins/losses to active features, save updated
    weights to learned_weights.json. Returns the new weight map.
    """
    idx_path = os.path.join(REPORTS_DIR, "_index.json")
    if not os.path.exists(idx_path):
        return _load_weights()

    try:
        idx = json.load(open(idx_path, encoding="utf-8"))
    except Exception:
        return _load_weights()

    # Tally per feature: {feature: {wins, total}}
    tally: dict[str, dict[str, int]] = {}

    for fname in idx[-window_runs:]:
        path = os.path.join(REPORTS_DIR, fname)
        if not os.path.exists(path):
            continue
        try:
            report = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue

        macro = report.get("macro", {})
        for bucket, picks in (report.get("buckets") or {}).items():
            for pick in picks:
                sym = pick.get("symbol")
                if not sym or sym not in current_prices:
                    continue
                won = _is_win(pick, current_prices[sym], bucket)
                if won is None:
                    continue
                feats = _features_at_pick(pick, macro)
                for f in feats:
                    e = tally.setdefault(f, {"wins": 0, "total": 0})
                    e["total"] += 1
                    if won:
                        e["wins"] += 1

    # Convert tally -> weight using smoothed hit-rate
    new_weights = {}
    for feat, e in tally.items():
        if e["total"] < _DEFAULT["min_samples"]:
            w = 1.0
            hit = (e["wins"] + _DEFAULT["smoothing"]) / (e["total"] + 2 * _DEFAULT["smoothing"])
        else:
            hit = (e["wins"] + _DEFAULT["smoothing"]) / (e["total"] + 2 * _DEFAULT["smoothing"])
            # 0.5 hit-rate → weight 1.0; 0.7 → 1.4; 0.3 → 0.6
            w = max(_DEFAULT["min_weight"],
                    min(_DEFAULT["max_weight"], 0.5 + (hit - 0.5) * 2.0))
        new_weights[feat] = {
            "weight":   round(w, 3),
            "hit_rate": round(hit * 100, 1),
            "wins":     e["wins"],
            "total":    e["total"],
        }

    payload = {
        "updated_at":  datetime.now().isoformat(timespec="seconds"),
        "window_runs": window_runs,
        "features":    new_weights,
    }
    os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Learned weights updated for {len(new_weights)} features → "
                f"{WEIGHTS_FILE}")
    return payload


def _load_weights() -> dict[str, Any]:
    if not os.path.exists(WEIGHTS_FILE):
        return {"features": {}}
    try:
        return json.load(open(WEIGHTS_FILE, encoding="utf-8"))
    except Exception:
        return {"features": {}}


def feature_weight(feature: str) -> float:
    """Public lookup used by patterns.predict_direction()."""
    w = _load_weights().get("features", {}).get(feature, {})
    return float(w.get("weight", 1.0))


# ── Expert advisor synthesis ────────────────────────────────────────────────

def expert_advice(buckets: dict, macro: dict, prior: dict,
                  weights: dict | None = None) -> str:
    """
    Synthesise everything into an advisor-style paragraph (max ~700 chars,
    plain English).  Combines macro regime, top conviction pick, learned
    accuracy, and a clear next action.
    """
    weights  = weights or _load_weights()
    n_feats  = len(weights.get("features", {}))
    samples  = sum(f.get("total", 0) for f in weights.get("features", {}).values())

    regime   = macro.get("regime", "neutral")
    geo_lvl  = (macro.get("geo") or {}).get("level", 50)
    bias     = macro.get("bias", 0)
    spy      = (macro.get("snapshot") or {}).get("SPY", {}).get("chg_pct")
    vix      = (macro.get("snapshot") or {}).get("VIX", {}).get("last")

    # Pick the highest-confidence intraday OR swing pick
    candidates: list[dict] = []
    for k in ("intraday", "swing"):
        for p in buckets.get(k, []):
            pr = p.get("predict") or {}
            if pr.get("direction") in ("UP", "DOWN"):
                candidates.append({"key": k, "pick": p, "conf": pr["confidence"]})
    candidates.sort(key=lambda x: x["conf"], reverse=True)
    top = candidates[0] if candidates else None

    parts: list[str] = []

    # 1. Market mood
    mood = {"risk-on":  "constructive — global risk appetite is healthy",
            "risk-off": "cautious — global investors are de-risking",
            "neutral":  "mixed — no strong global directional cue"}.get(regime, "mixed")
    parts.append(f"📌 *Today's market read:* {mood}.")
    if spy is not None:
        parts.append(f"S&P 500 last closed {spy:+.1f}%; "
                     f"VIX {vix:.0f}." if vix else f"S&P 500 {spy:+.1f}%.")
    if geo_lvl >= 65:
        parts.append("Geopolitical tape elevated — keep position sizes small.")
    elif geo_lvl <= 35:
        parts.append("Geopolitical mood improving.")

    # 2. Top conviction
    if top:
        p  = top["pick"]
        pr = p["predict"]
        lv = p["levels"]
        sym = p["symbol"].replace(".NS", "")
        tag = "same-day trade" if top["key"] == "intraday" else "short-term swing"
        parts.append(
            f"🎯 *My top conviction is {sym}* as a {tag}: predicting "
            f"{pr['direction']} with {pr['confidence']}% confidence. "
            f"Buy near ₹{lv['entry']:,.2f}, stop-loss ₹{lv['sl']:,.2f}, "
            f"target ₹{lv['target']:,.2f}."
        )
        if pr.get("reasons"):
            parts.append(f"Why: {pr['reasons'][0]}.")

    # 3. Learning footprint
    if samples > 0:
        prior_avail = prior.get("available")
        bucket_acc: list[str] = []
        if prior_avail:
            for b, info in prior["buckets"].items():
                hr = info.get("hit_rate")
                if hr is not None and info.get("count", 0) > 0:
                    bucket_acc.append(f"{b} {hr:.0f}%")
        acc_str = (", ".join(bucket_acc)) if bucket_acc else "calibrating"
        parts.append(
            f"📚 *Self-learning:* I have studied {samples} past picks across "
            f"{n_feats} signals. Recent accuracy → {acc_str}. "
            f"My weights have been auto-tuned accordingly."
        )

    # 4. Net stance
    if bias >= 2:
        stance = "Lean LONG; favour buys on dips."
    elif bias <= -2:
        stance = "Lean DEFENSIVE; raise cash and trim weak holdings."
    else:
        stance = "Stay BALANCED; trade individual setups, not the index."
    parts.append(f"🧭 *Stance:* {stance}")

    return " ".join(parts)
