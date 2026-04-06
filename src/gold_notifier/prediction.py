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
    """Load adaptive signal weights, prediction history, weekly forecasts and accuracy from disk."""
    try:
        if os.path.exists(PREDICTION_LOG_FILE):
            with open(PREDICTION_LOG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            weights = {**_DEFAULT_WEIGHTS, **data.get("weights", {})}
            return {
                "weights":          weights,
                "predictions":      data.get("predictions", []),
                "weekly_forecasts": data.get("weekly_forecasts", []),
                "accuracy":         data.get("accuracy", {}),
            }
    except Exception as exc:
        logger.warning(f"Prediction model load failed: {exc}")
    return {"weights": dict(_DEFAULT_WEIGHTS), "predictions": [], "weekly_forecasts": [], "accuracy": {}}


def save_prediction_model(model: dict, entry: dict) -> None:
    """Append today's prediction entry and persist weights, forecasts and accuracy to disk."""
    from datetime import datetime
    try:
        preds = [p for p in model["predictions"] if p.get("date") != entry["date"]]
        preds.append(entry)
        preds = preds[-90:]
        os.makedirs(os.path.dirname(PREDICTION_LOG_FILE) or ".", exist_ok=True)
        with open(PREDICTION_LOG_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "weights":          model["weights"],
                    "predictions":      preds,
                    "weekly_forecasts": model.get("weekly_forecasts", []),
                    "accuracy":         model.get("accuracy", {}),
                    "last_updated":     datetime.now().isoformat(),
                },
                fh, indent=2, default=str,
            )
        logger.info(f"Model saved ({len(preds)} entries).")
    except Exception as exc:
        logger.warning(f"Prediction model save failed: {exc}")


def save_weekly_forecast(model: dict, weekly_rows: list, generated_date: str) -> None:
    """Persist the weekly forecast rows into the model for future accuracy verification."""
    forecasts = model.get("weekly_forecasts", [])
    forecasts = [f for f in forecasts if f.get("generated_date") != generated_date]
    rows_to_save = []
    for row in weekly_rows:
        if not row.get("is_weekend"):
            d = row["date"]
            rows_to_save.append({
                "date":             d.isoformat() if hasattr(d, "isoformat") else str(d),
                "direction":        row["direction"],
                "mid_inr":          row["mid_inr"],
                "low_inr":          row["low_inr"],
                "high_inr":         row["high_inr"],
                "actual_inr":       None,
                "actual_direction": None,
                "in_range":         None,
                "dir_correct":      None,
            })
    forecasts.append({"generated_date": generated_date, "rows": rows_to_save})
    model["weekly_forecasts"] = forecasts[-12:]   # keep last 12 weekly forecasts


def _fetch_price_history() -> tuple[dict, dict]:
    """
    Fetch 90-day COMEX gold price history once for all verification tasks.
    Returns ({date_str→usd_close}, {date_str→inr_per_g}).
    """
    price_usd: dict = {}
    price_inr: dict = {}
    try:
        gc  = yf.Ticker("GC=F").history(period="90d")
        fx  = yf.Ticker("USDINR=X").history(period="90d")
        fx_d: dict = {}
        if fx is not None:
            for dt, row in fx.iterrows():
                fx_d[dt.date().isoformat()] = float(row["Close"])
        if gc is not None and len(gc) >= 2:
            for dt, row in gc.iterrows():
                d_str    = dt.date().isoformat()
                usd      = float(row["Close"])
                inr_rate = 84.0
                for offset in range(5):
                    c = (dt.date() + timedelta(days=offset)).isoformat()
                    if c in fx_d:
                        inr_rate = fx_d[c]; break
                price_usd[d_str] = usd
                price_inr[d_str] = round(usd * inr_rate / 31.1035 * INDIA_GOLD_DUTY_FACTOR)
        logger.info(f"Price history loaded: {len(price_usd)} trading days")
    except Exception as exc:
        logger.warning(f"Price history fetch failed: {exc}")
    return price_usd, price_inr


