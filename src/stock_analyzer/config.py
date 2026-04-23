"""
stock_analyzer/config.py
=========================
Central configuration for the Indian stock / mutual-fund analyser.

Nothing in here is financial advice — the output is an algorithmic ranking
for educational purposes only.
"""

from __future__ import annotations
import os

# ── Notification channels (reuse gold_notifier credentials) ────────────────
PHONE_NUMBER       = os.environ.get("GOLD_PHONE_NUMBER",    "919790967892")
PHONE_NUMBERS: list[str] = [
    n.strip() for n in
    os.environ.get("STOCK_PHONE_NUMBERS",
                   os.environ.get("GOLD_PHONE_NUMBERS",
                                  f"{PHONE_NUMBER},919789990096")).split(",")
    if n.strip()
]
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE", "7107567480")
GREEN_API_TOKEN    = os.environ.get("GREEN_API_TOKEN",    "")
GREEN_API_URL      = os.environ.get("GREEN_API_URL",      "https://7107.api.greenapi.com")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")

# ── Output paths ────────────────────────────────────────────────────────────
DATA_DIR          = "data"
REPORTS_DIR       = f"{DATA_DIR}/stock_reports"
IMAGE_OUTPUT_PATH = f"{DATA_DIR}/stock_report.png"
PDF_OUTPUT_PATH   = f"{DATA_DIR}/stock_report.pdf"
LOG_FILE          = f"{DATA_DIR}/stock_analyzer.log"
WATCHLIST_FILE    = f"{DATA_DIR}/stock_watchlist.txt"

# ── Theme ───────────────────────────────────────────────────────────────────
IMAGE_THEME = os.environ.get("STOCK_IMAGE_THEME", "dark").strip().lower()

# ── Stock universe — NIFTY 100 (covers NIFTY 50 + NIFTY Next 50) ────────────
# yfinance suffix: .NS = NSE, .BO = BSE. Using NSE for better liquidity.
NIFTY_50: list[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "ITC.NS",
    "LT.NS", "AXISBANK.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "HCLTECH.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "NESTLEIND.NS", "ADANIENT.NS", "POWERGRID.NS", "NTPC.NS", "TATAMOTORS.NS",
    "M&M.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "ONGC.NS", "COALINDIA.NS",
    "TECHM.NS", "BAJAJFINSV.NS", "HINDALCO.NS", "GRASIM.NS", "DRREDDY.NS",
    "CIPLA.NS", "DIVISLAB.NS", "EICHERMOT.NS", "BRITANNIA.NS", "HEROMOTOCO.NS",
    "BAJAJ-AUTO.NS", "INDUSINDBK.NS", "APOLLOHOSP.NS", "TATACONSUM.NS", "UPL.NS",
    "BPCL.NS", "SBILIFE.NS", "HDFCLIFE.NS", "ADANIPORTS.NS", "LTIM.NS",
]
NIFTY_NEXT_50: list[str] = [
    "ABB.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "AMBUJACEM.NS", "DMART.NS",
    "BAJAJHLDNG.NS", "BANKBARODA.NS", "BERGEPAINT.NS", "BOSCHLTD.NS", "CANBK.NS",
    "CHOLAFIN.NS", "COLPAL.NS", "DABUR.NS", "DLF.NS", "GAIL.NS",
    "GODREJCP.NS", "HAVELLS.NS", "HAL.NS", "ICICIGI.NS", "ICICIPRULI.NS",
    "IOC.NS", "IRCTC.NS", "JINDALSTEL.NS", "LICI.NS", "MARICO.NS",
    "MOTHERSON.NS", "NAUKRI.NS", "PIDILITIND.NS", "PNB.NS", "PFC.NS",
    "RECLTD.NS", "SIEMENS.NS", "SRF.NS", "SHREECEM.NS", "SHRIRAMFIN.NS",
    "TORNTPHARM.NS", "TRENT.NS", "TVSMOTOR.NS", "VEDL.NS", "VBL.NS",
    "ZOMATO.NS", "ZYDUSLIFE.NS", "INDIGO.NS", "IDEA.NS", "BANKINDIA.NS",
    "PAGEIND.NS", "MUTHOOTFIN.NS", "TATAPOWER.NS", "TATAELXSI.NS", "LUPIN.NS",
]
NIFTY_100: list[str] = NIFTY_50 + NIFTY_NEXT_50
# Back-compat alias
NIFTY_UNIVERSE: list[str] = NIFTY_100


