"""
automations/gold_notifier/fetchers.py
======================================
Live price fetching for gold and silver:
  - Yahoo Finance (yfinance)
  - open.er-api (XAU/USD fallback)
  - IBJA official Indian bullion rates
  - goodreturns.in Chennai retail history (curl_cffi)
"""

import html as _html
import logging
import re as _re
from datetime import date, datetime

import requests
import yfinance as yf

from .config import INDIA_GOLD_DUTY_FACTOR, INDIA_SILVER_DUTY_FACTOR
from lib.proxy import PROXIES

logger = logging.getLogger(__name__)


# ── USD/INR exchange rate ───────────────────────────────────────────────────

def _get_usd_inr_rate() -> float:
    """Return live USD/INR exchange rate; falls back to 84.0 on failure."""
    try:
        rate = yf.Ticker("USDINR=X").fast_info.last_price
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    logger.warning("Could not fetch live USD/INR rate; using fallback 84.0")
    return 84.0


# ── Gold price sources ──────────────────────────────────────────────────────

def _fetch_via_yfinance() -> dict | None:
    """Fetch gold futures price from Yahoo Finance (COMEX GC=F)."""
    try:
        info   = yf.Ticker("GC=F").fast_info
        price  = info.last_price
        prev   = info.previous_close
        change = price - prev
        return {
            "price_usd":  price,
            "change_usd": change,
            "change_pct": (change / prev) * 100,
            "source":     "Yahoo Finance – COMEX Gold Futures (GC=F)",
        }
    except Exception as exc:
        logger.warning(f"yfinance fetch failed: {exc}")
        return None


def _fetch_via_metals_api() -> dict | None:
    """Fallback: derive gold spot from open.er-api XAU/USD rate."""
    try:
        resp = requests.get(
            "https://open.er-api.com/v6/latest/USD",
            timeout=15, proxies=PROXIES,
        )
        resp.raise_for_status()
        xau_rate = resp.json()["rates"]["XAU"]
        usd_per_oz = 1.0 / xau_rate
        return {
            "price_usd":  usd_per_oz,
            "change_usd": None,
            "change_pct": None,
            "source":     "open.er-api (XAU/USD derived)",
        }
    except Exception as exc:
        logger.warning(f"Metals API fallback failed: {exc}")
        return None


def get_gold_price() -> dict | None:
    """
    Return a gold price dict with USD and INR values.
    Tries yfinance first, falls back to open.er-api.
    """
    data = _fetch_via_yfinance() or _fetch_via_metals_api()
    if not data or not data.get("price_usd"):
        logger.error("All price sources failed.")
        return None

    usd_inr       = _get_usd_inr_rate()
    price_usd     = data["price_usd"]
    price_inr_oz  = price_usd * usd_inr
    price_inr_g   = price_inr_oz / 31.1035

    data["change_inr_g"] = (
        data["change_usd"] * usd_inr / 31.1035 * INDIA_GOLD_DUTY_FACTOR
        if data.get("change_usd") is not None else None
    )
    data["price_inr_per_oz"] = price_inr_oz
    data["price_inr_per_g"]  = price_inr_g
    data["usd_inr_rate"]     = usd_inr

    ibja = _fetch_ibja_rates()
    if ibja:
        try:
            ibja_dt = date(int(ibja["date"][6:]), int(ibja["date"][3:5]), int(ibja["date"][:2]))
            if ibja_dt < date.today():
                logger.info(f"IBJA rate from {ibja['date']} (not today) — discarding stale rate")
                ibja = None
        except Exception:
            ibja = None
    data["ibja"] = ibja
    return data


# ── IBJA official rates ─────────────────────────────────────────────────────

def _fetch_ibja_rates() -> dict | None:
    """Scrape IBJA homepage for today's official Indian gold rates per gram."""
    try:
        hdrs = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":          "text/html,application/xhtml+xml",
            "Accept-Language": "en-IN,en;q=0.9",
        }
        r = requests.get("https://ibja.co/", headers=hdrs, proxies=PROXIES, timeout=12)
        if r.status_code != 200:
            logger.warning(f"IBJA returned HTTP {r.status_code}")
            return None
        date_m  = _re.search(r'id="lblDate">(\d{2}/\d{2}/\d{4})', r.text)
        g999_m  = _re.search(r'id="lblFineGold999">\s*₹\s*(\d[\d,]+)', r.text)
        g22k_m  = _re.search(r'id="lblSellingPriceFor22KT">\s*₹\s*(\d[\d,]+)', r.text)
        if not g999_m or not g22k_m:
            logger.warning("IBJA: could not parse rates from page")
            return None
        return {
            "24k":  int(g999_m.group(1).replace(",", "")),
            "22k":  int(g22k_m.group(1).replace(",", "")),
            "date": date_m.group(1) if date_m else "N/A",
        }
    except Exception as exc:
        logger.warning(f"IBJA fetch failed: {exc}")
        return None


