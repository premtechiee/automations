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
)
from .fetchers import (
    get_gold_price, get_silver_price, get_price_history_10d,
    _fetch_goodreturns_history,
)
from .analysis import (
    get_gold_analysis, get_geopolitical_analysis,
    get_global_market_signals, get_best_payment_date,
)
from .prediction import (
    load_prediction_model, save_prediction_model, save_weekly_forecast,
    _verify_past_predictions, _verify_weekly_forecasts, _recompute_weights,
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

    logger.info("Loading prediction model …")
    model = load_prediction_model()
    price_now_usd = data["price_usd"] if data else 0.0
    if price_now_usd > 0:
        model["predictions"], _ph_usd, _ph_inr = _verify_past_predictions(model["predictions"])
        _verify_weekly_forecasts(model, _ph_inr)
        model["weights"]  = _recompute_weights(model["predictions"])
        model["accuracy"] = get_model_accuracy_stats(model["predictions"])
        logger.info(f"Model accuracy: {model['accuracy']}")

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

    # Derive this month's actual low from goodreturns full history
    if payment:
        today_yr = date.today().year
        today_mo = date.today().month
        gr_full  = _fetch_goodreturns_history()
        month_rows = []
        if gr_full:
            for row in gr_full:
                row_d = row["date"]
                if row_d.month == today_mo and row_d.year == today_yr:
                    month_rows.append((row_d, row["22k"]))
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
    prediction = get_price_prediction(
        analysis, geo, history,
        global_signals=global_signals,
        weights=model["weights"],
    )

    logger.info("Generating 7-day price forecast …")
    weekly_prediction = get_weekly_prediction(analysis, geo, usd_inr, global_signals)
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

    message = format_message(
        data, analysis, payment, geo, history,
        prediction, weekly_prediction,
        global_signals=global_signals,
        monthly_low_pred=monthly_low_pred,
        silver=silver,
        channel=channel,
        model_stats=model.get("accuracy"),
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
            theme=theme,
        )
        print(f"Image saved as data/gold_update.png  (theme={theme})")
    else:
        img_path = generate_price_image(
            data, analysis, payment, geo, history,
            prediction, weekly_prediction, global_signals,
            monthly_low_pred=monthly_low_pred, silver=silver,
            theme=theme,
        )
        _notify(message, img_path, channel, trigger)


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
