"""
automations/gold_notifier/main.py
====================================
Core orchestration: fetch → analyse → predict → format → send.
"""

import logging
from datetime import date

from .config import (
    PHONE_NUMBER, PHONE_NUMBERS, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    INDIA_GOLD_DUTY_FACTOR, PREDICTION_LOG_FILE, IMAGE_THEME,
    IMAGE_OUTPUT_PATH,
)
from .fetchers import (
    get_gold_price, get_silver_price, get_price_history_10d,
    _fetch_goodreturns_history, fetch_grt_gold_rates,
)
from .analysis import (
    get_gold_analysis, get_geopolitical_analysis,
    get_global_market_signals, get_best_payment_date,
    get_scheme_payment_recommendation,
)
from .prediction import (
    load_prediction_model, save_prediction_model, save_weekly_forecast,
    _verify_past_predictions, _verify_weekly_forecasts, _recompute_weights,
    _compute_directional_bias,
    get_price_prediction, get_weekly_prediction, get_monthly_low_prediction,
    get_model_accuracy_stats,
)
from .formatter import format_message
from .image import generate_price_image
from lib.whatsapp import send_message as _send_msg, send_image as _send_img
from lib import telegram as _tg
from lib.proxy import PROXIES


def _notify(message: str, img_path: str | None = None, channel: str = "whatsapp", trigger: str = "Morning Update") -> None:
    """Send via Telegram or WhatsApp depending on `channel`."""
    from datetime import date as _date
    _caption = f"🥇 Gold Price Update | {trigger} — {_date.today().strftime('%d %b %Y')}"
    if channel == "telegram":
        if img_path:
            sent = _tg.send_photo(TELEGRAM_CHAT_ID, img_path, _caption, TELEGRAM_BOT_TOKEN, PROXIES)
            if not sent:
                logger.warning("Telegram photo failed — falling back to text.")
                _tg.send_message(TELEGRAM_CHAT_ID, message, TELEGRAM_BOT_TOKEN, PROXIES)
        else:
            _tg.send_message(TELEGRAM_CHAT_ID, message, TELEGRAM_BOT_TOKEN, PROXIES)
    else:
        for phone in PHONE_NUMBERS:
            if img_path:
                sent = _send_img(
                    phone, img_path, _caption,
                    GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL, PROXIES,
                )
                if not sent:
                    logger.warning(f"Image send failed for {phone} — falling back to text.")
                    _send_msg(phone, message, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL, PROXIES)
            else:
                _send_msg(phone, message, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL, PROXIES)

logger = logging.getLogger(__name__)


