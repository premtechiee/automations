"""
stock_analyzer/fetchers.py
===========================
All external-data I/O:
  • OHLCV + fundamentals via Yahoo Finance HTTP endpoints (no yfinance dep)
  • Mutual-fund NAV history via mfapi.in
  • Headlines via RSS
"""

from __future__ import annotations
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore

from lib.proxy import PROXIES

from .config import NEWS_RSS_FEEDS

logger = logging.getLogger(__name__)

# Real desktop Chrome UA — required for Yahoo's chart/quote endpoints.
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _make_session() -> requests.Session:
    s = requests.Session()
    # No urllib3 Retry — we want fail-fast on dead networks. One try only.
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(_UA)
    if PROXIES:
        s.proxies.update(PROXIES)
    return s


_SESSION = _make_session()
# Per-host blocklist: once a host fails twice, skip it for the rest of the run
# so we don't waste time retrying a blocked endpoint on every ticker.
# Per-host failure counters.  Only AUTH failures (429/401/403) kill a host;
# timeouts / parse errors are per-symbol and must not poison the whole run.
_DEAD_HOSTS: dict[str, int] = {}
_DEAD_THRESHOLD_AUTH  = 2   # 401/403/429 → whole host is blocking us
_DEAD_THRESHOLD_OTHER = 5   # timeout / parse → might be symbol-specific

# One-time Yahoo crumb (required by Yahoo since ~2024 without it = empty results)
_YF_CRUMB: str | None = None
_YF_CRUMB_TRIED: bool = False


def _host_dead(host: str) -> bool:
    return _DEAD_HOSTS.get(host, 0) >= _DEAD_THRESHOLD_AUTH


def _mark_host_auth_failed(host: str) -> None:
    """Call on 401/403/429 — hard block for remaining run."""
    _DEAD_HOSTS[host] = max(_DEAD_HOSTS.get(host, 0) + 1, _DEAD_THRESHOLD_AUTH)


def _mark_host_failed(host: str) -> None:
    """Legacy shim — only increments, never hard-blocks."""
    _DEAD_HOSTS[host] = _DEAD_HOSTS.get(host, 0) + 1


def _ensure_crumb() -> str | None:
    """Fetch a Yahoo Finance crumb token (needed since 2024 to get real data).
    Establishes a browser-like session so cookies are set before chart calls."""
    global _YF_CRUMB, _YF_CRUMB_TRIED
    if _YF_CRUMB_TRIED:
        return _YF_CRUMB
    _YF_CRUMB_TRIED = True
    try:
        # Visit the landing page to get Yahoo session cookies
        _SESSION.get("https://finance.yahoo.com", timeout=(4, 8))
        r = _SESSION.get(
            "https://query2.finance.yahoo.com/v1/test/getcrumb",
            timeout=(4, 8),
        )
        if r.status_code == 200 and r.text.strip():
            _YF_CRUMB = r.text.strip()
            logger.debug(f"Yahoo crumb obtained: {_YF_CRUMB[:8]}…")
    except Exception as exc:
        logger.debug(f"Crumb fetch skipped: {exc}")
    return _YF_CRUMB



# ── Stocks ──────────────────────────────────────────────────────────────────

_YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
_YF_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_STOOQ_URL    = "https://stooq.com/q/d/l/"  # CSV daily OHLCV fallback


def _period_to_range(period: str) -> str:
    p = period.lower().strip()
    return {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y",
            "2y": "2y", "5y": "5y", "ytd": "ytd", "max": "max"}.get(p, "6mo")


_YF_CHART_URL2 = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}"


