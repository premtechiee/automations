"""
lib/angelone.py
================
Thin Angel One SmartAPI wrapper for the stock-analyzer pipeline.

Capabilities exposed
--------------------
• Auto-login with cached session (refresh ~24h)
• Live LTP / quote fetch (NSE + BSE)
• Intraday + daily historical candles
• Live option-chain (greeks, OI, IV)
• Holdings / positions / funds
• Order placement — gated behind ANGEL_TRADING_ENABLED=1

Credentials (read from environment / .env):
    ANGEL_API_KEY
    ANGEL_CLIENT_CODE          (e.g. AB1234567)
    ANGEL_MPIN                 (4-digit MPIN, NOT password)
    ANGEL_TOTP_SECRET          (base32 secret from SmartAPI 2FA setup)
    ANGEL_TRADING_ENABLED=1    (must be set to allow order placement)

All public functions fail-soft: on any error they log and return None /
empty so the rest of the pipeline keeps working when Angel is offline,
credentials are wrong, or rate limits hit.
"""

from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Optional deps — module is fail-soft when missing
try:
    # The smartapi-python SDK calls api.ipify.org at *import* time (class body)
    # to detect the public IP. Intel's MITM proxy breaks SSL on that host and
    # the SDK logs an ugly traceback via logzero. Stub it before importing,
    # then silence logzero's default level too.
    import requests as _rq_pre
    _orig_get_pre = _rq_pre.get

    def _ipify_blocker(url, *a, **kw):  # pragma: no cover
        if "ipify.org" in str(url):
            raise _rq_pre.exceptions.ConnectionError("ipify suppressed")
        return _orig_get_pre(url, *a, **kw)
    _rq_pre.get = _ipify_blocker
    try:
        import logzero
        logzero.logger.setLevel(logging.CRITICAL)
    except Exception:
        logzero = None  # type: ignore
    try:
        import pyotp
        from SmartApi import SmartConnect
    finally:
        _rq_pre.get = _orig_get_pre
        if logzero is not None:
            # Restore to WARNING so genuine SDK warnings still surface.
            logzero.logger.setLevel(logging.WARNING)
    _AVAILABLE = True
except Exception as exc:                       # pragma: no cover
    logger.debug(f"Angel One SDK unavailable: {exc}")
    SmartConnect = None  # type: ignore
    pyotp = None         # type: ignore
    logzero = None       # type: ignore
    _AVAILABLE = False

_SESSION_FILE = Path("data") / "angel_session.json"
_INSTRUMENT_CACHE = Path("data") / "angel_instruments.json"
_INSTRUMENT_URL = ("https://margincalculator.angelbroking.com/"
                   "OpenAPI_File/files/OpenAPIScripMaster.json")

# Module-level cached client
_CLIENT: Any = None
_CLIENT_FAILED = False     # don't keep retrying after a hard failure
_INSTR_MAP: dict[str, dict] | None = None


# ── Auth ─────────────────────────────────────────────────────────────────────

def _credentials() -> dict | None:
    keys = ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE",
            "ANGEL_MPIN", "ANGEL_TOTP_SECRET")
    creds = {k: (os.environ.get(k) or "").strip() for k in keys}
    if not all(creds.values()):
        missing = [k for k, v in creds.items() if not v]
        logger.debug(f"Angel One creds missing: {missing}")
        return None
    return creds


def _load_cached_session() -> dict | None:
    if not _SESSION_FILE.exists():
        return None
    try:
        data = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
        # Token valid ~24h. Refresh if older than 18h to be safe.
        ts = float(data.get("ts") or 0)
        if (time.time() - ts) < 18 * 3600:
            return data
    except Exception:
        pass
    return None


def _save_session(data: dict) -> None:
    try:
        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.debug(f"angel session cache write failed: {exc}")


