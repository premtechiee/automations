"""
stock_analyzer/pdf_report.py
=============================
Detailed PDF report using reportlab (flowable tables, auto page-break).
Keep the image report crisp & scannable; this PDF has the long-form details.
"""

from __future__ import annotations
import logging
import os
from datetime import datetime

from reportlab.lib              import colors
from reportlab.lib.pagesizes    import A4
from reportlab.lib.styles       import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units        import mm
from reportlab.platypus         import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether,
)

from .config import PDF_OUTPUT_PATH, DISCLAIMER

logger = logging.getLogger(__name__)


# ── Styles ─────────────────────────────────────────────────────────────────

def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(
        "H1x", parent=ss["Heading1"], fontSize=20, textColor=colors.HexColor("#1E6BD8"),
        spaceAfter=6, leading=24))
    ss.add(ParagraphStyle(
        "H2x", parent=ss["Heading2"], fontSize=14, textColor=colors.HexColor("#1E6BD8"),
        spaceBefore=10, spaceAfter=4, leading=18))
    ss.add(ParagraphStyle(
        "muted", parent=ss["BodyText"], fontSize=9, textColor=colors.HexColor("#666"),
        spaceAfter=4))
    ss.add(ParagraphStyle(
        "body", parent=ss["BodyText"], fontSize=10, leading=13, spaceAfter=4))
    ss.add(ParagraphStyle(
        "cell", parent=ss["BodyText"], fontSize=8.5, leading=10))
    ss.add(ParagraphStyle(
        "cellb", parent=ss["BodyText"], fontSize=8.5, leading=10,
        textColor=colors.HexColor("#111"), fontName="Helvetica-Bold"))
    return ss


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def _fmt_num(v, places: int = 2):
    if v is None:
        return "—"
    return f"{v:,.{places}f}"


def _colour_pct(v):
    if v is None:
        return colors.grey
    return colors.HexColor("#148C5A") if v >= 0 else colors.HexColor("#C83240")


# ── Table builders ──────────────────────────────────────────────────────────

