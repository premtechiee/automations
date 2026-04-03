"""
automations/gold_notifier/image.py
====================================
Advanced dashboard-style gold price image generator.
Features: candlestick chart, gradient fills, gauge glow, sparklines,
          segmented tech meters, forecast area chart.
Data keys are mapped exactly to what each source function returns.
"""

import logging
import math as _math
import os
from datetime import datetime

from .config import INDIA_GOLD_DUTY_FACTOR, IMAGE_OUTPUT_PATH, IMAGE_THEME

logger = logging.getLogger(__name__)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _h_gradient(draw, x0, y0, x1, y1, col_l, col_r, steps=80):
    sw = max(1, (x1 - x0) // steps)
    for i in range(steps):
        t = i / max(1, steps - 1)
        c = tuple(int(col_l[j] + (col_r[j] - col_l[j]) * t) for j in range(3))
        sx = x0 + i * sw
        draw.rectangle([(sx, y0), (min(sx + sw, x1), y1)], fill=c)


def _v_gradient(draw, x0, y0, x1, y1, col_t, col_b, steps=60):
    sh = max(1, (y1 - y0) // steps)
    for i in range(steps):
        t = i / max(1, steps - 1)
        c = tuple(int(col_t[j] + (col_b[j] - col_t[j]) * t) for j in range(3))
        sy = y0 + i * sh
        draw.rectangle([(x0, sy), (x1, min(sy + sh, y1))], fill=c)


def _rounded_rect(draw, x0, y0, x1, y1, fill, radius=8):
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=fill)


def _shadow_rect(draw, x0, y0, x1, y1, fill, radius=8, soff=3, scol=None):
    if scol is None:
        scol = tuple(max(0, c - 28) for c in fill)
    draw.rounded_rectangle([(x0+soff, y0+soff), (x1+soff, y1+soff)], radius=radius, fill=scol)
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=fill)


