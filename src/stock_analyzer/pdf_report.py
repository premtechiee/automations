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
    Image as RLImage,
)

from .config import PDF_OUTPUT_PATH, DISCLAIMER
from . import charts

logger = logging.getLogger(__name__)


# ── Styles ─────────────────────────────────────────────────────────────────

def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(
        "H1x", parent=ss["Heading1"], fontSize=26,
        textColor=colors.HexColor("#0B2C66"),
        spaceAfter=4, leading=30, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle(
        "H2x", parent=ss["Heading2"], fontSize=16,
        textColor=colors.HexColor("#1E40AF"),
        spaceBefore=14, spaceAfter=6, leading=20, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle(
        "H3x", parent=ss["Heading3"], fontSize=13,
        textColor=colors.HexColor("#1E40AF"),
        spaceBefore=8, spaceAfter=3, leading=16, fontName="Helvetica-Bold"))
    ss.add(ParagraphStyle(
        "muted", parent=ss["BodyText"], fontSize=10,
        textColor=colors.HexColor("#5B6473"), spaceAfter=4, leading=13))
    ss.add(ParagraphStyle(
        "body", parent=ss["BodyText"], fontSize=11, leading=15, spaceAfter=5))
    ss.add(ParagraphStyle(
        "callout", parent=ss["BodyText"], fontSize=11, leading=15,
        textColor=colors.HexColor("#0B2C66"),
        backColor=colors.HexColor("#EAF1FB"),
        borderColor=colors.HexColor("#1E40AF"), borderWidth=1, borderRadius=6,
        borderPadding=10, spaceAfter=8))
    ss.add(ParagraphStyle(
        "cell", parent=ss["BodyText"], fontSize=9.5, leading=11.5))
    ss.add(ParagraphStyle(
        "cellb", parent=ss["BodyText"], fontSize=9.5, leading=11.5,
        textColor=colors.HexColor("#0F1B33"), fontName="Helvetica-Bold"))
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
    """Compact 2-line per-stock summary: headline + plan + rationale."""
    t   = p["tech"]; f = p["fund"]; lv = p["levels"]
    sym = p["symbol"].replace(".NS", "")
    rationale = _build_rationale(p)
    hold = lv.get("est_hold_days") or 0
    hold_tag = ("today" if hold == 0
                else "1y+" if hold >= 252
                else f"{hold}d")
    body = (
        f"<b>{sym}</b> · {f.get('sector','—')} · ₹{p['price']:,.2f} "
        f"(<font color='{'#148C5A' if t['chg_1d_pct'] >= 0 else '#C83240'}'>"
        f"{_fmt_pct(t['chg_1d_pct'])}</font>)"
        f" · RSI {t['rsi14']:.0f} · Score <b>{p['bucket_score']:.0f}/100</b><br/>"
        f"<b>Plan:</b> Buy ₹{lv['entry']:,.2f} · "
        f"<font color='#C83240'>SL ₹{lv['sl']:,.2f}</font> · "
        f"<font color='#148C5A'>Target ₹{lv['target']:,.2f}</font> · "
        f"<b>{lv.get('expected_profit_pct', 0):+.2f}%</b> · Hold {hold_tag} · "
        f"R:R 1:{lv.get('rr', 0):.1f}<br/>"
        f"<i>{rationale}</i>"
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


# ── Chart/metrics helpers ──────────────────────────────────────────────────

def _chart_flow(pil_img, content_w_mm: float = 182.0) -> RLImage:
    """Wrap a PIL image as a ReportLab flowable scaled to page content width."""
    import io as _io
    buf = _io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    # Scale to content width (182mm), preserving aspect ratio
    src_w, src_h = pil_img.size
    target_w = content_w_mm * mm
    target_h = target_w * (src_h / src_w)
    return RLImage(buf, width=target_w, height=target_h)


def _compute_breadth(enriched: list[dict]) -> dict:
    adv = dec = flat = 0
    big_up = big_dn = 0
    trending_up = 0
    rsi_vals: list[float] = []
    top_gainer = top_loser = None
    profit_samples: list[float] = []
    for e in enriched or []:
        t = e.get("tech") or {}
        v = t.get("chg_1d_pct")
        if v is None:
            continue
        if v > 0.2:   adv += 1
        elif v < -0.2: dec += 1
        else:          flat += 1
        if v >= 2.0:  big_up += 1
        if v <= -2.0: big_dn += 1
        if t.get("trend_up"):
            trending_up += 1
        rsi_vals.append(float(t.get("rsi14") or 50))
        if top_gainer is None or v > top_gainer[1]:
            top_gainer = (e["symbol"].replace(".NS", ""), v)
        if top_loser is None or v < top_loser[1]:
            top_loser = (e["symbol"].replace(".NS", ""), v)

    total = adv + dec + flat
    rsi_med = sorted(rsi_vals)[len(rsi_vals) // 2] if rsi_vals else 50

    return {
        "total":       total,
        "adv":         adv,
        "dec":         dec,
        "flat":        flat,
        "adv_pct":     (adv / total * 100) if total else 0,
        "dec_pct":     (dec / total * 100) if total else 0,
        "big_up":      big_up,
        "big_dn":      big_dn,
        "trending_up": trending_up,
        "trend_pct":   (trending_up / total * 100) if total else 0,
        "rsi_median":  rsi_med,
        "top_gainer":  top_gainer,
        "top_loser":   top_loser,
    }


def _add_breadth_metrics_section(story: list, enriched: list[dict],
                                  buckets: dict, ss) -> None:
    b = _compute_breadth(enriched)
    if not b["total"]:
        return

    # Bucket-level expected-profit summary
    bucket_stats = []
    for key, label in [("intraday", "Same-Day"),
                       ("swing",    "Short-Term"),
                       ("holding",  "Long-Term")]:
        picks = buckets.get(key) or []
        if not picks:
            continue
        profits = [float((p.get("levels") or {}).get("expected_profit_pct") or 0)
                   for p in picks]
        avg = sum(profits) / len(profits) if profits else 0
        best = max(profits) if profits else 0
        bucket_stats.append((label, len(picks), avg, best))

    story.append(Paragraph("📊 Market Breadth &amp; Key Metrics", ss["H2x"]))

    tg = b["top_gainer"] or ("—", 0)
    tl = b["top_loser"]  or ("—", 0)
    rows = [
        ["Metric", "Value"],
        ["Stocks analysed",            f"{b['total']}"],
        ["Advancers",                  f"{b['adv']} ({b['adv_pct']:.0f}%)"],
        ["Decliners",                  f"{b['dec']} ({b['dec_pct']:.0f}%)"],
        ["Unchanged",                  f"{b['flat']}"],
        ["Strong gainers (≥ +2%)",     f"{b['big_up']}"],
        ["Strong losers (≤ -2%)",      f"{b['big_dn']}"],
        ["Trending up (>50/200 EMA)",  f"{b['trending_up']} ({b['trend_pct']:.0f}%)"],
        ["Median RSI(14)",             f"{b['rsi_median']:.0f}"],
        ["Top gainer today",           f"{tg[0]}  ({tg[1]:+.2f}%)"],
        ["Top loser today",            f"{tl[0]}  ({tl[1]:+.2f}%)"],
    ]
    for label, n, avg, best in bucket_stats:
        rows.append([f"{label} picks — avg expected profit",
                     f"{n} picks · avg {avg:+.2f}%  ·  best {best:+.2f}%"])

    tbl = Table(rows, colWidths=[85 * mm, 97 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E6BD8")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F5F7FA"), colors.white]),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8))


