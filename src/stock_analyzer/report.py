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
            "bg":        (244, 247, 252),
            "panel":     (255, 255, 255),
            "panel2":    (240, 244, 250),
            "text":      (22, 27, 37),
            "muted":     (95, 108, 125),
            "accent":    (20, 110, 210),
            "accent2":   (105, 70, 220),
            "green":     (20, 150, 90),
            "green_bg":  (220, 245, 230),
            "red":       (210, 55, 70),
            "red_bg":    (252, 226, 228),
            "amber":     (210, 135, 25),
            "amber_bg":  (255, 240, 210),
            "border":    (216, 222, 232),
        }
    return {
        "bg":        (12, 16, 26),
        "panel":     (22, 28, 42),
        "panel2":    (29, 37, 55),
        "text":      (235, 238, 245),
        "muted":     (150, 160, 180),
        "accent":    (90, 170, 255),
        "accent2":   (170, 130, 255),
        "green":     (70, 215, 145),
        "green_bg":  (30, 70, 55),
        "red":       (255, 100, 115),
        "red_bg":    (80, 35, 45),
        "amber":     (255, 190, 85),
        "amber_bg":  (80, 60, 25),
        "border":    (44, 55, 78),
    }


# Mobile font scale — PNG renders at 1080px; chat clients downsample to
# ~360 logical px, so boost every font to keep text readable on phones.
_FONT_SCALE = 1.7


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    size = max(11, int(round(size * _FONT_SCALE)))
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

def _panel(draw, x0, y0, x1, y1, c_fill, c_border, radius=16):
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius,
                            fill=c_fill, outline=c_border, width=1)


def _cell(draw, text, x, y, fnt, fill, anchor="la"):
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def _pct_color(pal, v):
    if v is None:
        return pal["muted"]
    return pal["green"] if v >= 0 else pal["red"]


def _gradient_rect(img: Image.Image, x0: int, y0: int, x1: int, y1: int,
                    c_top: tuple, c_bot: tuple, radius: int = 20) -> None:
    """Vertical gradient rounded-rectangle drawn via a masked paste."""
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    grad = Image.new("RGB", (w, h), c_top)
    px = grad.load()
    for yy in range(h):
        t = yy / max(1, h - 1)
        r = int(c_top[0] + (c_bot[0] - c_top[0]) * t)
        g = int(c_top[1] + (c_bot[1] - c_top[1]) * t)
        b = int(c_top[2] + (c_bot[2] - c_top[2]) * t)
        for xx in range(w):
            px[xx, yy] = (r, g, b)
    if radius > 0:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
        img.paste(grad, (x0, y0), mask)
    else:
        img.paste(grad, (x0, y0))