def _stock_bucket_table(title: str, picks: list[dict], recommendation: str):
    header = ["Stock", "Sector", "Price ₹", "Today", "1 Mo", "3 Mo", "Momentum",
              "Finances", "Trend", "News", "Score", "Buy At", "Exit", "Target", "Profit% / Hold"]
    data = [header]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E6BD8")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 7.5),
        ("FONTSIZE",   (0, 1), (-1, -1), 7.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F5F7FA"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, p in enumerate(picks, start=1):
        t = p["tech"]; lv = p["levels"]
        sym = p["symbol"].replace(".NS", "")
        profit_pct = lv.get("expected_profit_pct", 0)
        hold_days  = lv.get("est_hold_days", 0)
        if hold_days == 0:
            hold_txt = "intraday"
        elif hold_days >= 252:
            hold_txt = "1y+"
        else:
            hold_txt = f"{hold_days}d"
        data.append([
            sym,
            (p["sector"] or "—")[:14],
            _fmt_num(p["price"]),
            _fmt_pct(t["chg_1d_pct"]),
            _fmt_pct(t["chg_1m_pct"]),
            _fmt_pct(t["chg_3m_pct"]),
            f"{t['rsi14']:.0f}",
            f"{p['fund']['score']:.0f}",
            f"{t.get('trend_up') and '↑' or '↓'}",
            f"{p['senti']['score']:.0f}",
            f"{p['bucket_score']:.0f}",
            _fmt_num(lv["entry"]),
            _fmt_num(lv["sl"]),
            _fmt_num(lv["target"]),
            f"{profit_pct:+.1f}% / {hold_txt}",
        ])
        # cell-level colours for % cells
        for col_idx, v in [(3, t["chg_1d_pct"]), (4, t["chg_1m_pct"]), (5, t["chg_3m_pct"])]:
            style.append(("TEXTCOLOR", (col_idx, i), (col_idx, i), _colour_pct(v)))
        style.append(("TEXTCOLOR", (12, i), (12, i), colors.HexColor("#C83240")))
        style.append(("TEXTCOLOR", (13, i), (13, i), colors.HexColor("#148C5A")))

    # Total must stay <= 182 mm (A4 portrait minus 14 mm margins each side)
    col_w = [16, 18, 13, 11, 11, 11, 10, 10, 9, 10, 11, 14, 13, 14, 11]  # = 182 mm
    tbl = Table(data, colWidths=[w * mm for w in col_w], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    return tbl


def _mf_table(mfs: list[dict]):
    header = ["Fund Name", "Category", "Unit Price ₹", "1 Mo %", "3 Mo %", "1 Yr %", "3 Yr %", "Overall"]
    data = [header]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#148C5A")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 9),
        ("FONTSIZE",   (0, 1), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F5F7FA"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, m in enumerate(mfs, start=1):
        data.append([
            m["name"][:52],
            (m["cat"] or "—")[:16],
            _fmt_num(m["nav"]),
            _fmt_pct(m["r_1m"]),
            _fmt_pct(m["r_3m"]),
            _fmt_pct(m["r_1y"]),
            _fmt_pct(m["r_3y"]),
            f"{m['score']:+.2f}",
        ])
        for col_idx, v in [(3, m["r_1m"]), (4, m["r_3m"]), (5, m["r_1y"]), (6, m["r_3y"])]:
            style.append(("TEXTCOLOR", (col_idx, i), (col_idx, i), _colour_pct(v)))

    # Total must stay <= 182 mm (A4 portrait minus 14 mm margins each side)
    col_w = [60, 22, 16, 14, 14, 14, 14, 14]  # = 168 mm, leaves breathing room
    tbl = Table(data, colWidths=[w * mm for w in col_w], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    return tbl


def _prior_table(prior: dict):
    if not prior.get("available"):
        return None
    header = ["Category", "Picks", "Correct", "Success Rate"]
    data = [header]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#666")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F5F7FA"), colors.white]),
    ]
    for b in ("intraday", "swing", "holding", "sell"):
        info = prior["buckets"].get(b, {})
        hr = info.get("hit_rate")
        data.append([b.capitalize(), info.get("count", 0), info.get("wins", 0),
                     f"{hr:.0f}%" if hr is not None else "—"])
    tbl = Table(data, colWidths=[40 * mm, 25 * mm, 25 * mm, 30 * mm], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    return tbl


def _per_stock_detail_row(p: dict, ss):
    """A small key-value paragraph block describing one stock in depth."""
    t   = p["tech"]; f = p["fund"]; lv = p["levels"]
    sym = p["symbol"].replace(".NS", "")
    rationale = _build_rationale(p)
    body = (
        f"<b>{sym} — {f.get('name','')}</b> &nbsp;|&nbsp; "
        f"Sector: {f.get('sector','—')} &nbsp;|&nbsp; "
        f"Company Size: {_fmt_mcap(f.get('mcap'))}<br/>"
        f"Current Price <b>₹{p['price']:,.2f}</b> &nbsp;"
        f"Today {_fmt_pct(t['chg_1d_pct'])}, 1 Month {_fmt_pct(t['chg_1m_pct'])}, "
        f"3 Months {_fmt_pct(t['chg_3m_pct'])}<br/>"
        f"Price/Earnings {_fmt_num(f.get('pe'))} &nbsp; Price/Book {_fmt_num(f.get('pb'))} &nbsp; "
        f"Return on Equity {_fmt_pct((f.get('roe') or 0) * 100 if f.get('roe') and abs(f['roe']) < 2 else f.get('roe'))} &nbsp; "
        f"Debt Level {_fmt_num(f.get('de'))} &nbsp; "
        f"Momentum {t['rsi14']:.0f} &nbsp; Daily Swing {t['atr_pct']:.2f}%<br/>"
        f"<b>Action:</b> Buy at ₹{lv['entry']:,.2f} &nbsp; "
        f"<font color='#C83240'>Exit if drops to ₹{lv['sl']:,.2f}</font> &nbsp; "
        f"<font color='#148C5A'>Profit Target ₹{lv['target']:,.2f}</font> &nbsp; "
        f"Score <b>{p['bucket_score']:.0f}/100</b><br/>"
        f"<b>Expected profit:</b> {lv.get('expected_profit_pct', 0):+.2f}% "
        f"(risk {lv.get('risk_pct', 0):.2f}%, R:R 1:{lv.get('rr', 0):.1f}) &nbsp;|&nbsp; "
        f"<b>Hold:</b> {lv.get('hold_hint','')}<br/>"
        f"<b>When to buy:</b> {lv.get('buy_window','')}<br/>"
        + (f"<b>5-day range:</b> ₹{lv['forecast_5d'][0]:,.2f} – ₹{lv['forecast_5d'][1]:,.2f}<br/>"
           if lv.get('forecast_5d') else "")
        + f"<i>{rationale}</i>"
    )
    return Paragraph(body, ss["body"])


def _build_rationale(p: dict) -> str:
    t, f, s = p["tech"], p["fund"], p["senti"]
    bits: list[str] = []
    bits.append("price trending up" if t["trend_up"] else "price trending down")
    if t["macd_hist"] > 0:     bits.append("momentum positive")
    else:                      bits.append("momentum negative")
    if t["rsi14"] > 70:        bits.append(f"overbought (may pull back)")
    elif t["rsi14"] < 30:      bits.append(f"oversold (may bounce)")
    if t["vol_ratio"] > 1.3:   bits.append(f"trading volume high (+{(t['vol_ratio'] - 1) * 100:.0f}%)")
    if f["score"] >= 65:       bits.append("healthy company finances")
    elif f["score"] <= 40:     bits.append("weak company finances")
    if s["matched"] and s["score"] >= 60:    bits.append("good news sentiment")
    elif s["matched"] and s["score"] <= 40:  bits.append("bad news sentiment")

    # Candlestick patterns
    for pat in (p.get("patterns") or [])[:2]:
        bits.append(pat.lower())

    # Prediction
    pred = p.get("predict") or {}
    if pred:
        arrow = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→"}.get(pred.get("direction"), "")
        bits.append(f"short-term outlook {arrow} {pred.get('direction','?')} "
                    f"({pred.get('confidence',0)}% confidence)")

    # Support / Resistance
    sr = p.get("sr") or {}
    if sr.get("support") and sr.get("resistance"):
        bits.append(f"support ₹{sr['support']:.2f} / resistance ₹{sr['resistance']:.2f}")

    return " · ".join(bits)


def _fmt_mcap(v):
    if not v:
        return "—"
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v >= 1e12: return f"₹{v / 1e12:.2f} Lakh Cr"
    if v >= 1e10: return f"₹{v / 1e10:.2f} K Cr"
    if v >= 1e7:  return f"₹{v / 1e7:.2f} Cr"
    return f"₹{v:,.0f}"


# ── Main entry ──────────────────────────────────────────────────────────────

def _add_macro_section(story: list, macro: dict, ss) -> None:
    """Global market + geopolitical risk strip on the cover page."""
    snap = macro.get("snapshot", {})
    geo  = macro.get("geo", {}) or {}
    regime = macro.get("regime", "neutral").upper()

    story.append(Paragraph("🌐 Global &amp; Geopolitical Snapshot", ss["H2x"]))

    # Markets table
    rows = [["Market", "Last", "Change %"]]
    label = {"SPY":"S&amp;P 500", "QQQ":"Nasdaq 100", "DJI":"Dow Jones",
             "VIX":"VIX (Fear)", "OIL":"WTI Crude", "DXY":"US Dollar Index",
             "GOLD":"Gold", "NIFTY":"Nifty 50"}
    for k in ("SPY", "QQQ", "DJI", "VIX", "OIL", "DXY", "GOLD", "NIFTY"):
        v = snap.get(k)
        if not v:
            continue
        rows.append([label.get(k, k), _fmt_num(v["last"]),
                     f"{v['chg_pct']:+.2f}%"])
    if len(rows) > 1:
        tbl = Table(rows, colWidths=[60 * mm, 35 * mm, 35 * mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#444")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("GRID",       (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#F5F7FA"), colors.white]),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 4))

    # Regime + geopolitical line
    geo_lvl = geo.get("level", 50)
    geo_color = ("#C83240" if geo_lvl >= 65 else
                  "#148C5A" if geo_lvl <= 35 else "#888")
    story.append(Paragraph(
        f"<b>Regime:</b> {regime} &nbsp;|&nbsp; "
        f"<b>Geopolitical risk:</b> "
        f"<font color='{geo_color}'>{geo_lvl:.0f}/100</font> "
        f"({geo.get('risk_off_hits', 0)} risk-off vs "
        f"{geo.get('risk_on_hits', 0)} risk-on headlines)",
        ss["body"]))

    # Top 2 geo headline samples
    samples = geo.get("off_samples", [])[:2]
    for s in samples:
        story.append(Paragraph(f"• {s}", ss["cell"]))

    # Macro reasons that influenced today's predictions
    if macro.get("reasons"):
        story.append(Spacer(1, 3))
        for r in macro["reasons"][:4]:
            story.append(Paragraph(f"→ {r}", ss["cell"]))

    # ── Nifty opening prediction (09:15 IST) ────────────────────────────
    opening = macro.get("opening") or {}
    if opening.get("direction"):
        arrow = {"UP": "↑", "DOWN": "↓", "FLAT": "→"}.get(opening["direction"], "→")
        op_colour = ("#148C5A" if opening["direction"] == "UP"
                     else "#C83240" if opening["direction"] == "DOWN" else "#888")
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"<b>🔮 Nifty Opening Prediction (09:15 IST):</b> "
            f"<font color='{op_colour}'><b>{arrow} {opening['direction']}</b></font> "
            f"({opening.get('gap_pct', '—')}, "
            f"{opening.get('confidence', 0)}% confidence)",
            ss["body"]))
        for note in (opening.get("notes") or [])[:3]:
            story.append(Paragraph(f"• {note}", ss["cell"]))
    story.append(Spacer(1, 8))


def _add_prediction_section(story: list, buckets: dict, ss) -> None:
    """Top-of-document 'Today's Prediction' summary using predict_direction output."""
    preds: list[tuple[str, dict]] = []
    for key, tag in [("intraday", "Same-Day"), ("swing", "Short-Term")]:
        for p in buckets.get(key, [])[:3]:
            if p.get("predict"):
                preds.append((tag, p))
    if not preds:
        return

    story.append(Paragraph("🔮 Today's Prediction &amp; Action Plan", ss["H2x"]))
    story.append(Paragraph(
        "Direction forecast for the next 1–5 sessions based on price trend, "
        "candlestick patterns and support/resistance levels.", ss["muted"]))

    header = ["Tag", "Stock", "Direction", "Confidence",
              "Buy At ₹", "Stop-Loss ₹", "Target ₹", "Support ₹", "Resistance ₹"]
    data = [header]
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6A1B9A")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("FONTSIZE",   (0, 1), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F5F0F8"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    arrow = {"UP": "↑ UP", "DOWN": "↓ DOWN", "SIDEWAYS": "→ FLAT"}
    colour = {"UP":  colors.HexColor("#148C5A"),
              "DOWN": colors.HexColor("#C83240"),
              "SIDEWAYS": colors.HexColor("#888")}
    for i, (tag, p) in enumerate(preds, start=1):
        pr = p["predict"]; lv = p["levels"]
        sym = p["symbol"].replace(".NS", "")
        data.append([
            tag, sym, arrow.get(pr["direction"], "?"),
            f"{pr['confidence']}%",
            _fmt_num(lv["entry"]),
            _fmt_num(lv["sl"]),
            _fmt_num(lv["target"]),
            _fmt_num(lv.get("support") or 0) if lv.get("support") else "—",
            _fmt_num(lv.get("resistance") or 0) if lv.get("resistance") else "—",
        ])
        style.append(("TEXTCOLOR", (2, i), (2, i), colour.get(pr["direction"], colors.black)))
        style.append(("TEXTCOLOR", (5, i), (5, i), colors.HexColor("#C83240")))
        style.append(("TEXTCOLOR", (6, i), (6, i), colors.HexColor("#148C5A")))

    col_w = [20, 22, 22, 18, 20, 20, 20, 20, 20]  # = 182 mm
    tbl = Table(data, colWidths=[w * mm for w in col_w], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    story.append(tbl)

    # Reasons under each prediction
    story.append(Spacer(1, 3))
    for tag, p in preds:
        sym = p["symbol"].replace(".NS", "")
        pr = p["predict"]
        reasons = " · ".join(pr.get("reasons", [])[:4])
        story.append(Paragraph(
            f"<b>{sym}</b> ({tag}): {reasons}", ss["cell"]))
    story.append(Spacer(1, 10))


def build_pdf_report(
    buckets: dict,
    mfs: list[dict],
    prior: dict,
    all_enriched: list[dict] | None = None,
    watchlist_symbols: list[str] | None = None,
    macro: dict | None = None,
    advice: str | None = None,
    out_path: str | None = None,
) -> str:
    out_path = out_path or PDF_OUTPUT_PATH
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm,  bottomMargin=14 * mm,
        title="Indian Market Intelligence Report",
    )
    ss = _styles()
    story: list = []

    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(Paragraph("📊 Indian Market — Intelligence Report", ss["H1x"]))
    story.append(Paragraph(
        datetime.now().strftime("%A, %d %b %Y  ·  %H:%M IST"), ss["muted"]))
    story.append(Paragraph(
        "Automated analysis combining price trends, company finances, and "
        "news sentiment across NIFTY 100 stocks plus your personal watchlist. "
        "Buy / Exit / Target prices are calculated using recent price swings.", ss["body"]))
    story.append(Spacer(1, 6))

    # ── Expert Advisor narrative ───────────────────────────────────────────
    if advice:
        story.append(Paragraph("🧠 Expert Advisor — Today's View", ss["H2x"]))
        story.append(Paragraph(
            advice.replace("*", "<b>", 1).replace("*", "</b>", 1)
                  .replace("\n", "<br/>"),
            ss["body"]))
        story.append(Spacer(1, 6))

    # ── Macro / Global snapshot ────────────────────────────────────────────
    if macro and macro.get("snapshot"):
        _add_macro_section(story, macro, ss)

    # ── Today's Prediction highlights ──────────────────────────────────────
    _add_prediction_section(story, buckets, ss)

    # ── Bucket tables ──────────────────────────────────────────────────────
    for title, key, action in [
        ("🔥 Same-Day Trades (buy & sell today)",          "intraday", "Buy at the given price, sell at profit target or exit price"),
        ("📈 Short-Term Trades (2–15 days)",               "swing",    "Buy on a dip, move exit price up as the stock rises"),
        ("🏦 Long-Term Investments (1 year or more)",      "holding",  "Add to your portfolio on dips; review every 3 months"),
        ("⚠️ AVOID / SELL (exit or don't buy)",             "sell",     "Sell existing holdings; avoid fresh buying"),
    ]:
        picks = buckets.get(key, [])
        if not picks:
            continue
        story.append(Paragraph(title, ss["H2x"]))
        story.append(Paragraph(f"<b>Recommended action:</b> {action}", ss["muted"]))
        story.append(_stock_bucket_table(title, picks, action))
        story.append(Spacer(1, 4))
        for p in picks:
            story.append(_per_stock_detail_row(p, ss))
        story.append(Spacer(1, 6))

    # ── Mutual funds ───────────────────────────────────────────────────────
    if mfs:
        story.append(PageBreak())
        story.append(Paragraph("💰 Top Mutual Funds (ranked by past returns)", ss["H2x"]))
        story.append(_mf_table(mfs))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<b>Overall score</b> = 50% of 1-year return + 30% of 3-month return + 20% of 1-month return. "
            "Choose <i>Direct — Growth</i> plans for long-term SIPs; avoid dividend-payout plans.",
            ss["muted"]))

    # ── Watchlist extract ─────────────────────────────────────────────────
    if watchlist_symbols and all_enriched:
        wl_set = set(watchlist_symbols)
        wl_rows = [e for e in all_enriched if e["symbol"] in wl_set]
        if wl_rows:
            story.append(PageBreak())
            story.append(Paragraph(
                f"⭐ Your Watchlist ({len(wl_rows)} stocks)", ss["H2x"]))
            story.append(Paragraph(
                "Every stock in your <code>data/stock_watchlist.txt</code> file, "
                "scored independently of the bucket filters.",
                ss["muted"]))
            # Attach a bucket-score column for each horizon
            for e in wl_rows:
                e.setdefault("bucket_score", e["composite"])
                e.setdefault("levels", {
                    "entry":  round(e["price"], 2),
                    "sl":     round(e["price"] * 0.95, 2),
                    "target": round(e["price"] * 1.10, 2),
                })
            story.append(_stock_bucket_table("Watchlist", wl_rows, "Reference only"))
            story.append(Spacer(1, 6))
            for p in wl_rows:
                story.append(_per_stock_detail_row(p, ss))

    # ── Prior-run accuracy ─────────────────────────────────────────────────
    pt = _prior_table(prior)
    if pt is not None:
        story.append(PageBreak())
        story.append(Paragraph("🧾 How Our Past Picks Performed", ss["H2x"]))
        story.append(pt)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Each previous pick's buy price is compared against today's price. "
            "Buy recommendations count as correct when the price went up; "
            "sell recommendations count as correct when the price went down.",
            ss["muted"]))

    # ── Footer ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>Disclaimer:</b> {DISCLAIMER}", ss["muted"]))

    doc.build(story)
    logger.info(f"PDF report saved → {out_path}")
    return out_path