def _fetch_history_yahoo(symbol: str, period: str, interval: str):
    """Yahoo chart endpoint — tries query1 then query2, with crumb."""
    import pandas as pd

    if _host_dead("yahoo"):
        return pd.DataFrame()

    crumb  = _ensure_crumb()
    rng    = _period_to_range(period)
    params: dict = {"range": rng, "interval": interval, "includePrePost": "false"}
    if crumb:
        params["crumb"] = crumb

    payload = None
    for base_url in (_YF_CHART_URL, _YF_CHART_URL2):
        url = base_url.format(sym=symbol)
        try:
            r = _SESSION.get(url, params=params, timeout=(4, 8))
            if r.status_code in (401, 403, 429):
                _mark_host_auth_failed("yahoo")
                logger.debug(f"[{symbol}] Yahoo chart blocked ({r.status_code}) on {url}")
                break  # auth failure — no point trying query2 with same session
            if r.status_code != 200:
                logger.debug(f"[{symbol}] Yahoo {r.status_code} on {url}")
                continue
            j = r.json()
            result = (j.get("chart") or {}).get("result") or []
            if result:
                payload = j
                break  # got data
            # empty result — try query2
        except Exception as exc:
            logger.debug(f"[{symbol}] Yahoo chart failed ({url}): {exc}")
            # timeout/parse = symbol-specific, don't kill the whole host

    if payload is None:
        return pd.DataFrame()


    try:
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return pd.DataFrame()
        node = result[0]
        ts   = node.get("timestamp") or []
        ind  = (node.get("indicators") or {}).get("quote") or [{}]
        q    = ind[0] if ind else {}
        adj  = ((node.get("indicators") or {}).get("adjclose") or [{}])
        adjc = (adj[0].get("adjclose") if adj else None) or [None] * len(ts)
        if not ts:
            return pd.DataFrame()
        df = pd.DataFrame({
            "Open":      q.get("open")   or [None] * len(ts),
            "High":      q.get("high")   or [None] * len(ts),
            "Low":       q.get("low")    or [None] * len(ts),
            "Close":     q.get("close")  or [None] * len(ts),
            "Adj Close": adjc,
            "Volume":    q.get("volume") or [0] * len(ts),
        }, index=pd.to_datetime(ts, unit="s"))
        df = df.dropna(subset=["Close"])
        return df
    except Exception as exc:
        logger.debug(f"[{symbol}] Yahoo chart parse failed: {exc}")
        return pd.DataFrame()


def _stooq_symbol(symbol: str) -> str | None:
    """Convert Yahoo NSE symbol -> Stooq symbol. e.g. RELIANCE.NS -> reliance.in"""
    s = symbol.lower()
    if s.endswith(".ns"):
        return s.replace(".ns", ".in")
    if s.endswith(".bo"):
        return s.replace(".bo", ".in")
    return None


def _fetch_history_stooq(symbol: str):
    """Free CSV fallback for Indian stocks via stooq.com."""
    import pandas as pd
    from io import StringIO

    if _host_dead("stooq"):
        return pd.DataFrame()

    sq = _stooq_symbol(symbol)
    if not sq:
        return pd.DataFrame()
    try:
        r = _SESSION.get(_STOOQ_URL, params={"s": sq, "i": "d"}, timeout=(4, 8))
        if r.status_code in (401, 403, 429):
            _mark_host_auth_failed("stooq")
            return pd.DataFrame()
        if r.status_code != 200 or not r.text or r.text.strip().startswith("No data"):
            # non-auth failure — count but don't hard-block
            _mark_host_failed("stooq")
            return pd.DataFrame()
        df = pd.read_csv(StringIO(r.text))
        if df.empty or "Close" not in df.columns:
            return pd.DataFrame()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        df = df.rename(columns=str.title)
        df = df.tail(180)
        if "Adj Close" not in df.columns:
            df["Adj Close"] = df["Close"]
        return df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
    except Exception as exc:
        logger.debug(f"[{symbol}] Stooq failed: {exc}")
        # timeout = likely symbol-specific, don't kill stooq for everyone
        return pd.DataFrame()


# ── NSE India direct API (authoritative for .NS symbols) ───────────────────

