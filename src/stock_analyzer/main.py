"""
stock_analyzer/main.py
=======================
Top-level orchestrator.
"""

from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Any

from lib.whatsapp import send_message as _wa_msg, send_image as _wa_img
from lib.telegram import send_message as _tg_msg, send_photo as _tg_img

from .config import (
    MUTUAL_FUNDS,
    GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL, PHONE_NUMBERS,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    IMAGE_OUTPUT_PATH, PDF_OUTPUT_PATH, WATCHLIST_FILE,
    resolve_universe, load_watchlist,
)
from .fetchers    import fetch_universe, fetch_mutual_fund, fetch_headlines
from .macro       import build_macro_context
from .learner     import update_learned_weights, expert_advice, _load_weights
from .recommender import enrich_stock, build_buckets, rank_mutual_funds
from .history     import save_report, load_previous_report, score_prior_calls
from .report      import build_report_image, build_text_summary
from .pdf_report  import build_pdf_report

logger = logging.getLogger(__name__)


# ── Console dry-run printer ─────────────────────────────────────────────────

def _print_console_dry_run(buckets: dict, mfs: list[dict], prior: dict,
                           watchlist: list[str] | None = None) -> None:
    BAR = "─" * 108
    print("\n" + BAR)
    print(f"  📊 STOCK ANALYZER — DRY RUN  ·  {datetime.now():%Y-%m-%d %H:%M IST}")
    print(BAR)

    if watchlist:
        print(f"\n  ⭐ Watchlist ({len(watchlist)}): "
              f"{', '.join(s.replace('.NS','') for s in watchlist[:12])}"
              f"{'…' if len(watchlist) > 12 else ''}")

    label  = {"intraday": "🔥 INTRADAY", "swing": "📈 SWING",
              "holding":  "🏦 HOLDING",  "sell":  "⚠️  SELL/AVOID"}
    action = {"intraday": "BUY → book at Target or SL",
              "swing":    "BUY on dip near Entry; trail SL",
              "holding":  "ACCUMULATE on dips",
              "sell":     "EXIT / AVOID new buys"}

    for key in ("intraday", "swing", "holding", "sell"):
        picks = buckets.get(key, [])
        print(f"\n  {label[key]}  ({len(picks)} picks)   → {action[key]}")
        print(f"  {'Symbol':<14}{'LTP':>10}{'1D%':>8}{'1M%':>8}{'RSI':>6}"
              f"{'Score':>8}{'Entry':>10}{'SL':>10}{'Target':>10}  Sector")
        for p in picks:
            t = p["tech"]; lv = p["levels"]
            sym = p["symbol"].replace(".NS", "")
            print(f"  {sym:<14}{p['price']:>10,.2f}{t['chg_1d_pct']:>+8.2f}"
                  f"{t['chg_1m_pct']:>+8.2f}{t['rsi14']:>6.0f}{p['bucket_score']:>8.0f}"
                  f"{lv['entry']:>10,.2f}{lv['sl']:>10,.2f}{lv['target']:>10,.2f}"
                  f"  {p['sector'][:20]}")

    print("\n  💰 MUTUAL FUNDS")
    print(f"  {'Scheme':<48}{'NAV':>10}{'1M%':>8}{'3M%':>8}{'1Y%':>8}{'Blend':>8}")
    for m in mfs:
        print(f"  {m['name'][:48]:<48}{m['nav']:>10,.2f}"
              f"{(m['r_1m'] or 0):>+8.2f}{(m['r_3m'] or 0):>+8.2f}"
              f"{(m['r_1y'] or 0):>+8.2f}{m['score']:>+8.2f}")

    if prior.get("available"):
        print("\n  🧾 PRIOR RUN REALISED ACCURACY")
        for b, info in prior["buckets"].items():
            hr = info.get("hit_rate")
            if hr is None: continue
            print(f"    {b:<10} {info['wins']}/{info['count']}   hit {hr:.0f}%")
    print("\n" + BAR + "\n")


# ── Senders ─────────────────────────────────────────────────────────────────

