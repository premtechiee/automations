"""
automations/gold_notifier/prediction.py
=========================================
Self-learning prediction model: load, verify, recompute weights, save,
generate today's direction prediction, 7-day forecast, and monthly low prediction.
"""

import json
import logging
import os
from datetime import date, timedelta

import yfinance as yf

from .config import PREDICTION_LOG_FILE, INDIA_GOLD_DUTY_FACTOR

logger = logging.getLogger(__name__)

# ── Default signal weights ─────────────────────────────────────────────────
_DEFAULT_WEIGHTS: dict = {
    "rsi": 1.2, "macd": 1.0, "bb": 1.1, "momentum_3d": 0.9, "momentum_5d": 1.0,
    "geo": 1.1, "dow": 0.7, "seasonality": 0.8,
    "real_yield": 1.5, "dxy": 1.3, "yields": 1.1, "yield_curve": 1.0,
    "vix": 1.1, "risk_assets": 1.0, "oil": 0.9, "silver_ratio": 0.8,
    "copper": 0.9, "eur_usd": 0.8, "etf_flow": 1.1, "gold_momentum": 1.0,
    "regime": 1.4,
}


# ── Model persistence ──────────────────────────────────────────────────────

def load_prediction_model() -> dict:
    """Load adaptive signal weights + prediction history from disk."""
    try:
        if os.path.exists(PREDICTION_LOG_FILE):
            with open(PREDICTION_LOG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            weights = {**_DEFAULT_WEIGHTS, **data.get("weights", {})}
            return {"weights": weights, "predictions": data.get("predictions", [])}
    except Exception as exc:
        logger.warning(f"Prediction model load failed: {exc}")
    return {"weights": dict(_DEFAULT_WEIGHTS), "predictions": []}


def save_prediction_model(model: dict, entry: dict) -> None:
    """Append today's prediction entry and persist model weights to disk."""
    from datetime import datetime
    try:
        preds = [p for p in model["predictions"] if p.get("date") != entry["date"]]
        preds.append(entry)
        preds = preds[-90:]
        os.makedirs(os.path.dirname(PREDICTION_LOG_FILE) or ".", exist_ok=True)
        with open(PREDICTION_LOG_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                {"weights": model["weights"], "predictions": preds,
                 "last_updated": datetime.now().isoformat()},
                fh, indent=2, default=str,
            )
        logger.info(f"Model saved ({len(preds)} entries).")
    except Exception as exc:
        logger.warning(f"Prediction model save failed: {exc}")


def _verify_yesterday_prediction(predictions: list, price_now_usd: float) -> list:
    """Mark the most recent unverified prediction as correct/incorrect."""
    today_str = date.today().isoformat()
    for p in reversed(predictions[-10:]):
        if p.get("actual_direction") is None and p.get("date", "") < today_str:
            saved = p.get("price_usd", 0)
            if saved > 0:
                pct = (price_now_usd - saved) / saved * 100
                if   pct >  0.15: actual = "UP"
                elif pct < -0.15: actual = "DOWN"
                else:             actual = "FLAT"
                p["actual_direction"] = actual
                p["correct"]          = (p["direction"] == actual)
                logger.info(
                    f"Self-check [{p['date']}]: Predicted {p['direction']} → Actual {actual} "
                    f"{'✅' if p['correct'] else '❌'}  (Δ{pct:+.2f}%)"
                )
            break
    return predictions


def _recompute_weights(predictions: list) -> dict:
    """Recalculate per-signal accuracy weights from the last 30 verified predictions."""
    weights  = dict(_DEFAULT_WEIGHTS)
    verified = [p for p in predictions if p.get("correct") is not None][-30:]
    if len(verified) < 5:
        return weights
    for sig in _DEFAULT_WEIGHTS:
        correct = incorrect = 0
        for p in verified:
            vote = (p.get("signal_votes") or {}).get(sig, 0)
            if vote == 0:
                continue
            actual_up = (p.get("actual_direction") == "UP")
            if (vote > 0) == actual_up:
                correct += 1
            else:
                incorrect += 1
        total = correct + incorrect
        if total >= 5:
            acc = correct / total
            weights[sig] = round(max(0.3, min(2.5, 0.3 + acc * 2.2)), 3)
    return weights


# ── Today's prediction ─────────────────────────────────────────────────────

def get_price_prediction(
    analysis: dict | None,
    geo: dict | None,
    history: list | None,
    global_signals: dict | None = None,
    weights: dict | None = None,
) -> dict:
    """Multi-factor weighted prediction of today's gold price direction (11 signals)."""
    W            = weights or _DEFAULT_WEIGHTS
    score        = 0.0
    signal_votes: dict = {}
    reasons_up   = []
    reasons_down = []

    # 1. RSI
    vote = 0
    if analysis:
        rsi = analysis["rsi"]
        if   rsi < 30: vote =  3; reasons_up.append(f"RSI {rsi:.0f} – deeply oversold, strong bounce likely")
        elif rsi < 42: vote =  2; reasons_up.append(f"RSI {rsi:.0f} – oversold, upward pressure building")
        elif rsi < 50: vote =  1; reasons_up.append(f"RSI {rsi:.0f} – below midline, mild bullish bias")
        elif rsi > 70: vote = -3; reasons_down.append(f"RSI {rsi:.0f} – overbought, pullback likely")
        elif rsi > 58: vote = -1; reasons_down.append(f"RSI {rsi:.0f} – above midline, mild bearish bias")
    signal_votes["rsi"] = vote; score += vote * W.get("rsi", 1.0)

    # 2. MACD
    vote = 0
    if analysis:
        if   analysis["macd_cross"] > 0: vote =  1; reasons_up.append("MACD bullish crossover – uptrend signal")
        elif analysis["macd_cross"] < 0: vote = -1; reasons_down.append("MACD bearish crossover – downtrend signal")
    signal_votes["macd"] = vote; score += vote * W.get("macd", 1.0)

    # 3. Bollinger Band
    vote = 0
    if analysis:
        bb = analysis["bb_pos"] * 100
        if   bb < 15: vote =  2; reasons_up.append(f"Bollinger {bb:.0f}% – at lower band, bounce zone")
        elif bb < 30: vote =  1; reasons_up.append(f"Bollinger {bb:.0f}% – near lower band, upside bias")
        elif bb > 85: vote = -2; reasons_down.append(f"Bollinger {bb:.0f}% – at upper band, reversal risk")
        elif bb > 70: vote = -1; reasons_down.append(f"Bollinger {bb:.0f}% – near upper band, resistance")
    signal_votes["bb"] = vote; score += vote * W.get("bb", 1.0)

    # 4. 3-day momentum
    vote = 0
    if history:
        trading_rows = [r for r in history if r.get("trading") is True]
        if len(trading_rows) >= 3:
            net3 = sum(r["chg"] for r in trading_rows[:3])
            if   net3 >  300: vote =  1; reasons_up.append(f"3-day net +₹{net3:,} – sustained upward momentum")
            elif net3 < -300: vote = -1; reasons_down.append(f"3-day net ₹{net3:,} – sustained downward pressure")
    signal_votes["momentum_3d"] = vote; score += vote * W.get("momentum_3d", 1.0)

    # 5. Geopolitical
    vote = 0
    if geo:
        gs = geo["geo_score"]
        if   gs >= 2:  vote =  2; reasons_up.append("Strong geopolitical tension – safe-haven demand")
        elif gs == 1:  vote =  1; reasons_up.append("Mild geopolitical risk – some safe-haven support")
        elif gs <= -1: vote = -1; reasons_down.append("Easing geopolitical risk – reduced safe-haven demand")
    signal_votes["geo"] = vote; score += vote * W.get("geo", 1.0)

    # 6. Day-of-week
    vote = 0
    dow = date.today().weekday()
    if dow == 0: reasons_down.append("Monday – watch for weekend gap risk")
    if dow == 4: vote = -1; reasons_down.append("Friday – profit-taking tendency")
    signal_votes["dow"] = vote; score += vote * W.get("dow", 1.0)

    # 7. DXY
    vote = global_signals.get("votes", {}).get("dxy", 0) if global_signals else 0
    if   vote > 0: reasons_up.append("Dollar weakening – gold tailwind (inverse relation)")
    elif vote < 0: reasons_down.append("Dollar strengthening – gold headwind (inverse relation)")
    signal_votes["dxy"] = vote; score += vote * W.get("dxy", 1.0)

    # 8. Yields
    vote = global_signals.get("votes", {}).get("yields", 0) if global_signals else 0
    if   vote > 0: reasons_up.append("Falling yields – gold opportunity cost drops")
    elif vote < 0: reasons_down.append("Rising yields – gold opportunity cost rises")
    signal_votes["yields"] = vote; score += vote * W.get("yields", 1.0)

    # 9. VIX
    vote = global_signals.get("votes", {}).get("vix", 0) if global_signals else 0
    if   vote > 0: reasons_up.append("Elevated VIX – fear driving safe-haven gold demand")
    elif vote < 0: reasons_down.append("Low VIX – calm markets, reduced safe-haven demand")
    signal_votes["vix"] = vote; score += vote * W.get("vix", 1.0)

    # 10. S&P 500
    vote = global_signals.get("votes", {}).get("risk_assets", 0) if global_signals else 0
    if   vote > 0: reasons_up.append("Equity selloff – risk-off flow into gold")
    elif vote < 0: reasons_down.append("Equity rally – risk-on rotation away from gold")
    signal_votes["risk_assets"] = vote; score += vote * W.get("risk_assets", 1.0)

    # 11. Oil
    vote = global_signals.get("votes", {}).get("oil", 0) if global_signals else 0
    if   vote > 0: reasons_up.append("Rising oil – inflation hedge demand for gold")
    elif vote < 0: reasons_down.append("Falling oil – lower inflation, mild gold drag")
    signal_votes["oil"] = vote; score += vote * W.get("oil", 1.0)

    s = float(score)
    if   s >= 5.0:  direction, emoji, confidence = "UP",   "🟢", "High"
    elif s >= 2.5:  direction, emoji, confidence = "UP",   "🟡", "Moderate"
    elif s >= 1.0:  direction, emoji, confidence = "UP",   "⚪", "Low"
    elif s <= -5.0: direction, emoji, confidence = "DOWN", "🔴", "High"
    elif s <= -2.5: direction, emoji, confidence = "DOWN", "🟠", "Moderate"
    elif s <= -1.0: direction, emoji, confidence = "DOWN", "⚪", "Low"
    else:           direction, emoji, confidence = "FLAT", "⚪", "Uncertain"

    active = sum(1 for v in signal_votes.values() if v != 0)
    logger.info(f"Prediction: {direction} ({confidence})  score={s:.2f}  active_signals={active}/11")
    return {
        "direction":    direction,
        "emoji":        emoji,
        "confidence":   confidence,
        "score":        round(s, 2),
        "signal_votes": signal_votes,
        "reasons_up":   reasons_up,
        "reasons_down": reasons_down,
    }


# ── 7-day forecast ─────────────────────────────────────────────────────────

def get_weekly_prediction(
    analysis: dict | None,
    geo: dict | None,
    usd_inr: float,
    global_signals: dict | None = None,
) -> list[dict] | None:
    """ATR-based 7-calendar-day gold price projection."""
    try:
        hist = yf.Ticker("GC=F").history(period="30d")
        if hist is None or len(hist) < 10:
            return None

        tr_vals = [
            max(float(hist["High"].iloc[i]) - float(hist["Low"].iloc[i]),
                abs(float(hist["High"].iloc[i]) - float(hist["Close"].iloc[i-1])),
                abs(float(hist["Low"].iloc[i])  - float(hist["Close"].iloc[i-1])))
            for i in range(1, len(hist))
        ]
        atr_usd       = sum(tr_vals[-14:]) / min(14, len(tr_vals))
        price_now_usd = float(hist["Close"].iloc[-1])

        base_score    = (
            (analysis["score"]               if analysis       else 0) +
            (geo["geo_score"]                if geo            else 0) +
            (global_signals.get("net_score", 0) if global_signals else 0)
        )
        raw_drift     = atr_usd * (base_score / 20.0)
        daily_drift   = max(-atr_usd * 0.4, min(atr_usd * 0.4, raw_drift))
        dow_mult      = {0: 0.95, 1: 1.0, 2: 1.05, 3: 1.05, 4: 0.90, 5: 0.0, 6: 0.0}

        def inr_per_g(usd_oz):
            return round(usd_oz * usd_inr / 31.1035 * INDIA_GOLD_DUTY_FACTOR)

        today_dt  = date.today()
        rows      = []
        proj_usd  = price_now_usd

        for offset in range(1, 8):
            day       = today_dt + timedelta(days=offset)
            dow       = day.weekday()
            is_weekend = dow >= 5
            day_drift  = daily_drift * dow_mult.get(dow, 1.0)
            proj_usd  += day_drift
            half_range = atr_usd * 0.55

            mid_inr  = inr_per_g(proj_usd)
            high_inr = inr_per_g(proj_usd + half_range)
            low_inr  = inr_per_g(proj_usd - half_range)

            threshold = atr_usd * 0.08
            if   day_drift > threshold:  direction, day_emoji = "UP",   "🟢"
            elif day_drift < -threshold: direction, day_emoji = "DOWN", "🔴"
            else:                        direction, day_emoji = "FLAT", "⚪"

            rows.append({
                "date":       day,
                "weekday":    day.strftime("%a"),
                "direction":  direction,
                "emoji":      day_emoji,
                "mid_inr":    mid_inr,
                "low_inr":    low_inr,
                "high_inr":   high_inr,
                "mid_22k":    round(mid_inr  * 22 / 24),
                "low_22k":    round(low_inr  * 22 / 24),
                "high_22k":   round(high_inr * 22 / 24),
                "is_weekend": is_weekend,
            })
        return rows
    except Exception as exc:
        logger.warning(f"Weekly prediction failed: {exc}")
        return None


# ── Monthly low prediction ─────────────────────────────────────────────────

def get_monthly_low_prediction(
    analysis: dict | None,
    geo: dict | None,
    usd_inr: float,
    payment: dict | None = None,
    global_signals: dict | None = None,
) -> dict | None:
    """Predict which remaining calendar day this month will have the lowest gold price."""
    import calendar as _cal

    def ordinal(n):
        return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"

    try:
        hist = yf.Ticker("GC=F").history(period="45d")
        if hist is None or len(hist) < 10:
            return None

        tr_vals = [
            max(float(hist["High"].iloc[i]) - float(hist["Low"].iloc[i]),
                abs(float(hist["High"].iloc[i]) - float(hist["Close"].iloc[i-1])),
                abs(float(hist["Low"].iloc[i])  - float(hist["Close"].iloc[i-1])))
            for i in range(1, len(hist))
        ]
        atr_usd       = sum(tr_vals[-14:]) / max(1, min(14, len(tr_vals)))
        price_now_usd = float(hist["Close"].iloc[-1])

        base_score    = (
            (analysis["score"]               if analysis       else 0.0) +
            (geo["geo_score"]                if geo            else 0.0) +
            (global_signals.get("net_score", 0) if global_signals else 0.0)
        )
        raw_drift    = atr_usd * (base_score / 20.0)
        daily_drift  = max(-atr_usd * 0.4, min(atr_usd * 0.4, raw_drift))
        dow_mult     = {0:0.95, 1:1.0, 2:1.05, 3:1.05, 4:0.90, 5:0.0, 6:0.0}

        def inr_per_g(usd_oz):
            return round(usd_oz * usd_inr / 31.1035 * INDIA_GOLD_DUTY_FACTOR)

        ranking_list = payment["ranking"] if payment and payment.get("ranking") else []
        rank_pos     = {int(d): pos for pos, (d, _) in enumerate(ranking_list)}
        num_ranked   = max(1, len(rank_pos))

        def hist_adj_usd(cal_day):
            if cal_day not in rank_pos:
                return 0.0
            norm = rank_pos[cal_day] / (num_ranked - 1)
            return atr_usd * (norm - 0.5) * 0.4

        today_dt   = date.today()
        month_end  = _cal.monthrange(today_dt.year, today_dt.month)[1]
        proj_usd   = price_now_usd
        candidates = []

        for offset in range(1, month_end - today_dt.day + 1):
            target    = today_dt + timedelta(days=offset)
            dow       = target.weekday()
            day_drift = daily_drift * dow_mult.get(dow, 1.0)
            proj_usd += day_drift
            adj_usd   = proj_usd + hist_adj_usd(target.day)
            half_rng  = atr_usd * 0.55

            mid_inr  = inr_per_g(adj_usd)
            candidates.append({
                "date":       target,
                "day":        target.day,
                "weekday":    target.strftime("%A"),
                "short_day":  target.strftime("%a"),
                "is_weekend": dow >= 5,
                "adj_usd":    adj_usd,
                "mid_inr":    mid_inr,
                "low_inr":    inr_per_g(adj_usd - half_rng),
                "high_inr":   inr_per_g(adj_usd + half_rng),
                "mid_22k":    round(mid_inr * 22 / 24),
                "low_22k":    round(inr_per_g(adj_usd - half_rng) * 22 / 24),
                "high_22k":   round(inr_per_g(adj_usd + half_rng) * 22 / 24),
            })

        if not candidates:
            return None

        sorted_cands = sorted(candidates, key=lambda x: x["adj_usd"])
        best = sorted_cands[0]
        top3 = sorted_cands[:3]

        hist_best_days = payment["top3_days"] if payment and payment.get("top3_days") else []
        hist_aligns    = best["day"] in hist_best_days

        abs_score = abs(base_score)
        raw_conf  = "High" if abs_score >= 4.0 else ("Moderate" if abs_score >= 2.0 else "Low")
        conf_levels = ["Low", "Moderate", "High"]
        conf_idx    = conf_levels.index(raw_conf) + (1 if hist_aligns else 0)
        confidence  = conf_levels[min(conf_idx, 2)]

        trend_word = (
            "falling" if daily_drift < -atr_usd * 0.05 else
            "rising"  if daily_drift >  atr_usd * 0.05 else "stable"
        )
        hist_note = (
            f" The {ordinal(best['day'])} is also historically one of the cheapest days."
            if hist_aligns else ""
        )
        reasoning = (
            f"Price is currently {trend_word}. "
            f"The model projects the lowest price around {best['date'].strftime('%d %b')} "
            f"(±₹{round((best['high_inr'] - best['low_inr']) / 2):,}/g uncertainty).{hist_note}"
        )

        logger.info(
            f"Monthly low prediction: {best['date'].strftime('%d %b')}  "
            f"₹{best['mid_inr']:,}/g  conf={confidence}  trend={trend_word}"
        )
        return {
            "predicted_date":    best["date"],
            "predicted_day":     best["day"],
            "predicted_weekday": best["weekday"],
            "predicted_inr":     best["mid_inr"],
            "predicted_22k":     best["mid_22k"],
            "low_inr":           best["low_inr"],
            "high_inr":          best["high_inr"],
            "low_22k":           best["low_22k"],
            "high_22k":          best["high_22k"],
            "top3":              top3,
            "confidence":        confidence,
            "days_remaining":    len(candidates),
            "hist_aligns":       hist_aligns,
            "reasoning":         reasoning,
            "trend_word":        trend_word,
            "base_score":        round(base_score, 2),
        }
    except Exception as exc:
        logger.warning(f"Monthly low prediction failed: {exc}")
        return None
