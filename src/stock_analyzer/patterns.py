"""
stock_analyzer/patterns.py
===========================
Candlestick pattern detection, support/resistance discovery and a short-term
direction predictor.  Pure-python / pandas only.

Used by:
  • recommender.py     — to refine SL / Target using real S/R levels
  • report.py          — to show the prediction block on the image & caption
  • pdf_report.py      — to narrate pattern + S/R reasons in rationale
"""

from __future__ import annotations
import pandas as pd


# ── Candlestick patterns ────────────────────────────────────────────────────

def _body(o, c): return abs(c - o)
def _upper(h, o, c): return h - max(o, c)
def _lower(l, o, c): return min(o, c) - l          # noqa: E741
def _range(h, l): return max(h - l, 1e-9)          # noqa: E741


def detect_candles(df: pd.DataFrame) -> list[str]:
    """Return human-readable names of patterns on the last 1-3 candles."""
    if len(df) < 3:
        return []
    o1, h1, l1, c1 = df.iloc[-1][["Open", "High", "Low", "Close"]]
    o2, h2, l2, c2 = df.iloc[-2][["Open", "High", "Low", "Close"]]
    o3, _,  _,  c3 = df.iloc[-3][["Open", "High", "Low", "Close"]]

    b1, r1 = _body(o1, c1), _range(h1, l1)
    up1, lo1 = _upper(h1, o1, c1), _lower(l1, o1, c1)
    b2, r2 = _body(o2, c2), _range(h2, l2)

    patterns: list[str] = []

    # Doji — very small body (<10% of range)
    if b1 < 0.1 * r1:
        patterns.append("Doji (indecision)")

    # Hammer — small body at top, long lower wick (bullish reversal after downtrend)
    elif b1 < 0.35 * r1 and lo1 > 2 * b1 and up1 < b1 and c2 < o2:
        patterns.append("Hammer (bullish reversal)")

    # Shooting Star — small body at bottom, long upper wick (bearish reversal)
    elif b1 < 0.35 * r1 and up1 > 2 * b1 and lo1 < b1 and c2 > o2:
        patterns.append("Shooting Star (bearish reversal)")

    # Marubozu — body fills ≥ 90% of range
    elif b1 > 0.9 * r1:
        patterns.append("Strong Bullish candle" if c1 > o1
                        else "Strong Bearish candle")

    # Bullish Engulfing — today's green body engulfs yesterday's red body
    if c1 > o1 and c2 < o2 and o1 <= c2 and c1 >= o2 and b1 > b2:
        patterns.append("Bullish Engulfing")
    # Bearish Engulfing
    elif c1 < o1 and c2 > o2 and o1 >= c2 and c1 <= o2 and b1 > b2:
        patterns.append("Bearish Engulfing")

    # Morning Star — down + small body + strong up closing above mid of first
    if c3 < o3 and b2 < 0.4 * r2 and c1 > o1 and c1 > (o3 + c3) / 2:
        patterns.append("Morning Star (bullish reversal)")
    # Evening Star
    if c3 > o3 and b2 < 0.4 * r2 and c1 < o1 and c1 < (o3 + c3) / 2:
        patterns.append("Evening Star (bearish reversal)")

    return patterns


def candle_bias(patterns: list[str]) -> int:
    """Rough bullish/bearish score from pattern names: +1 / 0 / −1 per pattern."""
    bias = 0
    for p in patterns:
        pl = p.lower()
        if "bullish" in pl or "hammer" in pl or "morning" in pl:
            bias += 1
        elif "bearish" in pl or "shooting" in pl or "evening" in pl:
            bias -= 1
    return bias


# ── Support / Resistance ────────────────────────────────────────────────────