def load_watchlist(path: str = WATCHLIST_FILE) -> list[str]:
    """Read the user's watchlist file. Each line = one symbol. '#' starts a comment.
    Bare tickers like `TATAPOWER` are auto-suffixed with `.NS`.
    Returns a de-duplicated list preserving order."""
    if not os.path.exists(path):
        return []
    seen: set[str] = set()
    out:  list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip().upper()
            if not line:
                continue
            if "." not in line:
                line = f"{line}.NS"
            if line not in seen:
                seen.add(line)
                out.append(line)
    return out


def resolve_universe(watchlist_path: str | None = None) -> list[str]:
    """Merge NIFTY_100 with user's watchlist (watchlist first, then the rest)."""
    wl = load_watchlist(watchlist_path or WATCHLIST_FILE)
    merged: list[str] = []
    seen: set[str] = set()
    for sym in wl + NIFTY_100:
        if sym not in seen:
            seen.add(sym)
            merged.append(sym)
    return merged


# ── Mutual funds (MFAPI.in scheme codes for popular direct-growth funds) ────
# Source: https://www.mfapi.in  (search by scheme name to get the code).
MUTUAL_FUNDS: list[dict] = [
    {"code": "120503", "name": "Parag Parikh Flexi Cap — Direct",   "cat": "Flexi Cap"},
    {"code": "119551", "name": "Mirae Asset Large Cap — Direct",    "cat": "Large Cap"},
    {"code": "118834", "name": "Axis Small Cap — Direct",           "cat": "Small Cap"},
    {"code": "118989", "name": "SBI Small Cap — Direct",            "cat": "Small Cap"},
    {"code": "120716", "name": "HDFC Mid-Cap Opportunities — Direct","cat": "Mid Cap"},
    {"code": "119598", "name": "Quant Active — Direct",             "cat": "Multi Cap"},
    {"code": "120465", "name": "Kotak Equity Opportunities — Direct","cat": "Large & Mid"},
    {"code": "118560", "name": "ICICI Pru Bluechip — Direct",       "cat": "Large Cap"},
    {"code": "125354", "name": "Nippon India Small Cap — Direct",   "cat": "Small Cap"},
    {"code": "120586", "name": "UTI Nifty 50 Index — Direct",       "cat": "Index"},
]

# ── Scoring weights (must sum to 1.0) ───────────────────────────────────────
WEIGHT_FUNDAMENTAL = 0.40
WEIGHT_TECHNICAL   = 0.45
WEIGHT_SENTIMENT   = 0.15

# ── Top-N in each bucket ────────────────────────────────────────────────────
TOP_INTRADAY  = 5
TOP_SWING     = 5
TOP_HOLDING   = 5
TOP_SELL      = 5
TOP_MF        = 5

# ── News sources (RSS, free) for basic sentiment ────────────────────────────
NEWS_RSS_FEEDS: list[str] = [
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.moneycontrol.com/rss/business.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]

# Keywords used for naive headline sentiment.
POS_WORDS = {
    "surge", "rally", "jump", "gain", "growth", "profit", "beats",
    "upgrade", "bullish", "record", "high", "rise", "soars", "boost",
    "outperform", "buy", "positive", "strong", "expansion", "wins",
}
NEG_WORDS = {
    "fall", "drop", "plunge", "loss", "miss", "downgrade", "bearish",
    "low", "slump", "cut", "concern", "weak", "decline", "sell",
    "negative", "probe", "fraud", "fine", "layoff", "delay", "ban",
}

DISCLAIMER = (
    "⚠️ EDUCATIONAL ONLY — not financial advice. "
    "Past performance does not guarantee future returns. "
    "Consult a SEBI-registered adviser before investing."
)