def _add_charts_section(story: list, buckets: dict, macro: dict | None,
                         enriched: list[dict], ss) -> None:
    """Embed analytics charts generated by charts.py."""
    try:
        # Expected profit bars (full width)
        top_picks = []
        for key in ("intraday", "swing", "holding"):
            top_picks.extend((buckets.get(key) or [])[:4])
        if top_picks:
            story.append(Paragraph("🎯 Expected Profit — Top Picks", ss["H2x"]))
            story.append(_chart_flow(
                charts.chart_expected_profit(
                    top_picks, "Expected profit % (colour = predicted direction)",
                    width=1150, height=340, theme="light",
                )
            ))
            story.append(Spacer(1, 4))

        # Macro bars
        if (macro or {}).get("snapshot"):
            story.append(Paragraph("🌐 Global Markets Overnight", ss["H2x"]))
            story.append(_chart_flow(
                charts.chart_macro(macro, width=1150, height=180, theme="light")
            ))
            story.append(Spacer(1, 4))

        # Risk/Reward + sector heatmap (side by side via table)
        rr = charts.chart_risk_reward(buckets, width=560, height=340, theme="light")
        sh = charts.chart_sector_heatmap(enriched, width=560, height=340, theme="light")
        story.append(Paragraph("🧭 Risk/Reward &amp; Sector Performance", ss["H2x"]))
        side = Table([[_chart_flow(rr, 90), _chart_flow(sh, 90)]],
                      colWidths=[92 * mm, 92 * mm])
        side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(side)
        story.append(Spacer(1, 4))

        # Breadth + confidence histogram side by side
        br = charts.chart_breadth(enriched, width=560, height=210, theme="light")
        cf = charts.chart_confidence_hist(buckets, width=560, height=210, theme="light")
        story.append(Paragraph("📈 Breadth &amp; Prediction Confidence", ss["H2x"]))
        side2 = Table([[_chart_flow(br, 90), _chart_flow(cf, 90)]],
                       colWidths=[92 * mm, 92 * mm])
        side2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(side2)
        story.append(Spacer(1, 6))
    except Exception as exc:
        logger.warning(f"PDF charts section failed: {exc}")