def find_support_resistance(df: pd.DataFrame, lookback: int = 60,
                             pivot: int = 3) -> dict:
    """
    Find nearest support (below current price) and resistance (above) using
    swing-high / swing-low pivots in the last `lookback` bars. A pivot is a
    high/low that exceeds its `pivot` neighbours on both sides.
    Also returns classical intraday pivot (P), R1, S1 from yesterday's HLC.
    """
    if len(df) < pivot * 2 + 2:
        price = float(df["Close"].iloc[-1])
        return {"support": price * 0.97, "resistance": price * 1.03,
                "pivot_p": price, "pivot_r1": price, "pivot_s1": price,
                "support_strength": 0, "resistance_strength": 0}

    window = df.tail(lookback)
    high, low, close = window["High"], window["Low"], window["Close"]
    price = float(close.iloc[-1])

    swing_highs: list[float] = []
    swing_lows:  list[float] = []
    for i in range(pivot, len(window) - pivot):
        seg_h = high.iloc[i - pivot:i + pivot + 1]
        seg_l = low.iloc[i - pivot:i + pivot + 1]
        if high.iloc[i] == seg_h.max():
            swing_highs.append(float(high.iloc[i]))
        if low.iloc[i] == seg_l.min():
            swing_lows.append(float(low.iloc[i]))

    resistances = sorted({round(h, 2) for h in swing_highs if h > price})
    supports    = sorted({round(l, 2) for l in swing_lows  if l < price}, reverse=True)

    support    = supports[0]    if supports    else price * 0.95
    resistance = resistances[0] if resistances else price * 1.05

    # Strength = how many times price tested a band near that level (± 0.5%)
    def _band_hits(levels: list[float], target: float) -> int:
        tol = target * 0.005
        return sum(1 for lv in levels if abs(lv - target) <= tol)

    s_strength = _band_hits(swing_lows,  support)
    r_strength = _band_hits(swing_highs, resistance)

    # Classical pivot from yesterday
    yh = float(df["High"].iloc[-2]); yl = float(df["Low"].iloc[-2])
    yc = float(df["Close"].iloc[-2])
    p  = (yh + yl + yc) / 3.0
    r1 = 2 * p - yl
    s1 = 2 * p - yh

    return {
        "support":             round(support, 2),
        "resistance":          round(resistance, 2),
        "support_strength":    s_strength,
        "resistance_strength": r_strength,
        "pivot_p":             round(p, 2),
        "pivot_r1":            round(r1, 2),
        "pivot_s1":            round(s1, 2),
    }


# ── Short-term direction prediction ─────────────────────────────────────────