_NSE_BASE  = "https://www.nseindia.com"
_NSE_HIST  = f"{_NSE_BASE}/api/historical/cm/equity"
_NSE_SESSION: requests.Session | None = None
_NSE_INIT: bool = False


def _nse_session() -> "requests.Session | None":
    """Return a warmed-up NSE session (homepage loads Cloudflare cookies)."""
    global _NSE_SESSION, _NSE_INIT
    if _NSE_INIT:
        return _NSE_SESSION
    _NSE_INIT = True
    if _host_dead("nse"):
        return None
    s = requests.Session()
    s.headers.update({
        "User-Agent": _UA["User-Agent"],
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
    })
    if PROXIES:
        s.proxies.update(PROXIES)
    try:
        # Load cookies / pass Cloudflare challenge
        s.get(_NSE_BASE, timeout=(5, 10))
        _NSE_SESSION = s
    except Exception as exc:
        logger.debug(f"NSE session init failed: {exc}")
        _mark_host_auth_failed("nse")
    return _NSE_SESSION


def _fetch_history_nse(symbol: str):
    """NSE India historical cash-market data for .NS symbols.
    Returns the same-format DataFrame as the Yahoo/Stooq fetchers."""
    import pandas as pd
    from datetime import timedelta

    if _host_dead("nse"):
        return pd.DataFrame()
    if not symbol.upper().endswith(".NS"):
        return pd.DataFrame()  # BSE / US symbols not handled here

    sym = symbol.upper().removesuffix(".NS")
    s   = _nse_session()
    if s is None:
        return pd.DataFrame()

    end   = datetime.now()
    start = end - timedelta(days=400)   # ~13 months — enough history
    try:
        r = s.get(
            _NSE_HIST,
            params={
                "symbol": sym,
                "series": '["EQ"]',
                "from":   start.strftime("%d-%m-%Y"),
                "to":     end.strftime("%d-%m-%Y"),
            },
            timeout=(4, 12),
        )
        if r.status_code in (401, 403, 429):
            _mark_host_auth_failed("nse")
            return pd.DataFrame()
        if r.status_code != 200:
            logger.debug(f"[{symbol}] NSE returned {r.status_code}")
            return pd.DataFrame()
        data = r.json().get("data") or []
        if not data:
            return pd.DataFrame()
        rows = []
        for item in data:
            try:
                rows.append({
                    "Date":      pd.to_datetime(item["CH_TIMESTAMP"]),
                    "Open":      float(item["CH_OPENING_PRICE"]),
                    "High":      float(item["CH_TRADE_HIGH_PRICE"]),
                    "Low":       float(item["CH_TRADE_LOW_PRICE"]),
                    "Close":     float(item["CH_CLOSING_PRICE"]),
                    "Adj Close": float(item["CH_CLOSING_PRICE"]),
                    "Volume":    int(item.get("CH_TOT_TRADED_QTY") or 0),
                })
            except (KeyError, ValueError, TypeError):
                continue
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index("Date").sort_index()
        return df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
    except Exception as exc:
        logger.debug(f"[{symbol}] NSE fetch failed: {exc}")
        return pd.DataFrame()


# ── Yahoo quote endpoint ─────────────────────────────────────────────────────

def _fetch_info_yahoo(symbol: str) -> dict[str, Any]:
    if _host_dead("yahoo"):
        return {}
    try:
        r = _SESSION.get(_YF_QUOTE_URL, params={"symbols": symbol},
                          timeout=(3, 5))
        if r.status_code != 200:
            return {}
        rs = ((r.json().get("quoteResponse") or {}).get("result") or [])
        return rs[0] if rs else {}
    except Exception as exc:
        logger.debug(f"[{symbol}] quote endpoint failed: {exc}")
        return {}