def _add_executive_summary(story: list, buckets: dict, macro: dict | None,
                            enriched: list[dict], prior: dict, ss,
                            market_forecast: dict | None = None) -> None:
    """TL;DR page 1 — one table covering the top picks, the market context,
    and past accuracy so a reader can act in < 30 seconds."""
    # Market context one-liner
    regime  = ((macro or {}).get("regime") or "neutral").upper()
    opening = (macro or {}).get("opening") or {}
    snap    = (macro or {}).get("snapshot") or {}
    nifty_d = (snap.get("NIFTY") or {}).get("chg_pct")
    spy_d   = (snap.get("SPY")   or {}).get("chg_pct")

    ctx_bits = [f"Global <b>{regime}</b>"]
    if opening.get("direction"):
        ctx_bits.append(
            f"Open {opening['direction']} ({opening.get('gap_pct','—')}, "
            f"{opening.get('confidence', 0)}% conf.)"
        )
    if nifty_d is not None:
        ctx_bits.append(f"Nifty {nifty_d:+.2f}%")
    if spy_d is not None:
        ctx_bits.append(f"S&amp;P {spy_d:+.2f}%")

    # Breadth
    adv = dec = flat = 0
    for e in enriched or []:
        v = (e.get("tech") or {}).get("chg_1d_pct")
        if v is None: continue
        if v > 0.2:   adv += 1
        elif v < -0.2: dec += 1
        else:          flat += 1
    total = adv + dec + flat
    if total:
        ctx_bits.append(
            f"Breadth <b>{adv}/{total}</b> up ({adv / total * 100:.0f}%)"
        )

    story.append(Paragraph("⚡ Executive Summary", ss["H1x"]))
    story.append(Paragraph(" &nbsp;·&nbsp; ".join(ctx_bits), ss["body"]))
    story.append(Spacer(1, 4))

    # Market-wide 5-session forecast (big callout)
    if market_forecast:
        mf = market_forecast
        arrow = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→"}.get(mf["direction"], "→")
        lo, hi = mf["band_pct"]
        colour = {"UP": "#148C5A", "DOWN": "#C83240"}.get(mf["direction"], "#555")
        story.append(Paragraph(
            f"<b><font color='{colour}'>🔮 Next-5-session Market Forecast: "
            f"{arrow} {mf['direction']}</font></b>  &nbsp;·&nbsp;  "
            f"<b>{mf['confidence']}% confidence</b>  &nbsp;·&nbsp;  "
            f"expected band <b>{lo:+.1f}% … {hi:+.1f}%</b>",
            ss["body"]))
        reasons = mf.get("reasons") or []
        if reasons:
            story.append(Paragraph(
                "Drivers: " + " · ".join(reasons[:4]), ss["muted"]))
        story.append(Spacer(1, 4))

    # TL;DR table: top 3 of each bucket in a single condensed grid
    header = ["Type", "Stock", "Price ₹", "Buy ₹", "SL ₹", "Target ₹",
              "Profit %", "Hold", "Conf."]
    data   = [header]
    style  = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E6BD8")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F5F7FA"), colors.white]),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]

    bucket_tag = [
        ("intraday", "Same-Day",    colors.HexColor("#1E6BD8")),
        ("swing",    "Short-Term",  colors.HexColor("#148C5A")),
        ("holding",  "Long-Term",   colors.HexColor("#6A1B9A")),
        ("sell",     "Avoid/Sell",  colors.HexColor("#C83240")),
    ]
    row_i = 1
    for key, label, tag_colour in bucket_tag:
        picks = (buckets.get(key) or [])[:3]
        for p in picks:
            lv = p["levels"]
            pr = p.get("predict") or {}
            pp = float(lv.get("expected_profit_pct") or 0)
            hd = lv.get("est_hold_days") or 0
            hold_tag = ("today" if hd == 0
                        else "1y+" if hd >= 252
                        else f"{hd}d")
            conf_txt = f"{pr.get('confidence','')}%" if pr else "—"
            data.append([
                label,
                p["symbol"].replace(".NS", ""),
                _fmt_num(p["price"]),
                _fmt_num(lv["entry"]),
                _fmt_num(lv["sl"]),
                _fmt_num(lv["target"]),
                f"{pp:+.2f}%",
                hold_tag,
                conf_txt,
            ])
            style.append(("TEXTCOLOR", (0, row_i), (0, row_i), tag_colour))
            style.append(("TEXTCOLOR", (4, row_i), (4, row_i), colors.HexColor("#C83240")))
            style.append(("TEXTCOLOR", (5, row_i), (5, row_i), colors.HexColor("#148C5A")))
            style.append(("TEXTCOLOR", (6, row_i), (6, row_i),
                          colors.HexColor("#148C5A") if pp >= 0 else colors.HexColor("#C83240")))
            row_i += 1

    if row_i == 1:  # no picks at all
        return

    col_w = [22, 24, 20, 22, 20, 22, 22, 16, 14]  # = 182 mm
    tbl = Table(data, colWidths=[w * mm for w in col_w], repeatRows=1)
    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    story.append(Spacer(1, 4))

    # Past hit-rate one-liner
    if prior.get("available"):
        parts = []
        for b in ("intraday", "swing", "holding", "sell"):
            info = prior["buckets"].get(b, {})
            hr = info.get("hit_rate")
            if hr is None:
                continue
            parts.append(f"{b.capitalize()} <b>{hr:.0f}%</b> ({info['wins']}/{info['count']})")
        if parts:
            story.append(Paragraph(
                "🧾 <b>Past picks hit-rate:</b>  " + "  ·  ".join(parts),
                ss["muted"]))
    story.append(Spacer(1, 8))