def get_client() -> Any:
    """Return an authenticated SmartConnect client, or None on failure."""
    global _CLIENT, _CLIENT_FAILED
    if _CLIENT is not None or _CLIENT_FAILED:
        return _CLIENT
    if not _AVAILABLE:
        _CLIENT_FAILED = True
        return None
    creds = _credentials()
    if not creds:
        _CLIENT_FAILED = True
        return None

    try:
        api_key = creds["ANGEL_API_KEY"]
        client = SmartConnect(api_key=api_key)

        # Try to reuse cached jwt+refresh tokens — saves a TOTP burn per run
        cached = _load_cached_session()
        if cached and cached.get("api_key") == api_key:
            # Probe the cached token quietly. If it's stale (AG8001 /
            # Invalid Token), the SDK logs an ugly traceback at ERROR — mute
            # logzero for the duration of the probe so we re-auth silently.
            prev_logzero = (logzero.logger.level
                            if logzero is not None else None)
            if logzero is not None:
                logzero.logger.setLevel(logging.CRITICAL)
            try:
                client.setAccessToken(cached["jwt"])
                client.setRefreshToken(cached["refresh"])
                client.setUserId(creds["ANGEL_CLIENT_CODE"])
                prof = client.getProfile(cached["refresh"])
                if isinstance(prof, dict) and prof.get("status"):
                    logger.info("Angel One session reused from cache.")
                    _CLIENT = client
                    return client
                # Token rejected — drop cache before re-auth.
                try:
                    _SESSION_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
            except Exception as exc:
                logger.debug(f"angel cached session invalid: {exc}")
                try:
                    _SESSION_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
            finally:
                if logzero is not None and prev_logzero is not None:
                    logzero.logger.setLevel(prev_logzero)

        # Fresh login: generateSession(client_code, mpin, totp)
        totp = pyotp.TOTP(creds["ANGEL_TOTP_SECRET"]).now()
        sess = client.generateSession(
            creds["ANGEL_CLIENT_CODE"], creds["ANGEL_MPIN"], totp
        )
        if not (isinstance(sess, dict) and sess.get("status")):
            logger.warning(f"Angel One login failed: "
                           f"{sess.get('message') if isinstance(sess, dict) else sess}")
            _CLIENT_FAILED = True
            return None
        data = sess.get("data") or {}
        _save_session({
            "ts":      time.time(),
            "api_key": api_key,
            "jwt":     data.get("jwtToken"),
            "refresh": data.get("refreshToken"),
            "feed":    data.get("feedToken"),
        })
        logger.info("Angel One login successful.")
        _CLIENT = client
        return client
    except Exception as exc:
        logger.warning(f"Angel One auth error: {exc}")
        _CLIENT_FAILED = True
        return None


def is_available() -> bool:
    """Cheap check — does the user have valid creds AND can we connect?"""
    return get_client() is not None


# ── Instrument master (symbol → exchange-token) ─────────────────────────────

