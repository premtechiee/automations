"""
stock_analyzer/fundamentals.py
===============================
Turn yfinance `.info` fields into a 0-100 fundamentals score.

The score rewards:
    • sensible valuation (P/E, P/B, PEG not absurd)
    • profitability (ROE, margins)
    • moderate leverage (debt/equity)
    • growth (earnings growth)
    • payouts (dividend yield) — optional bonus

Missing fields are tolerated — each sub-score is averaged only over
metrics that were actually available for the ticker.
"""

from __future__ import annotations


def _band(value: float, good: float, bad: float) -> float:
    """
    Map `value` to 0..100 assuming `good` → 100 and `bad` → 0.
    Handles either direction (good > bad or good < bad) and clips.
    """
    if value is None:
        return None  # type: ignore[return-value]
    if good == bad:
        return 50.0
    ratio = (value - bad) / (good - bad)
    return max(0.0, min(100.0, ratio * 100))


def score_fundamentals(info: dict) -> dict:
    """
    Returns {'score': 0..100, 'details': {...}}.
    """
    g = info.get  # shortcut

    subs: dict[str, float] = {}

    pe = g("trailingPE") or g("forwardPE")
    if pe and pe > 0:
        subs["valuation_pe"] = _band(pe, good=15, bad=60)

    pb = g("priceToBook")
    if pb and pb > 0:
        subs["valuation_pb"] = _band(pb, good=2, bad=10)

    peg = g("pegRatio")
    if peg and peg > 0:
        subs["valuation_peg"] = _band(peg, good=1, bad=3)

    roe = g("returnOnEquity")
    if roe is not None:
        subs["profit_roe"] = _band(roe * 100 if abs(roe) < 2 else roe,
                                   good=25, bad=5)

    pm = g("profitMargins")
    if pm is not None:
        subs["profit_margin"] = _band(pm * 100 if abs(pm) < 2 else pm,
                                      good=20, bad=2)

    de = g("debtToEquity")
    if de is not None:
        # yfinance often returns debt/equity as a percent (e.g. 120 = 1.2x)
        de_ratio = de / 100 if de > 5 else de
        subs["leverage_de"] = _band(de_ratio, good=0.3, bad=2.0)

    eg = g("earningsGrowth") or g("earningsQuarterlyGrowth")
    if eg is not None:
        subs["growth_earnings"] = _band(eg * 100 if abs(eg) < 5 else eg,
                                        good=25, bad=-10)

    rg = g("revenueGrowth")
    if rg is not None:
        subs["growth_revenue"] = _band(rg * 100 if abs(rg) < 5 else rg,
                                       good=20, bad=-5)

    dy = g("dividendYield")
    if dy is not None:
        subs["div_yield"] = _band(dy * 100 if dy < 1 else dy,
                                  good=3, bad=0)

    score = sum(subs.values()) / len(subs) if subs else 50.0

    return {
        "score":   round(score, 1),
        "details": {k: round(v, 1) for k, v in subs.items()},
        "pe":      pe,
        "pb":      pb,
        "roe":     roe,
        "de":      de,
        "mcap":    g("marketCap"),
        "sector":  g("sector") or g("industry") or "—",
        "name":    g("longName") or g("shortName") or "—",
    }
