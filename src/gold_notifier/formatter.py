"""
automations/gold_notifier/formatter.py
=========================================
WhatsApp text message formatter for the gold price update.
"""

import logging
from datetime import date, datetime

from .config import INDIA_GOLD_DUTY_FACTOR

logger = logging.getLogger(__name__)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"


def _plain(r: str) -> str:
    """Convert technical reason text into simple English."""
    return (r
        .replace("RSI", "price level")
        .replace("deeply oversold, strong bounce likely",  "price has dropped a lot — likely to go back up soon")
        .replace("oversold, upward pressure building",     "price is quite low — buyers are stepping in")
        .replace("below midline, mild bullish bias",       "price is on the lower side — slight upward tendency")
        .replace("overbought, pullback likely",            "price has risen too fast — may cool down soon")
        .replace("above midline, mild bearish bias",       "price is on the higher side — slight downward tendency")
        .replace("MACD bullish crossover – uptrend signal",  "short-term trend is turning upward")
        .replace("MACD bearish crossover – downtrend signal","short-term trend is turning downward")
        .replace("Bollinger", "price range indicator")
        .replace("at lower band, bounce zone",   "price is at a low support level — often bounces back from here")
        .replace("near lower band, upside bias", "price is near its recent low — has room to go up")
        .replace("at upper band, reversal risk", "price is near its recent high — may reverse downward")
        .replace("near upper band, resistance",  "price is close to resistance — may slow down")
        .replace("sustained upward momentum",   "gold has been rising steadily for 3 days")
        .replace("sustained downward pressure", "gold has been falling for 3 days")
        .replace("Strong geopolitical tension – safe-haven demand",    "global tensions are high — people are buying gold as safety")
        .replace("Mild geopolitical risk – some safe-haven support",   "some global uncertainty — mild support for gold")
        .replace("Easing geopolitical risk – reduced safe-haven demand","world situation calming — less urgency to buy gold")
        .replace("Monday – watch for weekend gap risk",      "Monday — watch for any big weekend news impact")
        .replace("Friday – profit-taking tendency",          "Friday — traders often sell before the weekend")
        .replace("Dollar weakening – gold tailwind (inverse relation)",    "US dollar is weaker — good for gold prices")
        .replace("Dollar strengthening – gold headwind (inverse relation)", "US dollar is stronger — puts pressure on gold")
        .replace("Falling yields – gold opportunity cost drops",   "US savings rates falling — gold becomes more attractive")
        .replace("Rising yields – gold opportunity cost rises",    "US savings rates rising — gold faces competition")
        .replace("Elevated VIX – fear driving safe-haven gold demand", "markets are fearful — more people buying gold as safety")
        .replace("Low VIX – calm markets, reduced safe-haven demand",  "markets are calm — less urgency to buy gold")
        .replace("Equity selloff – risk-off flow into gold",      "stock markets falling — investors moving money into gold")
        .replace("Equity rally – risk-on rotation away from gold","stock markets rising — some money moving out of gold")
        .replace("Rising oil – inflation hedge demand for gold",  "oil prices rising — gold in demand as inflation hedge")
        .replace("Falling oil – lower inflation, mild gold drag", "oil prices falling — less inflation pressure on gold")
    )


def _plain_geo_desc(key: str, vote: int, desc: str) -> str:
    """Translate a global signal key into a plain-English sentence."""
    if key == "dxy":
        if vote > 0: return "US dollar is falling — this is good for gold"
        if vote < 0: return "US dollar is rising — puts pressure on gold prices"
        return "US dollar is steady — no strong impact on gold"
    if key == "yields":
        if vote > 0: return "US interest rates are falling — gold becomes more attractive"
        if vote < 0: return "US interest rates are rising — makes gold less attractive"
        return "US interest rates are stable — no major impact"
    if key == "vix":
        if vote > 0: return "Markets are nervous / fearful — people are buying gold as safety"
        if vote < 0: return "Markets are very calm — less demand for gold as a safe option"
        return "Market nervousness is at a normal level"
    if key == "risk_assets":
        if vote > 0: return "Stock markets are falling — investors moving money into gold"
        if vote < 0: return "Stock markets are rising — some money moving away from gold"
        return "Stock markets are steady — no strong push for gold"
    if key == "oil":
        if vote > 0: return "Oil prices are rising — inflation concerns are boosting gold"
        if vote < 0: return "Oil prices are falling — less inflation worry, mild drag on gold"
        return "Oil prices are stable — no inflation signal for gold"
    return desc