def _verify_past_predictions(predictions: list) -> tuple[list, dict, dict]:
    """
    Verify ALL unverified past daily predictions using 90-day COMEX history.
    Old code only checked the single most-recent unverified entry; this catches
    any predictions missed due to downtime, weekends or errors.
    Logs a post-mortem of which signals were most misleading on wrong calls.
    Returns (updated_predictions, price_hist_usd, price_hist_inr).
    """
    today_str  = date.today().isoformat()
    unverified = [
        p for p in predictions
        if p.get("actual_direction") is None and p.get("date", "") < today_str
    ]
    price_usd, price_inr = _fetch_price_history()
    if not unverified:
        return predictions, price_usd, price_inr

    verified_count = 0
    wrong_signals: dict[str, int] = {}

    for p in unverified:
        pred_date   = p.get("date", "")
        saved_price = p.get("price_usd", 0)
        if saved_price <= 0:
            continue
        try:
            from datetime import datetime as _dt
            pred_dt = _dt.strptime(pred_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        # Find the next trading-day close after the prediction date
        actual_price: float | None = None
        for offset in range(1, 8):
            candidate = (pred_dt + timedelta(days=offset)).isoformat()
            if candidate in price_usd:
                actual_price = price_usd[candidate]; break
        if actual_price is None:
            continue

        pct = (actual_price - saved_price) / saved_price * 100
        if   pct >  0.15: actual = "UP"
        elif pct < -0.15: actual = "DOWN"
        else:             actual = "FLAT"
        p["actual_direction"] = actual
        p["correct"]          = (p["direction"] == actual)
        verified_count += 1
        status = "✅" if p["correct"] else "❌"
        logger.info(
            f"Self-check [{pred_date}]: Predicted {p['direction']} → Actual {actual} "
            f"{status}  (Δ{pct:+.2f}%)"
        )
        # Post-mortem: track which signals voted the wrong direction
        if not p["correct"]:
            actual_up = (actual == "UP")
            for sig, vote in (p.get("signal_votes") or {}).items():
                if vote != 0 and (vote > 0) != actual_up:
                    wrong_signals[sig] = wrong_signals.get(sig, 0) + 1

    if verified_count:
        logger.info(f"Verified {verified_count} prediction(s).")
    if wrong_signals:
        misleaders = sorted(wrong_signals.items(), key=lambda x: -x[1])[:5]
        logger.info("Signals that misled: " + ", ".join(f"{s}({c}×)" for s, c in misleaders))

    return predictions, price_usd, price_inr


def _verify_weekly_forecasts(model: dict, price_inr: dict) -> None:
    """
    For each saved weekly-forecast row whose date has passed, compare the actual
    INR price to the predicted range and check if the direction was correct.
    Summarises direction and range accuracy across all past forecasts.
    """
    today_str      = date.today().isoformat()
    verified_count = 0
    for forecast in model.get("weekly_forecasts", []):
        for row in forecast.get("rows", []):
            row_date = row.get("date", "")
            if row_date >= today_str or row.get("in_range") is not None:
                continue
            actual_inr = price_inr.get(row_date)
            if actual_inr is None:
                continue
            row["actual_inr"] = actual_inr
            row["in_range"]   = (row["low_inr"] <= actual_inr <= row["high_inr"])
            # Direction check vs the previous trading day
            try:
                from datetime import datetime as _dt3
                row_dt = _dt3.strptime(row_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            prev_inr: float | None = None
            for offset in range(1, 6):
                prev_d = (row_dt - timedelta(days=offset)).isoformat()
                prev_inr = price_inr.get(prev_d)
                if prev_inr:
                    break
            if prev_inr:
                diff_pct = (actual_inr - prev_inr) / prev_inr * 100
                if   diff_pct >  0.15: row["actual_direction"] = "UP"
                elif diff_pct < -0.15: row["actual_direction"] = "DOWN"
                else:                  row["actual_direction"] = "FLAT"
                row["dir_correct"] = (row["direction"] == row["actual_direction"])
            verified_count += 1

    if verified_count:
        all_rows = [r for f in model.get("weekly_forecasts", []) for r in f.get("rows", [])]
        dir_rows = [r for r in all_rows if r.get("dir_correct") is not None]
        rng_rows = [r for r in all_rows if r.get("in_range")   is not None]
        if dir_rows:
            dir_acc = round(sum(1 for r in dir_rows if r["dir_correct"]) / len(dir_rows) * 100, 1)
            logger.info(f"Weekly forecast direction accuracy: {dir_acc}% ({len(dir_rows)} rows)")
        if rng_rows:
            rng_acc = round(sum(1 for r in rng_rows if r["in_range"]) / len(rng_rows) * 100, 1)
            logger.info(f"Weekly forecast range accuracy: {rng_acc}% ({len(rng_rows)} rows)")


def _recompute_weights(predictions: list) -> dict:
    """
    Recalculate per-signal accuracy weights with exponential recency bias.
    Decay factor 0.93/step means recent wrong calls penalise a signal much more
    than mistakes from 30+ trading days ago.  Uses up to 60 verified predictions
    (was 30) and a lower minimum of 1.5 weighted points (was 5 raw counts).
    """
    weights  = dict(_DEFAULT_WEIGHTS)
    verified = [p for p in predictions if p.get("correct") is not None][-60:]
    if len(verified) < 3:
        return weights
    n       = len(verified)
    recency = [0.93 ** (n - 1 - i) for i in range(n)]   # most-recent weight = 1.0
    for sig in _DEFAULT_WEIGHTS:
        w_correct = w_wrong = 0.0
        for i, p in enumerate(verified):
            vote = (p.get("signal_votes") or {}).get(sig, 0)
            if vote == 0:
                continue
            actual_up = (p.get("actual_direction") == "UP")
            rw = recency[i]
            if (vote > 0) == actual_up:
                w_correct += rw
            else:
                w_wrong   += rw
        total = w_correct + w_wrong
        if total >= 1.5:   # ~2 recent data points minimum (was 5 raw counts)
            acc = w_correct / total
            # acc=0 → 0.20, acc=0.50 → 1.35, acc=1.0 → 2.50
            weights[sig] = round(max(0.20, min(2.50, 0.20 + acc * 2.30)), 3)
    return weights


def get_model_accuracy_stats(predictions: list) -> dict:
    """Compute rolling accuracy for 7d / 14d / 30d windows and the current streak."""
    verified = [p for p in predictions if p.get("correct") is not None]

    def _acc(window: int) -> tuple:
        sub = verified[-window:]
        if not sub:
            return None, 0
        return round(sum(1 for p in sub if p["correct"]) / len(sub) * 100, 1), len(sub)

    acc_7,  n_7  = _acc(7)
    acc_14, n_14 = _acc(14)
    acc_30, n_30 = _acc(30)
    streak = 0
    streak_type: str | None = None
    if verified:
        streak_type = "correct" if verified[-1]["correct"] else "wrong"
        for p in reversed(verified):
            if (p["correct"] and streak_type == "correct") or (not p["correct"] and streak_type == "wrong"):
                streak += 1
            else:
                break
    return {
        "acc_7":  acc_7,  "n_7":  n_7,
        "acc_14": acc_14, "n_14": n_14,
        "acc_30": acc_30, "n_30": n_30,
        "total":  len(verified),
        "streak": streak, "streak_type": streak_type,
    }


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


def _compute_forecast_bias(model: dict) -> tuple[float, float]:
    """
    Scan all verified weekly forecast rows to compute two adaptive corrections:

    1. **price_bias_pct** – average (actual − predicted) / predicted × 100.
       If we consistently predicted too high, this is negative → we'll shift
       all future forecasts down by this percentage.

    2. **ci_scale** – ratio of actual |error| to predicted CI half-width.
       If our confidence intervals have been too narrow (most actuals outside
       the range), this > 1 and we'll widen CIs; if too wide, < 1 and we narrow.
       Clamped to [0.60, 2.20].

    Returns (price_bias_pct, ci_scale).  Both default to (0.0, 1.0) when
    there is insufficient history.
    """
    all_rows = [
        r for f in model.get("weekly_forecasts", [])
        for r in f.get("rows", [])
        if r.get("actual_inr") and r.get("mid_inr")
    ]
    # Only use the last 60 verified rows (≈ 4 weeks of trading days)
    all_rows = all_rows[-60:]
    if len(all_rows) < 4:
        return 0.0, 1.0

    errors_pct: list[float] = []
    ci_ratios:  list[float] = []

    for r in all_rows:
        actual  = r["actual_inr"]
        mid     = r["mid_inr"]
        lo      = r.get("low_inr",  mid)
        hi      = r.get("high_inr", mid)
        ci_half = max(1, (hi - lo) / 2)

        err_pct  = (actual - mid) / mid * 100
        errors_pct.append(err_pct)

        # How wide did the CI need to be to capture the actual?
        needed = abs(actual - mid)
        ci_ratios.append(needed / ci_half)

    price_bias_pct = sum(errors_pct) / len(errors_pct)
    # Dampen: don't over-correct on sparse data; max meaningful bias ±3 %
    price_bias_pct = max(-3.0, min(3.0, price_bias_pct))

    # Median CI ratio (robust to outliers) — use 75th-pctile so most actuals fit
    ci_ratios_sorted = sorted(ci_ratios)
    p75_idx = int(len(ci_ratios_sorted) * 0.75)
    ci_scale = ci_ratios_sorted[min(p75_idx, len(ci_ratios_sorted) - 1)]
    ci_scale = max(0.60, min(2.20, ci_scale))

    logger.info(
        f"Forecast self-calibration: bias={price_bias_pct:+.2f}%  "
        f"CI_scale={ci_scale:.2f}  from {len(all_rows)} verified rows"
    )
    return price_bias_pct, ci_scale


def _compute_realized_vol(hist) -> float:
    """
    Compute 10-day realized volatility (annualised, as a fraction) from
    log daily returns.  Returns 0.15 (15 % p.a.) as a safe default.
    """
    try:
        import math as _m
        closes = [float(hist["Close"].iloc[i]) for i in range(len(hist))]
        if len(closes) < 5:
            return 0.15
        log_rets = [_m.log(closes[i] / closes[i - 1]) for i in range(max(1, len(closes) - 10), len(closes))]
        if not log_rets:
            return 0.15
        mean_r   = sum(log_rets) / len(log_rets)
        variance = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
        daily_vol = _m.sqrt(variance)
        return daily_vol * _m.sqrt(252)   # annualised
    except Exception:
        return 0.15


# ── 7-day forecast ─────────────────────────────────────────────────────────

def get_weekly_prediction(
    analysis: dict | None,
    geo: dict | None,
    usd_inr: float,
    global_signals: dict | None = None,
    model: dict | None = None,
) -> list[dict] | None:
    """
    Self-learning 7-calendar-day gold price forecast.

    Enhancements over previous version:
    ─────────────────────────────────
    1. **Bias correction** – compares past weekly forecast mid-prices to
       actual prices and applies a percentage offset to remove systematic
       over/under-estimation.

    2. **Adaptive confidence intervals** – measures how often actuals fell
       inside our predicted range in the past, then scales CIs so ~75 % of
       future actuals will be captured.

    3. **Realised volatility blend** – blends 14-day ATR with 10-day
       realised vol so the CI expands during high-vol regimes and
       contracts during calm ones.

    4. **Per-signal weight injection** – if model weights are provided,
       the normalised macro/tech/geo scores are re-scaled by their learned
       accuracy weights before being mixed.

    5. **Trending vs Ranging regime gate** – mean-reversion pull is only
       applied when RSI is extreme *and* the market is not in a strong
       trending regime (prevents conflicting signals).

    6. **Price-path anchoring** – instead of pure drift accumulation, each
       day's projection is anchored 20 % toward the bias-corrected starting
       price to prevent unchecked drift over 5 + days.

    7. **Corner cases** – handles None analysis/geo/global_signals,
       insufficient history, extreme ATR, usd_inr outliers (<50 or >120),
       and the case where every day is a weekend.
    """
    from .analysis import get_market_regime
    try:
        hist = yf.Ticker("GC=F").history(period="30d")
        if hist is None or len(hist) < 10:
            logger.warning("Weekly prediction: insufficient COMEX history")
            return None

        # ── Guard: usd_inr sanity ────────────────────────────────────
        safe_usd_inr = max(60.0, min(120.0, float(usd_inr or 84.0)))

        # ── Volatility: blend ATR and realised vol ────────────────────
        tr_vals = [
            max(float(hist["High"].iloc[i]) - float(hist["Low"].iloc[i]),
                abs(float(hist["High"].iloc[i]) - float(hist["Close"].iloc[i-1])),
                abs(float(hist["Low"].iloc[i])  - float(hist["Close"].iloc[i-1])))
            for i in range(1, len(hist))
        ]
        atr_usd       = sum(tr_vals[-14:]) / min(14, len(tr_vals))
        price_now_usd = float(hist["Close"].iloc[-1])

        # Sanity-guard on ATR (should not exceed 5 % of price)
        atr_usd = min(atr_usd, price_now_usd * 0.05)

        # Realised vol → daily dollar equivalent
        rv_annual = _compute_realized_vol(hist)
        rv_daily  = rv_annual / (252 ** 0.5) * price_now_usd   # $/oz per day
        # Blended volatility: 60 % ATR + 40 % realized
        vol_usd = atr_usd * 0.60 + rv_daily * 0.40

        # ── Pull bias + CI scale from past forecast errors ────────────
        price_bias_pct, ci_scale = (0.0, 1.0)
        if model:
            price_bias_pct, ci_scale = _compute_forecast_bias(model)

        # Starting price adjusted for systematic bias
        # e.g. if we always predicted 1.5 % too high, shift start down
        anchor_usd = price_now_usd * (1.0 + price_bias_pct / 100.0)

        # ── Normalise component scores to [-1, +1] ────────────────────
        raw_tech   = (analysis or {}).get("score", 0)
        tech_norm  = max(-1.0, min(1.0, raw_tech / 7.0))

        geo_norm   = max(-1.0, min(1.0, ((geo or {}).get("geo_score", 0)) / 2.0))

        macro_raw  = (global_signals or {}).get("net_score", 0)
        macro_norm = max(-1.0, min(1.0, macro_raw / 10.0))

        gold_mom   = (global_signals or {}).get("votes", {}).get("gold_momentum", 0)
        mom_norm   = max(-1.0, min(1.0, gold_mom / 2.0))

        # Apply learned signal accuracy weights if available
        W = (model or {}).get("weights", _DEFAULT_WEIGHTS)
        # Weight each normalised score by its learned accuracy (clamped to avoid dominance)
        w_tech  = min(2.0, W.get("regime",   1.4)) / 2.0   # proxy for overall tech weight
        w_macro = min(2.0, W.get("dxy",      1.3)) / 2.0   # macro anchor: DXY accuracy
        w_geo   = min(2.0, W.get("geo",      1.1)) / 2.0
        w_mom   = min(2.0, W.get("gold_momentum", 1.0)) / 2.0

        # ── Regime multiplier ─────────────────────────────────────────
        regime_info  = get_market_regime(global_signals, analysis)
        drift_factor = regime_info.get("drift_factor", 1.0)
        is_trending  = drift_factor >= 1.4 or drift_factor <= 0.7

        # ── Mean-reversion: only when not in strong trending regime ───
        mean_rev = 0.0
        rsi = (analysis or {}).get("rsi", 50.0)
        if not is_trending:
            if   rsi > 72: mean_rev = -(rsi - 72) / 28.0
            elif rsi < 28: mean_rev =  (28 - rsi) / 28.0

        # ── Day-of-week seasonality ───────────────────────────────────
        # Fraction of max_drift applied (0 = market closed)
        dow_adj = {0: 0.85, 1: 1.00, 2: 1.05, 3: 1.00, 4: 0.75, 5: 0.0, 6: 0.0}

        # Max daily drift: 0.25 × vol (realistic; old was 0.28 × ATR)
        max_drift_usd = vol_usd * 0.25

        def inr_per_g(usd_oz: float) -> int:
            return round(max(0.0, usd_oz) * safe_usd_inr / 31.1035 * INDIA_GOLD_DUTY_FACTOR)

        today_dt = date.today()
        rows:    list = []
        proj_usd = anchor_usd
        t        = 0   # trading-day counter

        for offset in range(1, 8):
            day        = today_dt + timedelta(days=offset)
            dow        = day.weekday()
            is_weekend = dow >= 5

            # Expanding CI half-width (√t uncertainty growth), scaled by ci_scale
            ci_multiplier = min(1.40, 0.45 + 0.10 * max(t, 1))
            ci_half       = vol_usd * ci_multiplier * ci_scale

            if is_weekend:
                mid_inr = inr_per_g(proj_usd)
                rows.append({
                    "date":       day,
                    "weekday":    day.strftime("%a"),
                    "direction":  "FLAT",
                    "emoji":      "⚪",
                    "confidence": "N/A",
                    "mid_inr":    mid_inr,
                    "low_inr":    inr_per_g(proj_usd - ci_half),
                    "high_inr":   inr_per_g(proj_usd + ci_half),
                    "mid_22k":    round(mid_inr * 22 / 24),
                    "low_22k":    round(inr_per_g(proj_usd - ci_half) * 22 / 24),
                    "high_22k":   round(inr_per_g(proj_usd + ci_half) * 22 / 24),
                    "is_weekend": True,
                })
                continue

            t += 1  # trading-day counter

            # Momentum decay: 20 % per trading day (half-life ≈ 3 days)
            mom_decay = 0.80 ** (t - 1)

            # Signal mix: tech-heavy early, macro-heavy later
            tech_w  = max(0.15, 0.55 - 0.10 * (t - 1))
            macro_w = min(0.75, 0.35 + 0.10 * (t - 1))
            rev_w   = min(0.30, 0.06 * t)   # mean-reversion grows with time

            # Composite directional signal
            signal = (
                tech_w  * tech_norm  * w_tech  * mom_decay +
                macro_w * macro_norm * w_macro             +
                0.10    * geo_norm   * w_geo               +
                0.08    * mom_norm   * w_mom   * mom_decay +
                rev_w   * mean_rev
            )
            signal = max(-1.0, min(1.0, signal))

            # Day drift with DOW seasonality and regime multiplier
            day_drift = signal * max_drift_usd * drift_factor * dow_adj.get(dow, 1.0)

            # Price-path anchoring: 20% pull back toward anchor each day
            # This prevents runaway-drift on day 5+ long forecasts
            anchor_pull = (anchor_usd - proj_usd) * 0.20
            proj_usd    = proj_usd + day_drift + anchor_pull

            # Direction determination
            thr = vol_usd * 0.04   # ≈ 4 % of daily vol
            if   day_drift > thr:  direction, day_emoji = "UP",   "🟢"
            elif day_drift < -thr: direction, day_emoji = "DOWN", "🔴"
            else:                  direction, day_emoji = "FLAT", "⚪"

            # Confidence label based on signal strength + regime
            sig_abs   = abs(signal)
            if   sig_abs >= 0.60 and drift_factor >= 1.2: conf_lbl = "High"
            elif sig_abs >= 0.30:                          conf_lbl = "Moderate"
            else:                                          conf_lbl = "Low"

            mid_inr  = inr_per_g(proj_usd)
            high_inr = inr_per_g(proj_usd + ci_half)
            low_inr  = inr_per_g(proj_usd - ci_half)

            rows.append({
                "date":       day,
                "weekday":    day.strftime("%a"),
                "direction":  direction,
                "emoji":      day_emoji,
                "confidence": conf_lbl,
                "mid_inr":    mid_inr,
                "low_inr":    low_inr,
                "high_inr":   high_inr,
                "mid_22k":    round(mid_inr  * 22 / 24),
                "low_22k":    round(low_inr  * 22 / 24),
                "high_22k":   round(high_inr * 22 / 24),
                "is_weekend": is_weekend,
            })

        if not rows:
            logger.warning("Weekly prediction: all 7 days are weekends?")
            return None

        logger.info(
            f"Weekly forecast: bias_corr={price_bias_pct:+.2f}%  "
            f"CI_scale={ci_scale:.2f}  vol_usd={vol_usd:.1f}  "
            f"drift_factor={drift_factor:.2f}"
        )
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