def send_price_update(dry_run: bool = False, channel: str = "whatsapp", trigger: str = "Morning Update", theme: str = IMAGE_THEME) -> None:
    """Fetch all data, run analysis, produce prediction, send update."""
    logger.info("─" * 50)
    logger.info(f"channel={channel}")
    logger.info("Fetching gold price …")
    data = get_gold_price()
    if data:
        logger.info(
            f"Gold: ${data['price_usd']:,.2f}/oz  |  ₹{data['price_inr_per_g']:,.2f}/g  |  "
            f"USD/INR={data['usd_inr_rate']:.2f}"
        )
        if data.get("ibja"):
            ibja = data["ibja"]
            logger.info(f"IBJA ({ibja['date']}): 24K=₹{ibja['24k']}/g  22K=₹{ibja['22k']}/g")

    logger.info("Fetching silver price …")
    silver = get_silver_price()
    if silver:
        logger.info(
            f"Silver: ${silver['price_usd']:.3f}/oz  ₹{silver['price_inr_g']:.2f}/g  "
            f"G/S ratio={silver.get('gs_ratio', '?')}"
        )

    logger.info("Fetching GRT Jewellers gold rates …")
    grt = fetch_grt_gold_rates()
    if grt:
        logger.info(f"GRT: 22K=₹{grt['22k']:,}/g  24K(est)=₹{grt['24k']:,}/g")

    logger.info("Loading prediction model …")
    model = load_prediction_model()
    price_now_usd = data["price_usd"] if data else 0.0
    if price_now_usd > 0:
        model["predictions"], _ph_usd, _ph_inr = _verify_past_predictions(model["predictions"])
        _verify_weekly_forecasts(model, _ph_inr)
        model["weights"]         = _recompute_weights(model["predictions"])
        model["bias_correction"] = _compute_directional_bias(model["predictions"])
        model["accuracy"]        = get_model_accuracy_stats(model["predictions"])
        logger.info(
            f"Model accuracy: {model['accuracy']}  "
            f"learned_bias={model['bias_correction']:+.2f}"
        )

    logger.info("Fetching geopolitical news …")
    geo = get_geopolitical_analysis()
    if geo:
        logger.info(f"Geo: {geo['geo_signal']}  bull={geo['bull_count']} bear={geo['bear_count']}")

    logger.info("Fetching global macro signals …")
    global_signals = get_global_market_signals()

    logger.info("Running technical analysis …")
    analysis = get_gold_analysis()
    if analysis:
        logger.info(
            f"Analysis: RSI={analysis['rsi']:.1f}  MACD={analysis['macd_val']:+.2f}  "
            f"BB={analysis['bb_pos']*100:.0f}%  score={analysis['score']}  "
            f"→ {analysis['recommendation']}"
        )

    logger.info("Computing best payment date …")
    payment = get_best_payment_date()
    if payment:
        logger.info(f"Best payment day: {payment['best_day']}  top3={payment['top3_days']}")

    usd_inr = data["usd_inr_rate"] if data else 84.0
    logger.info("Fetching 10-day price history …")
    history = get_price_history_10d(usd_inr)

    # Inject today's Chennai retail rate from goodreturns history
    if data and history:
        most_recent  = history[0]
        data["gr_chennai"] = {
            "24k":    most_recent["24k"],
            "22k":    most_recent["22k"],
            "date":   most_recent["date"],
            "source": "goodreturns.in Chennai",
        }
        logger.info(
            f"Chennai gold ({most_recent['date']}): "
            f"24K=₹{most_recent['24k']:,}/g  22K=₹{most_recent['22k']:,}/g"
        )

    # Derive this month's actual low from goodreturns full history. On
    # the first 1–2 days of a new month, this-month rows are very sparse
    # (often just today), which produces a misleading "low == today" reading
    # and an empty "Cheapest This Month" tile. When fewer than 5 rows exist
    # for the current calendar month, fall back to a rolling 22-trading-day
    # window so the user always sees a meaningful recent low.
    if payment:
        today_yr = date.today().year
        today_mo = date.today().month
        gr_full  = _fetch_goodreturns_history()
        month_rows: list = []
        if gr_full:
            for row in gr_full:
                row_d = row["date"]
                if row_d.month == today_mo and row_d.year == today_yr:
                    month_rows.append((row_d, row["22k"]))

        # Fallback: rolling last-22-days window if current month is sparse
        if len(month_rows) < 5 and gr_full:
            recent_22 = [(r["date"], r["22k"]) for r in gr_full[:22] if r.get("22k")]
            if len(recent_22) >= 5:
                month_rows = recent_22
                logger.info(
                    f"Current month sparse ({today_mo}/{today_yr}) — using "
                    f"rolling 22-day window for monthly low"
                )

        if month_rows:
            low_date_gr, low_22k_gr = min(month_rows, key=lambda x: x[1])
            payment["current_month_low_inr22k"] = low_22k_gr
            payment["current_month_low_date"]   = low_date_gr
            payment["current_month_low_day"]    = low_date_gr.day
            logger.info(
                f"Month low (goodreturns, {len(month_rows)} days): "
                f"₹{low_22k_gr:,}/g (22K) on {low_date_gr}"
            )
        else:
            existing_low = payment.get("current_month_low_price")
            if existing_low:
                existing_22k = round(
                    (existing_low / 31.1035) * usd_inr * INDIA_GOLD_DUTY_FACTOR * 22 / 24
                )
                payment["current_month_low_inr22k"] = existing_22k

    logger.info("Generating price prediction …")
    # Inject learned directional bias so get_price_prediction can shift the
    # score against systematic over-prediction (the explicit feedback loop).
    if data is not None:
        data["bias_correction"] = float(model.get("bias_correction", 0.0))
    prediction = get_price_prediction(
        analysis, geo, history,
        global_signals=global_signals,
        weights=model["weights"],
        data=data,
    )

    logger.info("Generating 7-day price forecast …")
    weekly_prediction = get_weekly_prediction(
        analysis, geo, usd_inr, global_signals,
        model=model,
        today_prediction=prediction,
    )
    if weekly_prediction:
        logger.info(f"7-day forecast: {[r['direction'] for r in weekly_prediction]}")
        save_weekly_forecast(model, weekly_prediction, date.today().isoformat())

    if data and price_now_usd > 0:
        save_prediction_model(model, {
            "date":             date.today().isoformat(),
            "price_usd":        round(price_now_usd, 2),
            "direction":        prediction["direction"],
            "score":            prediction["score"],
            "signal_votes":     prediction["signal_votes"],
            "actual_direction": None,
            "correct":          None,
        })

    logger.info("Predicting lowest-price day this month …")
    monthly_low_pred = get_monthly_low_prediction(
        analysis, geo, usd_inr, payment, global_signals
    )

    logger.info("Computing scheme-payment recommendation …")
    current_22k = (
        (data or {}).get("gr_chennai", {}).get("22k")
        or ((data or {}).get("ibja") or {}).get("22k")
    )
    scheme_reco = get_scheme_payment_recommendation(
        payment, analysis, current_22k_inr=current_22k
    )
    if scheme_reco:
        logger.info(
            f"Scheme reco: {scheme_reco['action']} "
            f"(score={scheme_reco['score']}, conf={scheme_reco['confidence']}, "
            f"pay_by={scheme_reco['pay_by_label']})"
        )

    # ── Build learning-status payload (shown in the report) ─────────────
    _bias  = float(model.get("bias_correction", 0.0))
    _shift = -_bias * 6.0   # mirrors prediction.py logic
    learning_status = {
        "bias":         _bias,
        "score_shift":  _shift,
        "acc":          (model.get("accuracy") or {}).get("acc_14")
                        or (model.get("accuracy") or {}).get("acc_30")
                        or (model.get("accuracy") or {}).get("acc_7"),
        "n":            (model.get("accuracy") or {}).get("n_14")
                        or (model.get("accuracy") or {}).get("n_30")
                        or (model.get("accuracy") or {}).get("n_7", 0),
        "flipped":      [k for k, v in (model.get("weights") or {}).items()
                         if isinstance(v, (int, float)) and v < 0],
    }

    message = format_message(
        data, analysis, payment, geo, history,
        prediction, weekly_prediction,
        global_signals=global_signals,
        monthly_low_pred=monthly_low_pred,
        silver=silver,
        channel=channel,
        model_stats=model.get("accuracy"),
        scheme_reco=scheme_reco,
        learning_status=learning_status,
    )

    channel_label = channel.capitalize()
    if dry_run:
        print("\n" + "=" * 50)
        print(f"DRY RUN — {channel_label} message preview:")
        print("=" * 50)
        print(message)
        print("=" * 50 + "\n")
        generate_price_image(
            data, analysis, payment, geo, history,
            prediction, weekly_prediction, global_signals,
            monthly_low_pred=monthly_low_pred, silver=silver,
            grt=grt,
            scheme_reco=scheme_reco,
            theme=theme,
            learning_status=learning_status,
        )
        print(f"Image saved as {IMAGE_OUTPUT_PATH}  (theme={theme})")
    else:
        img_path = generate_price_image(
            data, analysis, payment, geo, history,
            prediction, weekly_prediction, global_signals,
            monthly_low_pred=monthly_low_pred, silver=silver,
            grt=grt,
            scheme_reco=scheme_reco,
            theme=theme,
            learning_status=learning_status,
        )
        _notify(message, img_path, channel, trigger)

    # Archive runtime JSON state (predictions, alerts) under logs/<date>/.
    # The PNG already lives there because IMAGE_OUTPUT_PATH points at logs/.
    try:
        from lib.logging_setup import archive_artifacts
        from .config import PREDICTION_LOG_FILE, ALERT_STATE_FILE
        archive_artifacts("gold_notifier",
                          [PREDICTION_LOG_FILE, ALERT_STATE_FILE])
    except Exception as exc:
        logger.debug(f"artifact archival skipped: {exc}")


def send_test_message(channel: str = "whatsapp") -> None:
    """Send a simple test message to verify the configured notification channel."""
    from datetime import date as _date
    logger.info(f"Sending test message via {channel} …")
    today_str = _date.today().strftime("%A, %d %B %Y")
    _notify(
        f"🔔 *Gold Price Notifier* – Setup successful!\n"
        f"You will receive gold price updates at scheduled intervals.\n"
        f"──────────────────────────────\n"
        f"📡 Sent via {channel.capitalize()}  |  {today_str}",
        channel=channel,
        trigger="Test",
    )
