"""
automations/gold_notifier/analysis.py
======================================
Technical analysis, global macro signals, market regime, geopolitical
news sentiment, and best-payment-date analysis for gold.
"""

import calendar
import logging
from datetime import date, timedelta

import yfinance as yf

from .config import INDIA_GOLD_DUTY_FACTOR

logger = logging.getLogger(__name__)

# ── Geopolitical keyword sets ──────────────────────────────────────────────
_BULLISH_WORDS = [
    # Conflict / Risk
    "war", "conflict", "attack", "strike", "missile", "invasion", "nuclear",
    "sanctions", "crisis", "tension", "geopolit", "escalat", "coup",
    "explosion", "airstrike", "warship", "troops", "ambush",
    # Economic risk
    "inflation", "stagflation", "recession", "crash", "collapse",
    "uncertainty", "fear", "panic", "bank failure", "default", "debt ceiling",
    "credit crunch", "contagion", "systemic risk",
    # Trade / Dollar
    "tariff", "trade war", "trade deficit", "de-dollarization",
    "dollar falls", "dollar weakness", "weak dollar", "currency debasement",
    "central bank buying", "reserve accumulation",
    # Fed / Rates
    "rate cut", "fed cut", "dovish", "easing", "stimulus", "qe",
    "negative rates", "rate pause",
]
_BEARISH_WORDS = [
    # Peace / Calm
    "ceasefire", "peace deal", "truce", "agreement signed", "de-escalat",
    "stabilize", "calm", "diplomatic",
    # Economic strength
    "recovery", "growth", "surplus", "strong jobs", "beats expectations",
    "strong gdp", "soft landing",
    # Fed / Rates
    "rate hike", "hawkish", "fed hike", "higher for longer",
    "tightening", "rate rises",
    # Dollar strength
    "strong dollar", "dollar rises", "dollar rally", "dollar strengthens",
    # Trade deals
    "trade deal", "trade truce", "tariff relief", "tariff exemption",
    "trade agreement",
]


# ── Technical analysis ─────────────────────────────────────────────────────