def _send(channel: str, image_path: str, caption: str,
          pdf_path: str | None = None) -> None:
    if channel == "telegram":
        ok = _tg_img(TELEGRAM_CHAT_ID, image_path, caption, TELEGRAM_BOT_TOKEN)
        if not ok:
            _tg_msg(TELEGRAM_CHAT_ID, caption, TELEGRAM_BOT_TOKEN)
        if pdf_path and os.path.exists(pdf_path):
            try:
                from lib.telegram import send_document as _tg_doc  # type: ignore
                _tg_doc(TELEGRAM_CHAT_ID, pdf_path, "📄 Full PDF report",
                        TELEGRAM_BOT_TOKEN)
            except Exception as exc:
                logger.warning(f"Telegram PDF send failed: {exc}")
        return

    # WhatsApp → loop over recipients
    for phone in PHONE_NUMBERS:
        if not phone: continue
        ok = _wa_img(phone, image_path, caption,
                     GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL)
        if not ok:
            _wa_msg(phone, caption, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL)
        if pdf_path and os.path.exists(pdf_path):
            try:
                from lib.whatsapp import send_document as _wa_doc  # type: ignore
                _wa_doc(phone, pdf_path, "📄 Full PDF report",
                        GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL)
            except Exception as exc:
                logger.warning(f"WhatsApp PDF send failed: {exc}")


# ── Main flow ───────────────────────────────────────────────────────────────