def format_message(
    data: dict | None,
    analysis: dict | None = None,
    payment: dict | None = None,
    geo: dict | None = None,
    history: list | None = None,
    prediction: dict | None = None,
    weekly_prediction: list | None = None,
    global_signals: dict | None = None,
    monthly_low_pred: dict | None = None,
    silver: dict | None = None,
    channel: str = "whatsapp",
    model_stats: dict | None = None,
    scheme_reco: dict | None = None,
    learning_status: dict | None = None,
) -> str:
    now   = datetime.now().strftime("%d %b %Y, %I:%M %p")
    today = date.today()
    DIV   = "─" * 30

    def inr_g(usd_oz: float, usd_inr: float) -> str:
        return f"₹{round(usd_oz * usd_inr / 31.1035):,}"

    if not data:
        return (
            f"🥇 *Gold Price Update*\n{now}\n"
            f"⚠️ Could not fetch the price right now. Please try again later.\n"
            f"📡 Sent via {channel.capitalize()}"
        )

    usd_inr    = data["usd_inr_rate"]
    ibja       = data.get("ibja")
    gr_chennai = data.get("gr_chennai")

    if gr_chennai:
        p24k = gr_chennai["24k"]; p22k = gr_chennai["22k"]
        src  = f"goodreturns.in Chennai ({gr_chennai['date']})"
    elif ibja:
        p24k = ibja["24k"]; p22k = ibja["22k"]
        src  = f"IBJA ({ibja['date']})"
    else:
        p24k = round(data["price_inr_per_g"] * INDIA_GOLD_DUTY_FACTOR)
        p22k = round(p24k * 22 / 24)
        src  = "Live market estimate"

    chg_val = round(data["change_inr_g"]) if data.get("change_inr_g") is not None else None
    if chg_val and chg_val > 0:   chg_str = f"▲ up ₹{abs(chg_val):,}/g from yesterday"
    elif chg_val and chg_val < 0: chg_str = f"▼ down ₹{abs(chg_val):,}/g from yesterday"
    else:                         chg_str = "No change from yesterday"

    lines = [
        f"🥇 *Gold Price — {now}*",
        f"  Source : {src}",
        DIV,
        f"  24 Carat  ₹{p24k:,} per gram   (₹{p24k*8:,} for 8g)",
        f"  22 Carat  ₹{p22k:,} per gram   (₹{p22k*8:,} for 8g)",
        f"  Today    {chg_str}",
    ]

    if silver:
        s_inr_g  = silver["price_inr_g"]
        s_chg    = silver.get("change_inr_g")
        gs_ratio = silver.get("gs_ratio")
        if s_chg and s_chg > 0:   s_chg_str = f"▲ up ₹{abs(s_chg):.2f}/g from yesterday"
        elif s_chg and s_chg < 0: s_chg_str = f"▼ down ₹{abs(s_chg):.2f}/g from yesterday"
        else:                     s_chg_str = "No change from yesterday"
        lines += [
            DIV, f"🥈 *Silver Price*",
            f"  Silver (999)  ₹{s_inr_g:,.2f} per gram  (₹{silver['price_inr_kg']:,} per kg)",
            f"  COMEX         ${silver['price_usd']:.3f} per troy oz",
            f"  Today         {s_chg_str}",
        ]
        if gs_ratio:
            if   gs_ratio > 90: ratio_note = f"  Gold/Silver ratio: {gs_ratio} → gold is expensive vs silver"
            elif gs_ratio < 65: ratio_note = f"  Gold/Silver ratio: {gs_ratio} → gold is cheap vs silver"
            else:               ratio_note = f"  Gold/Silver ratio: {gs_ratio} (normal range 65–90)"
            lines.append(ratio_note)

    # Strong buy alert
    chg_30d   = analysis.get("chg_30d") if analysis else None
    strong    = (p24k < 12_500) and (chg_30d is not None) and (float(chg_30d) <= -5.0)
    if strong:
        c30 = float(chg_30d)  # type: ignore[arg-type]
        p30_ago = round(p24k / (1 + c30 / 100))
        lines += [
            DIV, f"🚨 *RARE BUYING OPPORTUNITY — ACT NOW!*",
            f"  24K is ₹{p24k:,}/g — BELOW ₹12,500 threshold!",
            f"  Price is {abs(c30):.1f}% CHEAPER than 30 days ago (was ₹{p30_ago:,}/g)",
            f"  ✅ This level is rarely seen — strong case to BUY gold NOW.",
            DIV,
        ]

    # Monthly low prediction
    if monthly_low_pred:
        mlp       = monthly_low_pred
        pred_date = mlp["predicted_date"]
        mon_name  = pred_date.strftime("%B %Y")
        day_label = f"{_ordinal(mlp['predicted_day'])} {pred_date.strftime('%B')} ({mlp['predicted_weekday']})"
        conf_em   = {"High": "🟢", "Moderate": "🟡", "Low": "🟠"}.get(mlp["confidence"], "⚪")
        lines += [
            DIV, f"🎯 *Best Day to Buy in {mon_name} — Prediction*",
            f"  📅 Predicted Cheapest Day  : {day_label}",
            f"  💰 Expected 24K price       : ₹{mlp['low_inr']:,} – ₹{mlp['high_inr']:,} per gram",
            f"  💎 Expected 22K price       : ₹{mlp['low_22k']:,} – ₹{mlp['high_22k']:,} per gram",
            f"  📊 Prediction confidence    : {conf_em} {mlp['confidence']}",
            f"  ⏳ Days remaining this month: {mlp['days_remaining']}",
        ]
        if mlp.get("hist_aligns"):
            lines.append(f"  ✅ Also matches historical cheapest day pattern!")
        top3 = mlp.get("top3", [])
        if len(top3) > 1:
            alt = " | ".join(
                f"{_ordinal(c['day'])} {c['date'].strftime('%b')} ({c['short_day']}) ≈ ₹{c['mid_inr']:,}/g"
                for c in top3[1:3]
            )
            lines.append(f"  🔄 Runner-up days           : {alt}")
        lines.append(f"  💡 {mlp['reasoning']}")
        lines.append(DIV)

    # Today's outlook
    if prediction or analysis or geo:
        lines += [DIV, "📊 *What to Expect Today*"]

        # Model self-accuracy stats
        if model_stats and model_stats.get("total", 0) >= 3:
            acc = model_stats.get("acc_14") or model_stats.get("acc_30") or model_stats.get("acc_7")
            n   = model_stats.get("n_14")   or model_stats.get("n_30")   or model_stats.get("n_7", 0)
            streak      = model_stats.get("streak", 0)
            streak_type = model_stats.get("streak_type")
            if acc is not None:
                acc_icon = "🟢" if acc >= 70 else ("🟡" if acc >= 55 else "🔴")
                acc_line = f"  🤖 Model accuracy (last {n} days): {acc_icon} {acc}%"
                if streak >= 3 and streak_type == "correct":
                    acc_line += f"  •  🔥 {streak}-day correct streak!"
                elif streak >= 2 and streak_type == "wrong":
                    acc_line += f"  •  ⚠️ Missed last {streak} in a row — treat with caution"
                lines.append(acc_line)

        # Self-learning status: shows the bias correction the model applied
        # to today's score after observing past mistakes. Negative bias means
        # the model used to over-call DOWN; positive means it over-called UP.
        if learning_status:
            ls   = learning_status
            bias = float(ls.get("bias", 0.0) or 0.0)
            sh   = float(ls.get("score_shift", 0.0) or 0.0)
            flipped = ls.get("flipped") or []
            if abs(bias) >= 0.05:
                arrow = "↓" if sh < 0 else "↑"
                lean  = "over-called UP" if bias > 0 else "over-called DOWN"
                lines.append(
                    f"  🧠 Self-learning: was {lean} "
                    f"→ today's score adjusted {arrow}{abs(sh):.1f} pts "
                    f"(bias {bias:+.2f})"
                )
            elif (ls.get("n") or 0) >= 3:
                lines.append(
                    f"  🧠 Self-learning: model is calibrated (no bias correction needed)"
                )
            if flipped:
                shown = ", ".join(flipped[:4])
                more  = f" (+{len(flipped) - 4} more)" if len(flipped) > 4 else ""
                lines.append(
                    f"  🔄 Inverted misleading signals: {shown}{more}"
                )

        if prediction:
            d     = prediction["direction"]
            conf  = prediction["confidence"]
            arrow = "📈" if d == "UP" else ("📉" if d == "DOWN" else "➡️")
            d_eng = {"UP":"likely to go UP","DOWN":"likely to go DOWN","FLAT":"likely to stay FLAT"}.get(d, d)
            c_eng = {"High":"very confident","Moderate":"fairly confident","Low":"not very sure","Uncertain":"unclear"}.get(conf, conf)
            all_r = prediction.get("reasons_up", []) + prediction.get("reasons_down", [])
            lines.append(f"  Price is {d_eng}  {arrow}  ({c_eng})")
            if all_r:
                lines.append(f"  Reason  : {_plain(all_r[0])}")

        if analysis:
            score2 = analysis["score"] + (geo["geo_score"] if geo else 0)
            if   score2 >= 5: advice = "🟢 Good time to buy — price is low"
            elif score2 >= 3: advice = "🟡 Reasonable to buy right now"
            elif score2 >= 1: advice = "⚪ Better to wait — price may drop a bit more"
            elif score2 >=-1: advice = "🟠 Hold off — price is on the higher side"
            else:             advice = "🔴 Not a good time — price is quite high"
            sup = inr_g(analysis["bb_low_usd"], usd_inr)
            rec = inr_g(analysis["recovery_usd"], usd_inr)
            lines.append(f"  Should I buy? {advice}")
            lines.append(f"  Good entry price : {sup}/g   Expected to recover to : {rec}/g")

        if geo:
            geo_eng = (geo["geo_signal"]
                .replace("🔴 HIGH RISK – Strong safe-haven demand",   "🔴 World tensions are very high — strong push for gold")
                .replace("🟠 ELEVATED – Geopolitical tensions active","🟠 Global tensions are active — supporting gold prices")
                .replace("🟡 MODERATE – Mixed macro signals",         "🟡 Mixed global signals — no clear direction")
                .replace("🟢 CALM – Risk-off sentiment easing",       "🟢 World situation is calming — less urgency for gold"))
            lines.append(f"  World news : {geo_eng}")

    # World market signals
    if global_signals:
        lines += [DIV, "🌍 *What the World Markets Say*"]
        descs  = global_signals.get("descriptions", {})
        votes  = global_signals.get("votes", {})
        labels = {
            "dxy":         "US Dollar    ",
            "yields":      "Interest Rates",
            "vix":         "Market Fear  ",
            "risk_assets": "Stock Markets",
            "oil":         "Oil Prices   ",
        }
        for key in ["dxy","yields","vix","risk_assets","oil"]:
            if key not in descs:
                continue
            v    = votes.get(key, 0)
            icon = "🟢" if v > 0 else ("🔴" if v < 0 else "⚪")
            eng  = _plain_geo_desc(key, v, descs[key])
            lines.append(f"  {icon} {labels.get(key, key)}: {eng}")
        net_eng = (global_signals["global_outlook"]
            .replace("🟢 Tailwinds (weak dollar / falling yields / fear)", "🟢 Overall good conditions for gold")
            .replace("🟡 Mildly positive for gold",  "🟡 Slightly positive for gold overall")
            .replace("⚪ Mixed — no clear macro direction", "⚪ No clear direction from world markets")
            .replace("🟠 Mildly negative for gold",  "🟠 Slightly negative for gold overall")
            .replace("🔴 Headwinds (strong dollar / rising yields / risk-on)", "🔴 Conditions are against gold right now"))
        lines.append(f"  Overall  : {net_eng}")

    # 7-day forecast
    if weekly_prediction:
        lines += [DIV, "📅 *Predicted Price for Next 7 Days  (24 Carat / 22 Carat per gram)*"]
        for row in weekly_prediction:
            d_str = row["date"].strftime("%a, %d %b")
            if row["is_weekend"]:
                lines.append(f"  {d_str}   📵 Market closed")
            else:
                arrow = "📈" if row["direction"]=="UP" else ("📉" if row["direction"]=="DOWN" else "➡️")
                lines.append(
                    f"  {d_str}  {arrow}{row['emoji']}  "
                    f"₹{row['low_inr']:,} – ₹{row['high_inr']:,}  /  "
                    f"₹{row['low_22k']:,} – ₹{row['high_22k']:,}"
                )
        lines.append("  ⚠️ These are estimates, not guarantees")

    # Best time to buy
    if payment:
        lines += [DIV, "📉 *Best Time to Buy This Month*"]
        lo_price = payment.get("current_month_low_price")
        lo_date  = payment.get("current_month_low_date")
        trend    = payment.get("current_month_trend")
        if lo_date and (lo_price or payment.get("current_month_low_inr22k")):
            lo_inr22 = payment.get("current_month_low_inr22k") or round(
                (lo_price / 31.1035) * usd_inr * INDIA_GOLD_DUTY_FACTOR * 22 / 24
            )
            days_ago = (today - lo_date).days
            d_lbl    = "today" if days_ago == 0 else f"{_ordinal(lo_date.day)} {lo_date.strftime('%b')} ({days_ago} days ago)"
            t_map    = {"falling":"still going down — better to wait a little",
                        "rising": "already going back up — the low is probably behind us",
                        "flat":   "not moving much — stable"}
            t_lbl = t_map.get(trend or "", "")
            lines.append(f"  Last cheapest date : {d_lbl}  •  ₹{lo_inr22:,}/g (22K)")
            if t_lbl:
                lines.append(f"  Price trend now : {t_lbl}")

        best_date = payment.get("best_date_this_month")
        if best_date:
            if best_date >= today:
                days_left = (best_date - today).days
                when = "today!" if days_left == 0 else f"{_ordinal(best_date.day)} {best_date.strftime('%B')} (in {days_left} days)"
            else:
                nd   = payment.get("best_date_next_month")
                when = nd.strftime(f"{_ordinal(nd.day)} %B %Y") if nd else "next month"
            lines.append(f"  Historically cheapest day each month : {_ordinal(payment['best_day'])}  •  Next : {when}")

        mn        = payment.get("scheme_month_names", {})
        top3s     = payment.get("scheme_top3_starts") or []
        best_sn   = payment.get("scheme_best_start_name", "")
        worst_pct = payment.get("scheme_worst_start_pct", 0)
        top3_str  = ",  ".join(
            f"{mn.get(m,'?')} (+{p}% costlier)" if p > 0 else mn.get(m,"?")
            for m, p in top3s
        ) if top3s else ""
        cur_extra = next((p for m, p in top3s if m == today.month), None)
        if   cur_extra is not None and cur_extra <= 0.5: scheme_note = f"✅ {mn.get(today.month,'This month')} is one of the best months to start a gold scheme!"
        elif cur_extra is not None and cur_extra <= 2.0: scheme_note = f"🟡 {mn.get(today.month,'This month')} is an okay month — only {cur_extra}% more than the ideal"
        elif cur_extra is not None:                       scheme_note = f"🔴 {mn.get(today.month,'This month')} is {cur_extra}% more expensive — {best_sn} would be better"
        else:                                             scheme_note = ""
        lines += [
            f"  Best month to start a gold scheme : {best_sn}",
            f"  Top 3 good months to start : {top3_str}",
            f"  Starting at the wrong month can cost you ~{worst_pct}% more over the scheme",
        ]
        if scheme_note:
            lines.append(f"  {scheme_note}")

        # Day-of-week & average monthly swing (added)
        best_dow_name  = payment.get("best_dow_name")
        worst_dow_name = payment.get("worst_dow_name")
        avg_swing      = payment.get("avg_monthly_swing_pct")
        if best_dow_name and worst_dow_name:
            lines.append(
                f"  Cheapest day of the week : {best_dow_name}   "
                f"•  Most expensive : {worst_dow_name}"
            )
        if avg_swing:
            lines.append(
                f"  Typical monthly swing : ~{avg_swing}%  "
                f"(gap between high and low within a month)"
            )

    # ── Gold Scheme Payment Recommendation (forward-looking) ──
    if scheme_reco:
        action = scheme_reco["action"]
        conf   = scheme_reco["confidence"]
        pay_by = scheme_reco.get("pay_by_label", "—")
        reasons = scheme_reco.get("reasons") or []
        save_g  = scheme_reco.get("est_savings_inr_g")
        save_p  = scheme_reco.get("est_savings_pct")
        tva     = scheme_reco.get("today_vs_avg_pct")

        action_label = {
            "PAY_NOW":      "🟢 PAY NOW — today is a good window",
            "PAY_BY_DATE":  "🟡 PAY BY THE TARGET DATE",
            "WAIT_FOR_DIP": "🟠 WAIT — better entry likely in a few days",
        }.get(action, action)

        conf_emoji = {"High":"🟢","Moderate":"🟡","Low":"⚪"}.get(conf, "⚪")

        lines += [DIV, "💰 *Gold Scheme — When to Pay This Month*"]
        lines.append(f"  Recommendation : {action_label}")
        lines.append(f"  Target payment date : {pay_by}")
        lines.append(f"  Confidence : {conf_emoji} {conf}")
        if tva is not None:
            if tva <= -0.5:
                lines.append(f"  Today is ~{abs(tva):.1f}% cheaper than this month's average")
            elif tva >= 0.5:
                lines.append(f"  Today is ~{tva:.1f}% above this month's average")
            else:
                lines.append("  Today is roughly at the month's average price")
        if save_g and save_p:
            lines.append(
                f"  Paying on the right day can save ~₹{save_g:,}/g  "
                f"(≈ {save_p}% vs the worst-day-of-month historically)"
            )
        if reasons:
            lines.append("  Why:")
            for r in reasons[:5]:
                lines.append(f"    • {r}")
        lines.append(
            "  💡 Gold-scheme rule of thumb: you accumulate MORE grams when "
            "the price is LOW — pay on dips, not on rallies."
        )

    # Last 10 days
    if history:
        lines += [DIV, "🗓️ *Gold Prices — Last 10 Days  (24 Carat / 22 Carat per gram)*"]
        for row in history[:10]:
            chg = row["chg"]
            if   chg > 0: c = f"  ▲ +₹{chg:,}"
            elif chg < 0: c = f"  ▼ -₹{abs(chg):,}"
            else:         c = "  ─ ₹0"
            lines.append(
                f"  {row['date']} {row['weekday']}  "
                f"₹{row['24k']:,} / ₹{row['22k']:,}{c}"
            )

    return "\n".join(l for l in lines if l is not None) + (
        f"\n{DIV}"
        f"\n📡 Sent via {channel.capitalize()}  |  {today.strftime('%A, %d %B %Y')}"
    )