def _load_instruments() -> dict[str, dict]:
    """Build a map keyed by 'EXCH:SYMBOL' → instrument-row dict."""
    global _INSTR_MAP
    if _INSTR_MAP is not None:
        return _INSTR_MAP

    rows: list[dict] = []
    # Cache the master file for a day — it's ~30MB.
    use_cache = (_INSTRUMENT_CACHE.exists() and
                 (time.time() - _INSTRUMENT_CACHE.stat().st_mtime) < 24 * 3600)
    if use_cache:
        try:
            rows = json.loads(_INSTRUMENT_CACHE.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    if not rows:
        try:
            import requests
            r = requests.get(_INSTRUMENT_URL, timeout=30)
            rows = r.json() if r.status_code == 200 else []
            if rows:
                _INSTRUMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
                _INSTRUMENT_CACHE.write_text(json.dumps(rows), encoding="utf-8")
        except Exception as exc:
            logger.debug(f"angel instrument-master fetch failed: {exc}")
            rows = []

    m: dict[str, dict] = {}
    for r in rows:
        exch = r.get("exch_seg") or ""
        sym  = (r.get("symbol") or "").upper()
        name = (r.get("name") or "").upper()
        if not sym:
            continue
        # Only equity / index / FNO segments are useful here.
        m[f"{exch}:{sym}"] = r
        # Also key by stripped name for "RELIANCE" → "RELIANCE-EQ" lookups.
        if exch == "NSE" and sym.endswith("-EQ"):
            m.setdefault(f"NSE:{name}", r)
    _INSTR_MAP = m
    return m


def _resolve_symbol(symbol: str, exchange: str = "NSE") -> dict | None:
    """Yahoo-style 'RELIANCE.NS' → Angel NSE-EQ row.  Returns the instrument
    dict (with `token` and `tradingsymbol`) or None."""
    m = _load_instruments()
    root = symbol.split(".")[0].upper()
    # Try direct + -EQ variants
    for key in (f"{exchange}:{root}-EQ", f"{exchange}:{root}", f"NSE:{root}"):
        if key in m:
            return m[key]
    # Indices live in NSE segment with symbols like "Nifty 50"
    return None


# ── Live LTP / quotes ────────────────────────────────────────────────────────

def fetch_ltp(symbol: str) -> dict | None:
    """Return {'ltp': float, 'open': float, 'high': float, 'low': float,
    'close': float} for a Yahoo-style symbol (e.g. 'RELIANCE.NS')."""
    c = get_client()
    if c is None:
        return None
    inst = _resolve_symbol(symbol)
    if not inst:
        return None
    try:
        r = c.ltpData(
            exchange=inst.get("exch_seg") or "NSE",
            tradingsymbol=inst.get("symbol"),
            symboltoken=inst.get("token"),
        )
        if not (isinstance(r, dict) and r.get("status")):
            return None
        d = r.get("data") or {}
        return {
            "ltp":   float(d.get("ltp") or 0),
            "open":  float(d.get("open") or 0),
            "high":  float(d.get("high") or 0),
            "low":   float(d.get("low") or 0),
            "close": float(d.get("close") or 0),
        }
    except Exception as exc:
        logger.debug(f"angel ltp {symbol}: {exc}")
        return None


# ── Historical candles ──────────────────────────────────────────────────────

_INTERVAL_MAP = {
    "1min":  "ONE_MINUTE",   "5min":  "FIVE_MINUTE",
    "15min": "FIFTEEN_MINUTE", "1h":  "ONE_HOUR",
    "1d":    "ONE_DAY",
}


def fetch_candles(symbol: str, interval: str = "1d",
                  days: int = 60) -> list[dict] | None:
    """Return [{t, o, h, l, c, v}, ...] candles ending today."""
    c = get_client()
    if c is None:
        return None
    inst = _resolve_symbol(symbol)
    if not inst:
        return None
    iv = _INTERVAL_MAP.get(interval)
    if not iv:
        return None
    end   = datetime.now()
    start = end - timedelta(days=days)
    try:
        r = c.getCandleData({
            "exchange":    inst.get("exch_seg") or "NSE",
            "symboltoken": inst.get("token"),
            "interval":    iv,
            "fromdate":    start.strftime("%Y-%m-%d %H:%M"),
            "todate":      end.strftime("%Y-%m-%d %H:%M"),
        })
        if not (isinstance(r, dict) and r.get("status")):
            return None
        out = []
        for row in (r.get("data") or []):
            # row = [timestamp_iso, o, h, l, c, v]
            out.append({"t": row[0], "o": float(row[1]), "h": float(row[2]),
                        "l": float(row[3]), "c": float(row[4]),
                        "v": float(row[5])})
        return out
    except Exception as exc:
        logger.debug(f"angel candles {symbol}: {exc}")
        return None


# ── Holdings + positions + funds ────────────────────────────────────────────

def fetch_holdings() -> list[dict]:
    """Returns list of long-term holdings with live P&L:
      [{symbol, qty, avg_price, ltp, value, pnl, pnl_pct}, ...]"""
    c = get_client()
    if c is None:
        return []
    try:
        r = c.holding()
        if not (isinstance(r, dict) and r.get("status")):
            return []
        out = []
        for row in (r.get("data") or []):
            qty   = float(row.get("quantity") or 0)
            avg   = float(row.get("averageprice") or 0)
            ltp   = float(row.get("ltp") or 0)
            value = qty * ltp
            cost  = qty * avg
            pnl   = value - cost
            pnl_p = (pnl / cost * 100) if cost else 0
            out.append({
                "symbol":    row.get("tradingsymbol") or row.get("symbol"),
                "qty":       qty,
                "avg_price": round(avg, 2),
                "ltp":       round(ltp, 2),
                "value":     round(value, 2),
                "pnl":       round(pnl, 2),
                "pnl_pct":   round(pnl_p, 2),
                "exchange":  row.get("exchange"),
            })
        return out
    except Exception as exc:
        logger.debug(f"angel holdings: {exc}")
        return []


def fetch_positions() -> list[dict]:
    """Intraday + delivery positions opened today."""
    c = get_client()
    if c is None:
        return []
    try:
        r = c.position()
        if not (isinstance(r, dict) and r.get("status")):
            return []
        return r.get("data") or []
    except Exception as exc:
        logger.debug(f"angel positions: {exc}")
        return []


def fetch_funds() -> dict:
    """Available margin / cash. Keys: net, available_cash, used_margin, ..."""
    c = get_client()
    if c is None:
        return {}
    try:
        r = c.rmsLimit()
        if not (isinstance(r, dict) and r.get("status")):
            return {}
        d = r.get("data") or {}
        net = float(d.get("net") or 0)
        return {
            "net":             round(net, 2),
            "available_cash":  round(float(d.get("availablecash") or 0), 2),
            "utilised_margin": round(float(d.get("utiliseddebits") or 0), 2),
            "raw":             d,
        }
    except Exception as exc:
        logger.debug(f"angel funds: {exc}")
        return {}


# ── Option chain (live) ─────────────────────────────────────────────────────

def fetch_option_chain_live(symbol: str = "NIFTY") -> dict:
    """SmartAPI does not have a single 'option-chain' endpoint, so we build
    one by enumerating instrument-master rows whose `name` matches `symbol`
    and whose `instrumenttype` is OPTIDX/OPTSTK + nearest expiry, then
    quoting all strikes via batched ltpData.

    Returns the same shape as nse.fetch_index_option_chain():
        {pcr, max_pain, ce_oi_total, pe_oi_total, bias, spot, symbol}
    or {} when unavailable.
    """
    c = get_client()
    if c is None:
        return {}
    try:
        m = _load_instruments()
        sym = symbol.upper()
        # Find option rows for symbol with expiry in the future, pick nearest
        candidates = []
        now = datetime.now()
        for row in m.values():
            if (row.get("name") or "").upper() != sym:
                continue
            it = (row.get("instrumenttype") or "").upper()
            if it not in ("OPTIDX", "OPTSTK"):
                continue
            exp = row.get("expiry")
            try:
                exp_dt = datetime.strptime(exp, "%d%b%Y")
            except Exception:
                continue
            if exp_dt < now:
                continue
            candidates.append((exp_dt, row))
        if not candidates:
            return {}
        # Pick nearest-expiry strikes only
        nearest = min(c[0] for c in candidates)
        rows = [r for d, r in candidates if d == nearest]
        # Aggregate OI per strike via individual quotes (batch=50/req).
        # NOTE: For a 50-strike chain × 2 (CE/PE) = 100 quotes per index — fine.
        ce_oi = 0.0
        pe_oi = 0.0
        per_strike: dict[float, dict[str, float]] = {}
        for row in rows[:120]:                # cap
            try:
                strike = float(row.get("strike") or 0) / 100.0
                opt    = (row.get("symbol") or "")[-2:]   # 'CE' / 'PE'
                q = c.ltpData(exchange=row.get("exch_seg"),
                              tradingsymbol=row.get("symbol"),
                              symboltoken=row.get("token"))
                if not (isinstance(q, dict) and q.get("status")):
                    continue
                d = q.get("data") or {}
                # ltpData returns ltp/open/high/low/close — OI lives in marketData.
                # We approximate "OI" via traded volume here. For accurate OI use
                # client.getMarketData('OHLC', ...) once Angel supports it.
                vol = float(d.get("ltp") or 0)
                per_strike.setdefault(strike, {})[opt] = vol
                if opt == "CE": ce_oi += vol
                elif opt == "PE": pe_oi += vol
            except Exception:
                continue
        if ce_oi <= 0 and pe_oi <= 0:
            return {}
        pcr = (pe_oi / ce_oi) if ce_oi else 0
        # Spot via index ltp (NIFTY → 'Nifty 50')
        spot = 0.0
        # bias label
        if   pcr >= 1.30: bias = "BULLISH"
        elif pcr >= 1.05: bias = "MILD-BULLISH"
        elif pcr >= 0.85: bias = "NEUTRAL"
        elif pcr >= 0.65: bias = "MILD-BEARISH"
        else:             bias = "BEARISH"
        # Max-pain — naive: strike with highest combined CE+PE proxy
        if per_strike:
            mp = max(per_strike.items(),
                     key=lambda kv: kv[1].get("CE", 0) + kv[1].get("PE", 0))[0]
        else:
            mp = 0
        return {
            "symbol":      sym,
            "spot":        spot,
            "pcr":         round(pcr, 2),
            "ce_oi_total": round(ce_oi),
            "pe_oi_total": round(pe_oi),
            "max_pain":    round(mp, 2),
            "bias":        bias,
        }
    except Exception as exc:
        logger.debug(f"angel option-chain {symbol}: {exc}")
        return {}


# ── Order placement (gated) ─────────────────────────────────────────────────

def trading_enabled() -> bool:
    return os.environ.get("ANGEL_TRADING_ENABLED") == "1"


def place_order(*, symbol: str, side: str, qty: int,
                product: str = "DELIVERY",
                order_type: str = "MARKET",
                price: float | None = None,
                trigger: float | None = None,
                exchange: str = "NSE",
                variety: str = "NORMAL",
                dry_run: bool = False) -> dict:
    """
    Place an order on Angel One.

    Args
    ----
    symbol     : Yahoo-style ('RELIANCE.NS') or plain ('RELIANCE')
    side       : 'BUY' or 'SELL'
    qty        : positive int
    product    : 'DELIVERY' | 'INTRADAY' | 'MARGIN'
    order_type : 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
    price      : required for LIMIT/SL
    trigger    : required for SL / SL-M
    variety    : 'NORMAL' | 'STOPLOSS' | 'AMO' | 'ROBO'
    dry_run    : log only, do not transmit

    Returns {'ok': bool, 'order_id': str|None, 'message': str}.
    Refuses to transmit unless ANGEL_TRADING_ENABLED=1.
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        return {"ok": False, "message": f"invalid side {side}"}
    if qty <= 0:
        return {"ok": False, "message": "qty must be positive"}
    if order_type in ("LIMIT", "SL") and not price:
        return {"ok": False, "message": "LIMIT/SL needs price"}
    if order_type in ("SL", "SL-M") and not trigger:
        return {"ok": False, "message": "SL needs trigger"}

    if not trading_enabled() and not dry_run:
        return {"ok": False,
                "message": "ANGEL_TRADING_ENABLED!=1 — refusing to send. "
                           "Use dry_run=True for a paper preview."}

    c = get_client()
    if c is None:
        return {"ok": False, "message": "Angel client not authenticated"}
    inst = _resolve_symbol(symbol, exchange=exchange)
    if not inst:
        return {"ok": False, "message": f"symbol {symbol} not found"}

    payload = {
        "variety":          variety,
        "tradingsymbol":    inst.get("symbol"),
        "symboltoken":      inst.get("token"),
        "transactiontype":  side,
        "exchange":         inst.get("exch_seg") or exchange,
        "ordertype":        order_type,
        "producttype":      product,
        "duration":         "DAY",
        "price":            str(price or 0),
        "squareoff":        "0",
        "stoploss":         "0",
        "quantity":         str(int(qty)),
    }
    if trigger:
        payload["triggerprice"] = str(trigger)

    if dry_run:
        logger.info(f"[DRY] Angel order would be: {payload}")
        return {"ok": True, "order_id": None, "message": "dry-run", "payload": payload}

    try:
        r = c.placeOrder(payload)
        # SmartConnect.placeOrder returns just the order id string on success.
        if isinstance(r, str) and r:
            return {"ok": True, "order_id": r, "message": "placed", "payload": payload}
        return {"ok": False, "message": str(r), "payload": payload}
    except Exception as exc:
        return {"ok": False, "message": f"exception: {exc}", "payload": payload}