# ── goodreturns.in Chennai history ──────────────────────────────────────────

def _fetch_goodreturns_history() -> list[dict] | None:
    """
    Scrape goodreturns.in Chennai gold rates for the last ~32 trading days.
    Uses curl_cffi browser impersonation to bypass Cloudflare.
    Returns list of {date, '24k', '22k', 'chg'} newest-first.
    """
    try:
        from curl_cffi import requests as _cr
    except ImportError:
        logger.warning("curl_cffi unavailable; goodreturns scraping skipped")
        return None
    try:
        r = _cr.get(
            "https://www.goodreturns.in/gold-rates/chennai.html",
            impersonate="chrome110", proxies=PROXIES, timeout=15,
        )
        if r.status_code != 200:
            logger.warning(f"goodreturns.in returned HTTP {r.status_code}")
            return None

        text    = _html.unescape(r.text)
        month_p = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
        row_pat = _re.compile(
            rf'<td>({month_p}\s+\d{{1,2}},\s+\d{{4}})</td>'
            r'.*?\u20b9\s*([\d,]+)'
            r'.*?\(([-+]?\d+)\)'
            r'.*?\u20b9\s*([\d,]+)'
            r'.*?\(([-+]?\d+)\)',
            _re.DOTALL | _re.IGNORECASE,
        )
        results = []
        for m in row_pat.finditer(text):
            date_str, p24_s, chg_s, p22_s, _ = m.groups()
            p24 = int(p24_s.replace(',', ''))
            p22 = int(p22_s.replace(',', ''))
            chg = int(chg_s)
            if not (5_000 <= p24 <= 25_000 and 4_000 <= p22 <= 23_000):
                continue
            try:
                d = datetime.strptime(date_str.strip(), "%b %d, %Y").date()
            except ValueError:
                continue
            results.append({"date": d, "24k": p24, "22k": p22, "chg": chg})

        if len(results) < 3:
            logger.warning(f"goodreturns.in: only {len(results)} rows parsed")
            return None

        results.sort(key=lambda x: x["date"], reverse=True)
        logger.info(f"goodreturns.in history: {len(results)} days")
        return results[:32]
    except Exception as exc:
        logger.warning(f"goodreturns.in fetch failed: {exc}")
        return None


def _fetch_goodreturns_silver_rate() -> dict | None:
    """
    Scrape goodreturns.in Chennai silver rate.
    Returns {price_inr_g, change_inr_g, date, source} or None.
    """
    try:
        from curl_cffi import requests as _cr
    except ImportError:
        logger.warning("curl_cffi unavailable; goodreturns silver scraping skipped")
        return None
    try:
        r = _cr.get(
            "https://www.goodreturns.in/silver-rates/chennai.html",
            impersonate="chrome110", proxies=PROXIES, timeout=15,
        )
        if r.status_code != 200:
            logger.warning(f"goodreturns.in silver returned HTTP {r.status_code}")
            return None

        text    = _html.unescape(r.text)
        month_p = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
        row_pat = _re.compile(
            rf'<td>({month_p}\s+\d{{1,2}},\s+\d{{4}})</td>'
            r'.*?\u20b9\s*([\d,]+)'
            r'.*?\(([-+]?\d+)\)',
            _re.DOTALL | _re.IGNORECASE,
        )
        for m in row_pat.finditer(text):
            date_str, p10g_s, chg_s = m.groups()
            p10g = int(p10g_s.replace(',', ''))
            chg  = int(chg_s)
            if not (700 <= p10g <= 5000):
                continue
            try:
                d = datetime.strptime(date_str.strip(), "%b %d, %Y").date()
            except ValueError:
                continue
            price_inr_g = round(p10g / 10, 2)
            logger.info(f"goodreturns.in Chennai silver: ₹{price_inr_g}/g  date={d}")
            return {
                "price_inr_g":  price_inr_g,
                "change_inr_g": round(chg / 10, 2),
                "date":         d,
                "source":       "goodreturns.in Chennai",
            }
        logger.warning("goodreturns.in silver: no matching rows found")
    except Exception as exc:
        logger.warning(f"goodreturns silver scraping failed: {exc}")
    return None


# ── Silver price ────────────────────────────────────────────────────────────

