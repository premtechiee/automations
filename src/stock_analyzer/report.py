"""
stock_analyzer/report.py
=========================
Build the PNG report and a plain-text summary.

Layout (dark theme):
  • Header with date + market snapshot
  • 4 stacked tables: Intraday | Swing | Long-term Hold | Sell/Avoid
  • Mutual-fund table
  • Prior-run hit-rate strip
  • Footer disclaimer
"""

from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .config import IMAGE_OUTPUT_PATH, IMAGE_THEME, DISCLAIMER

logger = logging.getLogger(__name__)


# ── Theme palette ───────────────────────────────────────────────────────────

def _palette(theme: str) -> dict:
    if theme == "light":
        return {
            "bg":       (245, 247, 250),
            "panel":    (255, 255, 255),
            "panel2":   (240, 243, 247),
            "text":     (20, 25, 35),
            "muted":    (100, 110, 125),
            "accent":   (20, 110, 210),
            "green":    (20, 150, 90),
            "red":      (210, 60, 70),
            "border":   (220, 225, 232),
        }
    return {
        "bg":       (14, 18, 28),
        "panel":    (22, 28, 42),
        "panel2":   (28, 35, 52),
        "text":     (235, 238, 245),
        "muted":    (140, 150, 170),
        "accent":   (90, 170, 255),
        "green":    (70, 210, 140),
        "red":      (255, 95, 110),
        "border":   (40, 50, 70),
    }


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for name in (
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.1f}%"


def _fmt_num(v, places: int = 2):
    if v is None:
        return "—"
    return f"{v:,.{places}f}"


# ── Drawing helpers ─────────────────────────────────────────────────────────

def _panel(draw, x0, y0, x1, y1, c_fill, c_border, radius=12):
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=c_fill, outline=c_border, width=1)


def _cell(draw, text, x, y, fnt, fill, anchor="la"):
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def _pct_color(pal, v):
    if v is None:
        return pal["muted"]
    return pal["green"] if v >= 0 else pal["red"]


# ── Table ───────────────────────────────────────────────────────────────────

def _draw_table(draw, pal, x0, y0, w, title: str, headers: list[str], rows: list[list[Any]],
                col_weights: list[float], header_color=None):
    f_title = _font(20, True)
    f_head  = _font(14, True)
    f_cell  = _font(14)

    row_h     = 28
    title_h   = 34
    header_h  = 26
    total_h   = title_h + header_h + row_h * max(1, len(rows)) + 10

    _panel(draw, x0, y0, x0 + w, y0 + total_h, pal["panel"], pal["border"])

    # title
    title_fill = header_color or pal["accent"]
    _cell(draw, title, x0 + 14, y0 + 8, f_title, title_fill)

    # column positions
    total_weight = sum(col_weights)
    col_xs = []
    cx = x0 + 14
    inner_w = w - 28
    for wt in col_weights:
        col_xs.append(cx)
        cx += int(inner_w * wt / total_weight)

    # header row
    hy = y0 + title_h + 4
    for i, h in enumerate(headers):
        _cell(draw, h, col_xs[i], hy, f_head, pal["muted"])
    draw.line([(x0 + 12, hy + header_h - 4), (x0 + w - 12, hy + header_h - 4)], fill=pal["border"], width=1)

    # data rows
    ry = hy + header_h
    for r_idx, row in enumerate(rows):
        if r_idx % 2 == 0:
            draw.rectangle([(x0 + 6, ry - 2), (x0 + w - 6, ry + row_h - 4)], fill=pal["panel2"])
        for i, val in enumerate(row):
            color = pal["text"]
            txt = str(val)
            if isinstance(val, tuple):   # (text, color_key) for coloured cells
                txt, key = val
                color = {"green": pal["green"], "red": pal["red"], "muted": pal["muted"]}.get(key, pal["text"])
            _cell(draw, txt, col_xs[i], ry + 4, f_cell, color)
        ry += row_h

    return total_h + 14


# ── Top-level renderer ──────────────────────────────────────────────────────