def fetch_stock(symbol: str, period: str = "6mo", interval: str = "1d") -> dict[str, Any] | None:
    """Fetch OHLCV history and a fundamentals snapshot for one ticker.
    Priority: Yahoo → Stooq → NSE India direct.
    All HTTP calls have hard timeouts so a slow host can't hang the run."""
    try:
        hist = _fetch_history_yahoo(symbol, period, interval)
        if hist is None or hist.empty:
            hist = _fetch_history_stooq(symbol)
        if hist is None or hist.empty:
            hist = _fetch_history_nse(symbol)   # NSE direct — works even when Yahoo/Stooq rate-limit
        if hist is None or hist.empty or len(hist) < 30:
            logger.warning(f"[{symbol}] insufficient history "
                           f"({0 if hist is None else len(hist)} rows)")
            return None
        info = _fetch_info_yahoo(symbol)
        return {"symbol": symbol, "history": hist, "info": info}
    except Exception as exc:
        logger.warning(f"[{symbol}] fetch failed: {exc}")
        return None


def fetch_universe(symbols: list[str]) -> list[dict[str, Any]]:
    import time
    # Warm up Yahoo crumb + NSE session concurrently before the ticker loop.
    _ensure_crumb()
    _nse_session()   # pre-load NSE cookies so first ticker isn't slower
    results: list[dict[str, Any]] = []
    for i, sym in enumerate(symbols, 1):
        logger.info(f"[{i}/{len(symbols)}] fetching {sym} …")
        data = fetch_stock(sym)
        if data:
            results.append(data)
        # Small courtesy delay to avoid triggering Yahoo rate-limit (429).
        if i < len(symbols):
            time.sleep(0.4)
    logger.info(f"Fetched {len(results)}/{len(symbols)} symbols successfully.")
    return results


# ── Mutual funds (mfapi.in — free, no key) ──────────────────────────────────

def fetch_mutual_fund(scheme_code: str) -> dict[str, Any] | None:
    if _host_dead("mfapi"):
        return None
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    try:
        # Short connect timeout so one dead host doesn't block the run long.
        r = _SESSION.get(url, timeout=(2, 5))
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data", [])
        if not data:
            return None
        # data is sorted newest-first: [{"date": "23-04-2026", "nav": "123.45"}, ...]
        parsed: list[tuple[datetime, float]] = []
        for row in data:
            try:
                d = datetime.strptime(row["date"], "%d-%m-%Y")
                parsed.append((d, float(row["nav"])))
            except Exception:
                continue
        parsed.sort(key=lambda x: x[0])
        return {
            "code":   scheme_code,
            "meta":   payload.get("meta", {}),
            "series": parsed,   # oldest → newest
        }
    except Exception as exc:
        # One connect-timeout is enough to declare mfapi unreachable for this run.
        _mark_host_auth_failed("mfapi")
        logger.warning(f"[MF {scheme_code}] fetch failed: {exc}")
        return None


# ── News RSS (naive keyword sentiment) ──────────────────────────────────────

def fetch_headlines(max_items: int = 200) -> list[str]:
    """Fetch Indian + global headlines (geopolitics, US markets, war)."""
    from .macro import GLOBAL_RSS_FEEDS
    feeds = list(NEWS_RSS_FEEDS) + list(GLOBAL_RSS_FEEDS)
    titles: list[str] = []
    for url in feeds:
        try:
            r = _SESSION.get(url, timeout=(3, 6))
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                t = item.findtext("title") or ""
                if t:
                    titles.append(t.strip())
                if len(titles) >= max_items:
                    break
        except Exception as exc:
            logger.debug(f"RSS fail {url}: {exc}")
        if len(titles) >= max_items:
            break
    logger.info(f"Fetched {len(titles)} headlines from RSS "
                f"(Indian + global/geopolitics).")
    return titles


# Map a company/symbol to a case-insensitive keyword for headline matching.
def ticker_to_keyword(symbol: str) -> str:
    root = symbol.split(".")[0]
    root = re.sub(r"[-&]", " ", root)
    return root.upper()