def get_silver_price() -> dict | None:
    """
    Fetch live silver price via yfinance (SI=F → SLV → SIVR fallback chain).
    Returns dict with USD/oz and INR/g values, plus gold/silver ratio.
    """
    usd_inr = _get_usd_inr_rate()

    SILVER_SOURCES = [
        ("SI=F",  1.0,  True),
        ("SLV",   10.0, False),
        ("SIVR",  10.0, False),
    ]
    price_usd: float | None = None
    chg_usd:   float | None = None
    source_tag = "SI=F"

    for sym, mult, _is_fut in SILVER_SOURCES:
        try:
            h = yf.Ticker(sym).history(period="10d")
            if h is None or len(h) < 1:
                continue
            raw = float(h["Close"].iloc[-1])
            if raw <= 0:
                continue
            price_usd  = raw * mult
            chg_usd    = (
                (float(h["Close"].iloc[-1]) - float(h["Close"].iloc[-2])) * mult
                if len(h) >= 2 else None
            )
            source_tag = sym
            logger.info(f"Silver: using {sym} (×{mult}) → ${price_usd:.3f}/oz")
            break
        except Exception as exc:
            logger.warning(f"Silver [{sym}] failed: {exc}")

    if price_usd is None or price_usd <= 0:
        logger.warning("Silver: all sources failed — no silver price available.")
        return None

    gr_silver = _fetch_goodreturns_silver_rate()
    if gr_silver and gr_silver["price_inr_g"] > 0:
        price_inr_g  = gr_silver["price_inr_g"]
        change_inr_g = gr_silver.get("change_inr_g")
        source_tag   = gr_silver["source"]
    else:
        price_inr_g  = price_usd * usd_inr / 31.1035 * INDIA_SILVER_DUTY_FACTOR
        change_inr_g = (
            round(chg_usd * usd_inr / 31.1035 * INDIA_SILVER_DUTY_FACTOR, 2)
            if chg_usd is not None else None
        )

    gs_ratio: float | None = None
    try:
        gold_h = yf.Ticker("GC=F").history(period="10d")
        if gold_h is not None and len(gold_h) >= 1:
            gold_usd = float(gold_h["Close"].iloc[-1])
            gs_ratio = round(gold_usd / price_usd, 1) if price_usd > 0 else None
    except Exception:
        pass

    logger.info(
        f"Silver ({source_tag}): ${price_usd:.3f}/oz  "
        f"₹{round(price_inr_g, 2):.2f}/g  "
        f"{'G/S=' + str(gs_ratio) if gs_ratio else ''}"
    )
    return {
        "price_usd":    round(price_usd, 3),
        "price_inr_g":  round(price_inr_g, 2),
        "price_inr_kg": round(price_inr_g * 1000),
        "change_usd":   round(chg_usd, 3)    if chg_usd    is not None else None,
        "change_inr_g": round(change_inr_g, 2) if change_inr_g is not None else None,
        "gs_ratio":     gs_ratio,
        "usd_inr_rate": usd_inr,
        "source":       source_tag,
    }


# ── 10-day price history ────────────────────────────────────────────────────

def get_price_history_10d(usd_inr: float) -> list[dict]:
    """
    Return last 10 calendar days of gold price as a list of dicts.
    Primary: goodreturns.in Chennai; fallback: COMEX-derived.
    """
    from datetime import timedelta

    today = date.today()
    gr = _fetch_goodreturns_history()
    if gr and len(gr) >= 5:
        rows = []
        for entry in gr[:10]:
            rows.append({
                "date":    entry["date"].strftime("%d %b"),
                "weekday": entry["date"].strftime("%a"),
                "24k":     entry["24k"],
                "22k":     entry["22k"],
                "chg":     entry["chg"],
                "trading": True,
            })
        return rows

    try:
        gc_hist = yf.Ticker("GC=F").history(period="25d")[["Close"]].copy()
        fx_hist = yf.Ticker("USDINR=X").history(period="25d")[["Close"]].copy()
        gc_hist.index = gc_hist.index.tz_localize(None)
        fx_hist.index = fx_hist.index.tz_localize(None)
        if gc_hist is None or len(gc_hist) < 2:
            return []

        fx_series = {d.date(): float(v) for d, v in fx_hist["Close"].items()}

        def get_fx(d):
            for delta in range(4):
                r = fx_series.get(d + timedelta(days=delta))
                if r:
                    return r
            return usd_inr

        price_by_date: dict = {}
        prev_p24 = None
        for dt, row in gc_hist.iterrows():
            day  = dt.date()
            p24  = round(row["Close"] * get_fx(day) / 31.1035 * INDIA_GOLD_DUTY_FACTOR)
            price_by_date[day] = (p24, prev_p24)
            prev_p24 = p24

        last_p24 = next(
            (p for d in sorted(price_by_date, reverse=True) for p, _ in [price_by_date[d]]),
            None,
        )
        rows = []
        for offset in range(10):
            day = today - timedelta(days=offset)
            if day in price_by_date:
                p24, p24_prev = price_by_date[day]
                chg = (p24 - p24_prev) if p24_prev is not None else 0
                last_p24 = p24
            else:
                p24  = last_p24 if last_p24 else 0
                chg  = 0
            p22 = round(p24 * (22 / 24)) if p24 else 0
            rows.append({
                "date":    day.strftime("%d %b"),
                "weekday": day.strftime("%a"),
                "24k":     p24,
                "22k":     p22,
                "chg":     chg,
                "trading": True,
            })
        return rows
    except Exception as exc:
        logger.warning(f"Price history fetch failed: {exc}")
        return []