def predict_direction(tech: dict, patterns: list[str], sr: dict,
                       macro: dict | None = None,
                       bucket: str | None = None,
                       senti: dict | None = None) -> dict:
    """
    Combine technicals + candlesticks + S/R proximity + global macro context
    + categorised news sentiment (earnings / corp_action / shareholder /
    regulatory / political / geopolitical / macro) into a short-term
    (1–5 day) outlook.  Returns direction ('UP'/'DOWN'/'SIDEWAYS'),
    confidence 0-100, and plain-English reasons.

    Every per-feature contribution is scaled by a learned weight from
    `learner.feature_weight()` (optionally bucket-specific) so the system
    improves as it accumulates real-world performance data. The final
    confidence is empirically calibrated via `learner.calibrated_confidence()`.
    """
    # Lazy import to avoid circulars
    try:
        from .learner import feature_weight as _fw
        from .learner import calibrated_confidence as _calib
    except Exception:
        def _fw(_, __=None): return 1.0
        def _calib(c):        return c

    def fw(feat):
        # bucket-aware lookup (falls back to global weight if bucket data missing)
        try:
            return _fw(feat, bucket)
        except TypeError:
            return _fw(feat)

    score   = 0.0
    reasons: list[str] = []
    price   = tech["price"]

    # Trend
    if tech.get("trend_up"):
        score += 2 * fw("trend_up");  reasons.append("Price is above its 50- & 200-day averages (uptrend)")
    else:
        score -= 1 * fw("trend_down"); reasons.append("Price is below its 50-day average (weak trend)")

    # Momentum
    if tech["macd_hist"] > 0:
        score += 1 * fw("macd_pos");  reasons.append("Momentum turning positive (MACD)")
    else:
        score -= 1 * fw("macd_neg");  reasons.append("Momentum fading (MACD)")

    # RSI extremes
    if tech["rsi14"] > 70:
        score -= 2 * fw("rsi_overbought"); reasons.append("Overbought — likely short-term pullback")
    elif tech["rsi14"] < 30:
        score += 2 * fw("rsi_oversold");   reasons.append("Oversold — possible bounce")
    elif 45 <= tech["rsi14"] <= 65:
        score += 1 * fw("rsi_strong");     reasons.append("Momentum healthy (RSI in strong zone)")

    # Volume
    if tech["vol_ratio"] > 1.4:
        score += 1 * fw("vol_surge"); reasons.append(f"Trading volume is {tech['vol_ratio']:.1f}× the usual — strong interest")
    elif tech["vol_ratio"] < 0.6:
        reasons.append("Trading volume low — weak conviction")

    # Candlestick bias
    cb = candle_bias(patterns)
    if cb > 0:
        score += cb * fw("candle_bullish"); reasons.append("Candle pattern suggests buyers in control")
    elif cb < 0:
        score += cb * fw("candle_bearish"); reasons.append("Candle pattern suggests sellers in control")

    # S/R proximity
    dist_r = (sr["resistance"] - price) / price * 100 if price else 99
    dist_s = (price - sr["support"]) / price * 100 if price else 99
    if dist_r < 1.0:
        score -= 1 * fw("near_resistance"); reasons.append(f"Price near resistance ₹{sr['resistance']:.2f} — may struggle to break above")
    elif dist_s < 1.0:
        score += 1 * fw("near_support");    reasons.append(f"Price near support ₹{sr['support']:.2f} — good risk:reward if it holds")

    # Translate score → direction
    if score >= 3:     direction = "UP"
    elif score <= -2:  direction = "DOWN"
    else:              direction = "SIDEWAYS"

    # ── Categorised news sentiment ──────────────────────────────────────
    # Each category becomes its own learnable feature tag so the learner
    # can attribute outcomes to specific drivers (earnings beat vs probe
    # vs FII outflow etc).  Score normalised to ±1 per category and capped.
    senti_bias = 0.0
    senti = senti or {}
    cats = senti.get("categories") or {}
    for cat, info in cats.items():
        pos = int(info.get("pos", 0))
        neg = int(info.get("neg", 0))
        if pos + neg == 0:
            continue
        norm = (pos - neg) / (pos + neg)               # −1 … +1
        magnitude = min(2.0, (pos + neg) / 2.0)         # cap impact
        # earnings & regulatory have stronger price impact → 1.5x base
        cat_strength = {
            "earnings": 1.5, "regulatory": 1.5, "shareholder": 1.3,
            "corp_action": 1.2, "geopolitical": 1.0,
            "political": 0.8, "macro": 0.8,
        }.get(cat, 1.0)
        feat = f"news_{cat}_{'pos' if norm > 0 else 'neg'}"
        contrib = norm * magnitude * cat_strength * fw(feat)
        score += contrib
        senti_bias += contrib
        if abs(contrib) >= 0.5:
            label = cat.replace("_", " ")
            reasons.append(
                f"{'Positive' if norm > 0 else 'Negative'} {label} news "
                f"(+{pos}/-{neg})"
            )

    # Re-classify after sentiment overlay
    if score >= 3:     direction = "UP"
    elif score <= -2:  direction = "DOWN"
    else:              direction = "SIDEWAYS"

    # Macro / global context (US market, VIX, oil, DXY, war/geopolitics).
    # This can flip SIDEWAYS ↔ directional or amplify confidence.
    macro_bias = 0
    if macro:
        macro_bias = int(macro.get("bias") or 0)
        regime = macro.get("regime")
        macro_w = fw(f"macro_{(regime or 'neutral').replace('-', '_')}")
        if macro.get("reasons"):
            reasons.append(macro["reasons"][0])
        score += macro_bias * macro_w
        # Re-classify after macro overlay
        if score >= 3:     direction = "UP"
        elif score <= -2:  direction = "DOWN"
        else:              direction = "SIDEWAYS"

    # Confidence — bounded; macro agreement amplifies; then empirically calibrated
    raw_confidence = min(95, 50 + abs(score) * 10)
    confidence     = _calib(raw_confidence)

    return {
        "direction":  direction,
        "confidence": int(confidence),
        "score":      round(score, 2),
        "macro_bias": macro_bias,
        "senti_bias": round(senti_bias, 2),
        "reasons":    reasons[:6],
    }