def _draw_prediction_panel(draw, pal, x0, y0, w, buckets: dict, macro: dict | None) -> int:
    """Draw Nifty opening-prediction banner + Today's Top Predictions table.
    Returns the new y-offset after the panel."""
    opening = (macro or {}).get("opening") or {}

    # Gather top predictions (same-day + short-term)
    preds: list[tuple[str, dict]] = []
    for key, tag in [("intraday", "SAME-DAY"), ("swing", "SHORT-TERM")]:
        for p in buckets.get(key, [])[:3]:
            if p.get("predict"):
                preds.append((tag, p))

    if not opening.get("direction") and not preds:
        return y0  # nothing to draw

    f_title = _font(20, True)
    f_body  = _font(15, True)
    f_cell  = _font(14)
    f_small = _font(12)

    dir_colour = {
        "UP":       pal["green"],
        "DOWN":     pal["red"],
        "SIDEWAYS": pal["muted"],
        "FLAT":     pal["muted"],
    }
    arrow = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→", "FLAT": "→"}

    # Compute height
    banner_h = 64 if opening.get("direction") else 0
    row_h    = 28
    table_h  = (40 + row_h * len(preds) + 16) if preds else 0
    total_h  = 10 + banner_h + (8 if banner_h and table_h else 0) + table_h + 10

    _panel(draw, x0, y0, x0 + w, y0 + total_h, pal["panel"], pal["border"])

    cy = y0 + 10

    # ── Opening banner ───────────────────────────────────────────────────
    if opening.get("direction"):
        d = opening["direction"]
        op_c = dir_colour.get(d, pal["text"])
        _cell(draw, "🔮 Nifty Opening Prediction (09:15 IST)",
              x0 + 14, cy + 4, f_title, pal["accent"])
        _cell(draw,
              f"{arrow.get(d, '→')}  {d}   ({opening.get('gap_pct','—')}, "
              f"{opening.get('confidence', 0)}% confidence)",
              x0 + 14, cy + 32, f_body, op_c)
        note = (opening.get("notes") or [""])[0]
        if note:
            _cell(draw, note[:120], x0 + 14, cy + 52, f_small, pal["muted"])
        cy += banner_h + 8

    # ── Predictions table ────────────────────────────────────────────────
    if preds:
        _cell(draw, "🔮 Today's Top Predictions", x0 + 14, cy + 2, f_title, pal["accent"])
        cy += 34

        headers = ["Stock", "Horizon", "Direction", "Confidence",
                   "Buy At", "Stop-Loss", "Target", "Expected Profit"]
        col_w   = [1.4, 1.6, 1.4, 1.3, 1.3, 1.3, 1.3, 1.8]
        total_wt = sum(col_w)
        inner_w = w - 28
        cx = x0 + 14
        col_xs = []
        for wt in col_w:
            col_xs.append(cx)
            cx += int(inner_w * wt / total_wt)

        # header
        for i, h in enumerate(headers):
            _cell(draw, h, col_xs[i], cy, _font(13, True), pal["muted"])
        draw.line([(x0 + 12, cy + 22), (x0 + w - 12, cy + 22)],
                  fill=pal["border"], width=1)
        cy += 26

        for r_idx, (tag, p) in enumerate(preds):
            if r_idx % 2 == 0:
                draw.rectangle([(x0 + 6, cy - 2), (x0 + w - 6, cy + row_h - 4)],
                               fill=pal["panel2"])
            pr  = p["predict"]
            lv  = p["levels"]
            sym = p["symbol"].replace(".NS", "")
            d   = pr["direction"]
            ep  = lv.get("expected_profit_pct", 0)
            row = [
                sym,
                tag,
                f"{arrow.get(d, '?')} {d}",
                f"{pr['confidence']}%",
                _fmt_num(lv["entry"]),
                _fmt_num(lv["sl"]),
                _fmt_num(lv["target"]),
                f"{ep:+.2f}%",
            ]
            for i, val in enumerate(row):
                colour = pal["text"]
                if i == 2:
                    colour = dir_colour.get(d, pal["text"])
                elif i == 5:
                    colour = pal["red"]
                elif i == 6 or i == 7:
                    colour = pal["green"] if ep >= 0 else pal["red"]
                _cell(draw, val, col_xs[i], cy + 4, f_cell, colour)
            cy += row_h

    return y0 + total_h + 14