def get_gold_analysis() -> dict | None:
    """RSI, SMA20/50, MACD, Bollinger Bands, 7d/30d momentum."""
    try:
        hist = yf.Ticker("GC=F").history(period="90d")
        if hist is None or len(hist) < 27:
            logger.warning("Not enough history for analysis.")
            return None

        close = hist["Close"]

        delta    = close.diff()
        avg_gain = delta.clip(lower=0).rolling(14).mean()
        avg_loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi      = float((100 - (100 / (1 + avg_gain / avg_loss))).iloc[-1])

        sma20     = float(close.rolling(20).mean().iloc[-1])
        sma50     = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        price_now = float(close.iloc[-1])

        ema12      = close.ewm(span=12, adjust=False).mean()
        ema26      = close.ewm(span=26, adjust=False).mean()
        macd_line  = ema12 - ema26
        macd_sig   = macd_line.ewm(span=9, adjust=False).mean()
        macd_val   = float(macd_line.iloc[-1])
        macd_cross = macd_val - float(macd_sig.iloc[-1])

        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_up  = float((bb_mid + 2 * bb_std).iloc[-1])
        bb_low = float((bb_mid - 2 * bb_std).iloc[-1])
        bb_pos = (price_now - bb_low) / (bb_up - bb_low)

        chg_7d  = ((price_now - float(close.iloc[-7]))  / float(close.iloc[-7]))  * 100
        chg_30d = ((price_now - float(close.iloc[-30])) / float(close.iloc[-30])) * 100

        score   = 0
        signals = []

        if rsi < 30:    signals.append("RSI oversold → strong buy signal");    score += 2
        elif rsi < 45:  signals.append("RSI slightly low → mild buy signal");  score += 1
        elif rsi > 70:  signals.append("RSI overbought → wait for correction"); score -= 2
        elif rsi > 55:  signals.append("RSI elevated → consider waiting");     score -= 1
        else:           signals.append("RSI neutral")

        if price_now < sma20:
            signals.append("Price below 20-day avg → buying opportunity"); score += 1
        else:
            signals.append("Price above 20-day avg → running hot");        score -= 1

        if sma50:
            if price_now < sma50:
                signals.append("Price below 50-day avg → undervalued zone"); score += 1
            else:
                signals.append("Price above 50-day avg → premium zone");    score -= 1

        if chg_7d < -2:   signals.append(f"Price fell {chg_7d:.1f}% in 7 days → dip to consider"); score += 1
        elif chg_7d > 3:  signals.append(f"Price rose {chg_7d:.1f}% in 7 days → momentum high");   score -= 1

        if macd_cross > 0: signals.append("MACD bullish crossover → upward momentum building"); score += 1
        else:              signals.append("MACD bearish crossover → downward pressure present"); score -= 1

        if bb_pos < 0.2:   signals.append("Price near lower Bollinger Band → oversold zone");     score += 2
        elif bb_pos > 0.8: signals.append("Price near upper Bollinger Band → overbought zone");   score -= 2
        else:              signals.append(f"Price in Bollinger mid-zone ({bb_pos*100:.0f}% of band)")

        if score >= 4:
            recommendation = "🟢 STRONG BUY – Excellent entry"
            invest_advice  = "Multiple indicators aligned. Price is in a dip.\n💰 Action: Enter lump sum now."
        elif score >= 2:
            recommendation = "🟡 GOOD TO BUY – Favourable entry"
            invest_advice  = "Good entry point. Consider staggered buying.\n💰 Action: Split lump sum into 2 tranches."
        elif score in (0, 1):
            recommendation = "⚪ NEUTRAL – Wait for confirmation"
            invest_advice  = "Market balanced. Wait for RSI < 45 or a 2% dip.\n💰 Action: Continue existing SIP."
        elif score >= -2:
            recommendation = "🟠 WAIT – Price elevated"
            invest_advice  = "Gold is running above averages.\n💰 Action: Pause lump sum."
        else:
            recommendation = "🔴 AVOID – Overbought territory"
            invest_advice  = "High RSI + upper BB + bearish signals.\n💰 Action: Only SIP continuity."

        return {
            "rsi":            rsi,
            "sma20":          sma20,
            "sma50":          sma50,
            "macd_val":       macd_val,
            "macd_cross":     macd_cross,
            "bb_low_usd":     bb_low,
            "bb_up_usd":      bb_up,
            "bb_pos":         bb_pos,
            "price_now_usd":  price_now,
            "chg_7d":         chg_7d,
            "chg_30d":        chg_30d,
            "score":          score,
            "signals":        signals,
            "recommendation": recommendation,
            "invest_advice":  invest_advice,
            "target_dip_usd": bb_low,
            "recovery_usd":   sma20,
        }
    except Exception as exc:
        logger.warning(f"Gold analysis failed: {exc}")
        return None


# ── Geopolitical news ──────────────────────────────────────────────────────

