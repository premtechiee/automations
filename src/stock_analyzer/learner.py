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
    """Return list of feature tags that were active when this pick was made.

    Richer feature set → more accurate learning:
      • trend / momentum / RSI / volume (legacy)
      • volatility regime (ATR%)
      • multi-timeframe price momentum (1-day / 1-month / 3-month buckets)
      • fundamental-score quintile
      • bucket-score quintile
      • candle bias + S/R proximity
      • macro regime + opening-gap direction
    """
    tags: list[str] = []
    t = pick.get("tech") or {}
    sr = pick.get("sr") or {}
    pr = pick.get("predict") or {}
    f  = pick.get("fund") or {}

    # ── Trend / momentum / RSI / volume ────────────────────────────────
    if t.get("trend_up"):              tags.append("trend_up")
    else:                              tags.append("trend_down")
    if t.get("macd_hist", 0) > 0:      tags.append("macd_pos")
    else:                              tags.append("macd_neg")
    rsi = t.get("rsi14") or 50
    if   rsi > 70:                     tags.append("rsi_overbought")
    elif rsi < 30:                     tags.append("rsi_oversold")
    elif 45 <= rsi <= 65:              tags.append("rsi_strong")
    vr = t.get("vol_ratio") or 0
    if   vr > 1.6:                     tags.append("vol_surge")
    elif vr < 0.6:                     tags.append("vol_dry")

    # ── Volatility regime (ATR%) ───────────────────────────────────────
    atr_pct = t.get("atr_pct") or 0
    if   atr_pct > 4.0:                tags.append("vol_regime_high")
    elif atr_pct < 1.5:                tags.append("vol_regime_low")
    else:                              tags.append("vol_regime_mid")

    # ── Multi-timeframe momentum ───────────────────────────────────────
    d1 = t.get("chg_1d_pct") or 0
    m1 = t.get("chg_1m_pct") or 0
    m3 = t.get("chg_3m_pct") or 0
    if   d1 >= 2.0:  tags.append("mom_1d_strong_up")
    elif d1 <= -2.0: tags.append("mom_1d_strong_down")
    if   m1 >= 5.0:  tags.append("mom_1m_up")
    elif m1 <= -5.0: tags.append("mom_1m_down")
    if   m3 >= 10.0: tags.append("mom_3m_up")
    elif m3 <= -10.0: tags.append("mom_3m_down")

    # ── Fundamental quality quintile ───────────────────────────────────
    fs = f.get("score")
    if fs is not None:
        if   fs >= 70: tags.append("fund_strong")
        elif fs >= 50: tags.append("fund_mid")
        else:          tags.append("fund_weak")

    # ── Bucket composite score quintile ────────────────────────────────
    bs = pick.get("bucket_score")
    if bs is not None:
        if   bs >= 75: tags.append("score_top")
        elif bs >= 60: tags.append("score_high")
        elif bs >= 45: tags.append("score_mid")
        else:          tags.append("score_low")

    # ── Candle bias ────────────────────────────────────────────────────
    for pat in pick.get("patterns", []):
        pl = pat.lower()
        if "bullish" in pl or "hammer" in pl or "morning" in pl:
            tags.append("candle_bullish")
        elif "bearish" in pl or "shooting" in pl or "evening" in pl:
            tags.append("candle_bearish")
        elif "doji" in pl:
            tags.append("candle_doji")

    # ── Macro regime + opening bias ────────────────────────────────────
    macro = macro or pr.get("macro") or {}
    if isinstance(macro, dict):
        regime = macro.get("regime")
        if regime in ("risk-on", "risk-off"):
            tags.append(f"macro_{regime.replace('-', '_')}")
        opening = (macro.get("opening") or {})
        od = opening.get("direction") or ""
        if   "GAP-UP"   in od: tags.append("open_gap_up")
        elif "GAP-DOWN" in od: tags.append("open_gap_down")
        elif "FLAT"     in od: tags.append("open_flat")

    # ── S/R proximity ──────────────────────────────────────────────────
    price = pick.get("price") or t.get("price") or 0
    if price and sr.get("support"):
        if (price - sr["support"]) / price * 100 < 1.0:
            tags.append("near_support")
    if price and sr.get("resistance"):
        if (sr["resistance"] - price) / price * 100 < 1.0:
            tags.append("near_resistance")

    # ── Categorised news sentiment (earnings / regulatory / political /
    # geopolitical / corp_action / shareholder / macro). We tag both the
    # category direction AND a "strong" variant when the signal is large
    # enough — this lets the learner discover, e.g., that 'earnings_pos'
    # is reliable but 'political_pos' is noise for swing trades.
    senti = pick.get("senti") or {}
    cats = senti.get("categories") or {}
    for cat, info in cats.items():
        pos = int(info.get("pos", 0))
        neg = int(info.get("neg", 0))
        total = pos + neg
        if total == 0:
            continue
        norm = (pos - neg) / total
        if norm > 0.2:
            tags.append(f"news_{cat}_pos")
            if total >= 3 and norm > 0.5:
                tags.append(f"news_{cat}_strong_pos")
        elif norm < -0.2:
            tags.append(f"news_{cat}_neg")
            if total >= 3 and norm < -0.5:
                tags.append(f"news_{cat}_strong_neg")

    # Overall sentiment quintile (legacy)
    sscore = senti.get("score")
    if sscore is not None:
        if   sscore >= 65: tags.append("senti_strong_pos")
        elif sscore >= 55: tags.append("senti_mild_pos")
        elif sscore <= 35: tags.append("senti_strong_neg")
        elif sscore <= 45: tags.append("senti_mild_neg")

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
    today's price, attribute wins/losses to active features **per bucket**,
    save updated weights to learned_weights.json. Returns the new payload.
    """
    idx_path = os.path.join(REPORTS_DIR, "_index.json")
    if not os.path.exists(idx_path):
        return _load_weights()

    try:
        idx = json.load(open(idx_path, encoding="utf-8"))
    except Exception:
        return _load_weights()

    # Tally: {feature: {bucket: {wins, total}}}
    tally: dict[str, dict[str, dict[str, int]]] = {}
    # Also keep an "all" tally across buckets for global weight
    all_tally: dict[str, dict[str, int]] = {}

    # Calibration buckets: track confidence→actual hit-rate
    calib: dict[str, dict[str, int]] = {}  # keyed "50-59", "60-69", ...

    total_picks_scored = 0
    total_wins         = 0

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
                total_picks_scored += 1
                if won:
                    total_wins += 1
                feats = _features_at_pick(pick, macro)
                for f in feats:
                    bd = tally.setdefault(f, {})
                    e  = bd.setdefault(bucket, {"wins": 0, "total": 0})
                    e["total"] += 1
                    if won:
                        e["wins"] += 1
                    a = all_tally.setdefault(f, {"wins": 0, "total": 0})
                    a["total"] += 1
                    if won:
                        a["wins"] += 1

                # Confidence calibration
                conf = (pick.get("predict") or {}).get("confidence")
                if conf is not None:
                    try:
                        conf = int(conf)
                    except Exception:
                        conf = None
                if conf is not None:
                    band = (f"{(conf // 10) * 10}-{(conf // 10) * 10 + 9}"
                            if conf < 100 else "90-99")
                    eb = calib.setdefault(band, {"wins": 0, "total": 0})
                    eb["total"] += 1
                    if won:
                        eb["wins"] += 1

    def _hit(wins, total):
        return (wins + _DEFAULT["smoothing"]) / (total + 2 * _DEFAULT["smoothing"])

    def _weight(hit, total):
        if total < _DEFAULT["min_samples"]:
            return 1.0
        # 0.5 hit → 1.0; 0.7 → 1.4; 0.3 → 0.6
        return max(_DEFAULT["min_weight"],
                   min(_DEFAULT["max_weight"], 0.5 + (hit - 0.5) * 2.0))

    new_weights: dict[str, Any] = {}
    for feat, all_e in all_tally.items():
        hit = _hit(all_e["wins"], all_e["total"])
        w   = _weight(hit, all_e["total"])
        per_bucket: dict[str, Any] = {}
        for bkt, e in tally.get(feat, {}).items():
            bhit = _hit(e["wins"], e["total"])
            per_bucket[bkt] = {
                "weight":   round(_weight(bhit, e["total"]), 3),
                "hit_rate": round(bhit * 100, 1),
                "wins":     e["wins"],
                "total":    e["total"],
            }
        new_weights[feat] = {
            "weight":   round(w, 3),
            "hit_rate": round(hit * 100, 1),
            "wins":     all_e["wins"],
            "total":    all_e["total"],
            "by_bucket": per_bucket,
        }

    # Calibration curve (for confidence display)
    calib_curve = {}
    for band, e in sorted(calib.items()):
        if e["total"] == 0:
            continue
        calib_curve[band] = {
            "wins":     e["wins"],
            "total":    e["total"],
            "hit_rate": round(e["wins"] / e["total"] * 100, 1),
        }

    overall_accuracy = (total_wins / total_picks_scored * 100) if total_picks_scored else None

    payload = {
        "updated_at":       datetime.now().isoformat(timespec="seconds"),
        "window_runs":      window_runs,
        "features":         new_weights,
        "calibration":      calib_curve,
        "overall_accuracy": overall_accuracy,
        "picks_scored":     total_picks_scored,
        "picks_won":        total_wins,
    }
    os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Learned weights updated: {len(new_weights)} features, "
                f"{total_picks_scored} picks scored "
                f"({overall_accuracy:.1f}% accurate)"
                if overall_accuracy is not None else
                f"Learned weights updated: {len(new_weights)} features")
    return payload


def _load_weights() -> dict[str, Any]:
    if not os.path.exists(WEIGHTS_FILE):
        return {"features": {}}
    try:
        return json.load(open(WEIGHTS_FILE, encoding="utf-8"))
    except Exception:
        return {"features": {}}


def feature_weight(feature: str, bucket: str | None = None) -> float:
    """Public lookup used by patterns.predict_direction().
    If `bucket` is given, prefer the bucket-specific weight when available
    (intraday/swing/holding/sell)."""
    feats = _load_weights().get("features", {}).get(feature, {})
    if bucket and "by_bucket" in feats:
        bw = feats["by_bucket"].get(bucket)
        if bw:
            return float(bw.get("weight", 1.0))
    return float(feats.get("weight", 1.0))


def calibrated_confidence(raw_conf: int | float) -> int:
    """Map raw confidence (0-100) to an empirically calibrated percentage
    based on past hit-rates of similar confidence bands."""
    w = _load_weights()
    calib = w.get("calibration") or {}
    if not calib:
        return int(raw_conf)
    try:
        c = int(raw_conf)
    except Exception:
        return 50
    band = (f"{(c // 10) * 10}-{(c // 10) * 10 + 9}" if c < 100 else "90-99")
    if band in calib and calib[band].get("total", 0) >= 5:
        return int(round(calib[band]["hit_rate"]))
    return c


def self_review(top_n: int = 5) -> dict[str, Any]:
    """Return a snapshot of model learning: most-reliable & least-reliable
    features, overall accuracy, calibration curve. Used in the reports."""
    w = _load_weights()
    feats = w.get("features", {})
    # Only consider features with meaningful sample size
    scored = [(name, d) for name, d in feats.items() if d.get("total", 0) >= 5]
    scored.sort(key=lambda kv: kv[1]["hit_rate"], reverse=True)

    best  = [{"name": n, **d} for n, d in scored[:top_n]]
    worst = [{"name": n, **d} for n, d in list(reversed(scored))[:top_n]]

    return {
        "updated_at":       w.get("updated_at"),
        "window_runs":      w.get("window_runs"),
        "overall_accuracy": w.get("overall_accuracy"),
        "picks_scored":     w.get("picks_scored", 0),
        "picks_won":        w.get("picks_won", 0),
        "n_features":       len(feats),
        "best_features":    best,
        "worst_features":   worst,
        "calibration":      w.get("calibration", {}),
    }


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