def build_report_image(buckets: dict, mfs: list[dict], prior: dict, out_path: str | None = None,
                        theme: str | None = None, macro: dict | None = None) -> str:
    theme = (theme or IMAGE_THEME).lower()
    pal = _palette(theme)
    out_path = out_path or IMAGE_OUTPUT_PATH
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    W = 1200
    H = 2400  # generous; we crop at the end
    img = Image.new("RGB", (W, H), pal["bg"])
    draw = ImageDraw.Draw(img)

    # ── Header ──────────────────────────────────────────────────────────────
    _panel(draw, 24, 24, W - 24, 120, pal["panel"], pal["border"], radius=14)
    _cell(draw, "📊  Indian Market — Daily Intelligence Report",
          40, 40, _font(28, True), pal["accent"])
    ts = datetime.now().strftime("%A, %d %b %Y  ·  %H:%M IST")
    _cell(draw, ts, 40, 80, _font(15), pal["muted"])

    y = 140

    # ── Nifty opening prediction banner + Today's Top Predictions ──────────
    y = _draw_prediction_panel(draw, pal, 24, y, W - 48, buckets, macro)

    # ── Stock buckets ───────────────────────────────────────────────────────
    stock_headers = ["Stock", "Sector", "Price", "Today", "1 Month", "Momentum", "Score", "Buy At", "Exit If Drops", "Profit Target"]
    stock_weights = [2.5,      2.2,     1.4,   1.1,  1.1,  1.0,   1.1,    1.3,    1.3, 1.3]

    def _rows_for(picks: list[dict]) -> list[list[Any]]:
        out = []
        for p in picks:
            t  = p["tech"]; lv = p["levels"]
            sym = p["symbol"].replace(".NS", "")
            out.append([
                sym,
                (p["sector"][:16], "muted"),
                _fmt_num(p["price"]),
                (_fmt_pct(t["chg_1d_pct"]), "green" if t["chg_1d_pct"] >= 0 else "red"),
                (_fmt_pct(t["chg_1m_pct"]), "green" if t["chg_1m_pct"] >= 0 else "red"),
                f"{t['rsi14']:.0f}",
                f"{p['bucket_score']:.0f}",
                _fmt_num(lv["entry"]),
                (_fmt_num(lv["sl"]), "red"),
                (_fmt_num(lv["target"]), "green"),
            ])
        return out

    for title, key, colour in [
        ("🔥 Same-Day Trades (buy & sell today)",     "intraday", pal["accent"]),
        ("📈 Short-Term Trades (2–15 days)",          "swing",    pal["green"]),
        ("🏦 Long-Term Investments (1 year or more)", "holding",  pal["accent"]),
        ("⚠️ Avoid / Sell Now",                       "sell",     pal["red"]),
    ]:
        y += _draw_table(
            draw, pal, 24, y, W - 48,
            title=title,
            headers=stock_headers,
            rows=_rows_for(buckets.get(key, [])),
            col_weights=stock_weights,
            header_color=colour,
        )

    # ── Mutual funds ────────────────────────────────────────────────────────
    mf_headers = ["Fund Name", "Category", "Unit Price", "1 Month", "3 Months", "1 Year", "Overall Score"]
    mf_weights = [4.5,       2.0,         1.3,   1.2,  1.2,  1.2,  1.2]
    mf_rows: list[list[Any]] = []
    for m in mfs:
        mf_rows.append([
            m["name"][:48],
            (m["cat"][:20], "muted"),
            _fmt_num(m["nav"], 2),
            (_fmt_pct(m["r_1m"]), "green" if (m["r_1m"] or 0) >= 0 else "red"),
            (_fmt_pct(m["r_3m"]), "green" if (m["r_3m"] or 0) >= 0 else "red"),
            (_fmt_pct(m["r_1y"]), "green" if (m["r_1y"] or 0) >= 0 else "red"),
            f"{m['score']:+.2f}",
        ])
    y += _draw_table(
        draw, pal, 24, y, W - 48,
        title="💰 Top Mutual Funds (ranked by past returns)",
        headers=mf_headers,
        rows=mf_rows or [["—", "—", "—", "—", "—", "—", "—"]],
        col_weights=mf_weights,
    )

    # ── Prior-run hit rate ──────────────────────────────────────────────────
    if prior.get("available"):
        hdr = ["Category", "Picks", "Correct", "Success Rate"]
        hw  = [2.0, 1.0, 1.0, 1.2]
        rows = []
        for b in ("intraday", "swing", "holding", "sell"):
            info = prior["buckets"].get(b, {})
            hr = info.get("hit_rate")
            rows.append([
                b.capitalize(),
                str(info.get("count", 0)),
                str(info.get("wins", 0)),
                (f"{hr:.0f}%" if hr is not None else "—",
                 "green" if (hr or 0) >= 60 else ("red" if (hr or 0) < 40 and hr is not None else "muted")),
            ])
        y += _draw_table(
            draw, pal, 24, y, W - 48,
            title="🧾 How Our Past Picks Performed",
            headers=hdr, rows=rows, col_weights=hw,
        )

    # ── Footer ──────────────────────────────────────────────────────────────
    y += 10
    _cell(draw, DISCLAIMER, 40, y + 6, _font(13), pal["muted"])
    y += 40

    # Crop to actual content
    img = img.crop((0, 0, W, min(H, y + 20)))
    img.save(out_path)
    logger.info(f"Report image saved → {out_path}")
    return out_path