def _pill(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
           fnt: ImageFont.ImageFont, fg: tuple, bg: tuple,
           pad_x: int = 18, pad_y: int = 10) -> int:
    """Rounded pill badge. Returns right-edge x."""
    tb = draw.textbbox((0, 0), text, font=fnt)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    x1 = x + tw + pad_x * 2
    y1 = y + th + pad_y * 2
    draw.rounded_rectangle([(x, y), (x1, y1)], radius=(y1 - y) // 2, fill=bg)
    draw.text((x + pad_x, y + pad_y - tb[1]), text, font=fnt, fill=fg)
    return x1


# ── Table ───────────────────────────────────────────────────────────────────

def _draw_table(draw, pal, x0, y0, w, title: str, headers: list[str], rows: list[list[Any]],
                col_weights: list[float], header_color=None, accent_bar: tuple | None = None):
    f_title = _font(20, True)
    f_head  = _font(13, True)
    f_cell  = _font(14)

    row_h     = 44
    title_h   = 56
    header_h  = 38
    total_h   = title_h + header_h + row_h * max(1, len(rows)) + 18

    _panel(draw, x0, y0, x0 + w, y0 + total_h, pal["panel"], pal["border"])

    # Left colour accent stripe
    if accent_bar is not None:
        draw.rounded_rectangle([(x0, y0 + 14), (x0 + 8, y0 + total_h - 14)],
                                radius=4, fill=accent_bar)

    # title
    title_fill = header_color or pal["accent"]
    _cell(draw, title, x0 + 22, y0 + 12, f_title, title_fill)

    # column positions
    total_weight = sum(col_weights)
    col_xs = []
    cx = x0 + 22
    inner_w = w - 44
    for wt in col_weights:
        col_xs.append(cx)
        cx += int(inner_w * wt / total_weight)

    # header row
    hy = y0 + title_h + 6
    for i, h in enumerate(headers):
        _cell(draw, h.upper(), col_xs[i], hy, f_head, pal["muted"])
    draw.line([(x0 + 18, hy + header_h - 6), (x0 + w - 18, hy + header_h - 6)],
               fill=pal["border"], width=2)

    # data rows
    ry = hy + header_h
    for r_idx, row in enumerate(rows):
        if r_idx % 2 == 0:
            draw.rounded_rectangle(
                [(x0 + 14, ry - 2), (x0 + w - 14, ry + row_h - 6)],
                radius=10, fill=pal["panel2"])
        for i, val in enumerate(row):
            color = pal["text"]
            txt = str(val)
            if isinstance(val, tuple):
                txt, key = val
                color = {"green": pal["green"], "red": pal["red"],
                         "muted": pal["muted"], "amber": pal["amber"]}.get(key, pal["text"])
            _cell(draw, txt, col_xs[i], ry + 8, f_cell, color)
        ry += row_h

    return total_h + 22


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
    f_body  = _font(16, True)
    f_cell  = _font(14)
    f_small = _font(12)

    dir_colour = {
        "UP":       pal["green"],
        "DOWN":     pal["red"],
        "SIDEWAYS": pal["muted"],
        "FLAT":     pal["muted"],
    }
    arrow = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→", "FLAT": "→"}

    banner_h = 110 if opening.get("direction") else 0
    row_h    = 44
    table_h  = (60 + row_h * len(preds) + 18) if preds else 0
    total_h  = 16 + banner_h + (12 if banner_h and table_h else 0) + table_h + 14

    _panel(draw, x0, y0, x0 + w, y0 + total_h, pal["panel"], pal["border"], radius=18)

    cy = y0 + 16

    if opening.get("direction"):
        d = opening["direction"]
        op_c = dir_colour.get(d, pal["text"])
        _cell(draw, "🔮 Nifty Opening Prediction (09:15 IST)",
              x0 + 22, cy + 2, f_title, pal["accent"])
        _cell(draw,
              f"{arrow.get(d, '→')}  {d}   ({opening.get('gap_pct','—')}, "
              f"{opening.get('confidence', 0)}% confidence)",
              x0 + 22, cy + 44, f_body, op_c)
        note = (opening.get("notes") or [""])[0]
        if note:
            _cell(draw, note[:140], x0 + 22, cy + 78, f_small, pal["muted"])
        cy += banner_h + 12

    if preds:
        _cell(draw, "🔮 Today's Top Predictions", x0 + 22, cy + 2, f_title, pal["accent"])
        cy += 50

        headers = ["Stock", "Horizon", "Direction", "Conf.",
                   "Buy", "SL", "Target", "Profit"]
        col_w   = [1.4, 1.5, 1.5, 1.0, 1.2, 1.2, 1.2, 1.3]
        total_wt = sum(col_w)
        inner_w = w - 44
        cx = x0 + 22
        col_xs = []
        for wt in col_w:
            col_xs.append(cx)
            cx += int(inner_w * wt / total_wt)

        for i, h in enumerate(headers):
            _cell(draw, h.upper(), col_xs[i], cy, _font(12, True), pal["muted"])
        draw.line([(x0 + 18, cy + 32), (x0 + w - 18, cy + 32)],
                  fill=pal["border"], width=2)
        cy += 40

        for r_idx, (tag, p) in enumerate(preds):
            if r_idx % 2 == 0:
                draw.rounded_rectangle(
                    [(x0 + 14, cy - 2), (x0 + w - 14, cy + row_h - 6)],
                    radius=10, fill=pal["panel2"])
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
                _cell(draw, val, col_xs[i], cy + 8, f_cell, colour)
            cy += row_h

    return y0 + total_h + 18


def _draw_charts_strip(img, draw, pal, x0, y0, w, buckets, macro,
                        enriched, theme: str = "dark") -> int:
    """Stack charts vertically — better readability on phones."""
    from . import charts

    _cell(draw, "📊 Advanced Market Analytics", x0 + 4, y0 + 6,
          _font(20, True), pal["accent"])
    y = y0 + 50

    try:
        top_picks = []
        for key in ("intraday", "swing", "holding"):
            top_picks.extend((buckets.get(key) or [])[:4])
        if top_picks:
            c1 = charts.chart_expected_profit(
                top_picks, "🎯 Expected Profit on Top Picks",
                width=w, height=420, theme=theme)
            img.paste(c1, (x0, y))
            y += c1.height + 16

        if (macro or {}).get("snapshot"):
            c2 = charts.chart_macro(macro, width=w, height=240, theme=theme)
            img.paste(c2, (x0, y))
            y += c2.height + 16

        c3 = charts.chart_risk_reward(buckets, width=w, height=380, theme=theme)
        img.paste(c3, (x0, y))
        y += c3.height + 16

        c4 = charts.chart_sector_heatmap(enriched, width=w, height=360, theme=theme)
        img.paste(c4, (x0, y))
        y += c4.height + 16

        half = (w - 18) // 2
        c5 = charts.chart_breadth(enriched, width=half, height=260, theme=theme)
        c6 = charts.chart_confidence_hist(buckets, width=half, height=260, theme=theme)
        img.paste(c5, (x0, y))
        img.paste(c6, (x0 + half + 18, y))
        y += max(c5.height, c6.height) + 18
    except Exception as exc:
        logger.warning(f"Chart strip render failed: {exc}")

    return y


def _draw_exec_summary(draw, pal, x0, y0, w, buckets, macro, enriched,
                        market_forecast: dict | None = None) -> int:
    """Mobile-first executive summary with pill badges and large type."""
    adv = dec = flat = total = 0
    for e in enriched or []:
        v = (e.get("tech") or {}).get("chg_1d_pct")
        if v is None: continue
        total += 1
        if v > 0.2:   adv += 1
        elif v < -0.2: dec += 1
        else:          flat += 1

    top_pick = None
    for key in ("intraday", "swing", "holding"):
        for p in (buckets.get(key) or []):
            pp = float((p.get("levels") or {}).get("expected_profit_pct") or 0)
            if top_pick is None or pp > top_pick[1]:
                top_pick = (p, pp, key)

    regime  = ((macro or {}).get("regime") or "neutral").upper()
    opening = (macro or {}).get("opening") or {}

    h = 320 if market_forecast else 250
    _panel(draw, x0, y0, x0 + w, y0 + h, pal["panel"], pal["border"], radius=18)

    _cell(draw, "⚡ Executive Summary", x0 + 24, y0 + 18,
          _font(22, True), pal["accent"])

    # Pill row
    py = y0 + 70
    f_pill = _font(13, True)
    regime_bg = {
        "RISK-ON":  pal["green_bg"], "BULLISH": pal["green_bg"],
        "RISK-OFF": pal["red_bg"],   "BEARISH": pal["red_bg"],
    }.get(regime, pal["panel2"])
    regime_fg = {
        "RISK-ON":  pal["green"], "BULLISH": pal["green"],
        "RISK-OFF": pal["red"],   "BEARISH": pal["red"],
    }.get(regime, pal["muted"])
    nx = _pill(draw, f"🌐 {regime}", x0 + 24, py, f_pill, regime_fg, regime_bg)
    if opening.get("direction"):
        od = opening["direction"]
        oc = pal["green_bg"] if "UP" in od else (pal["red_bg"] if "DOWN" in od else pal["panel2"])
        of = pal["green"] if "UP" in od else (pal["red"] if "DOWN" in od else pal["muted"])
        nx = _pill(draw, f"🔮 Open {od} {opening.get('gap_pct','')}",
                    nx + 12, py, f_pill, of, oc)
    if total:
        pct = adv / total * 100
        bc = pal["green_bg"] if pct >= 55 else (pal["red_bg"] if pct <= 45 else pal["amber_bg"])
        bf = pal["green"]    if pct >= 55 else (pal["red"]    if pct <= 45 else pal["amber"])
        _pill(draw, f"📊 {pct:.0f}% advancing ({adv}/{total})",
               nx + 12, py, f_pill, bf, bc)

    # Top idea block
    iy = y0 + 140
    if top_pick:
        p, pp, key = top_pick
        sym = p["symbol"].replace(".NS", "")
        lv  = p["levels"]
        tag = {"intraday": "SAME-DAY",
               "swing":    "SHORT-TERM",
               "holding":  "LONG-TERM"}.get(key, key.upper())
        _cell(draw, f"💡 TODAY'S BEST IDEA  ·  {tag}", x0 + 24, iy,
              _font(11, True), pal["muted"])
        _cell(draw, sym, x0 + 24, iy + 24, _font(26, True), pal["accent"])
        ladder = (f"Buy ₹{lv['entry']:,.0f}   →   Target ₹{lv['target']:,.0f}   "
                  f"(SL ₹{lv['sl']:,.0f})")
        _cell(draw, ladder, x0 + 24, iy + 76, _font(15, True), pal["text"])
        # right-side profit pill
        tc = pal["green"] if pp >= 0 else pal["red"]
        bg = pal["green_bg"] if pp >= 0 else pal["red_bg"]
        _pill(draw, f"{pp:+.2f}% expected", x0 + w - 320, iy + 30,
               _font(15, True), tc, bg)

    # Market forecast strip
    if market_forecast:
        mf = market_forecast
        arrow = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→"}.get(mf["direction"], "→")
        c  = {"UP": pal["green"], "DOWN": pal["red"]}.get(mf["direction"], pal["muted"])
        bg = {"UP": pal["green_bg"], "DOWN": pal["red_bg"]}.get(mf["direction"], pal["panel2"])
        lo, hi = mf["band_pct"]
        fy = y0 + h - 78
        draw.rounded_rectangle(
            [(x0 + 18, fy), (x0 + w - 18, fy + 64)],
            radius=14, fill=bg)
        _cell(draw,
              f"🔮 Next-5-session Forecast: {arrow} {mf['direction']}  ·  "
              f"{mf['confidence']}% confidence  ·  band {lo:+.1f}% … {hi:+.1f}%",
              x0 + 32, fy + 18, _font(14, True), c)

    return y0 + h + 18


def _draw_self_review(draw, pal, x0, y0, w, review: dict) -> int:
    """Mobile-optimised Model Self-Review card with pills & accent stripe."""
    best  = review.get("best_features") or []
    worst = review.get("worst_features") or []
    has_worst = bool(worst) and worst != best

    h = 100 + 70 + (62 if best else 0) + (62 if has_worst else 0) + 26
    _panel(draw, x0, y0, x0 + w, y0 + h, pal["panel"], pal["border"], radius=18)
    draw.rounded_rectangle([(x0, y0 + 14), (x0 + 8, y0 + h - 14)],
                            radius=4, fill=pal["accent2"])

    _cell(draw, "🧠 Model Self-Review", x0 + 24, y0 + 18,
          _font(20, True), pal["accent2"])
    _cell(draw, "What the automation has learned so far",
          x0 + 24, y0 + 56, _font(12), pal["muted"])

    acc = review.get("overall_accuracy")
    ps  = review.get("picks_scored", 0)
    pw  = review.get("picks_won", 0)
    nf  = review.get("n_features", 0)

    py = y0 + 100
    fp = _font(13, True)
    acc_txt = f"{acc:.1f}%" if acc is not None else "calibrating"
    acc_bg  = pal["green_bg"] if (acc or 0) >= 55 else pal["amber_bg"]
    acc_fg  = pal["green"]    if (acc or 0) >= 55 else pal["amber"]
    nx = _pill(draw, f"✅ {acc_txt} accuracy", x0 + 24, py, fp, acc_fg, acc_bg)
    nx = _pill(draw, f"🎯 {pw}/{ps} correct", nx + 12, py,
                fp, pal["accent"], pal["panel2"])
    _pill(draw, f"📡 {nf} signals", nx + 12, py,
           fp, pal["muted"], pal["panel2"])

    yy = y0 + 175
    if best:
        _cell(draw, "▲ MOST RELIABLE SIGNALS (boosted)", x0 + 24, yy,
              _font(12, True), pal["green"])
        line = "   ·   ".join(
            f"{b['name']} {b['hit_rate']:.0f}% (n={b['total']})"
            for b in best[:4]
        )
        _cell(draw, line, x0 + 24, yy + 26, _font(13), pal["text"])
        yy += 62

    if has_worst:
        _cell(draw, "▼ LEAST RELIABLE (auto-suppressed)", x0 + 24, yy,
              _font(12, True), pal["red"])
        line = "   ·   ".join(
            f"{b['name']} {b['hit_rate']:.0f}% (n={b['total']})"
            for b in worst[:4]
        )
        _cell(draw, line, x0 + 24, yy + 26, _font(13), pal["text"])

    return y0 + h + 18


# ── Splunk-style 1920×1080 dashboard helpers ─────────────────────────────────

def _sf(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """HD font loader — no mobile scale factor applied."""
    candidates = (
        ("arialbd.ttf", "arial.ttf"),
        ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"),
        ("LiberationSans-Bold.ttf", "LiberationSans-Regular.ttf"),
    )
    for pair in candidates:
        name = pair[0] if bold else pair[1]
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


_SPL_PAL_DARK: dict = {
    "bg":        (8,  11,  21),
    "panel":     (15, 20,  34),
    "panel2":    (20, 27,  44),
    "header_bg": (10, 14,  26),
    "text":      (218, 225, 240),
    "muted":     (100, 116, 148),
    "accent":    (64,  152, 255),
    "accent2":   (145, 108, 255),
    "green":     (44,  204, 124),
    "green_bg":  (18,  54,  40),
    "red":       (255,  70,  90),
    "red_bg":    (68,   22,  32),
    "amber":     (255, 175,  48),
    "amber_bg":  (64,   46,  12),
    "border":    (34,   44,  66),
    "grid":      (24,   32,  52),
}

_SPL_PAL_LIGHT: dict = {
    "bg":        (245, 247, 250),
    "panel":     (255, 255, 255),
    "panel2":    (240, 244, 250),
    "header_bg": (228, 234, 244),
    "text":      (22,  30,  46),
    "muted":     (110, 124, 150),
    "accent":    (16,  108, 220),
    "accent2":   (118,  72, 220),
    "green":     (28,  158,  92),
    "green_bg":  (220, 244, 230),
    "red":       (210,  44,  64),
    "red_bg":    (250, 226, 230),
    "amber":     (208, 134,  18),
    "amber_bg":  (252, 240, 212),
    "border":    (210, 220, 234),
    "grid":      (224, 230, 240),
}

# Active palette — mutated by build_report_image based on theme.
_SPL_PAL: dict = dict(_SPL_PAL_DARK)


def _kpi_tile(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
               label: str, value: str, sub: str, color: tuple) -> None:
    """Single Splunk-style KPI metric tile with top accent bar."""
    p = _SPL_PAL
    draw.rounded_rectangle([(x, y), (x + w, y + h)],
                            radius=6, fill=p["panel"], outline=p["border"])
    # top accent strip
    draw.rounded_rectangle([(x + 2, y + 2), (x + w - 2, y + 6)],
                            radius=3, fill=color)
    # label (small caps, muted)
    draw.text((x + 14, y + 16), label, font=_sf(9, True), fill=p["muted"])
    # big metric value centred
    draw.text((x + w // 2, y + h // 2 + 4), value,
              font=_sf(26, True), fill=color, anchor="mm")
    # subtext
    if sub:
        draw.text((x + w // 2, y + h - 13), sub,
                  font=_sf(9), fill=p["muted"], anchor="mm")


def _spl_table(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, max_h: int,
                title: str, headers: list[str], rows: list[list],
                col_weights: list[float], accent: tuple) -> int:
    """Compact Splunk-style data table that clips to max_h. Returns height used."""
    p   = _SPL_PAL
    TH  = 32   # title row height
    HH  = 20   # column-header row height
    RH  = 21   # data row height
    PL  = 12   # left padding (after accent bar)

    rows_fit = max(0, (max_h - TH - HH - 8) // RH)
    vis      = rows[:rows_fit]
    ah       = TH + HH + RH * max(1, len(vis)) + 8

    draw.rounded_rectangle([(x, y), (x + w, y + ah)],
                            radius=6, fill=p["panel"], outline=p["border"])
    # left accent bar
    draw.rounded_rectangle([(x, y + 4), (x + 4, y + ah - 4)],
                            radius=2, fill=accent)
    # title
    draw.text((x + PL + 4, y + 8), title,
              font=_sf(12, True), fill=accent)

    # column x-positions
    iw  = w - PL - 10
    twt = sum(col_weights)
    xs  = []
    cx  = x + PL + 4
    for wt in col_weights:
        xs.append(cx)
        cx += int(iw * wt / twt)

    # header row
    hy = y + TH
    for i, hdr in enumerate(headers):
        draw.text((xs[i], hy + 2), hdr.upper(),
                  font=_sf(9, True), fill=p["muted"])
    draw.line([(x + PL, hy + HH - 1), (x + w - 6, hy + HH - 1)],
              fill=p["border"], width=1)

    # data rows
    ry = hy + HH
    for r_idx, row in enumerate(vis):
        if r_idx % 2 == 0:
            draw.rectangle([(x + 4, ry), (x + w - 4, ry + RH - 1)],
                           fill=p["panel2"])
        for i, val in enumerate(row):
            color = p["text"]
            txt   = str(val)
            if isinstance(val, tuple):
                txt, key = val
                color = {"green": p["green"], "red": p["red"],
                         "muted": p["muted"], "amber": p["amber"]}.get(key, p["text"])
            draw.text((xs[i], ry + 3), txt, font=_sf(11), fill=color)
        ry += RH

    if len(rows) > rows_fit:
        draw.text((x + w - 6, y + ah - 8),
                  f"+{len(rows) - rows_fit} more",
                  font=_sf(9), fill=p["muted"], anchor="ra")
    return ah


# ── Splunk-style chart helpers (sparkline / bars / gauge / scatter) ─────────

def _spl_panel_frame(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                      title: str, accent: tuple, subtitle: str = "") -> tuple[int, int, int, int]:
    """Draw an outer Splunk panel with title + left accent bar.
    Returns inner drawing rect (ix, iy, iw, ih) reserved for the chart body."""
    p = _SPL_PAL
    d.rounded_rectangle([(x, y), (x + w, y + h)],
                        radius=6, fill=p["panel"], outline=p["border"])
    d.rounded_rectangle([(x, y + 4), (x + 4, y + h - 4)],
                        radius=2, fill=accent)
    d.text((x + 12, y + 6), title, font=_sf(10, True), fill=accent)
    if subtitle:
        d.text((x + w - 8, y + 8), subtitle,
               font=_sf(8), fill=p["muted"], anchor="ra")
    return (x + 12, y + 24, w - 24, h - 30)


def _spl_sparkline(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                    series: list[float], color: tuple, fill_area: bool = True) -> None:
    """Tiny line chart with optional shaded area beneath the curve."""
    if not series or len(series) < 2:
        return
    p = _SPL_PAL
    lo, hi = min(series), max(series)
    rng = hi - lo if hi > lo else 1.0
    pts: list[tuple[int, int]] = []
    n = len(series)
    for i, v in enumerate(series):
        px = x + int(i * (w - 1) / (n - 1))
        py = y + h - 1 - int((v - lo) * (h - 2) / rng)
        pts.append((px, py))

    if fill_area:
        # Build a translucent fill polygon under the curve (modern soft fade).
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld    = ImageDraw.Draw(layer)
        poly  = [(px - x, py - y) for px, py in pts]
        poly += [(w - 1, h - 1), (0, h - 1)]
        ld.polygon(poly, fill=(*color, 70))
        d._image.paste(layer, (x, y), layer)  # type: ignore[attr-defined]

    # Soft glow under the curve line
    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gld = ImageDraw.Draw(glow_layer)
    for i in range(len(pts) - 1):
        a, b2 = pts[i], pts[i + 1]
        gld.line([(a[0] - x, a[1] - y), (b2[0] - x, b2[1] - y)],
                 fill=(*color, 60), width=4)
    d._image.paste(glow_layer, (x, y), glow_layer)  # type: ignore[attr-defined]

    # The curve itself
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=color, width=2)
    # End-point marker with halo
    px, py = pts[-1]
    halo = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    hd   = ImageDraw.Draw(halo)
    hd.ellipse([(0, 0), (14, 14)], fill=(*color, 60))
    d._image.paste(halo, (px - 7, py - 7), halo)  # type: ignore[attr-defined]
    d.ellipse([(px - 3, py - 3), (px + 3, py + 3)], fill=color)


def _spl_bars_horiz(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                     items: list[tuple]) -> None:
    """Horizontal bar chart.

    Each item is either:
      (label, value 0-100, color)               – plain row
      (label, value 0-100, color, highlight)    – set highlight=True to render
                                                  a 🏆 badge + accent outline
                                                  marking the leader.
    """
    if not items:
        return
    p   = _SPL_PAL
    rh  = max(14, (h - 4) // max(len(items), 1))
    # Layout: [label] [bar] [value%].  Reserve enough for "100%" + trophy.
    lblw = min(110, max(70, w // 3))
    valw = 38                              # space for "100%" text
    pad  = 4                               # gap between columns
    barw = max(20, w - lblw - valw - pad * 2)

    def _fit_label(text: str, max_px: int, base: int = 9) -> tuple:
        """Shrink font + truncate so text fits inside max_px."""
        for sz in range(base, 6, -1):
            f = _sf(sz, True)
            try:
                if d.textlength(text, font=f) <= max_px:
                    return f, text
            except Exception:
                if len(text) * sz * 0.6 <= max_px:
                    return f, text
        # Hard truncate at smallest size with ellipsis.
        f = _sf(7, True)
        t = text
        while t and d.textlength(t + "…", font=f) > max_px:
            t = t[:-1]
        return f, (t + "…" if t else text[:1])

    for i, item in enumerate(items):
        if len(item) >= 4:
            lbl, val, col, hl = item[0], item[1], item[2], bool(item[3])
        else:
            lbl, val, col, hl = item[0], item[1], item[2], False
        ry  = y + i * rh + 2
        cy  = ry + rh // 2
        # label (with trophy prefix when this is the leader) — auto-fit
        disp = f"🏆 {lbl}" if hl else str(lbl)
        lbl_font, disp = _fit_label(disp, lblw - pad)
        d.text((x, cy), disp, font=lbl_font, fill=p["text"], anchor="lm")
        # track
        bar_x0 = x + lblw
        bar_x1 = bar_x0 + barw
        d.rounded_rectangle(
            [(bar_x0, cy - 5), (bar_x1, cy + 5)],
            radius=3, fill=p["panel2"])
        # filled portion
        bw = max(0, min(barw, int(barw * max(0.0, min(100.0, val)) / 100)))
        if bw > 0:
            d.rounded_rectangle(
                [(bar_x0, cy - 5), (bar_x0 + bw, cy + 5)],
                radius=3, fill=col)
            # subtle top-highlight stripe for a glossy, modern look
            hl_strip = Image.new("RGBA", (bw, 3), (255, 255, 255, 38))
            d._image.paste(hl_strip, (bar_x0, cy - 4), hl_strip)  # type: ignore[attr-defined]
            # leader outline + soft glow halo (kept inside the bar bounds)
            if hl:
                d.rounded_rectangle(
                    [(bar_x0 - 1, cy - 6), (bar_x0 + bw + 1, cy + 6)],
                    radius=4, outline=col, width=2)
                glow_w = bw + 6
                glow = Image.new("RGBA", (glow_w, 14), (0, 0, 0, 0))
                gd   = ImageDraw.Draw(glow)
                gd.rounded_rectangle([(0, 0), (glow_w, 14)],
                                      radius=5, fill=(*col, 55))
                d._image.paste(glow, (bar_x0 - 3, cy - 7), glow)  # type: ignore[attr-defined]
        # value — anchored to the right edge of our reserved column so it
        # never spills past the panel boundary.
        d.text((x + w - 2, cy),
               f"{val:.0f}%", font=_sf(9, True), fill=col, anchor="rm")


def _spl_bars_vert(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                    items: list[tuple[str, float, tuple]]) -> None:
    """Vertical bar histogram. Items = (label, height_value, color).
    Values can be any positive numbers — they get auto-scaled."""
    if not items:
        return
    p     = _SPL_PAL
    n     = len(items)
    gap   = 4
    bw    = max(8, (w - gap * (n - 1)) // max(n, 1))
    vmax  = max(v for _, v, _ in items) or 1.0
    avail = h - 22  # reserve 22 for x-axis label

    for i, (lbl, val, col) in enumerate(items):
        bh   = int(avail * val / vmax)
        bx   = x + i * (bw + gap)
        b_y0 = y + avail - bh
        b_y1 = y + avail
        d.rounded_rectangle([(bx, b_y0), (bx + bw, b_y1)],
                            radius=3, fill=col)
        # value above bar (skip if zero to reduce clutter)
        if val > 0:
            d.text((bx + bw // 2, b_y0 - 2),
                   f"{int(val)}",
                   font=_sf(9, True), fill=col, anchor="md")
        # x-axis label
        d.text((bx + bw // 2, y + avail + 4),
               lbl[:8], font=_sf(9), fill=p["muted"], anchor="ma")


def _spl_rr_chart(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                    items: list[tuple[str, float, float, tuple]]) -> None:
    """Tornado-style Risk vs Reward bar chart.

    items = [(symbol, risk_pct, reward_pct, accent_color), …]
    Risk extends LEFT from the centre line (red), Reward extends RIGHT (green).
    A small "R:R" ratio is rendered at the right edge.
    """
    if not items:
        return
    p   = _SPL_PAL
    n   = len(items)
    rh  = max(16, (h - 4) // max(n, 1))
    lblw = 56                     # symbol column on the left
    rrw  = 44                     # R:R ratio column on the right
    chart_w = w - lblw - rrw
    half_w  = chart_w // 2
    cx      = x + lblw + half_w   # centre line x

    # Auto-scale: use the larger of |risk_max| or reward_max so both sides share scale
    vmax = max(max(abs(it[1]), it[2]) for it in items) or 1.0

    # Faint vertical centre rule
    d.line([(cx, y + 2), (cx, y + n * rh)], fill=p["border"], width=1)
    # Faint quarter gridlines
    for frac in (0.5,):
        gx_l = cx - int(half_w * frac)
        gx_r = cx + int(half_w * frac)
        d.line([(gx_l, y + 2), (gx_l, y + n * rh)], fill=p["grid"], width=1)
        d.line([(gx_r, y + 2), (gx_r, y + n * rh)], fill=p["grid"], width=1)

    for i, (sym, risk, reward, _accent) in enumerate(items):
        ry = y + i * rh + 2
        my = ry + rh // 2
        # symbol label
        d.text((x + 2, my), sym[:7],
               font=_sf(9, True), fill=p["text"], anchor="lm")
        # risk bar (left, red)
        rw_px = max(1, int(half_w * min(1.0, abs(risk) / vmax)))
        d.rounded_rectangle(
            [(cx - rw_px, my - 5), (cx, my + 5)],
            radius=3, fill=p["red"])
        d.text((cx - rw_px - 2, my),
               f"{abs(risk):.1f}%",
               font=_sf(8, True), fill=p["red"], anchor="rm")
        # reward bar (right, green)
        gw_px = max(1, int(half_w * min(1.0, max(0, reward) / vmax)))
        d.rounded_rectangle(
            [(cx, my - 5), (cx + gw_px, my + 5)],
            radius=3, fill=p["green"])
        d.text((cx + gw_px + 2, my),
               f"{reward:.1f}%",
               font=_sf(8, True), fill=p["green"], anchor="lm")
        # R:R ratio chip on the right
        rr = (reward / abs(risk)) if abs(risk) > 0.01 else 0
        rr_col = (p["green"] if rr >= 2.0
                  else p["amber"] if rr >= 1.0 else p["red"])
        d.text((x + w - 2, my),
               f"{rr:.1f}:1",
               font=_sf(9, True), fill=rr_col, anchor="rm")

    # axis labels (small)
    d.text((cx - half_w, y + n * rh + 2),
           "← risk", font=_sf(8), fill=p["red"])
    d.text((cx + half_w, y + n * rh + 2),
           "reward →", font=_sf(8), fill=p["green"], anchor="ra")


def _spl_donut(d: ImageDraw.ImageDraw, x: int, y: int, size: int,
                pct: float, color: tuple, label: str = "",
                center_text: str | None = None) -> None:
    """Donut/ring gauge. `pct` 0-100. `center_text` overrides the centred number."""
    p   = _SPL_PAL
    box = [(x, y), (x + size, y + size)]
    pct = max(0.0, min(100.0, pct))

    # Soft outer glow (translucent halo) — modernizes the gauge
    glow = Image.new("RGBA",
                      (size + 16, size + 16), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    gd.ellipse([(0, 0), (size + 16, size + 16)],
                fill=(*color, 22))
    gd.ellipse([(4, 4), (size + 12, size + 12)],
                fill=(*color, 38))
    d._image.paste(glow, (x - 8, y - 8), glow)  # type: ignore[attr-defined]

    # Background ring (track)
    d.ellipse(box, fill=p["panel2"])
    # Filled arc — Pillow draws clockwise starting from 3 o'clock; offset -90°
    if pct > 0:
        d.pieslice(box, start=-90, end=-90 + 360 * pct / 100, fill=color)
    # Inner hole (creates the ring)
    inset = max(8, size // 4)
    d.ellipse([(x + inset, y + inset),
                (x + size - inset, y + size - inset)],
               fill=p["panel"])
    # Subtle inner border
    d.ellipse([(x + inset - 1, y + inset - 1),
                (x + size - inset + 1, y + size - inset + 1)],
               outline=p["border"], width=1)
    # Centre text
    cx, cy = x + size // 2, y + size // 2
    txt = center_text if center_text is not None else f"{pct:.0f}%"
    d.text((cx, cy - 2), txt,
           font=_sf(15, True), fill=color, anchor="mm")
    if label:
        d.text((cx, y + size + 10), label,
               font=_sf(9), fill=p["muted"], anchor="ma")


def _spl_scatter(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                  points: list[tuple[float, float, tuple, str]],
                  x_label: str = "Risk %", y_label: str = "Reward %") -> None:
    """Mini scatter plot. points = [(x_val, y_val, color, label), …]."""
    p = _SPL_PAL
    if not points:
        return
    pad_l, pad_r, pad_t, pad_b = 26, 6, 6, 18
    px0, py0 = x + pad_l, y + pad_t
    px1, py1 = x + w - pad_r, y + h - pad_b

    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    x_lo, x_hi = min(xs + [0]), max(xs + [1])
    y_lo, y_hi = min(ys + [0]), max(ys + [1])
    if x_hi == x_lo: x_hi = x_lo + 1
    if y_hi == y_lo: y_hi = y_lo + 1

    # axes
    d.line([(px0, py0), (px0, py1)], fill=p["grid"], width=1)
    d.line([(px0, py1), (px1, py1)], fill=p["grid"], width=1)
    # zero gridlines if 0 in range
    if x_lo < 0 < x_hi:
        zx = px0 + int((0 - x_lo) / (x_hi - x_lo) * (px1 - px0))
        d.line([(zx, py0), (zx, py1)], fill=p["border"], width=1)
    if y_lo < 0 < y_hi:
        zy = py1 - int((0 - y_lo) / (y_hi - y_lo) * (py1 - py0))
        d.line([(px0, zy), (px1, zy)], fill=p["border"], width=1)

    # plot points
    for xv, yv, col, lbl in points:
        cx = px0 + int((xv - x_lo) / (x_hi - x_lo) * (px1 - px0))
        cy = py1 - int((yv - y_lo) / (y_hi - y_lo) * (py1 - py0))
        d.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill=col)
        if lbl:
            d.text((cx + 7, cy - 6), lbl[:6],
                   font=_sf(9, True), fill=p["text"])

    # axis labels
    d.text((px0 + (px1 - px0) // 2, py1 + 4),
           x_label, font=_sf(9), fill=p["muted"], anchor="ma")
    d.text((x + 2, py0 + (py1 - py0) // 2),
           y_label, font=_sf(9), fill=p["muted"], anchor="lm")


def _spl_heatcells(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int,
                    cells: list[tuple[str, float]]) -> None:
    """Sector heatmap-style cells. Each cell = (label, pct change).
    Green / red intensity based on magnitude. Auto-grid."""
    p = _SPL_PAL
    if not cells:
        return
    n     = len(cells)
    # Choose a near-square grid (cols x rows) that fits all cells.
    if   n <= 2: cols = n
    elif n <= 4: cols = 2
    elif n <= 6: cols = 3
    elif n <= 9: cols = 3
    else:        cols = 4
    rows  = (n + cols - 1) // cols
    cw    = (w - (cols - 1) * 4) // cols
    ch    = (h - (rows - 1) * 4) // rows
    vmax  = max((abs(v) for _, v in cells), default=1.0) or 1.0

    # Auto-fit helper: shrink font and/or truncate so text never spills out.
    pad = 6  # horizontal padding inside each cell

    def _fit(text: str, max_px: int, base: int, bold: bool):
        """Return (font, text) where the rendered text fits within max_px."""
        for sz in range(base, 6, -1):
            f = _sf(sz, bold)
            try:
                tw = d.textlength(text, font=f)
            except Exception:
                tw = len(text) * sz * 0.6
            if tw <= max_px:
                return f, text
        # Still too wide at smallest size — hard-truncate with ellipsis.
        f = _sf(7, bold)
        t = text
        while t and d.textlength(t + "…", font=f) > max_px:
            t = t[:-1]
        return f, (t + "…" if t else text[:1])

    for i, (lbl, val) in enumerate(cells):
        cx = x + (i % cols) * (cw + 4)
        cy = y + (i // cols) * (ch + 4)
        intensity = min(1.0, abs(val) / vmax)
        if val >= 0:
            r = int(20  + 80  * (1 - intensity))
            g = int(160 + 60  * intensity)
            b = int(80  + 40  * (1 - intensity))
            col = (r, g, b)
        else:
            r = int(180 + 75 * intensity)
            g = int(60  + 30 * (1 - intensity))
            b = int(70  + 30 * (1 - intensity))
            col = (r, g, b)
        d.rounded_rectangle([(cx, cy), (cx + cw, cy + ch)],
                            radius=4, fill=col)
        max_text_px = max(10, cw - pad * 2)
        lbl_font, lbl_txt = _fit(lbl, max_text_px, 9, True)
        val_txt = f"{val:+.1f}%"
        val_font, val_txt = _fit(val_txt, max_text_px, 8, False)
        d.text((cx + cw // 2, cy + ch // 2 - 5),
               lbl_txt, font=lbl_font, fill=(255, 255, 255), anchor="mm")
        d.text((cx + cw // 2, cy + ch // 2 + 6),
               val_txt, font=val_font, fill=(245, 245, 250), anchor="mm")


def _draw_spl_chart_collage(d: ImageDraw.ImageDraw, img: Image.Image,
                              x: int, y: int, w: int, h: int,
                              buckets: dict, enriched: list[dict],
                              macro: dict | None, review: dict | None) -> None:
    """Two-row Splunk-style chart collage with varied panel sizes."""
    p   = _SPL_PAL
    GAP = 10
    # Two rows: row1 ≈ 56% height (sparkline-heavy), row2 ≈ 44% (gauges + heat)
    r1_h = int((h - GAP) * 0.56)
    r2_h = h - GAP - r1_h

    # Width grid: 5 equal cells, GAP between
    col_w = (w - 4 * GAP) // 5

    # ── Row 1 ────────────────────────────────────────────────────────────
    # [Top Picks 30D Trend  (2 cells wide)] [Sector Breadth] [Risk vs Reward] [Confidence]
    rx = x
    ry = y

    # Panel 1 — Top Picks 30D Trend (2-cell wide)
    p1_w = col_w * 2 + GAP
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, p1_w, r1_h,
        "📈  TOP PICKS — PRICE OVER LAST 30 DAYS",
        p["accent"],
        subtitle="line = daily close · right number = today's % move")
    picks: list[dict] = []
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or [])[:3]:
            if pk not in picks:
                picks.append(pk)
            if len(picks) >= 5:
                break
        if len(picks) >= 5:
            break
    if picks:
        row_h = ih // max(len(picks), 1)
        for i, pk in enumerate(picks):
            sym  = pk["symbol"].replace(".NS", "")
            tech = pk.get("tech") or {}
            series = tech.get("close_30d") or tech.get("history_close") or []
            if not series:
                lv = pk.get("levels") or {}
                series = [lv.get("sl", pk["price"] * 0.97),
                           pk["price"] * 0.99,
                           pk["price"],
                           lv.get("entry", pk["price"]),
                           lv.get("target", pk["price"] * 1.03)]
            chg = tech.get("chg_1d_pct", 0) or 0
            col = p["green"] if chg >= 0 else p["red"]
            ly  = iy + i * row_h
            d.text((ix, ly + 1), sym, font=_sf(10, True), fill=p["text"])
            d.text((ix + 78, ly + 2),
                   f"₹{pk['price']:,.0f}",
                   font=_sf(9), fill=p["muted"])
            d.text((ix + iw, ly + 2),
                   f"{chg:+.2f}%",
                   font=_sf(9, True), fill=col, anchor="ra")
            _spl_sparkline(d, ix, ly + 16, iw, max(10, row_h - 20),
                            [float(v) for v in series[-30:]], col)
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No price history",
               font=_sf(11), fill=p["muted"], anchor="mm")
    rx += p1_w + GAP

    # Panel 2 — Sector Breadth
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, col_w, r1_h,
        "🏭  WHICH SECTORS ARE RISING TODAY",
        p["green"],
        subtitle="% of stocks up in each sector (green ≥60 · red ≤40)")
    sec_map: dict[str, list[float]] = {}
    for e in enriched or []:
        # `sector` lives at the top level of an enriched stock dict
        # (set by enrich_stock as fund["sector"]). Older code looked it up
        # under e["info"]["sector"] which is always None and dumped every
        # stock into a single "Other" bucket.
        sec = (e.get("sector")
               or (e.get("info") or {}).get("sector")
               or (e.get("fund") or {}).get("sector")
               or "Other")
        sec = str(sec).strip() or "Other"
        chg = (e.get("tech") or {}).get("chg_1d_pct")
        if chg is None:
            continue
        sec_map.setdefault(sec[:14], []).append(float(chg))
    if sec_map:
        sec_items: list[tuple[str, float, tuple]] = []
        for sec, vals in sec_map.items():
            adv_pct = sum(1 for v in vals if v > 0.2) / len(vals) * 100
            col = (p["green"] if adv_pct >= 60
                   else p["red"] if adv_pct <= 40 else p["amber"])
            sec_items.append((sec, adv_pct, col))
        sec_items.sort(key=lambda t: t[1], reverse=True)
        # Fit as many rows as the panel can render (each bar is ~14px tall).
        max_rows = max(3, ih // 16)
        # Mark the leader for the bars helper to render a 🏆 badge.
        rendered = sec_items[:max_rows]
        if rendered:
            top_label = rendered[0][0]
            rendered = [(lbl, val, col, lbl == top_label)
                        for (lbl, val, col) in rendered]
        _spl_bars_horiz(d, ix, iy, iw, ih, rendered)
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No sector data",
               font=_sf(11), fill=p["muted"], anchor="mm")
    rx += col_w + GAP

    # Panel 3 — Risk vs Reward (tornado bars)
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, col_w, r1_h,
        "⚖️  HOW MUCH YOU RISK vs WIN",
        p["accent2"],
        subtitle="red ← loss% if SL hit · profit% → green · R:R = win÷risk")
    rr_items: list[tuple[str, float, float, tuple]] = []
    bucket_color = {"intraday": p["accent"], "swing": p["green"],
                    "holding":  p["accent2"], "sell": p["red"]}
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or [])[:5]:
            lv = pk.get("levels") or {}
            ent = lv.get("entry"); sl = lv.get("sl"); tg = lv.get("target")
            if not (ent and sl and tg):
                continue
            risk_pct   = abs((ent - sl) / ent * 100) if ent else 0
            reward_pct = (tg - ent) / ent * 100 if ent else 0
            rr_items.append((pk["symbol"].replace(".NS", ""),
                              risk_pct, reward_pct, bucket_color[k]))
            if len(rr_items) >= 8:
                break
        if len(rr_items) >= 8:
            break
    # Sort best R:R first
    rr_items.sort(
        key=lambda t: (t[2] / t[1]) if t[1] > 0.01 else 0,
        reverse=True)
    if rr_items:
        _spl_rr_chart(d, ix, iy, iw, ih, rr_items[:7])
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No predictions",
               font=_sf(11), fill=p["muted"], anchor="mm")
    rx += col_w + GAP

    # Panel 4 — Confidence histogram
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, col_w, r1_h,
        "🎯  HOW SURE IS THE MODEL?",
        p["amber"],
        subtitle="no. of buy ideas grouped by confidence band (%)")
    bins   = [0, 0, 0, 0, 0]
    labels = ["50-60", "60-70", "70-80", "80-90", "90+"]
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or []):
            pr = pk.get("predict")
            if not pr:
                continue
            c = int(pr.get("confidence", 0))
            if   c < 60: bins[0] += 1
            elif c < 70: bins[1] += 1
            elif c < 80: bins[2] += 1
            elif c < 90: bins[3] += 1
            else:        bins[4] += 1
    bin_colors = [p["muted"], p["amber"], p["amber"], p["green"], p["green"]]
    bar_items  = [(labels[i], bins[i], bin_colors[i]) for i in range(5)]
    if any(bins):
        _spl_bars_vert(d, ix, iy, iw, ih, bar_items)
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No predictions yet",
               font=_sf(11), fill=p["muted"], anchor="mm")

    # ── Row 2 ────────────────────────────────────────────────────────────
    # [Macro Heatmap (2-cell)] [Model Accuracy (1)] [Top Signal Strength (2-cell)]
    rx = x
    ry = y + r1_h + GAP

    # Panel 5 — Indian Indices + Global cues heatmap (2-cell wide)
    p5_w = col_w * 2 + GAP
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, p5_w, r2_h,
        "🇮🇳  INDIAN INDICES + GLOBAL CUES",
        p["accent"],
        subtitle="today's % move · green = up · red = down · 🛡 VIX = fear gauge")
    if (macro or {}).get("snapshot"):
        snap = macro["snapshot"]
        cells = []
        # Indian indices first (most relevant for the trader)
        for k, lbl in [
            ("NIFTY",          "Nifty"),
            ("BANKNIFTY",      "BNifty"),
            ("SENSEX",         "Sensex"),
            ("NIFTY100",       "N100"),
            ("NIFTY500",       "N500"),
            ("NIFTY_MIDCAP",   "Midcap"),
            ("NIFTY_SMALLCAP", "SmCap"),
            ("FINNIFTY",       "FinNty"),
            ("NIFTY_IT",       "IT"),
            ("NIFTY_AUTO",     "Auto"),
            ("NIFTY_PHARMA",   "Pharma"),
            ("NIFTY_FMCG",     "FMCG"),
            ("INDIA_VIX",      "IndVIX"),
            # Global cues
            ("SPY",            "S&P"),
            ("OIL",            "Oil"),
            ("GOLD",           "Gold"),
            ("INR",            "USDINR"),
            ("DXY",            "DXY"),
        ]:
            vd = snap.get(k) or {}
            v  = vd.get("chg_pct")
            if v is None:
                continue
            cells.append((lbl, float(v)))
        if cells:
            _spl_heatcells(d, ix, iy, iw, ih, cells)
        else:
            d.text((ix + iw // 2, iy + ih // 2),
                   "No macro data",
                   font=_sf(11), fill=p["muted"], anchor="mm")
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No macro data",
               font=_sf(11), fill=p["muted"], anchor="mm")
    rx += p5_w + GAP

    # Panel 6 — Model Accuracy donut
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, col_w, r2_h,
        "🧠  MODEL TRACK RECORD",
        p["accent2"],
        subtitle="% of past picks that hit target")
    acc = (review or {}).get("overall_accuracy") or 0
    ps  = (review or {}).get("picks_scored", 0)
    pw_ = (review or {}).get("picks_won", 0)
    nf  = (review or {}).get("n_features", 0)
    donut_size = min(ih - 6, iw // 2 - 6, 130)
    donut_size = max(60, donut_size)
    dx = ix + 2
    dy = iy + (ih - donut_size) // 2
    col = (p["green"] if acc >= 60 else p["amber"] if acc >= 45 else p["red"])
    _spl_donut(d, dx, dy, donut_size, acc, col,
                center_text=f"{acc:.0f}%" if acc else "—",
                label="")
    sx = ix + donut_size + 10
    sy = iy + max(0, (ih - 76) // 2)
    d.text((sx, sy),       f"{pw_}/{ps}",
           font=_sf(15, True), fill=p["text"])
    d.text((sx, sy + 20),  "hit target so far",
           font=_sf(8), fill=p["muted"])
    d.text((sx, sy + 42),  f"{nf}",
           font=_sf(15, True), fill=p["accent"])
    d.text((sx, sy + 62),  "signals used by model",
           font=_sf(8), fill=p["muted"])
    rx += col_w + GAP

    # Panel 7 — Top Signal Hit-Rates (2-cell wide horizontal bars)
    p7_w = col_w * 2 + GAP
    ix, iy, iw, ih = _spl_panel_frame(
        d, rx, ry, p7_w, r2_h,
        "📊  WHICH SIGNALS WORK BEST",
        p["green"],
        subtitle="green = reliable (>60%) · red = unreliable (<50%)")
    feats = []
    for f in (review or {}).get("best_features", [])[:4]:
        feats.append((f.get("name", "")[:14],
                      float(f.get("hit_rate", 0)),
                      p["green"]))
    seen = {f[0] for f in feats}
    for f in (review or {}).get("worst_features", [])[:3]:
        nm = f.get("name", "")[:14]
        if nm in seen:
            continue
        feats.append((nm, float(f.get("hit_rate", 0)), p["red"]))
    if feats:
        _spl_bars_horiz(d, ix, iy, iw, ih, feats[:7])
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "Calibrating signals…",
               font=_sf(11), fill=p["muted"], anchor="mm")


def _draw_spl_chart_row(d: ImageDraw.ImageDraw, img: Image.Image,
                         x: int, y: int, w: int, h: int,
                         buckets: dict, enriched: list[dict],
                         macro: dict | None, review: dict | None) -> None:
    """Bottom-of-canvas Splunk-style chart strip with 5 panels."""
    p   = _SPL_PAL
    GAP = 10
    pw  = (w - 4 * GAP) // 5

    # Panel 1: Top-pick sparklines (top 4 picks across same-day + swing)
    px = x
    ix, iy, iw, ih = _spl_panel_frame(d, px, y, pw, h,
                                       "📈  TOP PICKS — 30D PRICE TREND",
                                       p["accent"])
    picks: list[dict] = []
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or [])[:2]:
            if pk not in picks:
                picks.append(pk)
            if len(picks) >= 4:
                break
        if len(picks) >= 4:
            break
    if picks:
        row_h = ih // max(len(picks), 1)
        for i, pk in enumerate(picks):
            sym = pk["symbol"].replace(".NS", "")
            tech = pk.get("tech") or {}
            series = tech.get("close_30d") or tech.get("history_close") or []
            if not series:
                # Synthesise a tiny series from key levels so the panel still renders
                lv = pk.get("levels") or {}
                series = [lv.get("sl", pk["price"] * 0.97),
                           pk["price"] * 0.99,
                           pk["price"],
                           lv.get("entry", pk["price"]),
                           lv.get("target", pk["price"] * 1.03)]
            chg = tech.get("chg_1d_pct", 0) or 0
            col = p["green"] if chg >= 0 else p["red"]
            ry  = iy + i * row_h
            # symbol label + current price + chg%
            d.text((ix, ry + 1), sym, font=_sf(10, True), fill=p["text"])
            d.text((ix + 70, ry + 2),
                   f"₹{pk['price']:,.0f}",
                   font=_sf(9), fill=p["muted"])
            d.text((ix + iw, ry + 2),
                   f"{chg:+.2f}%",
                   font=_sf(9, True), fill=col, anchor="ra")
            # sparkline
            _spl_sparkline(d, ix, ry + 16, iw, max(10, row_h - 20),
                            [float(v) for v in series[-30:]], col)
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No price history",
               font=_sf(11), fill=p["muted"], anchor="mm")

    # Panel 2: Sector breadth horizontal bars
    px += pw + GAP
    ix, iy, iw, ih = _spl_panel_frame(d, px, y, pw, h,
                                       "🏭  SECTOR BREADTH",
                                       p["green"])
    sec_map: dict[str, list[float]] = {}
    for e in enriched or []:
        sec = (e.get("sector")
               or (e.get("info") or {}).get("sector")
               or (e.get("fund") or {}).get("sector")
               or "Other")
        sec = str(sec).strip() or "Other"
        chg = (e.get("tech") or {}).get("chg_1d_pct")
        if chg is None:
            continue
        sec_map.setdefault(sec[:14], []).append(float(chg))
    if sec_map:
        sec_items: list[tuple[str, float, tuple]] = []
        for sec, vals in sec_map.items():
            adv_pct = sum(1 for v in vals if v > 0.2) / len(vals) * 100
            col = (p["green"] if adv_pct >= 60
                   else p["red"] if adv_pct <= 40 else p["amber"])
            sec_items.append((sec, adv_pct, col))
        sec_items.sort(key=lambda t: t[1], reverse=True)
        max_rows = max(3, ih // 16)
        rendered = sec_items[:max_rows]
        if rendered:
            top_label = rendered[0][0]
            rendered = [(lbl, val, col, lbl == top_label)
                        for (lbl, val, col) in rendered]
        _spl_bars_horiz(d, ix, iy, iw, ih, rendered)
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No sector data",
               font=_sf(11), fill=p["muted"], anchor="mm")

    # Panel 3: Risk vs Reward scatter
    px += pw + GAP
    ix, iy, iw, ih = _spl_panel_frame(d, px, y, pw, h,
                                       "⚖️  RISK vs REWARD",
                                       p["accent2"], subtitle="all picks")
    sc_pts = []
    bucket_color = {"intraday": p["accent"], "swing": p["green"],
                    "holding":  p["accent2"], "sell": p["red"]}
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or [])[:6]:
            lv  = pk.get("levels") or {}
            ent = lv.get("entry"); sl = lv.get("sl"); tg = lv.get("target")
            if not (ent and sl and tg):
                continue
            risk_pct   = abs((ent - sl) / ent * 100) if ent else 0
            reward_pct = (tg - ent) / ent * 100 if ent else 0
            sym = pk["symbol"].replace(".NS", "")
            sc_pts.append((risk_pct, reward_pct, bucket_color[k], sym))
    if sc_pts:
        _spl_scatter(d, ix, iy, iw, ih, sc_pts,
                      x_label="Risk %", y_label="Reward %")
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No predictions",
               font=_sf(11), fill=p["muted"], anchor="mm")

    # Panel 4: Confidence histogram (vertical bars)
    px += pw + GAP
    ix, iy, iw, ih = _spl_panel_frame(d, px, y, pw, h,
                                       "🎯  PREDICTION CONFIDENCE",
                                       p["amber"])
    bins = [0, 0, 0, 0, 0]   # 50-60, 60-70, 70-80, 80-90, 90-100
    labels = ["50-60", "60-70", "70-80", "80-90", "90+"]
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or []):
            pr = pk.get("predict")
            if not pr:
                continue
            c = int(pr.get("confidence", 0))
            if   c < 60: bins[0] += 1
            elif c < 70: bins[1] += 1
            elif c < 80: bins[2] += 1
            elif c < 90: bins[3] += 1
            else:        bins[4] += 1
    bin_colors = [p["muted"], p["amber"], p["amber"], p["green"], p["green"]]
    bar_items  = [(labels[i], bins[i], bin_colors[i]) for i in range(5)]
    if any(bins):
        _spl_bars_vert(d, ix, iy, iw, ih, bar_items)
    else:
        d.text((ix + iw // 2, iy + ih // 2),
               "No predictions yet",
               font=_sf(11), fill=p["muted"], anchor="mm")

    # Panel 5: Hit-rate / model accuracy donut + sub-stats
    px += pw + GAP
    ix, iy, iw, ih = _spl_panel_frame(d, px, y, pw, h,
                                       "🧠  MODEL ACCURACY",
                                       p["accent2"])
    acc = (review or {}).get("overall_accuracy") or 0
    ps  = (review or {}).get("picks_scored", 0)
    pw_ = (review or {}).get("picks_won", 0)
    nf  = (review or {}).get("n_features", 0)
    # Reserve bottom strip for macro heatmap if we have data
    has_macro = bool((macro or {}).get("snapshot"))
    heat_h    = 56 if has_macro else 0
    top_h     = ih - heat_h - (4 if has_macro else 0)
    # Donut centred in left half of top area
    donut_size = min(top_h - 28, iw // 2 - 12, 120)
    donut_size = max(70, donut_size)
    dx = ix + 2
    dy = iy + (top_h - donut_size) // 2 - 4
    col = (p["green"] if acc >= 60 else p["amber"] if acc >= 45 else p["red"])
    _spl_donut(d, dx, dy, donut_size, acc, col,
                center_text=f"{acc:.0f}%" if acc else "—",
                label="")
    # Right side stats — vertically centred next to donut
    sx = ix + donut_size + 12
    avail_w = iw - donut_size - 12
    sy = iy + max(0, (top_h - 76) // 2)
    d.text((sx, sy),       f"{pw_}/{ps}",
           font=_sf(16, True), fill=p["text"])
    d.text((sx, sy + 22),  "hit target so far",
           font=_sf(8), fill=p["muted"])
    d.text((sx, sy + 44),  f"{nf}",
           font=_sf(16, True), fill=p["accent"])
    d.text((sx, sy + 66),  "signals used by model",
           font=_sf(8), fill=p["muted"])
    # tiny sector sentiment heatmap below the donut row if we have room
    if has_macro:
        snap = macro["snapshot"]
        cells = []
        for k, lbl in [("NIFTY", "Nifty"), ("SPY", "S&P"),
                       ("VIX", "VIX"), ("OIL", "Oil"),
                       ("GOLD", "Gold"), ("INR", "INR")]:
            vd = snap.get(k) or {}
            v = vd.get("chg_pct") or vd.get("last") or 0
            cells.append((lbl, float(v)))
        if cells:
            _spl_heatcells(d, ix, iy + top_h + 4, iw, heat_h - 4, cells)


# ── Main image renderer ───────────────────────────────────────────────────────

def build_report_image(buckets: dict, mfs: list[dict], prior: dict, out_path: str | None = None,
                        theme: str | None = None, macro: dict | None = None,
                        enriched: list[dict] | None = None,
                        market_forecast: dict | None = None,
                        review: dict | None = None,
                        angel_holdings: list[dict] | None = None,
                        angel_funds: dict | None = None) -> str:
    out_path = out_path or IMAGE_OUTPUT_PATH
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # Resolve theme → swap module-level palette so all helpers pick it up.
    chosen = (theme or IMAGE_THEME or "light").lower()
    _SPL_PAL.clear()
    _SPL_PAL.update(_SPL_PAL_LIGHT if chosen == "light" else _SPL_PAL_DARK)

    p  = _SPL_PAL          # active Splunk palette (light or dark)
    W, H = 1920, 1280      # canvas: header + KPIs + body + chart row + footer
    img  = Image.new("RGB", (W, H), p["bg"])
    d    = ImageDraw.Draw(img)
    M    = 14              # side margin
    GAP  = 10              # gap between panels

    # ── Header bar ─────────────────────────────────────────────────────────
    # gradient fill
    _gradient_rect(img, 0, 0, W, 62, (12, 16, 34), (8, 11, 22), radius=0)
    d.rectangle([(0, 60), (W, 62)], fill=p["accent"])          # accent underline
    d.text((M + 10, 12), "📊  Indian Market Intelligence",
           font=_sf(20, True), fill=p["text"])
    d.text((M + 10, 38), "Daily Report  ·  Stocks  ·  Mutual Funds  ·  Forecast",
           font=_sf(11), fill=p["muted"])
    ts = datetime.now().strftime("%A, %d %b %Y  ·  %H:%M IST")
    d.text((W - M - 10, 14), ts,
           font=_sf(11), fill=p["muted"], anchor="ra")
    session_tag = os.environ.get("STOCK_SESSION", "morning").upper()
    d.text((W - M - 10, 36), f"Session: {session_tag}",
           font=_sf(10, True), fill=p["accent"], anchor="ra")

    # ── KPI strip ──────────────────────────────────────────────────────────
    KPI_Y, KPI_H = 70, 116
    N_KPI   = 8
    KPI_GAP = 10
    kpi_w   = (W - 2 * M - (N_KPI - 1) * KPI_GAP) // N_KPI  # ≈226 px

    # compute values
    adv = dec = flat = total = 0
    for e in enriched or []:
        v = (e.get("tech") or {}).get("chg_1d_pct")
        if v is None:
            continue
        total += 1
        if v > 0.2:    adv  += 1
        elif v < -0.2: dec  += 1
        else:          flat += 1

    regime  = ((macro or {}).get("regime") or "neutral").upper()
    snap    = (macro or {}).get("snapshot") or {}
    opening = (macro or {}).get("opening") or {}

    top_pick: tuple | None = None
    for key in ("intraday", "swing", "holding"):
        for pk in (buckets.get(key) or []):
            pp = float((pk.get("levels") or {}).get("expected_profit_pct") or 0)
            if top_pick is None or pp > top_pick[1]:
                top_pick = (pk, pp)

    regime_c = {"RISK-ON": p["green"], "BULLISH": p["green"],
                "RISK-OFF": p["red"],  "BEARISH": p["red"]}.get(regime, p["amber"])
    bread_pct = adv / total * 100 if total else 0
    bread_c   = (p["green"] if bread_pct >= 55
                 else p["red"] if bread_pct <= 45 else p["amber"])

    mf_dir    = (market_forecast or {}).get("direction", "—")
    mf_conf   = (market_forecast or {}).get("confidence", 0)
    mf_c      = {"UP": p["green"], "DOWN": p["red"]}.get(mf_dir, p["amber"])

    vix_d  = snap.get("VIX") or {}
    vix_v  = vix_d.get("last", 0) or 0
    vix_c  = (p["red"] if vix_v > 25 else p["amber"] if vix_v > 18 else p["green"])

    gold_d = snap.get("GOLD") or {}
    gold_v = gold_d.get("chg_pct") or 0
    gold_c = p["green"] if gold_v >= 0 else p["red"]

    nifty_d = snap.get("NIFTY") or {}
    nifty_v = nifty_d.get("chg_pct") or 0
    nifty_c = p["green"] if nifty_v >= 0 else p["red"]

    bnifty_d = snap.get("BANKNIFTY") or {}
    bnifty_v = bnifty_d.get("chg_pct") or 0
    bnifty_c = p["green"] if bnifty_v >= 0 else p["red"]

    sensex_d = snap.get("SENSEX") or {}
    sensex_v = sensex_d.get("chg_pct") or 0
    sensex_c = p["green"] if sensex_v >= 0 else p["red"]

    acc     = (review or {}).get("overall_accuracy")
    acc_c   = (p["green"] if (acc or 0) >= 55
               else p["red"] if (acc or 0) < 45 else p["amber"])

    best_sym    = top_pick[0]["symbol"].replace(".NS", "") if top_pick else "—"
    best_profit = f"{top_pick[1]:+.1f}%" if top_pick else "—"
    profit_c    = ((p["green"] if top_pick[1] >= 0 else p["red"])
                   if top_pick else p["muted"])

    # Indian indices headline the KPI strip — VIX/Gold drop into the new
    # full-width Indian Indices ribbon below.
    kpi_data = [
        ("MARKET REGIME",   regime[:10],            "",                     regime_c),
        ("NIFTY 50",        f"{nifty_v:+.2f}%" if nifty_v else "—",
                                                    f"₹{nifty_d.get('last',0):,.0f}" if nifty_d.get("last") else "last session",
                                                                            nifty_c),
        ("BANK NIFTY",      f"{bnifty_v:+.2f}%" if bnifty_v else "—",
                                                    f"₹{bnifty_d.get('last',0):,.0f}" if bnifty_d.get("last") else "last session",
                                                                            bnifty_c),
        ("SENSEX",          f"{sensex_v:+.2f}%" if sensex_v else "—",
                                                    f"₹{sensex_d.get('last',0):,.0f}" if sensex_d.get("last") else "last session",
                                                                            sensex_c),
        ("BREADTH",         f"{bread_pct:.0f}%",    f"{adv}/{total} adv",   bread_c),
        ("BEST PICK",       best_sym,               best_profit,            profit_c),
        ("5-DAY FORECAST",  mf_dir[:8],             f"{mf_conf}% conf",     mf_c),
        ("MODEL ACCURACY",  f"{acc:.1f}%" if acc else "—",
                                                    f"{(review or {}).get('picks_scored',0)} picks",
                                                                            acc_c),
    ]
    for i, (lbl, val, sub, col) in enumerate(kpi_data):
        kx = M + i * (kpi_w + KPI_GAP)
        _kpi_tile(d, kx, KPI_Y, kpi_w, KPI_H, lbl, val, sub, col)

    # ── Indian Indices ribbon (broad-market + sectors + global cues) ──────
    # Drawn as a compact horizontal strip below the KPI tiles. Shows every
    # available index with today's % move so a trader can scan market
    # internals at a glance without searching for them on a broker app.
    RIB_Y = KPI_Y + KPI_H + 6
    RIB_H = 36
    d.rounded_rectangle([(M, RIB_Y), (W - M, RIB_Y + RIB_H)],
                        radius=6, fill=p["panel"], outline=p["border"])
    d.rounded_rectangle([(M, RIB_Y + 4), (M + 4, RIB_Y + RIB_H - 4)],
                        radius=2, fill=p["accent"])
    d.text((M + 12, RIB_Y + RIB_H // 2), "🇮🇳 INDIAN INDICES",
           font=_sf(10, True), fill=p["accent"], anchor="lm")

    # Compact tickers in priority order. VIX gets a 🛡 prefix, sectors get a
    # subtle muted label so broad-market indices stand out visually.
    ribbon_items: list[tuple[str, str, bool]] = [
        # (snap_key, display_label, is_sector)
        ("NIFTY",          "Nifty50",   False),
        ("BANKNIFTY",      "BankNifty", False),
        ("SENSEX",         "Sensex",    False),
        ("NIFTY100",       "Nifty100",  False),
        ("NIFTY200",       "Nifty200",  False),
        ("NIFTY500",       "Nifty500",  False),
        ("NIFTY_MIDCAP",   "Midcap",    False),
        ("NIFTY_SMALLCAP", "Smallcap",  False),
        ("FINNIFTY",       "FinNifty",  True),
        ("NIFTY_IT",       "IT",        True),
        ("NIFTY_AUTO",     "Auto",      True),
        ("NIFTY_PHARMA",   "Pharma",    True),
        ("NIFTY_FMCG",     "FMCG",      True),
        ("NIFTY_ENERGY",   "Energy",    True),
        ("NIFTY_METAL",    "Metal",     True),
        ("NIFTY_REALTY",   "Realty",    True),
        ("INDIA_VIX",      "🛡 IndVIX", False),
    ]
    # Filter to only those that actually returned data
    avail = [(k, lbl, sec) for (k, lbl, sec) in ribbon_items
             if (snap.get(k) or {}).get("chg_pct") is not None]

    rx_pos = M + 150        # leave room for the title
    rx_end = W - M - 8
    rib_w  = rx_end - rx_pos
    if avail:
        cell_w = max(70, rib_w // len(avail))
        for k, lbl, _is_sec in avail:
            vd = snap.get(k) or {}
            v  = vd.get("chg_pct") or 0
            col = (p["green"] if v > 0.05
                    else p["red"] if v < -0.05 else p["muted"])
            cy_r = RIB_Y + RIB_H // 2
            # label
            d.text((rx_pos, cy_r - 6), lbl[:9],
                   font=_sf(9, True), fill=p["muted"], anchor="lm")
            # value
            d.text((rx_pos, cy_r + 7), f"{v:+.2f}%",
                   font=_sf(10, True), fill=col, anchor="lm")
            rx_pos += cell_w
            if rx_pos > rx_end - cell_w + 20:
                break
    else:
        d.text((M + 160, RIB_Y + RIB_H // 2),
               "Indian indices unavailable (Yahoo throttled?)",
               font=_sf(9), fill=p["muted"], anchor="lm")

    # ── Institutional flows + index PCR ribbon (NSE direct, free) ─────────
    # Shows FII/DII net cash-market activity (₹ crore) + Nifty/BankNifty
    # PCR(OI) + max-pain. These are the most-watched intraday signals on
    # Dalal Street and are leading indicators for the broader index move.
    flows   = (macro or {}).get("flows") or {}
    pcr_idx = (macro or {}).get("pcr_index") or {}
    has_flows = flows.get("available")
    has_pcr   = bool(pcr_idx)
    has_angel = bool(angel_holdings) or bool(angel_funds)
    FLOW_Y = RIB_Y + RIB_H + 4
    FLOW_H = 30
    if has_flows or has_pcr or has_angel:
        d.rounded_rectangle([(M, FLOW_Y), (W - M, FLOW_Y + FLOW_H)],
                            radius=6, fill=p["panel"], outline=p["border"])
        d.rounded_rectangle([(M, FLOW_Y + 4), (M + 4, FLOW_Y + FLOW_H - 4)],
                            radius=2, fill=p["amber"] if has_flows else p["accent"])
        d.text((M + 12, FLOW_Y + FLOW_H // 2), "💸 INSTITUTIONAL",
               font=_sf(10, True), fill=p["amber"], anchor="lm")

        cy_f = FLOW_Y + FLOW_H // 2
        fx = M + 130

        if has_flows:
            fii = float(flows.get("fii_net") or 0)
            dii = float(flows.get("dii_net") or 0)
            verdict = flows.get("verdict") or "NEUTRAL"
            fii_col = (p["green"] if fii > 0 else p["red"] if fii < 0 else p["muted"])
            dii_col = (p["green"] if dii > 0 else p["red"] if dii < 0 else p["muted"])
            ver_col = (p["green"] if "BUY"  in verdict
                       else p["red"]  if "SELL" in verdict
                       else p["muted"])
            d.text((fx, cy_f), f"FII  ", font=_sf(10, True), fill=p["muted"], anchor="lm")
            d.text((fx + 28, cy_f), f"₹{fii:+,.0f}cr",
                   font=_sf(11, True), fill=fii_col, anchor="lm")
            fx += 150
            d.text((fx, cy_f), f"DII  ", font=_sf(10, True), fill=p["muted"], anchor="lm")
            d.text((fx + 28, cy_f), f"₹{dii:+,.0f}cr",
                   font=_sf(11, True), fill=dii_col, anchor="lm")
            fx += 150
            d.text((fx, cy_f), verdict,
                   font=_sf(10, True), fill=ver_col, anchor="lm")
            fx += 130

        # PCR + max-pain summary for indices
        for sym in ("NIFTY", "BANKNIFTY"):
            oc = pcr_idx.get(sym) or {}
            if not oc:
                continue
            pcr = oc.get("pcr") or 0
            mp  = oc.get("max_pain") or 0
            spot = oc.get("spot") or 0
            bias = oc.get("bias") or "NEUTRAL"
            bcol = (p["green"] if "BULL" in bias
                    else p["red"]  if "BEAR" in bias
                    else p["muted"])
            label = "Nifty" if sym == "NIFTY" else "BkNifty"
            txt = f"{label} PCR {pcr:.2f}  MP {mp:,.0f}"
            if spot:
                drift = (mp - spot) / spot * 100
                txt += f" ({drift:+.1f}%)"
            d.text((fx, cy_f), txt,
                   font=_sf(10, True), fill=bcol, anchor="lm")
            fx += 240
            if fx > W - M - 30:
                break

        # ── Angel One portfolio chip (right-aligned when present) ─────────
        if has_angel and fx < W - M - 220:
            cash = float((angel_funds or {}).get("available_cash") or 0)
            holds = angel_holdings or []
            total_pnl = sum(float(h.get("pnl") or 0) for h in holds)
            total_val = sum(float(h.get("value") or 0) for h in holds)
            pnl_col = (p["green"] if total_pnl > 0
                       else p["red"] if total_pnl < 0 else p["muted"])
            chip = (f"💼 {len(holds)} holdings  ₹{total_val/1e5:,.1f}L  "
                    f"P&L ₹{total_pnl:+,.0f}   💰 ₹{cash/1e3:,.0f}k cash")
            d.text((W - M - 12, cy_f), chip,
                   font=_sf(10, True), fill=pnl_col, anchor="rm")

    # ── Chart collage (top, just below ribbons) ────────────────────────────
    CHART_H = 326 - (FLOW_H + 4 if (has_flows or has_pcr or has_angel) else 0)
    CHART_Y = (FLOW_Y + FLOW_H + 8) if (has_flows or has_pcr or has_angel) else (RIB_Y + RIB_H + 8)
    _draw_spl_chart_collage(d, img, M, CHART_Y, W - 2 * M, CHART_H,
                              buckets, enriched or [], macro, review)

    # ── Body layout (below chart collage) ──────────────────────────────────
    BY  = CHART_Y + CHART_H + 10        # body starts after collage
    BH  = H - BY - 28 - 8               # leave footer (28) + bottom margin

    C1_W = 578
    C2_W = 618
    C3_W = W - 2 * M - C1_W - C2_W - 2 * GAP   # ≈ 668
    C1_X = M
    C2_X = C1_X + C1_W + GAP
    C3_X = C2_X + C2_W + GAP

    # shared stock table config — expanded with SL, R:R, Conf for full trade detail
    s_hdrs = ["Symbol", "Price", "Today", "Buy", "SL",
              "Target", "Profit", "R:R", "Conf", "Hold"]
    s_wts  = [1.4,      1.1,     0.85,    1.1,   1.1,
              1.1,      0.95,    0.7,     0.7,   0.85]

    def _rows_for(picks: list[dict], rank_by_profit: bool = True) -> list[list]:
        # Sort by expected profit descending so the most lucrative trades
        # surface at the top of every bucket table.
        if rank_by_profit:
            picks = sorted(
                picks,
                key=lambda x: float((x.get("levels") or {})
                                    .get("expected_profit_pct") or 0),
                reverse=True)
        out: list[list] = []
        for pk in picks:
            t  = pk["tech"]
            lv = pk["levels"]
            sym  = pk["symbol"].replace(".NS", "")
            ent  = float(lv.get("entry") or 0)
            sl   = float(lv.get("sl") or 0)
            tg   = float(lv.get("target") or 0)
            pp   = float(lv.get("expected_profit_pct") or 0)
            risk = abs((ent - sl) / ent * 100) if ent else 0
            rwd  = (tg - ent) / ent * 100 if ent else 0
            rr   = (rwd / risk) if risk > 0.01 else 0
            rr_color = ("green" if rr >= 2.0
                         else "amber" if rr >= 1.0 else "red")
            pred = pk.get("predict") or {}
            conf = int(pred.get("confidence", 0))
            conf_color = ("green" if conf >= 70
                          else "amber" if conf >= 55 else "muted")
            hold = lv.get("est_hold_days") or 0
            hold_tag = ("today" if hold == 0
                        else "1y+" if hold >= 252
                        else f"{hold}d")
            out.append([
                sym,
                _fmt_num(pk["price"]),
                (_fmt_pct(t["chg_1d_pct"]),
                 "green" if t["chg_1d_pct"] >= 0 else "red"),
                _fmt_num(ent),
                (_fmt_num(sl), "red"),
                (_fmt_num(tg), "green"),
                (f"{pp:+.1f}%", "green" if pp >= 0 else "red"),
                (f"{rr:.1f}", rr_color) if rr > 0 else ("—", "muted"),
                (f"{conf}%" if conf else "—", conf_color),
                (hold_tag, "muted"),
            ])
        return out

    # ── Column 1: Intraday + Swing + Position Sizing ──────────────────────
    cy1  = BY
    h1a  = _spl_table(d, C1_X, cy1, C1_W, (BH - GAP) // 2,
                      "🔥  SAME-DAY TRADES",
                      s_hdrs, _rows_for(buckets.get("intraday", [])),
                      s_wts, p["accent"])
    cy1 += h1a + GAP
    h1b  = _spl_table(d, C1_X, cy1, C1_W, (BH - h1a - GAP) // 2,
                      "📈  SHORT-TERM SWINGS",
                      s_hdrs, _rows_for(buckets.get("swing", [])),
                      s_wts, p["green"])
    cy1 += h1b + GAP

    # Position Sizing helper — fills the empty space below the swing table.
    # Tells the trader exactly how many shares to buy if they risk 1% of a
    # ₹1,00,000 portfolio per trade. Reads CAPITAL / RISK_PCT from env so the
    # user can tune them with STOCK_CAPITAL / STOCK_RISK_PCT.
    try:
        capital  = float(os.environ.get("STOCK_CAPITAL", "100000"))
    except ValueError:
        capital  = 100000.0
    try:
        risk_pct = float(os.environ.get("STOCK_RISK_PCT", "1.0"))
    except ValueError:
        risk_pct = 1.0
    risk_budget = capital * risk_pct / 100.0

    ps_hdrs = ["Symbol", "Entry", "SL", "Shares", "Cost ₹", "Risk ₹", "Reward ₹"]
    ps_wts  = [1.3, 1.1, 1.1, 0.9, 1.4, 1.1, 1.2]
    ps_rows: list[list] = []
    seen_syms: set[str] = set()
    for k in ("intraday", "swing", "holding"):
        for pk in (buckets.get(k) or []):
            sym = pk["symbol"].replace(".NS", "")
            if sym in seen_syms:
                continue
            lv  = pk.get("levels") or {}
            ent = float(lv.get("entry") or 0)
            sl  = float(lv.get("sl") or 0)
            tg  = float(lv.get("target") or 0)
            if ent <= 0 or sl <= 0 or abs(ent - sl) < 0.01:
                continue
            per_share_risk = abs(ent - sl)
            shares = int(risk_budget / per_share_risk) if per_share_risk else 0
            if shares <= 0:
                continue
            cost     = shares * ent
            risk_amt = shares * per_share_risk
            reward   = shares * abs(tg - ent) if tg else 0
            ps_rows.append([
                sym,
                _fmt_num(ent),
                (_fmt_num(sl), "red"),
                str(shares),
                f"₹{cost:,.0f}",
                (f"₹{risk_amt:,.0f}", "red"),
                (f"₹{reward:,.0f}", "green"),
            ])
            seen_syms.add(sym)
            if len(ps_rows) >= 6:
                break
        if len(ps_rows) >= 6:
            break

    if ps_rows and BY + BH - cy1 >= 80:
        cap_lakh = capital / 100000.0
        ps_subtitle = (f"📐  POSITION SIZING  ·  ₹{cap_lakh:.1f}L capital  ·  "
                        f"{risk_pct:.1f}% risk/trade  =  ₹{risk_budget:,.0f} max loss")
        _spl_table(d, C1_X, cy1, C1_W, BY + BH - cy1,
                   ps_subtitle,
                   ps_hdrs, ps_rows, ps_wts, p["amber"])

    # ── Column 2: Holding + Sell + MF + Prior ─────────────────────────────
    cy2 = BY
    h2a = _spl_table(d, C2_X, cy2, C2_W, int(BH * 0.30),
                     "🏦  LONG-TERM HOLDS",
                     s_hdrs, _rows_for(buckets.get("holding", [])),
                     s_wts, p["accent2"])
    cy2 += h2a + GAP

    h2b = _spl_table(d, C2_X, cy2, C2_W, int(BH * 0.22),
                     "⚠️  AVOID / SELL",
                     s_hdrs, _rows_for(buckets.get("sell", [])),
                     s_wts, p["red"])
    cy2 += h2b + GAP

    mf_hdrs = ["Fund", "Cat", "NAV", "1M", "1Y", "Score"]
    mf_wts  = [3.0, 1.4, 1.0, 0.8, 0.8, 0.8]
    mf_rows: list[list] = []
    for m in mfs:
        mf_rows.append([
            m["name"][:30],
            (m["cat"][:14], "muted"),
            _fmt_num(m["nav"], 2),
            (_fmt_pct(m["r_1m"]), "green" if (m["r_1m"] or 0) >= 0 else "red"),
            (_fmt_pct(m["r_1y"]), "green" if (m["r_1y"] or 0) >= 0 else "red"),
            f"{m['score']:+.1f}",
        ])
    remaining2 = BH - h2a - GAP - h2b - GAP
    prior_h    = 120 if prior.get("available") else 0
    h2c = _spl_table(d, C2_X, cy2, C2_W, remaining2 - GAP - prior_h,
                     "💰  TOP MUTUAL FUNDS",
                     mf_hdrs, mf_rows or [["—"] * 6],
                     mf_wts, p["amber"])
    cy2 += h2c + GAP

    if prior.get("available"):
        ph_hdrs = ["Category", "Picks", "Wins", "Hit Rate"]
        ph_wts  = [1.8, 0.8, 0.7, 1.0]
        ph_rows: list[list] = []
        for b in ("intraday", "swing", "holding", "sell"):
            info = prior["buckets"].get(b, {})
            hr   = info.get("hit_rate")
            ph_rows.append([
                b.capitalize(),
                str(info.get("count", 0)),
                str(info.get("wins", 0)),
                (f"{hr:.0f}%" if hr is not None else "—",
                 "green" if (hr or 0) >= 60
                 else "red" if (hr or 0) < 40 and hr is not None
                 else "muted"),
            ])
        h2d = _spl_table(d, C2_X, cy2, C2_W, BY + BH - cy2,
                         "🧾  PAST PERFORMANCE",
                         ph_hdrs, ph_rows, ph_wts, p["muted"])
        cy2 += h2d + GAP

    # Trader's Cheat Sheet — fills any leftover space in column 2 with
    # actionable plain-English rules tuned to today's regime/breadth/forecast.
    cs_remaining = BY + BH - cy2
    if cs_remaining >= 90:
        CS_H = min(cs_remaining, 220)
        d.rounded_rectangle([(C2_X, cy2), (C2_X + C2_W, cy2 + CS_H)],
                            radius=6, fill=p["panel"], outline=p["border"])
        d.rounded_rectangle([(C2_X, cy2 + 4), (C2_X + 4, cy2 + CS_H - 4)],
                            radius=2, fill=p["accent"])
        d.text((C2_X + 14, cy2 + 8),
               "📋  TRADER'S CHEAT SHEET",
               font=_sf(12, True), fill=p["accent"])
        d.text((C2_X + C2_W - 14, cy2 + 10),
               "rules for today",
               font=_sf(9), fill=p["muted"], anchor="ra")

        # Build today-aware rule lines
        regime_up = "RISK-ON" in str(regime).upper()
        regime_dn = "RISK-OFF" in str(regime).upper()
        bread_strong = bread_pct >= 60 if total else False
        bread_weak   = bread_pct <= 40 if total else False
        mf_up = (mf_dir == "UP")
        mf_dn = (mf_dir == "DOWN")

        cs_lines: list[tuple[str, tuple]] = []

        # 1. Bias
        if regime_up and bread_strong and mf_up:
            cs_lines.append(("✅ Bias: AGGRESSIVE BUY  ·  trend, breadth & forecast all aligned bullish",
                              p["green"]))
        elif regime_dn or bread_weak or mf_dn:
            cs_lines.append(("⚠ Bias: DEFENSIVE  ·  reduce size, prefer cash & quality holds only",
                              p["red"]))
        else:
            cs_lines.append(("➖ Bias: SELECTIVE  ·  trade only A-grade setups, smaller size",
                              p["amber"]))

        # 2. Entry rule
        cs_lines.append(("🎯 Entry: wait for price to touch 'Buy' level OR break above with volume > 1.3x avg",
                         p["text"]))
        # 3. Stop loss
        cs_lines.append(("🛡 Stop-loss: NEVER skip the SL. Exit immediately if price closes below it.",
                         p["red"]))
        # 4. Profit target
        cs_lines.append(("💰 Target: book 50% at first target. Trail SL to entry on the rest.",
                         p["green"]))
        # 5. Risk per trade
        cs_lines.append((f"📐 Risk: max {risk_pct:.0f}% of capital per trade  ·  see Position Sizing card →",
                         p["amber"]))
        # 6. Position count
        if regime_up:
            cs_lines.append(("🧺 Hold max 4-5 positions today  ·  diversify across 3+ sectors",
                             p["muted"]))
        else:
            cs_lines.append(("🧺 Hold max 2-3 positions today  ·  keep 50%+ in cash",
                             p["muted"]))

        for i, (txt, col) in enumerate(cs_lines):
            yy = cy2 + 32 + i * 18
            if yy + 14 > cy2 + CS_H - 4:
                break
            d.text((C2_X + 14, yy), txt, font=_sf(10), fill=col)

        cy2 += CS_H + GAP

    # ── Column 3: Overview + Forecast + Predictions + Self-review ──────────
    cy3 = BY

    # Market Overview card
    ES_H = 158
    d.rounded_rectangle([(C3_X, cy3), (C3_X + C3_W, cy3 + ES_H)],
                        radius=6, fill=p["panel"], outline=p["border"])
    d.rounded_rectangle([(C3_X, cy3 + 4), (C3_X + 4, cy3 + ES_H - 4)],
                        radius=2, fill=p["accent"])
    d.text((C3_X + 14, cy3 + 8), "⚡  MARKET OVERVIEW",
           font=_sf(12, True), fill=p["accent"])

    d.text((C3_X + 14, cy3 + 36), f"Regime: {regime}",
           font=_sf(13, True), fill=regime_c)
    if total:
        d.text((C3_X + 220, cy3 + 36),
               f"Breadth: {bread_pct:.0f}%  ({adv}↑  {dec}↓  {flat}→)",
               font=_sf(13), fill=bread_c)

    if opening.get("direction"):
        od   = opening["direction"]
        oc   = (p["green"] if "UP" in od
                else p["red"] if "DOWN" in od else p["muted"])
        arw  = "↑" if "UP" in od else ("↓" if "DOWN" in od else "→")
        d.text((C3_X + 14, cy3 + 64),
               f"Opening 09:15:  {arw} {od}  {opening.get('gap_pct','')}  "
               f"{opening.get('confidence', 0)}% conf",
               font=_sf(12), fill=oc)

    if top_pick:
        pk, pp = top_pick
        sym = pk["symbol"].replace(".NS", "")
        lv  = pk["levels"]
        pc  = p["green"] if pp >= 0 else p["red"]
        d.text((C3_X + 14, cy3 + 96),
               f"Top Pick:  {sym}   ₹{lv['entry']:,.0f} → ₹{lv['target']:,.0f}",
               font=_sf(13, True), fill=p["text"])
        d.text((C3_X + 14, cy3 + 120),
               f"Expected profit: {pp:+.2f}%     SL: ₹{lv['sl']:,.0f}",
               font=_sf(12), fill=pc)
    cy3 += ES_H + GAP

    # ── Top Profit Opportunities card (ranked top-5 across all BUY buckets) ─
    all_picks: list[tuple[dict, float, str]] = []
    for k_label, k_tag in [("intraday", "DAY"),
                           ("swing", "SWG"),
                           ("holding", "HLD")]:
        for pk in (buckets.get(k_label) or []):
            pp_v = float((pk.get("levels") or {})
                          .get("expected_profit_pct") or 0)
            if pp_v > 0:                       # only positive-profit BUY ideas
                all_picks.append((pk, pp_v, k_tag))
    all_picks.sort(key=lambda t: t[1], reverse=True)
    top5 = all_picks[:5]

    if top5 and cy3 < BY + BH - 80:
        TP_HDR = 30
        TP_RH  = 26
        TP_H   = TP_HDR + TP_RH * len(top5) + 8
        TP_H   = min(TP_H, BY + BH - cy3 - 8)
        d.rounded_rectangle([(C3_X, cy3), (C3_X + C3_W, cy3 + TP_H)],
                            radius=6, fill=p["panel"], outline=p["border"])
        d.rounded_rectangle([(C3_X, cy3 + 4), (C3_X + 4, cy3 + TP_H - 4)],
                            radius=2, fill=p["green"])
        d.text((C3_X + 14, cy3 + 8),
               "★  TOP PROFIT OPPORTUNITIES",
               font=_sf(12, True), fill=p["green"])
        d.text((C3_X + C3_W - 14, cy3 + 10),
               f"{len(top5)} of {len(all_picks)}",
               font=_sf(9), fill=p["muted"], anchor="ra")

        # Sub-column layout for each row
        col_x = [
            C3_X + 14,        # rank #
            C3_X + 36,        # symbol
            C3_X + 130,       # tag
            C3_X + 178,       # buy
            C3_X + 250,       # → target
            C3_X + 348,       # SL
            C3_X + 432,       # profit %
            C3_X + 528,       # R:R
            C3_X + 588,       # conf
        ]
        for i, (pk, pp_v, tag) in enumerate(top5):
            ry  = cy3 + TP_HDR + i * TP_RH
            if ry + TP_RH - 2 > cy3 + TP_H:
                break
            # alt row stripe
            if i % 2 == 0:
                d.rectangle([(C3_X + 6, ry),
                              (C3_X + C3_W - 6, ry + TP_RH - 2)],
                             fill=p["panel2"])
            sym = pk["symbol"].replace(".NS", "")
            lv  = pk.get("levels") or {}
            ent = float(lv.get("entry") or 0)
            sl  = float(lv.get("sl") or 0)
            tg  = float(lv.get("target") or 0)
            risk = abs((ent - sl) / ent * 100) if ent else 0
            rwd  = (tg - ent) / ent * 100 if ent else 0
            rr   = (rwd / risk) if risk > 0.01 else 0
            rr_c = (p["green"] if rr >= 2.0
                    else p["amber"] if rr >= 1.0 else p["red"])
            conf = int((pk.get("predict") or {}).get("confidence", 0))
            conf_c = (p["green"] if conf >= 70
                      else p["amber"] if conf >= 55 else p["muted"])
            tag_c = {"DAY": p["accent"],
                     "SWG": p["green"],
                     "HLD": p["accent2"]}.get(tag, p["muted"])
            tag_bg = {"DAY": p["panel2"],
                      "SWG": p["green_bg"],
                      "HLD": p["panel2"]}.get(tag, p["panel2"])

            cy_t = ry + TP_RH // 2
            d.text((col_x[0], cy_t), f"#{i + 1}",
                   font=_sf(10, True), fill=p["muted"], anchor="lm")
            d.text((col_x[1], cy_t), sym[:9],
                   font=_sf(11, True), fill=p["text"], anchor="lm")
            # tag chip
            d.rounded_rectangle(
                [(col_x[2] - 2, cy_t - 8), (col_x[2] + 38, cy_t + 8)],
                radius=4, fill=tag_bg)
            d.text((col_x[2] + 18, cy_t), tag,
                   font=_sf(9, True), fill=tag_c, anchor="mm")
            d.text((col_x[3], cy_t), f"₹{ent:,.0f}",
                   font=_sf(10), fill=p["text"], anchor="lm")
            d.text((col_x[4], cy_t), f"→ ₹{tg:,.0f}",
                   font=_sf(10, True), fill=p["green"], anchor="lm")
            d.text((col_x[5], cy_t), f"SL ₹{sl:,.0f}",
                   font=_sf(10), fill=p["red"], anchor="lm")
            d.text((col_x[6], cy_t), f"{pp_v:+.1f}%",
                   font=_sf(11, True), fill=p["green"], anchor="lm")
            d.text((col_x[7], cy_t), f"{rr:.1f}R",
                   font=_sf(10, True), fill=rr_c, anchor="lm")
            if conf:
                d.text((col_x[8], cy_t), f"{conf}%",
                       font=_sf(10, True), fill=conf_c, anchor="lm")
        cy3 += TP_H + GAP

    # Market forecast banner
    if market_forecast and cy3 < BY + BH - 60:
        mf_bg = ({"UP": p["green_bg"], "DOWN": p["red_bg"]}
                 .get(mf_dir, (18, 24, 42)))
        arw   = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→"}.get(mf_dir, "→")
        lo, hi = market_forecast["band_pct"]
        MF_H  = 70
        d.rounded_rectangle([(C3_X, cy3), (C3_X + C3_W, cy3 + MF_H)],
                            radius=6, fill=mf_bg, outline=p["border"])
        d.text((C3_X + 14, cy3 + 8), "🔮  NEXT 5-SESSION FORECAST",
               font=_sf(10, True), fill=p["muted"])
        d.text((C3_X + 14, cy3 + 30),
               f"{arw} {mf_dir}   ·   {mf_conf}% confidence   ·   band {lo:+.1f}% … {hi:+.1f}%",
               font=_sf(14, True), fill=mf_c)
        reasons = "  ·  ".join((market_forecast.get("reasons") or [])[:3])
        if reasons:
            d.text((C3_X + 14, cy3 + 54), reasons[:120],
                   font=_sf(9), fill=p["muted"])
        cy3 += MF_H + GAP

    # NOTE: An older "🎯 TODAY'S PREDICTIONS" table used to render here, but it
    # duplicates the data already shown in the "💎 TOP PROFIT OPPORTUNITIES"
    # card above (same picks, same buy/SL/target/profit/conf). Removed to free
    # vertical space for the Self-Review card and avoid an empty-looking panel.

    # Self-review card
    if review and cy3 < BY + BH - 80:
        acc_v  = review.get("overall_accuracy")
        ps     = review.get("picks_scored", 0)
        pw     = review.get("picks_won", 0)
        nf     = review.get("n_features", 0)
        best   = review.get("best_features") or []
        worst  = [w for w in (review.get("worst_features") or []) if w not in best]
        SR_H   = min(168, BY + BH - cy3 - 2)
        d.rounded_rectangle([(C3_X, cy3), (C3_X + C3_W, cy3 + SR_H)],
                            radius=6, fill=p["panel"], outline=p["border"])
        d.rounded_rectangle([(C3_X, cy3 + 4), (C3_X + 4, cy3 + SR_H - 4)],
                            radius=2, fill=p["accent2"])
        d.text((C3_X + 14, cy3 + 8), "🧠  MODEL SELF-REVIEW",
               font=_sf(12, True), fill=p["accent2"])
        acc_txt = f"{acc_v:.1f}%" if acc_v else "calibrating"
        acc_col = p["green"] if (acc_v or 0) >= 55 else p["amber"]
        d.text((C3_X + 14, cy3 + 34),
               f"Accuracy: {acc_txt}   {pw}/{ps} correct   {nf} signals tracked",
               font=_sf(12), fill=acc_col)
        if best and SR_H > 70:
            line = "  ·  ".join(
                f"{b['name']} {b.get('hit_rate', 0):.0f}%"
                for b in best[:4])
            d.text((C3_X + 14, cy3 + 62),
                   f"▲ Best signals:  {line}",
                   font=_sf(11), fill=p["green"])
        if worst and SR_H > 110:
            wline = "  ·  ".join(
                f"{b['name']} {b.get('hit_rate', 0):.0f}%"
                for b in worst[:3])
            d.text((C3_X + 14, cy3 + 88),
                   f"▼ Suppressed:  {wline}",
                   font=_sf(11), fill=p["muted"])

    # ── Footer bar ─────────────────────────────────────────────────────────
    d.rectangle([(0, H - 24), (W, H)], fill=p["header_bg"])
    d.line([(0, H - 24), (W, H - 24)], fill=p["border"], width=1)
    d.text((M + 10, H - 16), DISCLAIMER[:200], font=_sf(9), fill=p["muted"])
    d.text((W - M - 10, H - 16),
           f"© Generated {datetime.now().strftime('%d %b %Y · %H:%M')}",
           font=_sf(9), fill=p["muted"], anchor="ra")

    img.save(out_path)
    logger.info(f"Report image saved → {out_path}  [{W}×{H}]")
    return out_path


# ── Text summary (for WhatsApp/Telegram caption + console) ──────────────────

def build_text_summary(buckets: dict, mfs: list[dict], prior: dict,
                        macro: dict | None = None,
                        market_forecast: dict | None = None) -> str:
    """Compact, scannable caption (WhatsApp/Telegram + console).
    Target: < 60 lines so users can read on one screen."""
    lines: list[str] = []
    lines.append(f"📊 *Market Brief* — {datetime.now().strftime('%d %b %Y · %H:%M')}")

    # ── Macro one-liner ────────────────────────────────────────────────────
    if macro and macro.get("snapshot"):
        snap = macro["snapshot"]
        regime = macro.get("regime", "neutral").upper()
        bits: list[str] = [f"🌐 {regime}"]
        for k, label in [("SPY", "S&P"), ("NIFTY", "Nifty"),
                         ("VIX", "VIX"), ("OIL", "Oil"), ("GOLD", "Gold")]:
            v = snap.get(k)
            if not v:
                continue
            if k == "VIX":
                bits.append(f"{label} {v['last']:.0f}")
            else:
                bits.append(f"{label} {v['chg_pct']:+.1f}%")
        geo_lvl = (macro.get("geo") or {}).get("level", 50)
        if geo_lvl >= 65:
            bits.append("⚠️Geo risk HIGH")
        lines.append("  ·  ".join(bits))

    # ── Opening prediction (one line) ──────────────────────────────────────
    _session = (os.environ.get("STOCK_SESSION") or "").lower()
    opening = (macro or {}).get("opening") or {}
    if opening and _session in ("preopen", "", "morning"):
        arrow = {"GAP-UP": "🟢↑", "MILD GAP-UP": "🟢↗",
                 "GAP-DOWN": "🔴↓", "MILD GAP-DOWN": "🔴↘",
                 "FLAT OPEN": "⚪→"}.get(opening["direction"], "⚪")
        lines.append(
            f"🔮 *Open 09:15:* {arrow} {opening['direction']} "
            f"({opening['gap_pct']}, {opening['confidence']}% conf.)"
        )

    # ── Market-wide 5-session forecast ─────────────────────────────────────
    if market_forecast:
        mf = market_forecast
        arrow = {"UP": "↑", "DOWN": "↓", "SIDEWAYS": "→"}.get(mf["direction"], "→")
        lo, hi = mf["band_pct"]
        lines.append(
            f"🌍 *Market forecast (5 sessions):* {arrow} {mf['direction']} "
            f"· {mf['confidence']}% conf. · band {lo:+.1f}% … {hi:+.1f}%"
        )
    lines.append("")

    # ── Bucket picks — one line per pick, max 3 per bucket ────────────────
    labels = [("🔥 Same-Day (exit today)",          "intraday"),
              ("📈 Short-Term (2–15 days)",         "swing"),
              ("🏦 Long-Term (≥1 year)",            "holding"),
              ("⚠️ Avoid / Sell",                   "sell")]
    if _session == "preopen":
        labels = [("📈 *Swing Picks for Today*",    "swing"),
                  ("🔥 Same-Day (after 09:15)",     "intraday"),
                  ("🏦 Long-Term",                  "holding"),
                  ("⚠️ Avoid / Sell",               "sell")]

    dir_emoji = {"UP": "🟢", "DOWN": "🔴", "SIDEWAYS": "⚪"}
    for title, key in labels:
        picks = (buckets.get(key) or [])[:3]
        if not picks:
            continue
        lines.append(f"*{title}*")
        for p in picks:
            lv = p["levels"]
            pr = p.get("predict") or {}
            sym = p["symbol"].replace(".NS", "")
            hold = lv.get("est_hold_days") or 0
            hold_tag = ("intraday" if hold == 0
                        else "1y+" if hold >= 252
                        else f"{hold}d")
            conf_tag = f" · {dir_emoji.get(pr.get('direction'),'')}{pr.get('confidence','')}%" if pr else ""
            lines.append(
                f"• *{sym}*  ₹{lv['entry']:,.0f} → ₹{lv['target']:,.0f}  "
                f"(*{lv.get('expected_profit_pct', 0):+.1f}%*, "
                f"SL ₹{lv['sl']:,.0f}, {hold_tag}{conf_tag})"
            )
        lines.append("")

    # ── Mutual funds — top 3 one-liners ────────────────────────────────────
    if mfs:
        lines.append("*💰 Top Funds*")
        for m in mfs[:3]:
            lines.append(f"• {m['name'][:36]}  1Y {_fmt_pct(m['r_1y'])}")
        lines.append("")

    # ── Past picks — one-line summary ──────────────────────────────────────
    if prior.get("available"):
        parts = []
        for b in ("intraday", "swing", "holding", "sell"):
            info = prior["buckets"].get(b, {})
            hr = info.get("hit_rate")
            if hr is None:
                continue
            parts.append(f"{b[:4].capitalize()} {hr:.0f}%")
        if parts:
            lines.append(f"🧾 *Past hit-rate:* {' · '.join(parts)}")
            lines.append("")

    lines.append(f"_{DISCLAIMER}_")
    return "\n".join(lines)