def _sparkline(draw, x0, y0, x1, y1, values, col_up, col_dn, bg=None):
    """Draw a tiny sparkline chart inside the given bbox."""
    if not values or len(values) < 2:
        return
    if bg:
        draw.rectangle([(x0, y0), (x1, y1)], fill=bg)
    mn, mx = min(values), max(values)
    rng = max(mx - mn, 1)
    n = len(values)
    def _sx(i): return int(x0 + i * (x1 - x0) / max(1, n - 1))
    def _sy(v): return int(y1 - (v - mn) / rng * (y1 - y0))
    pts = [(_sx(i), _sy(v)) for i, v in enumerate(values)]
    col = col_up if values[-1] >= values[0] else col_dn
    if len(pts) >= 2:
        draw.line(pts, fill=col, width=2)
    # end dot
    draw.ellipse([(pts[-1][0]-3, pts[-1][1]-3), (pts[-1][0]+3, pts[-1][1]+3)], fill=col)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_price_image(
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
    theme: str = IMAGE_THEME,
    out_path: str = IMAGE_OUTPUT_PATH,
) -> str | None:
    """Render a full gold dashboard PNG and return path, or None on failure."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        logger.warning("Pillow not installed.")
        return None

    # ── Palette ──────────────────────────────────────────────────────────
    if theme == "dark":
        BG      = ( 10,  12,  22)
        CARD    = ( 20,  25,  42)
        CARD2   = ( 26,  32,  52)
        CARD3   = ( 34,  42,  65)
        INK     = (228, 232, 248)
        INK2    = (160, 170, 205)
        INK3    = (100, 112, 152)
        GLD     = (255, 200,  48)
        GLD2    = (200, 148,  28)
        SIL     = (185, 198, 220)
        BLU     = ( 78, 158, 255)
        GRN     = ( 46, 196,  98)
        GRN2    = ( 22, 130,  60)
        RED     = (240,  68,  68)
        RED2    = (170,  36,  36)
        AMB     = (255, 178,  36)
        MUT     = (110, 120, 155)
        DIV     = ( 36,  46,  74)
        SHD     = (  4,   5,  14)
        HDR_L   = ( 18,  28,  62)
        HDR_R   = ( 48,  18,  88)
        CANDLE_UP   = ( 22, 160,  78)
        CANDLE_DN   = (220,  48,  48)
        GLOW_COL    = (255, 200,  48, 90)
    else:
        BG      = (244, 246, 252)
        CARD    = (255, 255, 255)
        CARD2   = (238, 242, 252)
        CARD3   = (222, 228, 246)
        INK     = ( 16,  20,  48)
        INK2    = ( 65,  78, 118)
        INK3    = (122, 134, 172)
        GLD     = (148,  98,   0)
        GLD2    = (188, 145,  35)
        SIL     = ( 72,  88, 128)
        BLU     = ( 25,  98, 215)
        GRN     = ( 18, 140,  62)
        GRN2    = (  6,  94,  38)
        RED     = (196,  24,  24)
        RED2    = (138,  10,  10)
        AMB     = (178, 112,   0)
        MUT     = (128, 140, 175)
        DIV     = (208, 216, 238)
        SHD     = (178, 184, 210)
        HDR_L   = ( 12,  38,  98)
        HDR_R   = ( 68,   8, 118)
        CANDLE_UP   = ( 18, 140,  62)
        CANDLE_DN   = (196,  24,  24)
        GLOW_COL    = (148,  98,   0, 80)

    W   = 1080
    PAD = 20
    now = datetime.now()

    # ── Fonts ─────────────────────────────────────────────────────────────
    def _fnt(sz, bold=False):
        cands = (
            ["C:/Windows/Fonts/segoeuib.ttf",
             "C:/Windows/Fonts/seguisb.ttf",
             "C:/Windows/Fonts/arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            if bold else
            ["C:/Windows/Fonts/segoeui.ttf",
             "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        )
        for p in cands:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, sz)
                except Exception:
                    pass
        return ImageFont.load_default()

    Fhero  = _fnt(40, True)
    Ftitle = _fnt(21, True)
    Flabel = _fnt(15, True)
    Fbody  = _fnt(14)
    Fsmall = _fnt(13)
    Ftiny  = _fnt(11)
    Fsec   = _fnt(16, True)

    def _tw(txt, fnt):
        try:
            bb = fnt.getbbox(str(txt))
            return bb[2] - bb[0]
        except Exception:
            return len(str(txt)) * max(5, getattr(fnt, "size", 12) // 2)

    def _th(fnt):
        try:
            return fnt.getbbox("Ag")[3]
        except Exception:
            return getattr(fnt, "size", 12) + 2

    # ── Extract values ────────────────────────────────────────────────────
    usd_inr    = (data.get("usd_inr_rate") if data else None) or 84.0
    ibja       = data.get("ibja")       if data else None
    gr_ch      = data.get("gr_chennai") if data else None

    if gr_ch:
        p24k, p22k = gr_ch["24k"], gr_ch["22k"]
        src_lbl    = f"Chennai Retail  {gr_ch['date']}"
    elif ibja:
        p24k, p22k = ibja["24k"], ibja["22k"]
        src_lbl    = f"IBJA  {ibja['date']}"
    elif data:
        p24k = round(data.get("price_inr_per_g", 0) * INDIA_GOLD_DUTY_FACTOR)
        p22k = round(p24k * 22 / 24)
        src_lbl = "Live estimate"
    else:
        p24k = p22k = 0
        src_lbl = "N/A"

    chg_inr = data.get("change_inr_g") if data else None
    chg_7d  = (analysis or {}).get("chg_7d")
    chg_30d = (analysis or {}).get("chg_30d")

    rsi      = (analysis or {}).get("rsi")
    bb_pos   = (analysis or {}).get("bb_pos")
    macd_val = (analysis or {}).get("macd_val")
    macd_cross = (analysis or {}).get("macd_cross")
    sma20    = (analysis or {}).get("sma20")
    sma50    = (analysis or {}).get("sma50")
    a_score  = (analysis or {}).get("score", 0)
    a_rec    = (analysis or {}).get("recommendation", "")

    geo_signal = (geo or {}).get("geo_signal", "")
    geo_score  = (geo or {}).get("geo_score", 0)
    bull_cnt   = (geo or {}).get("bull_count", 0)
    bear_cnt   = (geo or {}).get("bear_count", 0)

    pred_dir   = (prediction or {}).get("direction", "FLAT")
    pred_score = float((prediction or {}).get("score", 0))
    geo_s      = float((geo or {}).get("geo_score", 0))
    combined   = round(a_score + geo_s + pred_score * 0.3, 1)

    hist_rows  = (history or [])[:10]
    wk_all     = (weekly_prediction or [])[:7]

    ag_inr_kg  = (silver or {}).get("price_inr_kg") or 0
    ag_chg     = (silver or {}).get("change_inr_g")
    gs_ratio   = (silver or {}).get("gs_ratio")

    votes       = (global_signals or {}).get("votes", {})
    descs       = (global_signals or {}).get("descriptions", {})
    net_score   = (global_signals or {}).get("net_score", 0)
    g_outlook   = (global_signals or {}).get("global_outlook", "")
    dxy_val     = (global_signals or {}).get("dxy_val")
    vix_val     = (global_signals or {}).get("vix_now")
    yield_val   = (global_signals or {}).get("yield_now")
    gs_raw      = (global_signals or {}).get("gold_silver_ratio")

    best_day     = (payment or {}).get("best_day")
    top3_days    = (payment or {}).get("top3_days", [])
    win_label    = (payment or {}).get("this_month_window", "")
    ml_day       = (payment or {}).get("current_month_low_day")
    ml_price_22k = (payment or {}).get("current_month_low_inr22k")
    ml_trend     = (payment or {}).get("current_month_trend", "")

    # Sparkline source: last 7 history 22K prices (oldest→newest)
    hist_22k_spark = [r.get("22k", 0) for r in reversed(hist_rows)][:7]

    # ── Canvas size ───────────────────────────────────────────────────────
    n_sig    = len(descs)
    n_hl     = len((geo or {}).get("top_headlines", []))

    H_HDR   = 112
    H_KPI   = 128
    H_CHART = 260   # taller for candlestick + axis labels
    H_GAUGE = 310   # taller for glow + forecast area
    H_TECH  = 92    # taller for segmented dots
    H_SIG   = max(0, n_sig * 34 + 54) if n_sig else 0
    H_BUY   = 106
    H_GEO   = 84 + max(0, n_hl * 22)
    H_FTR   = 52
    SH      = 40    # section header height (slightly taller for gradient)
    GAP     = 14

    n_secs = 5 + (1 if H_SIG else 0)
    TOTAL_H = (H_HDR + H_KPI + H_CHART + H_GAUGE + H_TECH + H_SIG + H_BUY + H_GEO
               + H_FTR + n_secs * SH + GAP * (n_secs + 4) + 40)

    img  = Image.new("RGB", (W, TOTAL_H), BG)
    drw  = ImageDraw.Draw(img)
    y    = 0

    # ── Helper: RGBA alpha-composite overlay ──────────────────────────────
    def _alpha_overlay(poly_pts, fill_rgba):
        nonlocal img, drw
        ov = Image.new("RGBA", (W, TOTAL_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.polygon(poly_pts, fill=fill_rgba)
        img_rgba = img.convert("RGBA")
        img_rgba.alpha_composite(ov)
        img = img_rgba.convert("RGB")
        drw = ImageDraw.Draw(img)

    # ── Helper: glow circle ──────────────────────────────────────────────
    def _glow_circle(cx, cy, r_outer, r_inner, col_rgba):
        """Draw a glowing halo ring using alpha overlay."""
        nonlocal img, drw
        ov = Image.new("RGBA", (W, TOTAL_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        r, g, b, a = col_rgba
        for radius in range(r_outer, r_inner - 1, -2):
            alpha = int(a * (r_outer - radius) / max(1, r_outer - r_inner))
            od.ellipse([(cx - radius, cy - radius), (cx + radius, cy + radius)],
                       fill=(r, g, b, alpha), outline=None)
        img_rgba = img.convert("RGBA")
        img_rgba.alpha_composite(ov)
        img = img_rgba.convert("RGB")
        drw = ImageDraw.Draw(img)

    # ── Helper: section header with gradient ─────────────────────────────
    def _sec(label):
        nonlocal y
        # background gradient (subtle left→right)
        _h_gradient(drw, PAD, y, W - PAD, y + SH, CARD2, CARD3, steps=60)
        # rounded frame
        drw.rounded_rectangle([(PAD, y), (W - PAD, y + SH)], radius=6,
                               outline=DIV, width=1)
        # gold left accent bar
        drw.rounded_rectangle([(PAD, y), (PAD + 5, y + SH)], radius=3, fill=GLD)
        drw.text((PAD + 14, y + 11), label, font=Fsec, fill=INK)
        # gold bottom strip
        drw.rectangle([(PAD, y + SH - 2), (W - PAD, y + SH)], fill=GLD2)
        y += SH + 8

    # ── Helper: pill ──────────────────────────────────────────────────────
    def _pill(px, py, txt, bg, fg=None, fnt=None):
        if fnt is None: fnt = Fsmall
        if fg  is None: fg  = BG if sum(bg) > 380 else INK
        tw = _tw(txt, fnt)
        pw, ph = tw + 18, 22
        drw.rounded_rectangle([(px, py), (px + pw, py + ph)], radius=6, fill=bg)
        drw.text((px + 9, py + 4), txt, font=fnt, fill=fg)
        return pw + 6

    # ── Helper: hbar ─────────────────────────────────────────────────────
    def _hbar(x0, y0, x1, y1, pct, fg, bg=None):
        if bg is None: bg = CARD3
        drw.rounded_rectangle([(x0, y0), (x1, y1)], radius=3, fill=bg)
        fe = x0 + int(max(0.0, min(1.0, pct)) * (x1 - x0))
        if fe > x0:
            drw.rounded_rectangle([(x0, y0), (fe, y1)], radius=3, fill=fg)

    # ── Helper: segmented dot meter ───────────────────────────────────────
    def _dot_meter(x0, y0, dots=10, filled=5, col_on=None, col_off=None):
        if col_on  is None: col_on  = GLD
        if col_off is None: col_off = CARD3
        d, gap = 8, 4
        for i in range(dots):
            cx = x0 + i * (d + gap)
            c  = col_on if i < filled else col_off
            drw.ellipse([(cx, y0), (cx + d, y0 + d)], fill=c)

    # ── Helper: vote colour ──────────────────────────────────────────────
    def _vote_col(v):
        if   v >= 2:  return GRN2
        elif v == 1:  return GRN
        elif v == 0:  return AMB
        elif v == -1: return RED
        else:         return RED2

    # =========================================================== #
    # ① HERO HEADER                                               #
    # =========================================================== #
    _h_gradient(drw, 0, 0, W, H_HDR, HDR_L, HDR_R, steps=80)
    drw.rectangle([(0, H_HDR - 4), (W, H_HDR)], fill=GLD)

    drw.text((PAD, 14), "GOLD PRICE DASHBOARD", font=Fhero, fill=GLD)
    if os.name == "nt":
        dt_str = now.strftime("%#d %B %Y  •  %H:%M IST")
    else:
        dt_str = now.strftime("%-d %B %Y  •  %H:%M IST")
    drw.text((PAD, 62), dt_str, font=Fbody, fill=INK2)
    drw.text((PAD, 80), f"Source: {src_lbl}", font=Ftiny, fill=MUT)

    if chg_inr is not None:
        chg_22k = chg_inr * 22 / 24
        arrow = "▲" if chg_22k >= 0 else "▼"
        ccol  = GRN if chg_22k >= 0 else RED
        ctxt  = f"{arrow} ₹{abs(chg_22k):,.0f}/g  22K today"
        drw.text((W - _tw(ctxt, Ftitle) - PAD, 46), ctxt, font=Ftitle, fill=ccol)

    y = H_HDR + GAP

    # =========================================================== #
    # ② KPI CARDS  (22K hero | 24K | Silver | USD/INR)            #
    # =========================================================== #
    gap_c = 10
    n_c   = 4
    cw_22k  = (W - 2 * PAD - 3 * gap_c) * 32 // 100
    cw_rest = (W - 2 * PAD - cw_22k - 3 * gap_c) // 3
    card_widths = [cw_22k, cw_rest, cw_rest, cw_rest]

    kpis = [
        ("22K GOLD",   f"₹{p22k:,}",              "/g",  GLD,  True),
        ("24K GOLD",   f"₹{p24k:,}",              "/g",  GLD2, False),
        ("SILVER 999", f"₹{ag_inr_kg:,.0f}" if ag_inr_kg else "—", "/kg", SIL, False),
        ("USD / INR",  f"₹{usd_inr:.2f}",          "",    BLU,  False),
    ]

    for idx, (lbl, val, unit, acc, is_hero) in enumerate(kpis):
        cx0 = PAD + sum(card_widths[:idx]) + idx * gap_c
        cx1 = cx0 + card_widths[idx]
        cy0, cy1 = y, y + H_KPI
        _shadow_rect(drw, cx0, cy0, cx1, cy1, CARD, radius=10, soff=4, scol=SHD)
        strip_h = 7 if is_hero else 5
        drw.rounded_rectangle([(cx0, cy0), (cx1, cy0 + strip_h)], radius=3, fill=acc)

        val_font = _fnt(24, True) if is_hero else Ftitle
        lbl_font = Fsmall if is_hero else Ftiny
        drw.text((cx0 + 12, cy0 + 13), lbl, font=lbl_font,
                 fill=GLD if is_hero else INK3)
        drw.text((cx0 + 12, cy0 + (34 if is_hero else 30)), val, font=val_font, fill=INK)
        if unit:
            drw.text((cx0 + 14 + _tw(val, val_font), cy0 + (44 if is_hero else 40)),
                     unit, font=Ftiny, fill=INK2)

        # sub-lines
        if idx == 0:    # 22K hero
            if chg_inr is not None:
                chg_22k = chg_inr * 22 / 24
                arr = "▲" if chg_22k >= 0 else "▼"
                col = GRN if chg_22k >= 0 else RED
                drw.text((cx0 + 12, cy0 + 78), f"{arr} ₹{abs(chg_22k):,.0f}/g today",
                         font=Fsmall, fill=col)
            if chg_7d is not None:
                drw.text((cx0 + 12, cy0 + 96),
                         f"7d: {chg_7d:+.2f}%     30d: {chg_30d:+.2f}%" if chg_30d
                         else f"7d: {chg_7d:+.2f}%",
                         font=Ftiny, fill=INK2)
            helper = f"8g=₹{p22k * 8:,}  •  10g=₹{p22k * 10:,}"
            drw.text((cx0 + 12, cy0 + 110), helper, font=Ftiny, fill=MUT)
            # sparkline (bottom strip)
            if len(hist_22k_spark) >= 2:
                _sparkline(drw, cx0 + 12, cy0 + H_KPI - 20,
                           cx1 - 12, cy0 + H_KPI - 6,
                           hist_22k_spark, GRN, RED, bg=CARD2)
        elif idx == 1:  # 24K
            if chg_30d is not None:
                drw.text((cx0 + 12, cy0 + 72), f"30d: {chg_30d:+.2f}%", font=Fsmall, fill=INK2)
            if len(hist_22k_spark) >= 2:
                spark_24k = [r.get("24k", 0) for r in reversed(hist_rows)][:7]
                _sparkline(drw, cx0 + 12, cy0 + H_KPI - 20,
                           cx1 - 12, cy0 + H_KPI - 6,
                           spark_24k, GRN, RED, bg=CARD2)
        elif idx == 2 and gs_ratio:
            gs_col = RED if gs_ratio > 90 else (GRN if gs_ratio < 65 else INK2)
            drw.text((cx0 + 12, cy0 + 72), f"G/S ratio: {gs_ratio:.0f}", font=Fsmall, fill=gs_col)
            if ag_chg is not None:
                drw.text((cx0 + 12, cy0 + 90), f"Δ ₹{ag_chg:+.2f}/g", font=Ftiny, fill=INK2)
        elif idx == 3 and dxy_val:
            drw.text((cx0 + 12, cy0 + 72), f"DXY: {dxy_val:.1f}", font=Fsmall, fill=INK2)
            if vix_val:
                drw.text((cx0 + 12, cy0 + 90), f"VIX: {vix_val:.1f}", font=Ftiny, fill=INK2)

    y += H_KPI + GAP

    # =========================================================== #
    # ③ 10-DAY PRICE TREND — CANDLESTICK CHART                    #
    # =========================================================== #
    if len(hist_rows) >= 2:
        _sec("10-DAY 22K GOLD PRICE TREND")
        chart_h  = H_CHART - 8
        split_x  = PAD + int((W - 2 * PAD) * 0.70)

        drw.rounded_rectangle([(PAD, y), (split_x, y + chart_h)], radius=10, fill=CARD)
        # subtle inner gradient tint
        _h_gradient(drw, PAD + 2, y + 2, split_x - 2, y + chart_h - 2,
                    CARD, CARD2, steps=40)

        # build price series (oldest→newest)
        closings_22k = [r.get("22k", 0) for r in reversed(hist_rows)]
        closings_24k = [r.get("24k", 0) for r in reversed(hist_rows)]
        dates_lbl    = [str(r.get("date", ""))[-5:] for r in reversed(hist_rows)]
        n_bars = len(closings_22k)

        cmin = min(closings_22k); cmax = max(closings_22k)
        rng  = max(cmax - cmin, 1)

        lpad, rpad, tpad, bpad = 56, 10, 20, 30
        ax0 = PAD + lpad; ax1 = split_x - rpad
        ay0 = y  + tpad;  ay1 = y + chart_h - bpad

        def _cx(i):
            return int(ax0 + (i + 0.5) * (ax1 - ax0) / max(1, n_bars))
        def _cy(p):
            return int(ay1 - (p - cmin) / rng * (ay1 - ay0))

        bar_w = max(4, (ax1 - ax0) // max(1, n_bars) - 4)

        # ── Grid lines + price axis labels (right side) ──────────────────
        for gp in [0.0, 0.25, 0.5, 0.75, 1.0]:
            gy = int(ay1 - gp * (ay1 - ay0))
            drw.line([(ax0, gy), (ax1, gy)], fill=DIV, width=1)
            pv = cmin + gp * rng
            lbl_str = f"₹{pv:,.0f}"
            drw.text((PAD + 2, gy - 8), lbl_str, font=Ftiny, fill=MUT)

        # ── Gradient area fill under line (RGBA composite) ───────────────
        area_pts = [(ax0, ay1)]
        for i, cl in enumerate(closings_22k):
            area_pts.append((_cx(i), _cy(cl)))
        area_pts.append((ax1, ay1))
        area_rgba = (CANDLE_UP[0], CANDLE_UP[1], CANDLE_UP[2], 35)
        _alpha_overlay(area_pts, area_rgba)

        # ── Candlestick bars ─────────────────────────────────────────────
        for i, cl in enumerate(closings_22k):
            px = _cx(i)
            prev = closings_22k[i - 1] if i > 0 else cl
            is_up = cl >= prev
            op = prev if i > 0 else cl
            hi = max(cl, op) * 1.0025
            lo = min(cl, op) * 0.9975
            body_col = CANDLE_UP if is_up else CANDLE_DN
            # wick
            drw.line([(px, _cy(hi)), (px, _cy(lo))], fill=body_col, width=2)
            # body
            by0 = min(_cy(cl), _cy(op))
            by1 = max(_cy(cl), _cy(op))
            body_h = max(2, by1 - by0)
            drw.rounded_rectangle([(px - bar_w // 2, by0), (px + bar_w // 2, by0 + body_h)],
                                   radius=2, fill=body_col)
            # date label every other
            if i % 2 == 0:
                dl = dates_lbl[i] if i < len(dates_lbl) else ""
                drw.text((px - len(dl) * 3, ay1 + 4), dl, font=Ftiny, fill=INK3)

        # ── Gold trend overlay line ───────────────────────────────────────
        trend_pts = [(_cx(i), _cy(cl)) for i, cl in enumerate(closings_22k)]
        if len(trend_pts) >= 2:
            drw.line(trend_pts, fill=GLD2, width=2)

        # ── Current price annotation ──────────────────────────────────────
        last_px, last_py = _cx(n_bars - 1), _cy(closings_22k[-1])
        price_lbl = f"₹{closings_22k[-1]:,}"
        lbl_w = _tw(price_lbl, Ftiny) + 10
        drw.rounded_rectangle([(last_px - 2, last_py - 16), (last_px + lbl_w, last_py - 2)],
                               radius=3, fill=GLD)
        drw.text((last_px + 4, last_py - 15), price_lbl, font=Ftiny,
                 fill=BG if sum(GLD) > 380 else INK)

        # ── Stats panel (right of chart) ──────────────────────────────────
        drw.rounded_rectangle([(split_x + 6, y), (W - PAD, y + chart_h)], radius=10, fill=CARD)
        # header strip
        _h_gradient(drw, split_x + 6, y, W - PAD, y + 32, GLD, GLD2, steps=30)
        drw.rounded_rectangle([(split_x + 6, y), (W - PAD, y + 32)], radius=8, outline=GLD, width=0)
        spx = split_x + 16
        drw.text((spx, y + 9), "COMEX", font=Flabel, fill=BG if sum(GLD) > 380 else INK)

        sy = y + 38
        price_usd = (analysis or {}).get("price_now_usd")
        if price_usd:
            drw.text((spx, sy), f"${price_usd:,.1f}/oz", font=Fbody, fill=INK); sy += 22

        for stat_lbl, val, col in [
            ("7d Chg",  f"{chg_7d:+.2f}%" if chg_7d  is not None else "—",
             GRN if chg_7d  and chg_7d  > 0 else (RED if chg_7d  and chg_7d  < 0 else INK2)),
            ("30d Chg", f"{chg_30d:+.2f}%" if chg_30d is not None else "—",
             GRN if chg_30d and chg_30d > 0 else (RED if chg_30d and chg_30d < 0 else INK2)),
        ]:
            drw.text((spx, sy), stat_lbl, font=Ftiny, fill=INK3); sy += 14
            drw.text((spx, sy), val,       font=Fbody, fill=col);  sy += 20

        sy += 4
        drw.line([(spx, sy), (W - PAD - 10, sy)], fill=DIV, width=1); sy += 8

        drw.text((spx, sy), "22K vs yesterday", font=Ftiny, fill=INK3); sy += 14
        if closings_22k and len(closings_22k) >= 2:
            delta_1d   = closings_22k[-1] - closings_22k[-2]
            dcol       = GRN if delta_1d >= 0 else RED
            darrow     = "▲" if delta_1d >= 0 else "▼"
            drw.text((spx, sy), f"{darrow} ₹{abs(delta_1d):,}/g", font=Fbody, fill=dcol); sy += 22

        if closings_22k:
            drw.text((spx, sy), "22K multiples", font=Ftiny, fill=INK3); sy += 14
            drw.text((spx, sy), f"8g  = ₹{closings_22k[-1] * 8:,}",  font=Ftiny, fill=INK2); sy += 14
            drw.text((spx, sy), f"10g = ₹{closings_22k[-1] * 10:,}", font=Ftiny, fill=INK2); sy += 16

        # mini sparkline in stats panel
        if len(hist_22k_spark) >= 2:
            sy += 4
            drw.text((spx, sy), "10d trend", font=Ftiny, fill=INK3); sy += 14
            _sparkline(drw, spx, sy, W - PAD - 12, sy + 28,
                       hist_22k_spark, GRN, RED, bg=CARD2)

        y += chart_h + GAP

    # =========================================================== #
    # ④ SIGNAL GAUGE  +  7-DAY FORECAST                           #
    # =========================================================== #
    _sec("PREDICTION SIGNAL GAUGE")
    ga_top = y

    GCX = PAD + (W // 2 - PAD) // 2
    GCY = y + 158
    GR  = 108

    def _gauge(score):
        t  = max(-1.0, min(1.0, score / 10))
        nd = 180 + t * 82      # PIL arc angle: 180=left, 360=right

        zones = [(180, 222, RED2), (222, 252, RED), (252, 278, CARD3),
                 (278, 308, GRN),  (308, 360, GRN2)]
        for sa, ea, col in zones:
            drw.arc([(GCX - GR, GCY - GR), (GCX + GR, GCY + GR)],
                    start=sa, end=ea, fill=col, width=24)
        # outer ring
        drw.arc([(GCX - GR - 4, GCY - GR - 4), (GCX + GR + 4, GCY + GR + 4)],
                start=180, end=360, fill=DIV, width=2)

        # ticks
        for deg in range(180, 361, 20):
            r2 = _math.radians(deg)
            x1 = GCX + (GR + 4) * _math.cos(r2); y1 = GCY + (GR + 4) * _math.sin(r2)
            x2 = GCX + (GR - 24) * _math.cos(r2); y2 = GCY + (GR - 24) * _math.sin(r2)
            drw.line([(x1, y1), (x2, y2)], fill=INK3, width=1)

        # ── Glow around hub (concentric alpha rings) ──────────────────────
        _glow_circle(GCX, GCY, r_outer=30, r_inner=10, col_rgba=GLOW_COL)

        # ── Needle with glow layering ─────────────────────────────────────
        nr  = _math.radians(nd)
        nx  = GCX + (GR - 20) * _math.cos(nr)
        ny2 = GCY + (GR - 20) * _math.sin(nr)
        # shadow needle
        drw.line([(GCX, GCY), (nx, ny2)], fill=SHD, width=7)
        # glow needle (wide dim)
        drw.line([(GCX, GCY), (nx, ny2)], fill=GLD2, width=5)
        # bright needle (thin, on top)
        drw.line([(GCX, GCY), (nx, ny2)], fill=GLD, width=2)
        # hub
        drw.ellipse([(GCX - 10, GCY - 10), (GCX + 10, GCY + 10)], fill=GLD)
        drw.ellipse([(GCX - 4,  GCY - 4),  (GCX + 4,  GCY + 4)],  fill=INK)

        drw.text((GCX - 20, GCY - GR - 22), "SELL", font=Ftiny, fill=RED)
        drw.text((GCX + GR - 14, GCY + 12), "BUY",  font=Ftiny, fill=GRN)

        s_txt = f"Score: {score:+.1f}"
        drw.text((GCX - _tw(s_txt, Flabel) // 2, GCY + 16), s_txt, font=Flabel, fill=INK)

        if   score >= 7:   ver, vc = "STRONG BUY",  GRN2
        elif score >= 3:   ver, vc = "BUY",          GRN
        elif score <= -7:  ver, vc = "STRONG SELL",  RED2
        elif score <= -3:  ver, vc = "SELL",          RED
        else:              ver, vc = "NEUTRAL",       AMB
        drw.text((GCX - _tw(ver, Ftitle) // 2, GCY + 40), ver, font=Ftitle, fill=vc)

    _gauge(combined)

    # --- 7-day forecast panel ---
    fx0 = W // 2 + 6
    fy0 = ga_top
    fy1 = ga_top + H_GAUGE - GAP
    _shadow_rect(drw, fx0, fy0, W - PAD, fy1, CARD, radius=8, soff=3, scol=SHD)
    # header strip
    _h_gradient(drw, fx0, fy0, W - PAD, fy0 + 32, GLD, GLD2, steps=30)
    drw.text((fx0 + 12, fy0 + 9), "7-DAY PRICE FORECAST", font=Flabel,
             fill=BG if sum(GLD) > 380 else INK)

    wry = fy0 + 38
    drw.text((fx0 + 12,  wry), "Day", font=Ftiny, fill=INK3)
    drw.text((fx0 + 68,  wry), "Dir", font=Ftiny, fill=INK3)
    drw.text((fx0 + 114, wry), "22K mid (₹/g)", font=Ftiny, fill=GLD)
    drw.text((fx0 + 255, wry), "22K range",           font=Ftiny, fill=INK3)
    wry += 18
    drw.line([(fx0 + 10, wry), (W - PAD - 8, wry)], fill=DIV, width=1)
    wry += 6

    forecast_mids = []
    forecast_los  = []
    forecast_his  = []
    forecast_dirs = []

    for row in wk_all[:7]:
        is_wknd = row.get("is_weekend", False)
        wd       = str(row.get("weekday", ""))[:3]
        dirn     = str(row.get("direction", "FLAT")).upper()
        mid_22k  = row.get("mid_22k") or round((row.get("mid_inr",  0) or 0) * 22 / 24)
        lo_22k   = row.get("low_22k") or round((row.get("low_inr",  mid_22k) or mid_22k) * 22 / 24)
        hi_22k   = row.get("high_22k") or round((row.get("high_inr", mid_22k) or mid_22k) * 22 / 24)

        if not is_wknd and mid_22k:
            forecast_mids.append(mid_22k)
            forecast_los.append(lo_22k)
            forecast_his.append(hi_22k)
            forecast_dirs.append(dirn)

        if wry < fy1 - 60:
            if is_wknd:
                drw.rectangle([(fx0 + 8, wry - 2), (W - PAD - 6, wry + 22)], fill=CARD2)
                drw.text((fx0 + 12, wry + 2), wd, font=Fsmall, fill=INK3)
                drw.text((fx0 + 68, wry + 2), "Weekend", font=Fsmall, fill=MUT)
            else:
                pcol = GRN if "UP" in dirn else (RED if "DOWN" in dirn else AMB)
                arr  = "▲" if "UP" in dirn else ("▼" if "DOWN" in dirn else "—")
                drw.text((fx0 + 12, wry + 2), wd, font=Fsmall, fill=INK)
                _pill(fx0 + 58, wry, f"{arr} {dirn}", pcol, fnt=Ftiny)
                mid_txt   = f"₹{mid_22k:,}"
                range_txt = f"₹{lo_22k:,} – ₹{hi_22k:,}"
                drw.text((fx0 + 114, wry + 2), mid_txt,   font=Fsmall, fill=GLD)
                drw.text((fx0 + 255, wry + 4), range_txt, font=Ftiny,  fill=INK2)
            wry += 26

    # ── Forecast area mini-chart ──────────────────────────────────────────
    if len(forecast_mids) >= 2:
        wry += 8
        drw.line([(fx0 + 10, wry), (W - PAD - 8, wry)], fill=DIV, width=1); wry += 6
        drw.text((fx0 + 12, wry), "Forecast band", font=Ftiny, fill=INK3); wry += 14
        fc_x0 = fx0 + 10; fc_x1 = W - PAD - 10
        fc_y0 = wry;       fc_y1 = min(wry + 42, fy1 - 8)
        if fc_y1 - fc_y0 >= 16:
            drw.rectangle([(fc_x0, fc_y0), (fc_x1, fc_y1)], fill=CARD2)
            f_all = forecast_los + forecast_his
            f_mn  = min(f_all); f_mx = max(f_all); f_rng = max(f_mx - f_mn, 1)
            n_f   = len(forecast_mids)
            def _fx(i): return int(fc_x0 + i * (fc_x1 - fc_x0) / max(1, n_f - 1))
            def _fy(v): return int(fc_y1 - (v - f_mn) / f_rng * (fc_y1 - fc_y0))
            # confidence band (alpha)
            band_top = [(_fx(i), _fy(forecast_his[i])) for i in range(n_f)]
            band_bot = [(_fx(i), _fy(forecast_los[i])) for i in range(n_f)]
            band_pts = band_top + list(reversed(band_bot))
            _alpha_overlay(band_pts, (CANDLE_UP[0], CANDLE_UP[1], CANDLE_UP[2], 55))
            # mid line + coloured dots
            mid_pts = [(_fx(i), _fy(forecast_mids[i])) for i in range(n_f)]
            if len(mid_pts) >= 2:
                drw.line(mid_pts, fill=GLD, width=2)
            for i, (fx, fy) in enumerate(mid_pts):
                dcol = GRN if "UP" in forecast_dirs[i] else (RED if "DOWN" in forecast_dirs[i] else AMB)
                drw.ellipse([(fx - 4, fy - 4), (fx + 4, fy + 4)], fill=dcol, outline=CARD, width=1)

    # Macro outlook
    if g_outlook:
        outlook_clean = (g_outlook.replace("🟢", "").replace("🔴", "")
                         .replace("🟡", "").replace("⚪", "").replace("🟠", "").strip())
        y_ol = fy1 - 16
        drw.text((fx0 + 12, y_ol), f"Macro: {outlook_clean}"[:44], font=Ftiny, fill=INK2)

    y = ga_top + H_GAUGE

    # =========================================================== #
    # ⑤ TECHNICAL INDICATORS ROW — SEGMENTED DOT METERS           #
    # =========================================================== #
    _sec("TECHNICAL INDICATORS")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_TECH)], radius=8, fill=CARD)
    # subtle header gradient inside card
    _h_gradient(drw, PAD + 2, y + 2, W - PAD - 2, y + 28, CARD, CARD2, steps=40)

    cols  = 5
    cw_ti = (W - 2 * PAD - 20) // cols
    ti_items = [
        ("RSI (14)",    f"{rsi:.1f}" if rsi is not None else "—",
         GRN if rsi and rsi < 45 else (RED if rsi and rsi > 70 else AMB),
         (rsi or 50) / 100 if rsi else 0.5, 10),
        ("MACD",        f"{macd_val:+.2f}" if macd_val is not None else "—",
         GRN if macd_cross and macd_cross > 0 else RED,
         0.5 + (macd_cross or 0) / 20, 10),
        ("BB Position", f"{bb_pos * 100:.0f}%" if bb_pos is not None else "—",
         GRN if bb_pos and bb_pos < 0.3 else (RED if bb_pos and bb_pos > 0.7 else AMB),
         bb_pos or 0.5, 10),
        ("Tech Score",  f"{a_score:+d}",
         GRN if a_score >= 2 else (RED if a_score <= -2 else AMB),
         max(0.0, min(1.0, (a_score + 8) / 16)), 10),
        ("Macro Net",   f"{net_score:+d}",
         GRN if net_score >= 2 else (RED if net_score <= -2 else AMB),
         max(0.0, min(1.0, (net_score + 10) / 20)), 10),
    ]

    for ci, (lbl, val, vcol, pct, n_dots) in enumerate(ti_items):
        tx = PAD + 10 + ci * cw_ti
        drw.text((tx, y + 8),  lbl, font=Ftiny,  fill=INK3)
        drw.text((tx, y + 24), val, font=Flabel, fill=vcol)
        filled = max(0, min(n_dots, round(pct * n_dots)))
        _dot_meter(tx, y + H_TECH - 20, dots=n_dots, filled=filled,
                   col_on=vcol, col_off=CARD3)
        # percentage text beneath dots
        drw.text((tx + n_dots * 12 + 4, y + H_TECH - 20), f"{int(pct*100)}%",
                 font=Ftiny, fill=INK3)
        if ci < cols - 1:
            drw.line([(tx + cw_ti - 6, y + 10), (tx + cw_ti - 6, y + H_TECH - 10)],
                    fill=DIV, width=1)

    sma_txt = ""
    if sma20 and sma50 and (analysis or {}).get("price_now_usd"):
        p = (analysis or {}).get("price_now_usd", 0)
        sma_txt = f"SMA20: ${sma20:,.0f}  SMA50: ${sma50:,.0f}  Price: ${p:,.0f}"
        drw.text((PAD + 12, y + H_TECH - 5), sma_txt, font=Ftiny, fill=MUT)

    y += H_TECH + GAP

    # =========================================================== #
    # ⑥ WORLD MACRO SIGNALS TABLE                                 #
    # =========================================================== #
    if descs:
        _sec("WORLD MACRO SIGNALS")
        row_h        = 34
        n_rows_show  = min(len(descs), 12)
        t_h          = n_rows_show * row_h + 6

        COL_NAME = 175
        COL_VAL  = 80
        COL_PILL = 100
        COL_BAR  = W - 2 * PAD - COL_NAME - COL_VAL - COL_PILL - 10

        drw.rectangle([(PAD, y), (W - PAD, y + 22)], fill=CARD3)
        drw.text((PAD + 30,              y + 4), "Indicator", font=Ftiny, fill=INK3)
        drw.text((PAD + COL_NAME,        y + 4), "Signal",    font=Ftiny, fill=INK3)
        drw.text((W - PAD - COL_PILL - COL_VAL + 4, y + 4), "Value",  font=Ftiny, fill=INK3)
        drw.text((W - PAD - COL_PILL + 8,           y + 4), "Rating", font=Ftiny, fill=INK3)
        y += 22

        SIGNAL_LABELS = {
            "real_yield":    ("Real Yield",   "tip_val"),
            "dxy":           ("DXY (Dollar)", "dxy_val"),
            "yields":        ("10Y Yield",    "yield_now"),
            "yield_curve":   ("Yield Curve",  "yield_curve_spread"),
            "vix":           ("VIX",          "vix_now"),
            "risk_assets":   ("S&P 500 1d",   "sp500_1d"),
            "oil":           ("Oil 5d%",      "oil_5d"),
            "silver_ratio":  ("Gold/Silver",  "gold_silver_ratio"),
            "copper":        ("Copper 5d%",   "copper_5d"),
            "eur_usd":       ("EUR/USD",      "eurusd_val"),
            "etf_flow":      ("GLD ETF",      "gld_5d"),
            "gold_momentum": ("Gold 5d%",     "gold_5d"),
        }

        for ri, (key, desc_txt) in enumerate(descs.items()):
            if ri >= n_rows_show: break
            ry     = y + ri * row_h
            row_bg = CARD if ri % 2 == 0 else CARD2
            drw.rectangle([(PAD, ry), (W - PAD, ry + row_h - 2)], fill=row_bg)

            vote = votes.get(key, 0)
            vc   = _vote_col(vote)

            drw.ellipse([(PAD + 8, ry + 11), (PAD + 20, ry + 23)], fill=vc)

            disp_name = SIGNAL_LABELS.get(key, (key.replace("_", " ").title(), ""))[0]
            drw.text((PAD + 26, ry + 10), disp_name[:22], font=Fsmall, fill=INK)

            raw_key = SIGNAL_LABELS.get(key, ("", ""))[1]
            raw_v   = (global_signals or {}).get(raw_key)
            val_txt = ""
            if raw_v is not None:
                if isinstance(raw_v, float):
                    val_txt = f"{raw_v:.2f}" if abs(raw_v) < 100 else f"{raw_v:.0f}"
                else:
                    val_txt = str(raw_v)
            vx = W - PAD - COL_PILL - COL_VAL + 4
            drw.text((vx, ry + 10), val_txt[:10], font=Fsmall, fill=INK2)

            bx0  = PAD + COL_NAME
            bx1  = W - PAD - COL_PILL - COL_VAL - 8
            norm = max(0.0, min(1.0, (vote + 2) / 4))
            _hbar(bx0, ry + 13, bx1, ry + 21, norm, vc)

            vote_lbl = {2: "BULLISH", 1: "MILD ▲", 0: "NEUTRAL",
                        -1: "MILD ▼", -2: "BEARISH"}.get(vote, str(vote))
            _pill(W - PAD - COL_PILL + 2, ry + 6, vote_lbl, vc, fnt=Ftiny)

        y += t_h + GAP

    # =========================================================== #
    # ⑦ BUYING GUIDE                                              #
    # =========================================================== #
    _sec("BUYING GUIDE")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_BUY)], radius=8, fill=CARD)

    cw3 = (W - 2 * PAD - 20) // 3
    cx1s = PAD + 12
    drw.text((cx1s, y + 8), "Best Day to Buy", font=Ftiny, fill=INK3)
    if best_day:
        drw.text((cx1s, y + 24), f"📅 {_ordinal(best_day)} of month", font=Flabel, fill=GLD)
        if win_label:
            drw.text((cx1s, y + 48), f"Window: {win_label}", font=Ftiny, fill=INK2)
        if top3_days:
            drw.text((cx1s, y + 62),
                     f"Top 3: {', '.join(_ordinal(d) for d in top3_days)}", font=Ftiny, fill=MUT)

    drw.line([(PAD + cw3 + 6, y + 8), (PAD + cw3 + 6, y + H_BUY - 8)], fill=DIV, width=1)

    cx2s = PAD + cw3 + 18
    drw.text((cx2s, y + 8), "This Month Low (22K)", font=Ftiny, fill=INK3)
    if ml_day:
        drw.text((cx2s, y + 24), f"📉 {_ordinal(ml_day)}", font=Flabel, fill=GRN)
        if ml_price_22k:
            drw.text((cx2s, y + 48), f"₹{ml_price_22k:,}/g", font=Fbody, fill=INK2)
        if ml_trend:
            tcol = GRN if ml_trend == "falling" else (RED if ml_trend == "rising" else INK2)
            drw.text((cx2s, y + 68), f"Trend: {ml_trend}", font=Ftiny, fill=tcol)
    else:
        drw.text((cx2s, y + 24), "Calculating...", font=Fbody, fill=MUT)

    drw.line([(PAD + cw3 * 2 + 10, y + 8), (PAD + cw3 * 2 + 10, y + H_BUY - 8)], fill=DIV, width=1)

    cx3s = PAD + cw3 * 2 + 22
    drw.text((cx3s, y + 8), "Today's Recommendation", font=Ftiny, fill=INK3)
    if a_rec:
        rec_clean = (a_rec.replace("🟢", "").replace("🔴", "")
                    .replace("🟡", "").replace("⚪", "").replace("🟠", "").strip())
        rcol  = GRN if "BUY" in a_rec.upper() else (RED if any(w in a_rec.upper() for w in ("AVOID", "WAIT")) else AMB)
        lines = rec_clean.split(" – ")
        drw.text((cx3s, y + 24), lines[0][:22], font=Flabel, fill=rcol)
        if len(lines) > 1:
            drw.text((cx3s, y + 46), lines[1][:30], font=Ftiny, fill=INK2)
    drw.text((cx3s, y + 72), f"Prediction: {pred_dir}  ({pred_score:+.1f})", font=Ftiny, fill=INK2)

    y += H_BUY + GAP

    # =========================================================== #
    # ⑧ GEO / NEWS SENTIMENT                                      #
    # =========================================================== #
    _sec("GEOPOLITICAL SENTIMENT")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_GEO)], radius=8, fill=CARD)

    geo_clean = (geo_signal.replace("🔴", "").replace("🟠", "")
                .replace("🟡", "").replace("🟢", "").strip())
    gcol      = GRN if geo_score < 0 else (RED if geo_score >= 2 else AMB)
    drw.text((PAD + 12, y + 8),  geo_clean[:50], font=Flabel, fill=gcol)

    ppx = PAD + 12
    ppx += _pill(ppx, y + 32, f"▲ {bull_cnt} bullish", GRN2)
    ppx += _pill(ppx, y + 32, f"▼ {bear_cnt} bearish", RED2)

    headlines = (geo or {}).get("top_headlines", [])
    hly = y + 60
    for title, bc, brc in headlines[:n_hl]:
        hcol = GRN2 if bc > brc else (RED2 if brc > bc else MUT)
        drw.text((PAD + 12, hly), f"• {title[:90]}", font=Ftiny, fill=hcol)
        hly += 20

    y += H_GEO + GAP

    # =========================================================== #
    # ⑨ FOOTER                                                    #
    # =========================================================== #
    fy = TOTAL_H - H_FTR
    _h_gradient(drw, 0, fy, W, TOTAL_H, HDR_R, HDR_L, steps=60)
    drw.rectangle([(0, fy), (W, fy + 3)], fill=GLD)
    drw.text((PAD, fy + 16),
             "Data: COMEX/MCX  •  INR rates include 15.5% duty+GST  •  Not financial advice",
             font=Ftiny, fill=INK2)
    if os.name == "nt":
        ts = now.strftime("Generated %#d %B %Y  %H:%M IST")
    else:
        ts = now.strftime("Generated %-d %B %Y  %H:%M IST")
    drw.text((W - PAD - _tw(ts, Ftiny), fy + 16), ts, font=Ftiny, fill=INK3)

    # ── Save ──────────────────────────────────────────────────────────────
    final_h = min(TOTAL_H, y + H_FTR + 8)
    img = img.crop((0, 0, W, final_h))
    img.save(out_path, format="PNG", optimize=True)
    logger.info("Image saved → %s  (%dx%d)", out_path, W, final_h)
    return out_path