def _add_self_review_section(story: list, review: dict, ss) -> None:
    """Render the model's self-assessment: overall accuracy + best/worst
    signals + calibration quality. Shown to the user so they can see that
    the automation is actively learning from its past picks."""
    acc = review.get("overall_accuracy")
    ps  = review.get("picks_scored", 0)
    pw  = review.get("picks_won", 0)
    nf  = review.get("n_features", 0)
    acc_txt = f"{acc:.1f}%" if acc is not None else "calibrating…"

    story.append(Paragraph("🧠 Model Self-Review", ss["H2x"]))
    story.append(Paragraph(
        f"Overall accuracy <b>{acc_txt}</b>  ·  "
        f"<b>{pw}/{ps}</b> past picks correct  ·  "
        f"<b>{nf}</b> signals tracked",
        ss["body"]))
    story.append(Spacer(1, 3))

    best  = review.get("best_features") or []
    worst = review.get("worst_features") or []

    def _ft_table(rows: list[dict], title_colour: str) -> Table:
        data = [["Signal", "Hit-rate", "Samples", "Weight"]]
        for r in rows:
            data.append([
                r.get("name", "—"),
                f"{r.get('hit_rate', 0):.0f}%",
                str(r.get("total", 0)),
                f"{r.get('weight', 1.0):.2f}×",
            ])
        t = Table(data, colWidths=[70 * mm, 22 * mm, 22 * mm, 22 * mm],
                  repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(title_colour)),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("GRID",       (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#F5F7FA"), colors.white]),
            ("ALIGN",      (1, 0), (-1, -1), "RIGHT"),
        ]))
        return t

    if best:
        story.append(Paragraph("<b>Most reliable signals</b> (boosted)", ss["muted"]))
        story.append(_ft_table(best, "#148C5A"))
        story.append(Spacer(1, 4))
    if worst:
        story.append(Paragraph("<b>Least reliable signals</b> (suppressed)", ss["muted"]))
        story.append(_ft_table(worst, "#C83240"))
        story.append(Spacer(1, 4))

    cal = review.get("calibration") or []
    cal = [r for r in cal if isinstance(r, dict)]
    if cal:
        data = [["Confidence band", "Hit-rate", "Samples"]]
        for r in cal:
            data.append([
                r.get("band", "—"),
                f"{r.get('hit_rate', 0):.0f}%",
                str(r.get("total", 0)),
            ])
        t = Table(data, colWidths=[70 * mm, 34 * mm, 34 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6A1B9A")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("GRID",       (0, 0), (-1, -1), 0.25, colors.HexColor("#DDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#F5F7FA"), colors.white]),
            ("ALIGN",      (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(Paragraph("<b>Confidence calibration</b> (higher conf. should win more)", ss["muted"]))
        story.append(t)
        story.append(Spacer(1, 4))


def build_pdf_report(
    buckets: dict,
    mfs: list[dict],
    prior: dict,
    all_enriched: list[dict] | None = None,
    watchlist_symbols: list[str] | None = None,
    macro: dict | None = None,
    advice: str | None = None,
    out_path: str | None = None,
    market_forecast: dict | None = None,
    review: dict | None = None,
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

    # ── Hero banner ────────────────────────────────────────────────────────
    hero = Table(
        [[Paragraph(
            "<font color='#FFFFFF' size='20'><b>📊 Indian Market Intelligence</b></font>"
            "<br/><font color='#DCE6F8' size='11'>"
            "Daily Report · Stocks · Funds · Forecast</font>"
            f"<br/><font color='#B8C8E6' size='10'>{datetime.now().strftime('%A, %d %b %Y  ·  %H:%M IST')}</font>",
            ss["body"])]],
        colWidths=[doc.width],
    )
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E40AF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ]))
    story.append(hero)
    story.append(Spacer(1, 12))

    # ── Executive Summary (TL;DR page 1) ───────────────────────────────────
    _add_executive_summary(story, buckets, macro, all_enriched or [], prior, ss,
                            market_forecast=market_forecast)
    # Model self-review immediately follows TL;DR on same page if space allows
    if review:
        _add_self_review_section(story, review, ss)
    story.append(PageBreak())

    # ── Intro paragraph ────────────────────────────────────────────────────
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

    # ── Market Breadth metrics ─────────────────────────────────────────────
    _add_breadth_metrics_section(story, all_enriched or [], buckets, ss)

    # ── Advanced charts (expected profit, macro, risk/reward, sector,
    #     breadth, confidence) ─────────────────────────────────────────────
    _add_charts_section(story, buckets, macro, all_enriched or [], ss)

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