def get_geopolitical_analysis() -> dict | None:
    """
    Score gold-relevant news headlines for bullish/bearish sentiment.
    Fetches from multiple tickers for broader coverage, de-duplicates headlines.
    """
    try:
        # Cast a wider net: gold futures, gold ETFs, bonds (TLT), macro (SPY), DXY
        _NEWS_TICKERS = ["GC=F", "GLD", "IAU", "TLT", "SPY", "DX-Y.NYB"]
        seen_titles: set = set()
        all_items: list  = []
        for sym in _NEWS_TICKERS:
            try:
                items = yf.Ticker(sym).news or []
                for item in items[:15]:
                    title = (item.get("content") or {}).get("title") or item.get("title", "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_items.append(title)
            except Exception:
                pass

        bull_count = bear_count = 0
        top_headlines = []

        for title in all_items:
            t    = title.lower()
            bull = sum(1 for w in _BULLISH_WORDS if w in t)
            bear = sum(1 for w in _BEARISH_WORDS if w in t)
            bull_count += bull
            bear_count += bear
            if bull or bear:
                top_headlines.append((title, bull, bear))

        top_headlines.sort(key=lambda x: x[1] + x[2], reverse=True)
        top_headlines = top_headlines[:5]
        net = bull_count - bear_count

        if   net >= 5: geo_signal, geo_impact, geo_score = "🔴 HIGH RISK – Strong safe-haven demand",         "War/conflict/tariff news intensifying → gold demand rising fast.",     2
        elif net >= 2: geo_signal, geo_impact, geo_score = "🟠 ELEVATED – Geopolitical tensions active",     "Ongoing tensions/macro risks actively supporting gold prices.",          1
        elif net >= 0: geo_signal, geo_impact, geo_score = "🟡 MODERATE – Mixed macro signals",              "No dominant catalyst. Price driven mainly by technicals.",               0
        else:          geo_signal, geo_impact, geo_score = "🟢 CALM – Risk-off sentiment easing",            "Peace/stabilisation/deal news may reduce gold's safe-haven premium.",  -1

        return {
            "geo_signal":    geo_signal,
            "geo_impact":    geo_impact,
            "geo_score":     geo_score,
            "bull_count":    bull_count,
            "bear_count":    bear_count,
            "top_headlines": top_headlines,
            "total_news":    len(all_items),
        }
    except Exception as exc:
        logger.warning(f"Geopolitical analysis failed: {exc}")
        return None


# ── Global macro signals ───────────────────────────────────────────────────

def get_global_market_signals() -> dict | None:
    """
    Fetch 11 global macro indicators: real yields (TIP), DXY, 10Y yields,
    yield curve, VIX, S&P500, oil, gold/silver ratio, copper, EUR/USD, GLD ETF.
    """
    MACRO_TICKERS = {
        "tip": "TIP", "dxy": "DX-Y.NYB", "yields": "^TNX",
        "short_rate": "^IRX", "vix": "^VIX", "sp500": "^GSPC",
        "oil": "CL=F", "silver": "SI=F", "gold_fut": "GC=F",
        "copper": "HG=F", "eurusd": "EURUSD=X", "gld": "GLD",
    }
    closes: dict  = {}
    volumes: dict = {}
    for name, sym in MACRO_TICKERS.items():
        try:
            h = yf.Ticker(sym).history(period="15d")
            if h is not None and len(h) >= 2:
                closes[name] = h["Close"].dropna()
                if "Volume" in h.columns:
                    volumes[name] = h["Volume"].dropna()
        except Exception:
            pass

    if len(closes) < 2:
        logger.warning("Global macro: too few tickers returned data.")
        return None

    votes: dict        = {}
    descriptions: dict = {}
    raw: dict          = {}

    def _pct(s, n=1):
        if len(s) < n + 1: return 0.0
        return (float(s.iloc[-1]) - float(s.iloc[-1-n])) / float(s.iloc[-1-n]) * 100

    def _pct_window(s, window=5):
        if len(s) < window + 1: return 0.0
        return (float(s.iloc[-1]) - float(s.iloc[-1-window])) / float(s.iloc[-1-window]) * 100

    # 1. Real yields (TIP ETF)
    if "tip" in closes:
        s = closes["tip"]; c1d = _pct(s,1); c5d = _pct_window(s,5)
        raw.update({"tip_val": float(s.iloc[-1]), "tip_1d": c1d, "tip_5d": c5d})
        if   c5d < -0.5 or c1d < -0.3:  votes["real_yield"] = -2; descriptions["real_yield"] = f"TIPS ETF {c1d:+.2f}%/{c5d:+.1f}%(5d) → real yields rising → headwind"
        elif c5d < -0.2 or c1d < -0.15: votes["real_yield"] = -1; descriptions["real_yield"] = f"TIPS ETF {c5d:+.1f}%(5d) → real yields edging up → mild headwind"
        elif c5d >  0.5 or c1d >  0.3:  votes["real_yield"] = +2; descriptions["real_yield"] = f"TIPS ETF {c1d:+.2f}%/{c5d:+.1f}%(5d) → real yields falling → tailwind"
        elif c5d >  0.2 or c1d >  0.15: votes["real_yield"] = +1; descriptions["real_yield"] = f"TIPS ETF {c5d:+.1f}%(5d) → real yields slightly down → mild tailwind"
        else:                            votes["real_yield"] =  0; descriptions["real_yield"] = f"TIPS ETF flat ({c1d:+.2f}%) → real yields stable"

    # 2. DXY
    if "dxy" in closes:
        s = closes["dxy"]; c1d = _pct(s,1); c5d = _pct_window(s,5)
        raw.update({"dxy_val": float(s.iloc[-1]), "dxy_1d": c1d, "dxy_5d": c5d})
        if   c1d > 0.3 or c5d > 0.8:   votes["dxy"] = -2; descriptions["dxy"] = f"DXY {c1d:+.2f}%/{c5d:+.1f}%(5d) → strong dollar → headwind"
        elif c1d > 0.15 or c5d > 0.4:  votes["dxy"] = -1; descriptions["dxy"] = f"DXY {c1d:+.2f}%/{c5d:+.1f}%(5d) → dollar rising → mild headwind"
        elif c1d < -0.3 or c5d < -0.8: votes["dxy"] = +2; descriptions["dxy"] = f"DXY {c1d:+.2f}%/{c5d:+.1f}%(5d) → sharp dollar fall → strong tailwind"
        elif c1d < -0.15 or c5d < -0.4:votes["dxy"] = +1; descriptions["dxy"] = f"DXY {c1d:+.2f}%/{c5d:+.1f}%(5d) → dollar weakening → tailwind"
        else:                           votes["dxy"] =  0; descriptions["dxy"] = f"DXY {c1d:+.2f}% → flat"

    # 3 & 4. Nominal yields + yield curve
    if "yields" in closes:
        s = closes["yields"]; ynow = float(s.iloc[-1]); ychg = ynow - float(s.iloc[-2]); y5d = ynow - float(s.iloc[max(-6,-len(s))])
        raw.update({"yield_now": ynow, "yield_chg": ychg, "yield_5d": y5d})
        if   ychg > 0.08 or y5d > 0.2:  votes["yields"] = -2; descriptions["yields"] = f"10Y {ynow:.2f}% ({ychg:+.2f}) → sharp yield rise → bearish"
        elif ychg > 0.04 or y5d > 0.1:  votes["yields"] = -1; descriptions["yields"] = f"10Y {ynow:.2f}% ({ychg:+.2f}) → rising → mild bearish"
        elif ychg < -0.08 or y5d < -0.2:votes["yields"] = +2; descriptions["yields"] = f"10Y {ynow:.2f}% ({ychg:+.2f}) → sharp fall → strong bullish"
        elif ychg < -0.04 or y5d < -0.1:votes["yields"] = +1; descriptions["yields"] = f"10Y {ynow:.2f}% ({ychg:+.2f}) → falling → bullish"
        else:                            votes["yields"] =  0; descriptions["yields"] = f"10Y {ynow:.2f}% → stable"

    if "short_rate" in closes and "yields" in closes:
        spread = float(closes["yields"].iloc[-1]) - float(closes["short_rate"].iloc[-1])
        raw["yield_curve_spread"] = spread
        if   spread < -1.0: votes["yield_curve"] = +2; descriptions["yield_curve"] = f"Yield curve deeply inverted ({spread:+.2f}%) → recession risk → safe-haven bid"
        elif spread < -0.3: votes["yield_curve"] = +1; descriptions["yield_curve"] = f"Yield curve inverted ({spread:+.2f}%) → mild recession risk → gold support"
        elif spread >  1.5: votes["yield_curve"] = -1; descriptions["yield_curve"] = f"Yield curve steep ({spread:+.2f}%) → healthy economy → risk-on"
        else:               votes["yield_curve"] =  0; descriptions["yield_curve"] = f"Yield curve spread {spread:+.2f}% → normal range"

    # 5. VIX
    if "vix" in closes:
        s = closes["vix"]; vnow = float(s.iloc[-1]); vchg = vnow - float(s.iloc[-2])
        raw.update({"vix_now": vnow, "vix_chg": vchg})
        if   vnow > 30 or vchg > 3.0:  votes["vix"] = +2; descriptions["vix"] = f"VIX {vnow:.1f} ({vchg:+.1f}) → extreme fear → strong safe-haven demand"
        elif vnow > 20 or vchg > 1.5:  votes["vix"] = +1; descriptions["vix"] = f"VIX {vnow:.1f} ({vchg:+.1f}) → elevated fear → safe-haven bid"
        elif vnow < 13 and vchg < -1.5:votes["vix"] = -2; descriptions["vix"] = f"VIX {vnow:.1f} → extreme calm → demand very low"
        elif vnow < 16 and vchg < -0.5:votes["vix"] = -1; descriptions["vix"] = f"VIX {vnow:.1f} → low volatility → reduced safe-haven demand"
        else:                           votes["vix"] =  0; descriptions["vix"] = f"VIX {vnow:.1f} → moderate"

    # 6. S&P 500
    if "sp500" in closes:
        s = closes["sp500"]; c1d = _pct(s,1); c5d = _pct_window(s,5)
        raw.update({"sp500_1d": c1d, "sp500_5d": c5d})
        if   c1d > 1.2 and c5d > 3.0:  votes["risk_assets"] = -2; descriptions["risk_assets"] = f"S&P {c1d:+.1f}%/{c5d:+.1f}%(5d) → strong risk-on → rotation from gold"
        elif c1d > 0.6 and c5d > 1.5:  votes["risk_assets"] = -1; descriptions["risk_assets"] = f"S&P {c1d:+.1f}%/{c5d:+.1f}%(5d) → risk-on → mild rotation from gold"
        elif c1d < -1.2 and c5d < -3.0:votes["risk_assets"] = +2; descriptions["risk_assets"] = f"S&P {c1d:+.1f}%/{c5d:+.1f}%(5d) → sharp selloff → strong safe-haven bid"
        elif c1d < -0.6 and c5d < -1.5:votes["risk_assets"] = +1; descriptions["risk_assets"] = f"S&P {c1d:+.1f}%/{c5d:+.1f}%(5d) → risk-off → safe-haven bid"
        else:                           votes["risk_assets"] =  0; descriptions["risk_assets"] = f"S&P {c1d:+.1f}% → mixed"

    # 7. Oil
    if "oil" in closes:
        s = closes["oil"]; c5d = _pct_window(s,5)
        raw["oil_5d"] = c5d
        if   c5d > 5.0:  votes["oil"] = +2; descriptions["oil"] = f"Oil {c5d:+.1f}%(5d) → strong inflation → gold boost"
        elif c5d > 2.5:  votes["oil"] = +1; descriptions["oil"] = f"Oil {c5d:+.1f}%(5d) → rising inflation → mild gold boost"
        elif c5d < -5.0: votes["oil"] = -2; descriptions["oil"] = f"Oil {c5d:+.1f}%(5d) → deflation risk → gold drag"
        elif c5d < -2.5: votes["oil"] = -1; descriptions["oil"] = f"Oil {c5d:+.1f}%(5d) → softening commodities → mild drag"
        else:            votes["oil"] =  0; descriptions["oil"] = f"Oil {c5d:+.1f}%(5d) → neutral"

    # 8. Gold/Silver ratio
    if "silver" in closes and "gold_fut" in closes:
        g_val = float(closes["gold_fut"].iloc[-1]); s_val = float(closes["silver"].iloc[-1])
        ratio = g_val / s_val if s_val > 0 else 80.0
        raw["gold_silver_ratio"] = round(ratio, 1)
        if   ratio > 90: votes["silver_ratio"] = -1; descriptions["silver_ratio"] = f"G/S ratio {ratio:.0f} → gold expensive vs silver → correction risk"
        elif ratio > 80: votes["silver_ratio"] =  0; descriptions["silver_ratio"] = f"G/S ratio {ratio:.0f} → slightly elevated"
        elif ratio < 65: votes["silver_ratio"] = +1; descriptions["silver_ratio"] = f"G/S ratio {ratio:.0f} → gold cheap vs silver"
        else:            votes["silver_ratio"] =  0; descriptions["silver_ratio"] = f"G/S ratio {ratio:.0f} → normal range"

    # 9. Copper
    if "copper" in closes:
        s = closes["copper"]; c5d = _pct_window(s,5); c1d = _pct(s,1)
        raw["copper_5d"] = c5d
        if   c5d < -4.0 or c1d < -2.0: votes["copper"] = +2; descriptions["copper"] = f"Copper {c5d:+.1f}%(5d) → sharp economic fear → gold UP"
        elif c5d < -2.0 or c1d < -1.0: votes["copper"] = +1; descriptions["copper"] = f"Copper {c5d:+.1f}%(5d) → economic uncertainty → mild gold support"
        elif c5d >  4.0 or c1d >  2.0: votes["copper"] = -2; descriptions["copper"] = f"Copper {c5d:+.1f}%(5d) → economic optimism → risk-on drags gold"
        elif c5d >  2.0 or c1d >  1.0: votes["copper"] = -1; descriptions["copper"] = f"Copper {c5d:+.1f}%(5d) → economic strength → mild drag"
        else:                           votes["copper"] =  0; descriptions["copper"] = f"Copper {c5d:+.1f}%(5d) → neutral"

    # 10. EUR/USD
    if "eurusd" in closes:
        s = closes["eurusd"]; c1d = _pct(s,1); c5d = _pct_window(s,5)
        raw.update({"eurusd_val": float(s.iloc[-1]), "eurusd_5d": c5d})
        if   c5d > 1.0 or c1d > 0.5:  votes["eur_usd"] = +1; descriptions["eur_usd"] = f"EUR/USD {c1d:+.2f}%/{c5d:+.1f}%(5d) → euro rising → gold tailwind"
        elif c5d < -1.0 or c1d < -0.5:votes["eur_usd"] = -1; descriptions["eur_usd"] = f"EUR/USD {c1d:+.2f}%/{c5d:+.1f}%(5d) → euro falling → gold headwind"
        else:                          votes["eur_usd"] =  0; descriptions["eur_usd"] = f"EUR/USD {c1d:+.2f}% → flat"

    # 11. GLD ETF flow
    if "gld" in closes and "gld" in volumes:
        s = closes["gld"]; v = volumes["gld"]; c5d = _pct_window(s,5)
        v_list = [float(v.iloc[i]) for i in range(-min(6,len(v)), 0)]
        if len(v_list) >= 6:
            v_recent = sum(v_list[-3:]) / 3; v_prior = sum(v_list[:3]) / 3
            v_trend  = (v_recent - v_prior) / max(v_prior, 1) * 100
        else:
            v_trend = 0.0
        raw.update({"gld_5d": c5d, "gld_vol_trend": v_trend})
        if   c5d > 2.0 and v_trend > 10: votes["etf_flow"] = +2; descriptions["etf_flow"] = f"GLD +{c5d:.1f}%(5d) + volume surge → strong institutional buying"
        elif c5d > 1.0:                  votes["etf_flow"] = +1; descriptions["etf_flow"] = f"GLD {c5d:+.1f}%(5d) → ETF inflow momentum"
        elif c5d < -2.0 and v_trend > 10:votes["etf_flow"] = -2; descriptions["etf_flow"] = f"GLD {c5d:.1f}%(5d) + volume → heavy selling"
        elif c5d < -1.0:                 votes["etf_flow"] = -1; descriptions["etf_flow"] = f"GLD {c5d:+.1f}%(5d) → outflow"
        else:                            votes["etf_flow"] =  0; descriptions["etf_flow"] = f"GLD {c5d:+.1f}%(5d) → neutral ETF flow"

    # Gold 5d momentum
    if "gold_fut" in closes:
        s = closes["gold_fut"]; c5d = _pct_window(s,5); c1d = _pct(s,1)
        raw.update({"gold_5d": c5d, "gold_1d": c1d})
        if   c5d > 3.0:  votes["gold_momentum"] = +2; descriptions["gold_momentum"] = f"COMEX gold +{c5d:.1f}%(5d) → strong uptrend"
        elif c5d > 1.5:  votes["gold_momentum"] = +1; descriptions["gold_momentum"] = f"COMEX gold {c5d:+.1f}%(5d) → mild upward momentum"
        elif c5d < -3.0: votes["gold_momentum"] = -2; descriptions["gold_momentum"] = f"COMEX gold {c5d:.1f}%(5d) → strong downtrend"
        elif c5d < -1.5: votes["gold_momentum"] = -1; descriptions["gold_momentum"] = f"COMEX gold {c5d:+.1f}%(5d) → mild downward momentum"
        else:            votes["gold_momentum"] =  0; descriptions["gold_momentum"] = f"COMEX gold {c5d:+.1f}%(5d) → ranging"

    net = sum(votes.values())
    if   net >= 5:  outlook = "🟢 Strong tailwinds — multiple bullish forces aligned"
    elif net >= 2:  outlook = "🟢 Tailwinds (weak dollar / falling yields / fear)"
    elif net == 1:  outlook = "🟡 Mildly positive for gold"
    elif net == 0:  outlook = "⚪ Mixed — no clear macro direction"
    elif net == -1: outlook = "🟠 Mildly negative for gold"
    elif net >= -4: outlook = "🔴 Headwinds (strong dollar / rising yields / risk-on)"
    else:           outlook = "🔴 Strong headwinds — multiple bearish forces aligned"

    logger.info(
        f"Global macro: real_yield={votes.get('real_yield',0)}  DXY={votes.get('dxy',0)}  "
        f"10Y={votes.get('yields',0)}  curve={votes.get('yield_curve',0)}  "
        f"VIX={votes.get('vix',0)}  S&P={votes.get('risk_assets',0)}  "
        f"oil={votes.get('oil',0)}  Ag/Au={votes.get('silver_ratio',0)}  "
        f"Cu={votes.get('copper',0)}  EUR={votes.get('eur_usd',0)}  "
        f"GLD={votes.get('etf_flow',0)}  mom={votes.get('gold_momentum',0)}  net={net}"
    )
    return {**raw, "votes": votes, "descriptions": descriptions,
            "net_score": net, "global_outlook": outlook}


# ── Market regime ──────────────────────────────────────────────────────────

def get_market_regime(global_signals: dict | None, analysis: dict | None) -> dict:
    """Classify macro regime: RISK_OFF_HIGH / RISK_OFF / NEUTRAL / RISK_ON / RISK_ON_HIGH."""
    if not global_signals:
        return {"regime": "NEUTRAL", "strength": 0.5,
                "description": "No macro data", "drift_factor": 1.0}

    votes    = global_signals.get("votes", {})
    vix_now  = global_signals.get("vix_now", 18)
    sp5d     = global_signals.get("sp500_5d", 0)
    dxy_5d   = global_signals.get("dxy_5d", 0)
    tip_5d   = global_signals.get("tip_5d", 0)
    g5d      = global_signals.get("gold_5d", 0)

    gold_trending_up   = g5d > 1.5
    gold_trending_down = g5d < -1.5

    risk_off_signals = sum([vix_now > 25, sp5d < -2.0, dxy_5d < -0.5, tip_5d > 0.3,
                            votes.get("copper", 0) > 0, gold_trending_up])
    risk_on_signals  = sum([vix_now < 15, sp5d > 2.0,  dxy_5d > 0.5,  tip_5d < -0.3,
                            votes.get("copper", 0) < 0, gold_trending_down])

    if   risk_off_signals >= 5: regime, desc, df = "RISK_OFF_HIGH", "Extreme risk-off: flight to gold",    1.6
    elif risk_off_signals >= 3: regime, desc, df = "RISK_OFF",      "Risk-off: safe-haven demand rising",   1.25
    elif risk_on_signals >= 5:  regime, desc, df = "RISK_ON_HIGH",  "Extreme risk-on: gold under pressure", 0.6
    elif risk_on_signals >= 3:  regime, desc, df = "RISK_ON",       "Risk-on: gold facing headwinds",       0.8
    else:                       regime, desc, df = "NEUTRAL",       "Mixed signals — no dominant regime",   1.0

    strength = round(min(1.0, max(risk_off_signals, risk_on_signals) / 6), 2)
    logger.info(f"Market regime: {regime} (strength={strength:.0%}, drift_factor={df}×)")
    return {"regime": regime, "strength": strength, "description": desc,
            "drift_factor": df, "risk_off_count": risk_off_signals, "risk_on_count": risk_on_signals}


# ── Best monthly payment date ──────────────────────────────────────────────

def get_best_payment_date() -> dict | None:
    """
    Three analyses for an 11-month gold scheme:
      1. Best day of month (historically lowest price)
      2. Best calendar month to start the scheme (detrended 5-year data)
      3. Current month actual low + trend
    """
    _MONTH_NAMES = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                    7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    _MONTH_FULL  = {1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
                    7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"}
    try:
        hist = yf.Ticker("GC=F").history(period="5y")
        if hist is None or len(hist) < 60:
            logger.warning("Not enough history for payment date analysis.")
            return None

        hist = hist[["Close","Low"]].copy()
        hist.index = hist.index.tz_localize(None)
        hist["day"]       = hist.index.day
        hist["month"]     = hist.index.to_period("M")
        hist["cal_month"] = hist.index.month
        hist["year_val"]  = hist.index.year

        def day_of_monthly_low(group):
            return int(group.loc[group["Close"].idxmin(), "day"])

        monthly_low_days = hist.groupby("month", group_keys=False).apply(day_of_monthly_low)
        freq             = monthly_low_days[monthly_low_days <= 28].value_counts()
        best_day_by_freq = int(freq.idxmax())
        top3_days_by_freq = [int(d) for d in freq.head(3).index.tolist()]

        def pct_above_low(group):
            lo = group["Close"].min()
            group = group.copy()
            group["pct_above_low"] = ((group["Close"] - lo) / lo) * 100
            return group

        hist     = hist.groupby("month", group_keys=False).apply(pct_above_low)
        day_avg  = hist[hist["day"] <= 28].groupby("day")["pct_above_low"].mean().sort_values()
        ranking  = [(int(d), round(float(v), 2)) for d, v in day_avg.items()]
        best_day = best_day_by_freq
        top3_days = top3_days_by_freq

        # Best start month (detrended)
        annual_avg         = hist.groupby("year_val")["Close"].transform("mean")
        hist["norm_close"] = hist["Close"] / annual_avg
        norm_by_cal        = hist.groupby("cal_month")["norm_close"].mean()
        scheme_avgs        = {}
        for start_m in range(1, 13):
            months_11 = [(start_m - 1 + i) % 12 + 1 for i in range(11)]
            vals = norm_by_cal[norm_by_cal.index.isin(months_11)]
            scheme_avgs[start_m] = float(vals.mean()) if len(vals) > 0 else 1.0
        scheme_rank     = sorted(scheme_avgs.items(), key=lambda x: x[1])
        best_start_m    = scheme_rank[0][0]
        min_avg         = scheme_rank[0][1]
        scheme_rank_pct = [(m, round((avg / min_avg - 1) * 100, 1)) for m, avg in scheme_rank]
        top3_starts     = scheme_rank_pct[:3]
        worst_start_pct = scheme_rank_pct[-1][1]

        # Current month actual
        today      = date.today()
        this_month = hist[hist.index.date >= today.replace(day=1)].copy()
        current_month_low_day   = None
        current_month_low_price = None
        current_month_low_date  = None
        current_month_trend     = None

        if len(this_month) >= 2:
            low_idx                 = this_month["Low"].idxmin()
            current_month_low_price = float(this_month.loc[low_idx, "Low"])
            current_month_low_date  = low_idx.date()
            current_month_low_day   = int(current_month_low_date.day)
            if len(this_month) >= 5:
                recent  = float(this_month["Close"].iloc[-3:].mean())
                earlier = float(this_month["Close"].iloc[-6:-3].mean()) if len(this_month) >= 6 else recent
                if   recent < earlier * 0.998: current_month_trend = "falling"
                elif recent > earlier * 1.002: current_month_trend = "rising"
                else:                          current_month_trend = "flat"

        def ordinal(n):
            return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"

        try:
            best_date_this_month = today.replace(day=best_day)
        except ValueError:
            best_date_this_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])

        if best_date_this_month < today:
            nm = today.month % 12 + 1
            ny = today.year + (1 if today.month == 12 else 0)
            try:
                best_date_next_month = today.replace(year=ny, month=nm, day=best_day)
            except ValueError:
                best_date_next_month = today.replace(year=ny, month=nm, day=calendar.monthrange(ny, nm)[1])
        else:
            best_date_next_month = None

        ws = max(1, best_day - 1); we = min(28, best_day + 1)
        this_month_window = f"{ordinal(ws)} – {ordinal(we)} {best_date_this_month.strftime('%B')}"

        return {
            "best_day":               best_day,
            "best_date_this_month":   best_date_this_month,
            "best_date_next_month":   best_date_next_month,
            "top3_days":              top3_days,
            "worst_day":              ranking[-1][0],
            "this_month_window":      this_month_window,
            "ranking":                ranking,
            "best_pct_above_low":     dict(ranking).get(best_day, 0.0),
            "worst_pct_above_low":    ranking[-1][1],
            "freq_months":            int(freq.get(best_day, 0)),
            "total_months":           int(len(monthly_low_days)),
            "current_month_low_day":   current_month_low_day,
            "current_month_low_price": current_month_low_price,
            "current_month_low_date":  current_month_low_date,
            "current_month_trend":     current_month_trend,
            "days_elapsed":            today.day,
            "scheme_best_start_month": best_start_m,
            "scheme_best_start_name":  _MONTH_FULL[best_start_m],
            "scheme_top3_starts":      top3_starts,
            "scheme_worst_start_pct":  worst_start_pct,
            "scheme_month_names":      _MONTH_NAMES,
        }
    except Exception as exc:
        logger.warning(f"Best payment date analysis failed: {exc}")
        return None