# ── Text summary (for WhatsApp/Telegram caption + console) ──────────────────

def build_text_summary(buckets: dict, mfs: list[dict], prior: dict,
                        macro: dict | None = None) -> str:
    lines: list[str] = []
    lines.append(f"📊 *Market Report* — {datetime.now().strftime('%d %b %Y %H:%M')}")
    lines.append("")

    # ── Macro / global context strip ───────────────────────────────────────
    if macro and macro.get("snapshot"):
        snap = macro["snapshot"]
        regime = macro.get("regime", "neutral").upper()
        bits: list[str] = [f"_Global mood: *{regime}*_"]
        for k, label in [("SPY", "S&P"), ("VIX", "VIX"), ("OIL", "Crude"),
                         ("DXY", "Dollar"), ("GOLD", "Gold")]:
            v = snap.get(k)
            if not v:
                continue
            if k == "VIX":
                bits.append(f"{label} {v['last']:.0f}")
            else:
                bits.append(f"{label} {v['chg_pct']:+.1f}%")
        geo = macro.get("geo", {})
        if geo.get("level", 50) >= 65:
            bits.append("⚠️ Geopolitical risk *HIGH*")
        elif geo.get("level", 50) <= 35:
            bits.append("Geopolitical mood positive")
        lines.append("  ·  ".join(bits))
        lines.append("")

    # ── Pre-open opening prediction (used most prominently at 08:00 IST) ──
    _session = (os.environ.get("STOCK_SESSION") or "").lower()
    opening = (macro or {}).get("opening") or {}
    if opening and _session in ("preopen", "", "morning"):
        arrow = {"GAP-UP": "🟢↑", "MILD GAP-UP": "🟢↗",
                 "GAP-DOWN": "🔴↓", "MILD GAP-DOWN": "🔴↘",
                 "FLAT OPEN": "⚪→"}.get(opening["direction"], "⚪")
        lines.append(
            f"*🔮 Nifty Opening Prediction (09:15 IST):* "
            f"{arrow} *{opening['direction']}* "
            f"({opening['gap_pct']}, {opening['confidence']}% confidence)"
        )
        if opening.get("notes"):
            lines.append(f"_Why:_ {opening['notes'][0]}")
        lines.append("")

        # Pre-open action plan for market open
        if _session == "preopen":
            lines.append("*🎯 Plan for 09:15 Market Open:*")
            lines.append("  1. Wait for 09:15–09:30 volatility to settle")
            lines.append("  2. Validate each pick against the Nifty opening prediction above")
            lines.append("  3. Enter swing positions only after price holds above entry for 10 min")
            lines.append("  4. Skip any name that *gaps above its target* at open")
            lines.append("")

    # ── Prediction block (top buy picks across intraday + swing) ──────────
    preds: list[dict] = []
    for key in ("intraday", "swing"):
        for p in buckets.get(key, [])[:3]:
            if p.get("predict"):
                preds.append({"key": key, "p": p})
    if preds:
        lines.append("*🔮 Today's Prediction & Action*")
        dir_emoji = {"UP": "🟢", "DOWN": "🔴", "SIDEWAYS": "⚪"}
        for item in preds[:5]:
            p  = item["p"]
            lv = p["levels"]
            pr = p["predict"]
            sym = p["symbol"].replace(".NS", "")
            tag = "SAME-DAY" if item["key"] == "intraday" else "SHORT-TERM"
            lines.append(
                f"  {dir_emoji.get(pr['direction'],'⚪')} *{sym}* ({tag}) — "
                f"{pr['direction']} ({pr['confidence']}% confidence)"
            )
            lines.append(
                f"      Buy ₹{lv['entry']:,.2f}  |  Stop-Loss ₹{lv['sl']:,.2f}  |  "
                f"Target ₹{lv['target']:,.2f}"
            )
            if lv.get("support") and lv.get("resistance"):
                lines.append(
                    f"      Support ₹{lv['support']:,.2f}  |  Resistance ₹{lv['resistance']:,.2f}"
                )
            if pr.get("reasons"):
                lines.append(f"      Why: {pr['reasons'][0]}")
        lines.append("")

    labels = [("🔥 Same-Day Trades", "intraday"),
              ("📈 Short-Term (2–15 days)",    "swing"),
              ("🏦 Long-Term Hold",  "holding"),
              ("⚠️ Avoid / Sell",    "sell")]
    # At 08:00 pre-open, swing is the headline (intraday can only act at 09:15)
    if _session == "preopen":
        labels = [("📈 *SWING PICKS FOR TODAY* (2–15 days)", "swing"),
                  ("🔥 Same-Day Setups (act after 09:15)",   "intraday"),
                  ("🏦 Long-Term Hold",                      "holding"),
                  ("⚠️ Avoid / Sell",                        "sell")]
    for title, key in labels:
        picks = buckets.get(key, [])
        if not picks:
            continue
        lines.append(f"*{title}*")
        for p in picks:
            lv = p["levels"]
            sym = p["symbol"].replace(".NS", "")
            lines.append(
                f"  • *{sym}*  Buy ₹{lv['entry']:,.2f}  SL ₹{lv['sl']:,.2f}  "
                f"Target ₹{lv['target']:,.2f}  ({p['bucket_score']:.0f}/100)"
            )
            lines.append(
                f"      Expected profit *{lv.get('expected_profit_pct', 0):+.2f}%* "
                f"(risk {lv.get('risk_pct', 0):.2f}%, R:R 1:{lv.get('rr', 0):.1f}) · "
                f"Hold: {lv.get('hold_hint', '')}"
            )
            lines.append(f"      When to buy: {lv.get('buy_window', '')}")
            if lv.get("forecast_5d"):
                lo, hi = lv["forecast_5d"]
                lines.append(f"      5-day range: ₹{lo:,.2f} – ₹{hi:,.2f}")
        lines.append("")

    if mfs:
        lines.append("*💰 Top Mutual Funds*")
        for m in mfs:
            lines.append(f"  • {m['name'][:40]}  1-Year Return {_fmt_pct(m['r_1y'])}")
        lines.append("")

    if prior.get("available"):
        lines.append("*🧾 Past Picks Performance*")
        for b, info in prior["buckets"].items():
            hr = info.get("hit_rate")
            if hr is None:
                continue
            lines.append(f"  • {b}: {info['wins']}/{info['count']} correct  ({hr:.0f}% success)")
        lines.append("")

    lines.append(DISCLAIMER)
    return "\n".join(lines)