def run_report(dry_run: bool = False, channel: str = "whatsapp",
               theme: str | None = None,
               watchlist_path: str | None = None,
               make_pdf: bool = True) -> dict[str, Any]:
    logger.info("== Stock analyzer run starting ==")

    # 1. Resolve universe (watchlist ∪ NIFTY 100)
    watchlist = load_watchlist(watchlist_path or WATCHLIST_FILE)
    if watchlist:
        logger.info(f"Watchlist: {len(watchlist)} symbols from "
                    f"{watchlist_path or WATCHLIST_FILE}")

    _limit   = int(os.environ.get("STOCK_UNIVERSE_LIMIT", "0") or 0)
    full_uni = resolve_universe(watchlist_path)
    universe = full_uni[:_limit] if _limit > 0 else full_uni
    logger.info(f"Universe: {len(universe)} symbols "
                f"(total available: {len(full_uni)})")

    stocks    = fetch_universe(universe)
    mf_raw    = [fetch_mutual_fund(m["code"]) for m in MUTUAL_FUNDS]
    headlines = fetch_headlines()
    macro     = build_macro_context(headlines)
    logger.info(f"Macro regime: {macro.get('regime')} | bias={macro.get('bias')} "
                f"| geo-risk={macro.get('geo', {}).get('level')}")

    # NSE corporate announcements (fetched once, dispatched per-stock)
    nse_filings: list[dict] = []
    try:
        from .nse import fetch_corp_announcements
        nse_filings = fetch_corp_announcements() or []
        logger.info(f"NSE corp announcements: {len(nse_filings)} filings")
    except Exception as exc:
        logger.debug(f"NSE corp announcements skipped: {exc}")

    # ── Angel One live overlay (replaces stale prices, adds portfolio) ───
    # Fail-soft — pipeline runs unchanged when creds absent or Angel down.
    angel_holdings: list[dict] = []
    angel_funds:    dict       = {}
    try:
        from lib import angelone
        if angelone.is_available():
            # 1. Live LTP overlay — refresh last-close on each fetched stock
            #    so all downstream tech indicators / pick prices are accurate
            #    even if Yahoo is stale or weekend-frozen.
            replaced = 0
            for pkg in stocks:
                hist = pkg.get("history") or []
                if not hist:
                    continue
                live = angelone.fetch_ltp(pkg["symbol"])
                if live and live.get("ltp"):
                    hist[-1]["close"] = live["ltp"]
                    replaced += 1
            logger.info(f"Angel One LTP overlay: refreshed {replaced}/{len(stocks)} symbols")

            # 2. Portfolio holdings + funds for personalised report cards
            angel_holdings = angelone.fetch_holdings()
            angel_funds    = angelone.fetch_funds()
            logger.info(f"Angel One: {len(angel_holdings)} holdings, "
                        f"₹{angel_funds.get('available_cash', 0):,.0f} cash")
        else:
            logger.debug("Angel One not authenticated — overlay skipped.")
    except Exception as exc:
        logger.debug(f"Angel One overlay skipped: {exc}")

    if not stocks:
        logger.error("No stock data — aborting.")
        return {"ok": False, "error": "no data"}

    # 2. Analyse
    enriched = [enrich_stock(s, headlines, macro=macro,
                             nse_announcements=nse_filings) for s in stocks]

    # 3. Rank
    buckets = build_buckets(enriched)
    mfs     = rank_mutual_funds([m for m in mf_raw if m])

    # 4. Compare against prior run
    prev           = load_previous_report()
    current_prices = {s["symbol"]: s["price"] for s in enriched}
    prior          = score_prior_calls(prev, current_prices)

    # 4b. Self-learning: update feature weights from full history.
    #    Done AFTER predictions for this run because next run's predictor
    #    will pick up the freshly-tuned weights.
    try:
        update_learned_weights(current_prices, window_runs=30)
    except Exception as exc:
        logger.warning(f"Learner update skipped: {exc}")

    # 4c. Market-wide forecast (breadth + macro + prediction ensemble)
    try:
        from .market_forecast import forecast_market
        market_forecast = forecast_market(enriched, buckets, macro)
    except Exception as exc:
        logger.warning(f"Market forecast skipped: {exc}")
        market_forecast = None

    # 4d. Model self-review snapshot (best/worst features, overall accuracy)
    try:
        from .learner import self_review
        review = self_review(top_n=5)
    except Exception as exc:
        logger.warning(f"Self-review skipped: {exc}")
        review = None

    # 5. Persist
    payload = {
        "generated_at":    datetime.now().isoformat(timespec="seconds"),
        "buckets":         buckets,
        "mfs":             mfs,
        "watchlist":       watchlist,
        "macro":           {
            "regime":   macro.get("regime"),
            "bias":     macro.get("bias"),
            "geo":      macro.get("geo"),
            "snapshot": macro.get("snapshot"),
        },
        "market_forecast": market_forecast,
        "self_review":     review,
    }
    save_report(payload)

    # 6. Present
    _print_console_dry_run(buckets, mfs, prior, watchlist)

    # Expert advisor narrative (uses macro + learned weights + prior accuracy)
    advice = expert_advice(buckets, macro, prior, weights=_load_weights())

    image   = build_report_image(buckets, mfs, prior,
                                 out_path=IMAGE_OUTPUT_PATH, theme=theme,
                                 macro=macro, enriched=enriched,
                                 market_forecast=market_forecast,
                                 review=review,
                                 angel_holdings=angel_holdings,
                                 angel_funds=angel_funds)
    caption = build_text_summary(buckets, mfs, prior, macro=macro,
                                  market_forecast=market_forecast)
    caption = f"{advice}\n\n{caption}"
    _label  = os.environ.get("STOCK_SESSION_LABEL", "").strip()
    if _label:
        caption = f"*{_label}*\n\n{caption}"

    pdf_path: str | None = None
    if make_pdf:
        try:
            pdf_path = build_pdf_report(
                buckets, mfs, prior,
                all_enriched=enriched,
                watchlist_symbols=watchlist,
                macro=macro,
                advice=advice,
                out_path=PDF_OUTPUT_PATH,
                market_forecast=market_forecast,
                review=review,
            )
        except Exception as exc:
            logger.error(f"PDF generation failed: {exc}")

    # 7. Deliver
    if dry_run:
        logger.info("Dry-run: skipping send. Image + PDF saved locally; console printed.")
    else:
        _send(channel, image, caption, pdf_path=pdf_path)

    logger.info("== Stock analyzer run complete ==")
    return {
        "ok":      True,
        "image":   image,
        "pdf":     pdf_path,
        "buckets": buckets,
        "mfs":     mfs,
        "prior":   prior,
    }


def send_test_message(channel: str = "whatsapp") -> None:
    msg = f"✅ Stock analyzer test — {datetime.now():%Y-%m-%d %H:%M}"
    if channel == "telegram":
        _tg_msg(TELEGRAM_CHAT_ID, msg, TELEGRAM_BOT_TOKEN)
    else:
        for p in PHONE_NUMBERS:
            _wa_msg(p, msg, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL)
