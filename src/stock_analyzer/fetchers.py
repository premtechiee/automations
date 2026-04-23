"""
stock_analyzer/fetchers.py
===========================
All external-data I/O:
  • OHLCV + fundamentals via yfinance
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
import yfinance as yf

from lib.proxy import PROXIES  # applies HTTP(S)_PROXY env vars for yfinance/curl_cffi

from .config import NEWS_RSS_FEEDS

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (compatible; stock-analyzer/1.0)"}


# ── Stocks ──────────────────────────────────────────────────────────────────

def fetch_stock(symbol: str, period: str = "6mo", interval: str = "1d") -> dict[str, Any] | None:
    """Fetch OHLCV history and a fundamentals snapshot for one ticker."""
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period=period, interval=interval, auto_adjust=False)
        if hist.empty or len(hist) < 30:
            logger.warning(f"[{symbol}] insufficient history ({len(hist)} rows)")
            return None

        info: dict[str, Any] = {}
        try:
            info = dict(tk.fast_info or {})
        except Exception:
            pass
        try:
            info.update(tk.info or {})
        except Exception as exc:
            logger.debug(f"[{symbol}] .info failed: {exc}")

        return {
            "symbol":  symbol,
            "history": hist,
            "info":    info,
        }
    except Exception as exc:
        logger.warning(f"[{symbol}] fetch failed: {exc}")
        return None


def fetch_universe(symbols: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i, sym in enumerate(symbols, 1):
        logger.info(f"[{i}/{len(symbols)}] fetching {sym} …")
        data = fetch_stock(sym)
        if data:
            results.append(data)
    logger.info(f"Fetched {len(results)}/{len(symbols)} symbols successfully.")
    return results


# ── Mutual funds (mfapi.in — free, no key) ──────────────────────────────────

def fetch_mutual_fund(scheme_code: str) -> dict[str, Any] | None:
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    try:
        # (connect, read) — fail fast if proxy blocks this host.
        r = requests.get(url, timeout=(4, 10), headers=_UA, proxies=PROXIES or None)
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
            r = requests.get(url, timeout=10, headers=_UA, proxies=PROXIES or None)
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
