"""
stock_analyzer/nse.py
======================
Free NSE India data fetchers (no account, no API key).

Public endpoints used:
  • FII/DII activity         – /api/fiidiiTradeReact
  • Corporate announcements  – /api/corporate-announcements
  • Equity option-chain      – /api/option-chain-equities?symbol=...
  • Index   option-chain     – /api/option-chain-indices?symbol=NIFTY

NSE blocks raw requests — the session must first visit nseindia.com to set
cookies before hitting /api/*. We cache the warm session for the run.

All fetchers are fail-soft: any error returns an empty/neutral result so
the rest of the pipeline keeps working when NSE is down or throttling.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from lib.proxy import PROXIES

logger = logging.getLogger(__name__)

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}


def _make_nse_session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=2, pool_maxsize=2)
    s.mount("https://", adapter)
    s.headers.update(_NSE_HEADERS)
    if PROXIES:
        s.proxies.update(PROXIES)
    return s


_SESSION: requests.Session | None = None
_WARMED = False
_NSE_DEAD = False  # if warmup ever fails, give up for the rest of the run


def _ensure_session() -> requests.Session | None:
    """Visit the NSE landing page so the API endpoints accept us."""
    global _SESSION, _WARMED, _NSE_DEAD
    if _NSE_DEAD:
        return None
    if _SESSION is not None and _WARMED:
        return _SESSION
    _SESSION = _make_nse_session()
    try:
        # Hit the homepage and the market-data page — sets several cookies
        _SESSION.get("https://www.nseindia.com/", timeout=(4, 8))
        _SESSION.get("https://www.nseindia.com/option-chain",
                     timeout=(4, 8))
        _WARMED = True
        return _SESSION
    except Exception as exc:
        logger.debug(f"NSE warmup failed: {exc}")
        _NSE_DEAD = True
        return None


def _get_json(path: str, params: dict | None = None) -> dict | None:
    s = _ensure_session()
    if s is None:
        return None
    url = f"https://www.nseindia.com{path}"
    try:
        r = s.get(url, params=params or {}, timeout=(4, 10))
        if r.status_code != 200:
            logger.debug(f"NSE {path} -> {r.status_code}")
            return None
        return r.json()
    except Exception as exc:
        logger.debug(f"NSE {path} failed: {exc}")
        return None


# ── 1. FII / DII daily flows ────────────────────────────────────────────────

def fetch_fii_dii() -> dict[str, Any]:
    """
    Latest FII + DII cash market activity (₹ crore).

    Returns:
        {
          "available": bool,
          "date":      "YYYY-MM-DD",
          "fii_buy":   <crore>,
          "fii_sell":  <crore>,
          "fii_net":   <crore>,    # +ve = inflow (bullish)
          "dii_buy":   <crore>,
          "dii_sell":  <crore>,
          "dii_net":   <crore>,    # +ve = inflow (bullish)
          "verdict":   "STRONG-BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG-SELL"
        }
    """
    j = _get_json("/api/fiidiiTradeReact")
    out: dict[str, Any] = {"available": False}
    if not isinstance(j, list) or not j:
        return out

    fii = next((r for r in j if str(r.get("category", "")).upper().startswith("FII")), None)
    dii = next((r for r in j if str(r.get("category", "")).upper().startswith("DII")), None)
    if not fii or not dii:
        return out

    def _f(d: dict, k: str) -> float:
        try:
            return float(d.get(k) or 0)
        except Exception:
            return 0.0

    fii_net = _f(fii, "netValue")
    dii_net = _f(dii, "netValue")
    combined = fii_net + dii_net

    # Verdict — both flows bullish or both bearish dominate
    if   combined >  3000: verdict = "STRONG-BUY"
    elif combined >  1000: verdict = "BUY"
    elif combined < -3000: verdict = "STRONG-SELL"
    elif combined < -1000: verdict = "SELL"
    else:                  verdict = "NEUTRAL"

    out.update({
        "available": True,
        "date":      str(fii.get("date") or datetime.now().strftime("%d-%b-%Y")),
        "fii_buy":   _f(fii, "buyValue"),
        "fii_sell":  _f(fii, "sellValue"),
        "fii_net":   round(fii_net, 1),
        "dii_buy":   _f(dii, "buyValue"),
        "dii_sell":  _f(dii, "sellValue"),
        "dii_net":   round(dii_net, 1),
        "combined_net": round(combined, 1),
        "verdict":   verdict,
    })
    return out


# ── 2. Corporate announcements (board meetings / results / insider trades) ──

def fetch_corp_announcements(max_items: int = 80) -> list[dict[str, Any]]:
    """
    Latest filings from NSE corporate announcements.
    Returns up to `max_items` items: [{symbol, subject, date}, ...]
    """
    j = _get_json("/api/corporate-announcements", {"index": "equities"})
    if not isinstance(j, list):
        return []
    items: list[dict[str, Any]] = []
    for row in j[:max_items]:
        items.append({
            "symbol":  row.get("symbol") or "",
            "subject": (row.get("subject") or row.get("desc") or "").strip()[:160],
            "date":    row.get("an_dt") or row.get("sort_date") or "",
        })
    return items


def announcements_for(symbol: str, all_items: list[dict]) -> list[dict]:
    """Filter announcements for a given symbol root (RELIANCE.NS -> RELIANCE)."""
    root = symbol.split(".")[0].upper()
    return [a for a in all_items if str(a.get("symbol") or "").upper() == root][:5]


# ── 3. Option chain — PCR + max-pain ────────────────────────────────────────

def _pcr_and_maxpain(records: list[dict], spot: float) -> dict[str, Any]:
    """Internal: compute PCR(OI) and max-pain from option-chain rows.
    `records` is the `filtered.data` list returned by NSE's option-chain APIs.
    """
    total_ce_oi = total_pe_oi = 0.0
    pain_by_strike: dict[float, float] = {}
    strikes_seen: set[float] = set()

    for r in records:
        try:
            strike = float(r.get("strikePrice") or 0)
        except Exception:
            continue
        if strike <= 0:
            continue
        strikes_seen.add(strike)
        ce = r.get("CE") or {}
        pe = r.get("PE") or {}
        ce_oi = float(ce.get("openInterest") or 0)
        pe_oi = float(pe.get("openInterest") or 0)
        total_ce_oi += ce_oi
        total_pe_oi += pe_oi
        # Aggregate per-strike OI for max-pain calculation later
        pain_by_strike[strike] = pain_by_strike.get(strike, 0)

    if total_ce_oi <= 0 and total_pe_oi <= 0:
        return {}

    pcr = (total_pe_oi / total_ce_oi) if total_ce_oi > 0 else 0.0

    # Max-pain: at each strike S, total pain = Σ CE_OI*max(spot-S,0) + PE_OI*max(S-spot,0)
    # We iterate strikes; pick strike with min pain.
    pain: dict[float, float] = {}
    for s in sorted(strikes_seen):
        p_total = 0.0
        for r in records:
            try:
                k = float(r.get("strikePrice") or 0)
            except Exception:
                continue
            ce = (r.get("CE") or {})
            pe = (r.get("PE") or {})
            ce_oi = float(ce.get("openInterest") or 0)
            pe_oi = float(pe.get("openInterest") or 0)
            if s > k:
                p_total += ce_oi * (s - k)
            elif s < k:
                p_total += pe_oi * (k - s)
        pain[s] = p_total

    if not pain:
        return {}

    max_pain_strike = min(pain.items(), key=lambda kv: kv[1])[0]

    # Sentiment from PCR (OI-based)
    if   pcr >= 1.30: bias = "BULLISH"      # heavy put writing
    elif pcr >= 1.05: bias = "MILD-BULLISH"
    elif pcr >= 0.85: bias = "NEUTRAL"
    elif pcr >= 0.65: bias = "MILD-BEARISH"
    else:             bias = "BEARISH"      # heavy call writing

    # Distance from spot to max-pain (% of spot)
    drift_pct = ((max_pain_strike - spot) / spot * 100) if spot else 0

    return {
        "pcr":               round(pcr, 2),
        "ce_oi_total":       round(total_ce_oi),
        "pe_oi_total":       round(total_pe_oi),
        "max_pain":          round(max_pain_strike, 2),
        "max_pain_drift_pct": round(drift_pct, 2),
        "bias":              bias,
    }


def fetch_index_option_chain(symbol: str = "NIFTY") -> dict[str, Any]:
    """PCR + max-pain for an INDEX (NIFTY / BANKNIFTY / FINNIFTY)."""
    j = _get_json("/api/option-chain-indices", {"symbol": symbol})
    if not isinstance(j, dict):
        return {}
    rec = ((j.get("filtered") or {}).get("data")) or (j.get("records") or {}).get("data") or []
    spot = (((j.get("records") or {}).get("underlyingValue")) or 0)
    try:
        spot = float(spot)
    except Exception:
        spot = 0.0
    out = _pcr_and_maxpain(rec, spot)
    if out:
        out["symbol"] = symbol
        out["spot"]   = spot
    return out


def fetch_equity_option_chain(symbol: str) -> dict[str, Any]:
    """PCR + max-pain for an EQUITY (e.g. 'RELIANCE'). Strip .NS / .BO suffix."""
    sym = symbol.split(".")[0].upper()
    j = _get_json("/api/option-chain-equities", {"symbol": sym})
    if not isinstance(j, dict):
        return {}
    rec = ((j.get("filtered") or {}).get("data")) or (j.get("records") or {}).get("data") or []
    spot = (((j.get("records") or {}).get("underlyingValue")) or 0)
    try:
        spot = float(spot)
    except Exception:
        spot = 0.0
    out = _pcr_and_maxpain(rec, spot)
    if out:
        out["symbol"] = sym
        out["spot"]   = spot
    return out
