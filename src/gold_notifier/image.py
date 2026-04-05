"""
gold_notifier/image.py – Modern advanced dashboard image generator.
Ultra-clean finance-app aesthetic: dark-card glass panels, gradient
hero, per-day 22K/24K/Silver change badges, candlestick chart,
forecast confidence band, glowing gauge needle, segmented meters.
"""
import logging
import math as _math
import os
from datetime import datetime

from .config import INDIA_GOLD_DUTY_FACTOR, IMAGE_OUTPUT_PATH, IMAGE_THEME

logger = logging.getLogger(__name__)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"


# ── Module-level drawing helpers ────────────────────────────────────────────

def _h_gradient(draw, x0, y0, x1, y1, c_l, c_r, steps=80):
    sw = max(1, (x1 - x0) // steps)
    for i in range(steps):
        t = i / max(1, steps - 1)
        c = tuple(int(c_l[j] + (c_r[j] - c_l[j]) * t) for j in range(3))
        sx = x0 + i * sw
        draw.rectangle([(sx, y0), (min(sx + sw, x1), y1)], fill=c)


def _v_gradient(draw, x0, y0, x1, y1, c_t, c_b, steps=60):
    sh = max(1, (y1 - y0) // steps)
    for i in range(steps):
        t = i / max(1, steps - 1)
        c = tuple(int(c_t[j] + (c_b[j] - c_t[j]) * t) for j in range(3))
        sy = y0 + i * sh
        draw.rectangle([(x0, sy), (x1, min(sy + sh, y1))], fill=c)


def _shadow_rect(draw, x0, y0, x1, y1, fill, radius=10, soff=4, scol=None):
    if scol is None:
        scol = tuple(max(0, c - 30) for c in fill)
    draw.rounded_rectangle([(x0 + soff, y0 + soff), (x1 + soff, y1 + soff)],
                            radius=radius, fill=scol)
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=fill)


def _sparkline(draw, x0, y0, x1, y1, values, col_up, col_dn, bg=None):
    if not values or len(values) < 2:
        return
    if bg:
        draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=3, fill=bg)
    vmin, vmax = min(values), max(values)
    rng = max(vmax - vmin, 1)
    n = len(values)
    def _sx(i): return int(x0 + i * (x1 - x0) / max(1, n - 1))
    def _sy(v): return int(y1 - (v - vmin) / rng * (y1 - y0))
    pts = [(_sx(i), _sy(v)) for i, v in enumerate(values)]
    col = col_up if values[-1] >= values[0] else col_dn
    if len(pts) >= 2:
        draw.line(pts, fill=col, width=2)
    draw.ellipse([(pts[-1][0] - 3, pts[-1][1] - 3),
                  (pts[-1][0] + 3, pts[-1][1] + 3)], fill=col)


# ── Main generator ──────────────────────────────────────────────────────────

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
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not installed.")
        return None

    # ── Palette ────────────────────────────────────────────────────────────
    if theme == "dark":
        BG       = (  9,  11,  21)
        PANEL    = ( 18,  22,  38)
        CARD     = ( 24,  29,  50)
        CARD2    = ( 30,  38,  65)
        CARD3    = ( 38,  48,  80)
        INK      = (230, 235, 252)
        INK2     = (158, 170, 208)
        INK3     = ( 95, 108, 150)
        GLD      = (255, 202,  50)
        GLD2     = (210, 155,  30)
        GLD3     = (255, 230, 130)
        SIL      = (188, 200, 224)
        BLU      = ( 80, 160, 255)
        GRN      = ( 46, 200,  96)
        GRN2     = ( 22, 138,  58)
        RED      = (242,  70,  70)
        RED2     = (172,  38,  38)
        AMB      = (255, 180,  36)
        MUT      = (108, 120, 158)
        DIV      = ( 34,  44,  72)
        SHD      = (  3,   4,  12)
        HDR_L    = ( 14,  22,  68)
        HDR_R    = ( 52,  12,  98)
        C_UP     = ( 38, 195,  92)
        C_DN     = (232,  58,  58)
        GLOW     = (255, 202,  50, 100)
        ACCENT   = ( 80, 160, 255)
    else:
        BG       = (240, 243, 252)
        PANEL    = (248, 250, 255)
        CARD     = (255, 255, 255)
        CARD2    = (235, 240, 255)
        CARD3    = (218, 226, 248)
        INK      = ( 12,  18,  50)
        INK2     = ( 58,  72, 118)
        INK3     = (118, 132, 175)
        GLD      = (152, 100,   0)
        GLD2     = (192, 148,  32)
        GLD3     = (220, 180,  80)
        SIL      = ( 68,  85, 130)
        BLU      = ( 22,  95, 215)
        GRN      = ( 16, 138,  58)
        GRN2     = (  4,  90,  35)
        RED      = (198,  22,  22)
        RED2     = (140,   8,   8)
        AMB      = (180, 115,   0)
        MUT      = (130, 142, 178)
        DIV      = (205, 214, 240)
        SHD      = (175, 182, 212)
        HDR_L    = ( 10,  35, 100)
        HDR_R    = ( 72,  10, 125)
        C_UP     = ( 16, 138,  58)
        C_DN     = (198,  22,  22)
        GLOW     = (152, 100,   0, 85)
        ACCENT   = ( 22,  95, 215)

    W   = 1080
    PAD = 22
    now = datetime.now()

    # ── Fonts ──────────────────────────────────────────────────────────────
    def _fnt(sz, bold=False):
        cands = (
            ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
            if bold else
            ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        )
        for p in cands:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, sz)
                except Exception:
                    pass
        return ImageFont.load_default()

    F48b  = _fnt(48, True)   # hero price
    F32b  = _fnt(32, True)   # large price
    F22b  = _fnt(22, True)   # section subtitle / card price
    F18b  = _fnt(18, True)   # label bold
    F16b  = _fnt(16, True)   # section header text
    F14   = _fnt(14)          # body text
    F13   = _fnt(13)
    F12   = _fnt(12)
    F11   = _fnt(11)

    def _tw(t, f):
        try:
            bb = f.getbbox(str(t)); return bb[2] - bb[0]
        except Exception:
            return len(str(t)) * max(5, getattr(f, "size", 12) // 2)

    # ── Extract values ──────────────────────────────────────────────────────
    usd_inr = (data.get("usd_inr_rate") if data else None) or 84.0
    ibja    = data.get("ibja")       if data else None
    gr_ch   = data.get("gr_chennai") if data else None

    if gr_ch:
        p24k, p22k = gr_ch["24k"], gr_ch["22k"]
        src_lbl = f"Chennai Retail • {gr_ch['date']}"
    elif ibja:
        p24k, p22k = ibja["24k"], ibja["22k"]
        src_lbl = f"IBJA • {ibja['date']}"
    elif data:
        p24k = round(data.get("price_inr_per_g", 0) * INDIA_GOLD_DUTY_FACTOR)
        p22k = round(p24k * 22 / 24)
        src_lbl = "Live estimate"
    else:
        p24k = p22k = 0
        src_lbl = "N/A"

    chg_inr  = data.get("change_inr_g") if data else None   # 24K per gram
    chg_22k  = (chg_inr * 22 / 24) if chg_inr is not None else None
    chg_7d   = (analysis or {}).get("chg_7d")
    chg_30d  = (analysis or {}).get("chg_30d")

    rsi        = (analysis or {}).get("rsi")
    bb_pos     = (analysis or {}).get("bb_pos")
    macd_val   = (analysis or {}).get("macd_val")
    macd_cross = (analysis or {}).get("macd_cross")
    sma20      = (analysis or {}).get("sma20")
    sma50      = (analysis or {}).get("sma50")
    price_usd  = (analysis or {}).get("price_now_usd")
    a_score    = (analysis or {}).get("score", 0)
    a_rec      = (analysis or {}).get("recommendation", "")

    geo_signal = (geo or {}).get("geo_signal", "")
    geo_score  = (geo or {}).get("geo_score", 0)
    bull_cnt   = (geo or {}).get("bull_count", 0)
    bear_cnt   = (geo or {}).get("bear_count", 0)

    pred_dir   = (prediction or {}).get("direction", "FLAT")
    pred_score = float((prediction or {}).get("score", 0))
    geo_s      = float(geo_score)
    combined   = round(a_score + geo_s + pred_score * 0.3, 1)

    hist_rows = (history or [])[:10]
    wk_all    = (weekly_prediction or [])[:7]

    ag_inr_kg = (silver or {}).get("price_inr_kg") or 0
    ag_inr_g  = (silver or {}).get("price_inr_g") or (ag_inr_kg / 1000 if ag_inr_kg else 0)
    ag_chg    = (silver or {}).get("change_inr_g")
    ag_24h_pct = None   # will compute from silver chg
    if ag_inr_g and ag_chg is not None:
        ag_24h_pct = ag_chg / (ag_inr_g - ag_chg) * 100 if (ag_inr_g - ag_chg) else None
    gs_ratio  = (silver or {}).get("gs_ratio")

    votes     = (global_signals or {}).get("votes", {})
    descs     = (global_signals or {}).get("descriptions", {})
    net_score = (global_signals or {}).get("net_score", 0)
    g_outlook = (global_signals or {}).get("global_outlook", "")
    dxy_val   = (global_signals or {}).get("dxy_val")
    vix_val   = (global_signals or {}).get("vix_now")

    best_day     = (payment or {}).get("best_day")
    top3_days    = (payment or {}).get("top3_days", [])
    win_label    = (payment or {}).get("this_month_window", "")
    ml_day       = (payment or {}).get("current_month_low_day")
    ml_price_22k = (payment or {}).get("current_month_low_inr22k")
    ml_trend     = (payment or {}).get("current_month_trend", "")

    # price history series — Sort newest-first so [:10] always gives the last 10 days,
    # then reverse for chart rendering (oldest on left, newest on right).
    def _parse_hist_date(r):
        """Return sortable key from a history row's date string (e.g. '05 Apr')."""
        import datetime as _dt
        ds = str(r.get("date", ""))
        for fmt in ("%d %b", "%Y-%m-%d", "%d-%m-%Y", "%b %d, %Y"):
            try:
                return _dt.datetime.strptime(ds, fmt).date()
            except ValueError:
                pass
        return _dt.date.min

    hist_sorted  = sorted(hist_rows, key=_parse_hist_date, reverse=True)[:10]
    hist_chart   = list(reversed(hist_sorted))   # oldest → newest for chart

    closings_22k = [r.get("22k", 0) for r in hist_chart]
    closings_24k = [r.get("24k", 0) for r in hist_chart]
    # lstrip("0") correctly handles both "05 Apr" → "5 Apr" and "15 Apr" → "15 Apr"
    dates_lbl    = [str(r.get("date", "")).lstrip("0") or str(r.get("date", "")) for r in hist_chart]

    # per-day changes (index i → change vs previous day)
    daily_chg_22k = []
    for i, cl in enumerate(closings_22k):
        daily_chg_22k.append(cl - closings_22k[i - 1] if i > 0 else 0)
    daily_chg_24k = []
    for i, cl in enumerate(closings_24k):
        daily_chg_24k.append(cl - closings_24k[i - 1] if i > 0 else 0)

    n_sig = len(descs)
    n_hl  = len((geo or {}).get("top_headlines", []))

    # ── Section heights ─────────────────────────────────────────────────────
    H_HDR   = 120
    H_KPI   = 140    # taller for per-day change badge
    H_HIST  = 30     # per-day history strip below KPI
    H_CHART = 272
    H_GAUGE = 320
    H_TECH  = 100
    H_SIG   = (n_sig * 36 + 56) if n_sig else 0
    H_BUY   = 112
    H_GEO   = 90 + n_hl * 22
    H_FTR   = 56
    SH      = 42
    GAP     = 14

    n_secs = 5 + (1 if H_SIG else 0)
    TOTAL_H = (H_HDR + H_KPI + H_HIST + H_CHART + H_GAUGE + H_TECH + H_SIG
               + H_BUY + H_GEO + H_FTR + n_secs * SH + GAP * (n_secs + 5) + 30)

    img = Image.new("RGB", (W, TOTAL_H), BG)
    drw = ImageDraw.Draw(img)
    y   = 0

    # ── Internal helpers ────────────────────────────────────────────────────

    def _alpha_poly(pts, rgba):
        nonlocal img, drw
        ov = Image.new("RGBA", (W, TOTAL_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.polygon(pts, fill=rgba)
        base = img.convert("RGBA")
        base.alpha_composite(ov)
        img = base.convert("RGB")
        drw = ImageDraw.Draw(img)

    def _alpha_rect(x0, y0, x1, y1, rgba, radius=0):
        nonlocal img, drw
        ov = Image.new("RGBA", (W, TOTAL_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        if radius:
            od.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=rgba)
        else:
            od.rectangle([(x0, y0), (x1, y1)], fill=rgba)
        base = img.convert("RGBA")
        base.alpha_composite(ov)
        img = base.convert("RGB")
        drw = ImageDraw.Draw(img)

    def _glow_hub(cx, cy, r_out, r_in, rgba):
        nonlocal img, drw
        r, g, b, a = rgba
        ov = Image.new("RGBA", (W, TOTAL_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for rad in range(r_out, r_in - 1, -2):
            al = int(a * (r_out - rad) / max(1, r_out - r_in))
            od.ellipse([(cx - rad, cy - rad), (cx + rad, cy + rad)],
                       fill=(r, g, b, al))
        base = img.convert("RGBA")
        base.alpha_composite(ov)
        img = base.convert("RGB")
        drw = ImageDraw.Draw(img)

    # Section header
    def _sec(label, icon=""):
        nonlocal y
        _h_gradient(drw, PAD, y, W - PAD, y + SH, HDR_L, HDR_R, steps=60)
        drw.rounded_rectangle([(PAD, y), (W - PAD, y + SH)], radius=8,
                               outline=GLD2, width=1)
        drw.rounded_rectangle([(PAD, y), (PAD + 6, y + SH)], radius=4, fill=GLD)
        txt = f"{icon}  {label}" if icon else label
        drw.text((PAD + 16, y + 12), txt, font=F16b, fill=GLD3)
        drw.rectangle([(PAD, y + SH - 2), (W - PAD, y + SH)], fill=GLD2)
        y += SH + 8

    # Pill badge
    def _pill(px, py, txt, bg, fg=None, fnt=None, h=24, pad=10):
        if fnt is None: fnt = F12
        if fg  is None: fg  = INK if sum(bg) > 400 else (BG if sum(bg) > 200 else INK)
        tw  = _tw(txt, fnt)
        pw  = tw + pad * 2
        drw.rounded_rectangle([(px, py), (px + pw, py + h)], radius=h // 2, fill=bg)
        drw.text((px + pad, py + (h - 14) // 2), txt, font=fnt, fill=fg)
        return pw + 6

    # Horizontal progress bar
    def _hbar(x0, y0, x1, y1, pct, fg, bg=None, radius=3):
        if bg is None: bg = CARD3
        drw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=bg)
        fe = x0 + int(max(0.0, min(1.0, pct)) * (x1 - x0))
        if fe > x0:
            drw.rounded_rectangle([(x0, y0), (fe, y1)], radius=radius, fill=fg)

    # Dot meter (segmented)
    def _dots(x0, y0, n=10, filled=5, col_on=None, col_off=None, d=9, gap=4):
        col_on  = col_on  or GLD
        col_off = col_off or CARD3
        for i in range(n):
            cx = x0 + i * (d + gap)
            c  = col_on if i < filled else col_off
            drw.ellipse([(cx, y0), (cx + d, y0 + d)], fill=c)

    def _vote_col(v):
        if   v >= 2:  return GRN2
        elif v == 1:  return GRN
        elif v == 0:  return AMB
        elif v == -1: return RED
        else:         return RED2

    # Change badge helper: coloured inline chip
    def _chg_badge(px, py, chg, unit="", fnt=None):
        """Draw a compact coloured change badge. Returns width used."""
        if fnt is None: fnt = F12
        if chg is None: return 0
        col  = GRN if chg >= 0 else RED
        arr  = "▲" if chg >= 0 else "▼"
        txt  = f"{arr} ₹{abs(chg):,.0f}{unit}"
        tw   = _tw(txt, fnt)
        pw   = tw + 14
        _alpha_rect(px, py, px + pw, py + 20, (*col, 38), radius=4)
        drw.text((px + 7, py + 3), txt, font=fnt, fill=col)
        return pw + 6

    # ======================================================== #
    # ① HERO HEADER                                            #
    # ======================================================== #
    _h_gradient(drw, 0, 0, W, H_HDR, HDR_L, HDR_R, steps=100)
    # subtle diagonal shimmer strip
    _alpha_rect(0, 0, W, H_HDR, (255, 255, 255, 12))
    drw.rectangle([(0, H_HDR - 5), (W, H_HDR)], fill=GLD)

    # App name
    drw.text((PAD, 12), "✦ GOLD PRICE DASHBOARD", font=F22b, fill=GLD3)
    # Date / time
    if os.name == "nt":
        dt_str = now.strftime("%#d %B %Y   ·   %H:%M IST")
    else:
        dt_str = now.strftime("%-d %B %Y   ·   %H:%M IST")
    drw.text((PAD, 44), dt_str, font=F14, fill=INK2)
    drw.text((PAD, 66), f"Source: {src_lbl}", font=F11, fill=MUT)

    # Right — hero 22K price + today's change
    h_val = f"₹{p22k:,}"
    hx = W - _tw(h_val, F48b) - PAD
    drw.text((hx, 6), h_val, font=F48b, fill=GLD)
    drw.text((hx, 60), "22K / gram", font=F11, fill=MUT)
    if chg_22k is not None:
        bx = hx - 160
        _chg_badge(bx, 40, chg_22k, "/g", fnt=F13)
        # pct change
        pct_col = GRN if chg_22k >= 0 else RED
        if chg_30d:
            drw.text((bx, 64), f"30d {chg_30d:+.1f}%", font=F11, fill=pct_col)

    y = H_HDR + GAP

    # ======================================================== #
    # ② KPI CARDS  22K | 24K | Silver | USD/INR               #
    # ======================================================== #
    gap_c   = 12
    cw_hero = (W - 2 * PAD - 3 * gap_c) * 33 // 100
    cw_rest = (W - 2 * PAD - cw_hero - 3 * gap_c) // 3
    card_ws = [cw_hero, cw_rest, cw_rest, cw_rest]

    # Build per-day change for silver & usd
    ag_chg_g   = ag_chg          # silver per gram change
    usd_chg    = None             # no direct delta, skip

    kpi_data = [
        # (label, price_txt, unit, accent, per_day_chg, pct_str, sub2, is_hero)
        ("22K GOLD",
         f"₹{p22k:,}", "/g", GLD,
         chg_22k,
         f"7d {chg_7d:+.1f}%" if chg_7d else None,
         f"8g ₹{p22k*8:,}  ·  10g ₹{p22k*10:,}",
         True),
        ("24K GOLD",
         f"₹{p24k:,}", "/g", GLD2,
         chg_inr,
         f"30d {chg_30d:+.1f}%" if chg_30d else None,
         None, False),
        ("SILVER 999",
         f"₹{ag_inr_g:,.1f}" if ag_inr_g else "—", "/g", SIL,
         ag_chg_g,
         f"G/S {gs_ratio:.0f}" if gs_ratio else None,
         None, False),
        ("USD / INR",
         f"₹{usd_inr:.2f}", "", BLU,
         None,
         f"DXY {dxy_val:.1f}" if dxy_val else None,
         f"VIX {vix_val:.1f}" if vix_val else None,
         False),
    ]

    spark_22 = closings_22k[-7:]   # last 7 of the sorted oldest→newest series
    spark_24 = closings_24k[-7:]

    for idx, (lbl, val, unit, acc, day_chg, sub1, sub2, hero) in enumerate(kpi_data):
        cx0 = PAD + sum(card_ws[:idx]) + idx * gap_c
        cx1 = cx0 + card_ws[idx]
        cy0, cy1 = y, y + H_KPI
        _shadow_rect(drw, cx0, cy0, cx1, cy1, PANEL, radius=12, soff=5, scol=SHD)
        # top accent stripe — gradient
        _h_gradient(drw, cx0, cy0, cx1, cy0 + (8 if hero else 5), acc, GLD3 if hero else acc, steps=20)
        drw.rounded_rectangle([(cx0, cy0), (cx1, cy0 + (8 if hero else 5))],
                               radius=6, outline=acc, width=0)

        px = cx0 + 14
        # Label
        drw.text((px, cy0 + 14), lbl, font=F12, fill=acc if hero else INK3)
        # Main price
        vf = F22b if hero else F18b
        drw.text((px, cy0 + 32), val, font=vf, fill=INK)
        if unit:
            drw.text((px + _tw(val, vf) + 4, cy0 + 42), unit, font=F11, fill=INK3)

        # Per-day change badge
        if day_chg is not None:
            _chg_badge(px, cy0 + 72, day_chg, "/g", fnt=F12)
        elif idx == 3:  # USD card no chg, show COMEX
            if price_usd:
                drw.text((px, cy0 + 72), f"COMEX ${price_usd:,.1f}/oz", font=F12, fill=INK3)

        # sub1 — percentage or note
        if sub1:
            s1col = GRN if "+" in sub1 else (RED if "-" in sub1 else INK3)
            drw.text((px, cy0 + 94), sub1, font=F11, fill=s1col)

        # sub2
        if sub2:
            drw.text((px, cy0 + 110), sub2, font=F11, fill=MUT)

        # sparkline at bottom right of hero/24K cards
        if idx in (0, 1):
            spark = spark_22 if idx == 0 else spark_24
            if len(spark) >= 2:
                sk_x0 = cx1 - 70
                sk_y0 = cy0 + 70
                sk_x1 = cx1 - 8
                sk_y1 = cy0 + H_KPI - 8
                _sparkline(drw, sk_x0, sk_y0, sk_x1, sk_y1, spark, GRN, RED, bg=CARD2)

    y += H_KPI + GAP

    # ── Per-day change strip (history bar) ─────────────────────────────────
    if closings_22k and len(closings_22k) >= 2:
        strip_h = H_HIST
        drw.rounded_rectangle([(PAD, y), (W - PAD, y + strip_h)], radius=8, fill=PANEL)
        drw.rounded_rectangle([(PAD, y), (PAD + 5, y + strip_h)], radius=3, fill=GLD)
        drw.text((PAD + 14, y + 8), "DAILY 22K CHANGES", font=F11, fill=MUT)
        n_show  = min(len(closings_22k), 7)
        cell_w  = (W - 2 * PAD - 20) // n_show
        idxs    = list(range(max(0, len(closings_22k) - n_show), len(closings_22k)))
        for j, ii in enumerate(idxs):
            dc  = daily_chg_22k[ii]
            col = GRN if dc >= 0 else RED
            arr = "▲" if dc >= 0 else "▼"
            dx  = PAD + 20 + j * cell_w
            lbl_d = dates_lbl[ii] if ii < len(dates_lbl) else ""
            drw.text((dx, y + 7), lbl_d, font=F11, fill=INK3)
            drw.text((dx, y + 17), f"{arr}{abs(dc):,.0f}", font=F11, fill=col)
        y += strip_h + GAP

    # ======================================================== #
    # ③ 10-DAY LINE + AREA CHART                               #
    # ======================================================== #
    if len(closings_22k) >= 2:
        _sec("10-DAY 22K PRICE TREND", "📈")
        ch = H_CHART - 8
        split_x = PAD + int((W - 2 * PAD) * 0.70)

        # Chart background
        drw.rounded_rectangle([(PAD, y), (split_x, y + ch)], radius=12, fill=PANEL)
        _v_gradient(drw, PAD + 2, y + 2, split_x - 2, y + ch - 2, PANEL, CARD2, steps=40)

        n_pts  = len(closings_22k)
        cmin   = min(closings_22k); cmax = max(closings_22k)
        pad_pct = 0.10
        lo_ext = cmin - (cmax - cmin) * pad_pct
        hi_ext = cmax + (cmax - cmin) * pad_pct
        rng    = max(hi_ext - lo_ext, 1)

        LP, RP, TP, BP = 62, 16, 20, 32
        ax0 = PAD + LP; ax1 = split_x - RP
        ay0 = y + TP;   ay1 = y + ch - BP

        # evenly spaced x — point i sits at fraction i/(n-1)
        def _cx(i): return int(ax0 + i * (ax1 - ax0) / max(1, n_pts - 1))
        def _cy(p): return int(ay1 - (p - lo_ext) / rng * (ay1 - ay0))

        # ── Horizontal grid lines + left price axis ───────────────────────
        for gp in [0.0, 0.25, 0.5, 0.75, 1.0]:
            gy  = int(ay1 - gp * (ay1 - ay0))
            pv  = lo_ext + gp * rng
            drw.line([(ax0, gy), (ax1, gy)], fill=DIV, width=1)
            lbl_str = f"₹{pv:,.0f}"
            drw.text((PAD + 2, gy - 7), lbl_str, font=F11, fill=MUT)

        # ── Vertical day guide lines ──────────────────────────────────────
        for i in range(n_pts):
            gx = _cx(i)
            drw.line([(gx, ay0), (gx, ay1)], fill=DIV, width=1)

        # ── Gradient area fill (two-pass: deep bottom + lighter top) ─────
        area_pts = [(_cx(0), ay1)]
        for i, cl in enumerate(closings_22k):
            area_pts.append((_cx(i), _cy(cl)))
        area_pts.append((_cx(n_pts - 1), ay1))

        # Deep fill (bottom half)
        _alpha_poly(area_pts, (C_UP[0], C_UP[1], C_UP[2], 55))
        # Lighter top wash for gradient feel
        top_wash = [(_cx(0), int(ay0 + (ay1 - ay0) * 0.4))]
        for i, cl in enumerate(closings_22k):
            top_wash.append((_cx(i), _cy(cl)))
        top_wash.append((_cx(n_pts - 1), int(ay0 + (ay1 - ay0) * 0.4)))
        _alpha_poly(top_wash, (C_UP[0], C_UP[1], C_UP[2], 25))

        # ── Smooth line ───────────────────────────────────────────────────
        line_pts = [(_cx(i), _cy(cl)) for i, cl in enumerate(closings_22k)]
        # overall trend colour: green if last > first, else red
        trend_up  = closings_22k[-1] >= closings_22k[0]
        line_col  = C_UP if trend_up else C_DN
        if len(line_pts) >= 2:
            drw.line(line_pts, fill=line_col, width=3)

        # ── Data-point dots + per-day change labels ───────────────────────
        for i, cl in enumerate(closings_22k):
            px, py2 = _cx(i), _cy(cl)
            is_up   = cl >= closings_22k[i - 1] if i > 0 else True
            dot_col = C_UP if is_up else C_DN
            # outer glow ring
            drw.ellipse([(px - 6, py2 - 6), (px + 6, py2 + 6)], fill=PANEL)
            # filled dot
            drw.ellipse([(px - 4, py2 - 4), (px + 4, py2 + 4)], fill=dot_col)
            # white centre pin
            drw.ellipse([(px - 1, py2 - 1), (px + 1, py2 + 1)], fill=CARD)

            # per-day change label above each point
            if i > 0:
                dc     = daily_chg_22k[i]
                dc_col = C_UP if dc >= 0 else C_DN
                dc_arr = "▲" if dc >= 0 else "▼"
                dc_txt = f"{dc_arr}{abs(dc):,.0f}"
                tw_dc  = _tw(dc_txt, F11)
                label_y = py2 - 18
                # keep label inside chart top
                if label_y < ay0 + 2:
                    label_y = py2 + 8
                drw.text((px - tw_dc // 2, label_y), dc_txt, font=F11, fill=dc_col)

            # date label below axis (every point)
            if i < len(dates_lbl):
                dl    = dates_lbl[i]
                tw_dl = _tw(dl, F11)
                drw.text((px - tw_dl // 2, ay1 + 5), dl, font=F11, fill=INK3)

        # ── Current price callout tag ─────────────────────────────────────
        lx, ly = _cx(n_pts - 1), _cy(closings_22k[-1])
        pl  = f"₹{closings_22k[-1]:,}"
        pw  = _tw(pl, F11) + 12
        tag_x = max(ax0, lx - pw // 2)
        drw.rounded_rectangle([(tag_x, ly - 20), (tag_x + pw, ly - 6)],
                               radius=4, fill=GLD)
        drw.text((tag_x + 6, ly - 19), pl, font=F11,
                 fill=BG if sum(GLD) > 350 else INK)

        # ── Stats panel ──────────────────────────────────────────────────
        sx0 = split_x + 8
        drw.rounded_rectangle([(sx0, y), (W - PAD, y + ch)], radius=12, fill=PANEL)
        # Header
        _h_gradient(drw, sx0, y, W - PAD, y + 34, GLD2, GLD, steps=30)
        drw.rounded_rectangle([(sx0, y), (W - PAD, y + 34)], radius=10, outline=GLD2, width=0)
        spx = sx0 + 14
        drw.text((spx, y + 9), "COMEX / STATS", font=F14, fill=BG if sum(GLD) > 350 else INK)

        sy = y + 42
        if price_usd:
            drw.text((spx, sy), f"${price_usd:,.1f}  /oz", font=F18b, fill=INK); sy += 26
        for sl, sv, sc in [
            ("1-Day Chg", f"₹{abs(chg_22k):,.0f}/g" if chg_22k is not None else "—",
             GRN if (chg_22k or 0) >= 0 else RED),
            ("7d Chg",  f"{chg_7d:+.2f}%"  if chg_7d  else "—",
             GRN if (chg_7d  or 0) > 0 else RED),
            ("30d Chg", f"{chg_30d:+.2f}%" if chg_30d else "—",
             GRN if (chg_30d or 0) > 0 else RED),
        ]:
            drw.text((spx, sy), sl, font=F11, fill=INK3); sy += 14
            arr2 = ("▲ " if sv.lstrip("-").lstrip("₹").replace(",","").replace("+","").replace(".","").isdigit() or True else "")
            drw.text((spx, sy), sv, font=F14, fill=sc); sy += 20
        sy += 4
        drw.line([(spx, sy), (W - PAD - 12, sy)], fill=DIV, width=1); sy += 10

        # 22K vs yesterday
        drw.text((spx, sy), "22K vs yesterday", font=F11, fill=INK3); sy += 14
        if len(closings_22k) >= 2:
            d1 = closings_22k[-1] - closings_22k[-2]
            d1c = GRN if d1 >= 0 else RED
            drw.text((spx, sy), f"{'▲' if d1>=0 else '▼'} ₹{abs(d1):,}/g",
                     font=F14, fill=d1c); sy += 22
        drw.line([(spx, sy), (W - PAD - 12, sy)], fill=DIV, width=1); sy += 8

        # Multiples
        if closings_22k:
            cv = closings_22k[-1]
            drw.text((spx, sy), "22K multiples", font=F11, fill=INK3); sy += 14
            for g, v in [(8, cv * 8), (10, cv * 10), (12, cv * 12)]:
                drw.text((spx, sy), f"{g}g = ₹{v:,}", font=F11, fill=INK2); sy += 13

        # Trend sparkline
        if len(spark_22) >= 2:
            sy += 8
            drw.text((spx, sy), "10-day trend", font=F11, fill=INK3); sy += 14
            _sparkline(drw, spx, sy, W - PAD - 14, sy + 32, spark_22, GRN, RED, bg=CARD2)

        y += ch + GAP

    # ======================================================== #
    # ④ SIGNAL GAUGE + 7-DAY FORECAST                          #
    # ======================================================== #
    _sec("PREDICTION & SIGNAL GAUGE", "⚡")
    ga_top = y

    # Gauge (left half)
    GCX = PAD + (W // 2 - PAD) // 2
    GCY = y + 165
    GR  = 112

    def _gauge(score):
        t  = max(-1.0, min(1.0, score / 10))
        nd = 180 + t * 82

        # Zone arcs (background glow rings first)
        zones_def = [(180, 222, RED2, "SELL"), (222, 252, RED, ""),
                     (252, 278, CARD3, ""), (278, 308, GRN, ""),
                     (308, 360, GRN2, "BUY")]
        for sa, ea, col, _ in zones_def:
            # subtle glow behind arc
            _alpha_poly(
                [(GCX, GCY)] + [(GCX + (GR + 18) * _math.cos(_math.radians(d)),
                                  GCY + (GR + 18) * _math.sin(_math.radians(d)))
                                 for d in range(int(sa), int(ea) + 1, 3)] + [(GCX, GCY)],
                (*col, 30)
            )
            drw.arc([(GCX - GR, GCY - GR), (GCX + GR, GCY + GR)],
                    start=sa, end=ea, fill=col, width=26)
        # Outer ring
        drw.arc([(GCX - GR - 5, GCY - GR - 5), (GCX + GR + 5, GCY + GR + 5)],
                start=180, end=360, fill=DIV, width=2)
        # Inner ring
        drw.arc([(GCX - GR + 26, GCY - GR + 26), (GCX + GR - 26, GCY + GR - 26)],
                start=180, end=360, fill=DIV, width=1)

        # Ticks
        for deg in range(180, 361, 18):
            r2 = _math.radians(deg)
            t_len = 8 if deg % 36 == 0 else 4
            x1 = GCX + (GR + 5) * _math.cos(r2); y1 = GCY + (GR + 5) * _math.sin(r2)
            x2 = GCX + (GR - t_len) * _math.cos(r2); y2 = GCY + (GR - t_len) * _math.sin(r2)
            drw.line([(x1, y1), (x2, y2)], fill=INK3, width=1)

        # Labels
        drw.text((GCX - GR - 30, GCY + 8), "SELL", font=F11, fill=RED)
        drw.text((GCX + GR + 8,  GCY + 8), "BUY",  font=F11, fill=GRN)

        # Glow around hub
        _glow_hub(GCX, GCY, r_out=36, r_in=12, rgba=GLOW)

        # Needle
        nr  = _math.radians(nd)
        nx  = GCX + (GR - 22) * _math.cos(nr)
        ny2 = GCY + (GR - 22) * _math.sin(nr)
        drw.line([(GCX, GCY), (nx, ny2)], fill=SHD, width=8)
        drw.line([(GCX, GCY), (nx, ny2)], fill=GLD2, width=5)
        drw.line([(GCX, GCY), (nx, ny2)], fill=GLD, width=2)
        # Hub
        drw.ellipse([(GCX - 11, GCY - 11), (GCX + 11, GCY + 11)], fill=GLD)
        drw.ellipse([(GCX - 5,  GCY - 5),  (GCX + 5,  GCY + 5)],  fill=INK)

        # Score text
        st = f"Score: {score:+.1f}"
        drw.text((GCX - _tw(st, F14) // 2, GCY + 18), st, font=F14, fill=INK)
        if   score >= 7:   ver, vc = "STRONG BUY",  GRN2
        elif score >= 3:   ver, vc = "BUY",          GRN
        elif score <= -7:  ver, vc = "STRONG SELL",  RED2
        elif score <= -3:  ver, vc = "SELL",          RED
        else:              ver, vc = "NEUTRAL",       AMB
        drw.text((GCX - _tw(ver, F22b) // 2, GCY + 38), ver, font=F22b, fill=vc)

    _gauge(combined)

    # Forecast panel (right half)
    fx0 = W // 2 + 8
    fy0 = ga_top
    fy1 = ga_top + H_GAUGE - GAP
    _shadow_rect(drw, fx0, fy0, W - PAD, fy1, PANEL, radius=10, soff=4, scol=SHD)
    _h_gradient(drw, fx0, fy0, W - PAD, fy0 + 34, GLD2, GLD, steps=30)
    drw.text((fx0 + 14, fy0 + 9), "7-DAY FORECAST", font=F16b,
             fill=BG if sum(GLD) > 350 else INK)

    wry = fy0 + 40
    for hdr, x in [("Day", fx0 + 14), ("Dir", fx0 + 68), ("22K mid", fx0 + 122),
                   ("Range (low – high)", fx0 + 248)]:
        drw.text((x, wry), hdr, font=F11, fill=GLD if hdr == "22K mid" else INK3)
    wry += 18
    drw.line([(fx0 + 8, wry), (W - PAD - 8, wry)], fill=DIV, width=1)
    wry += 6

    fc_mids, fc_los, fc_his, fc_dirs = [], [], [], []

    for row in wk_all[:7]:
        is_wk   = row.get("is_weekend", False)
        wd      = str(row.get("weekday", ""))[:3]
        dirn    = str(row.get("direction", "FLAT")).upper()
        mid_22  = row.get("mid_22k") or round((row.get("mid_inr", 0) or 0) * 22 / 24)
        lo_22   = row.get("low_22k") or round((row.get("low_inr",  mid_22) or mid_22) * 22 / 24)
        hi_22   = row.get("high_22k") or round((row.get("high_inr", mid_22) or mid_22) * 22 / 24)

        if not is_wk and mid_22:
            fc_mids.append(mid_22); fc_los.append(lo_22)
            fc_his.append(hi_22);   fc_dirs.append(dirn)

        if wry < fy1 - 72:
            if is_wk:
                _alpha_rect(fx0 + 6, wry - 2, W - PAD - 6, wry + 24, (*CARD2, 180), radius=4)
                drw.text((fx0 + 14, wry + 4), wd, font=F12, fill=INK3)
                drw.text((fx0 + 68, wry + 4), "Weekend", font=F12, fill=MUT)
            else:
                pcol = GRN2 if "UP" in dirn else (RED2 if "DOWN" in dirn else AMB)
                arr3 = "▲" if "UP" in dirn else ("▼" if "DOWN" in dirn else "—")
                drw.text((fx0 + 14, wry + 4), wd, font=F13, fill=INK)
                _pill(fx0 + 60, wry + 2, f"{arr3} {dirn}", pcol, fnt=F11, h=20)
                drw.text((fx0 + 122, wry + 4), f"₹{mid_22:,}", font=F13, fill=GLD)
                drw.text((fx0 + 248, wry + 4), f"₹{lo_22:,} – ₹{hi_22:,}", font=F11, fill=INK2)
            wry += 28

    # Forecast area mini-chart
    if len(fc_mids) >= 2:
        wry += 6
        drw.line([(fx0 + 8, wry), (W - PAD - 8, wry)], fill=DIV, width=1); wry += 6
        drw.text((fx0 + 14, wry), "Forecast confidence band", font=F11, fill=INK3); wry += 14
        fc_x0 = fx0 + 10; fc_x1 = W - PAD - 10
        fc_y0 = wry;       fc_y1 = min(wry + 50, fy1 - 10)
        if fc_y1 - fc_y0 >= 20:
            drw.rounded_rectangle([(fc_x0, fc_y0), (fc_x1, fc_y1)], radius=6, fill=CARD2)
            fa = fc_los + fc_his
            fmn = min(fa); fmx = max(fa); frng = max(fmx - fmn, 1)
            nf  = len(fc_mids)
            def _fx(i2): return int(fc_x0 + i2 * (fc_x1 - fc_x0) / max(1, nf - 1))
            def _fy(v2): return int(fc_y1 - (v2 - fmn) / frng * (fc_y1 - fc_y0))
            band_top = [(_fx(i2), _fy(fc_his[i2])) for i2 in range(nf)]
            band_bot = [(_fx(i2), _fy(fc_los[i2]))  for i2 in range(nf)]
            _alpha_poly(band_top + list(reversed(band_bot)),
                        (C_UP[0], C_UP[1], C_UP[2], 55))
            mid_pts = [(_fx(i2), _fy(fc_mids[i2])) for i2 in range(nf)]
            if len(mid_pts) >= 2:
                drw.line(mid_pts, fill=GLD, width=2)
            for i2, (fxp, fyp) in enumerate(mid_pts):
                dc2 = GRN if "UP" in fc_dirs[i2] else (RED if "DOWN" in fc_dirs[i2] else AMB)
                drw.ellipse([(fxp - 4, fyp - 4), (fxp + 4, fyp + 4)], fill=dc2, outline=CARD, width=1)

    if g_outlook:
        oc = (g_outlook.replace("🟢","").replace("🔴","").replace("🟡","")
              .replace("⚪","").replace("🟠","").strip())
        drw.text((fx0 + 14, fy1 - 18), f"Macro Outlook: {oc}"[:46], font=F11, fill=INK2)

    y = ga_top + H_GAUGE

    # ======================================================== #
    # ⑤ TECHNICAL INDICATORS — DOT METERS                      #
    # ======================================================== #
    _sec("TECHNICAL INDICATORS", "📊")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_TECH)], radius=10, fill=PANEL)
    _h_gradient(drw, PAD + 2, y + 2, W - PAD - 2, y + 32, PANEL, CARD2, steps=40)

    cols  = 5
    cw_ti = (W - 2 * PAD - 20) // cols
    ti_items = [
        ("RSI (14)", f"{rsi:.1f}" if rsi is not None else "—",
         GRN if rsi and rsi < 45 else (RED if rsi and rsi > 70 else AMB),
         (rsi or 50) / 100 if rsi else 0.5),
        ("MACD", f"{macd_val:+.2f}" if macd_val is not None else "—",
         GRN if macd_cross and macd_cross > 0 else RED,
         max(0.0, min(1.0, 0.5 + (macd_cross or 0) / 20))),
        ("BB Pos", f"{bb_pos * 100:.0f}%" if bb_pos is not None else "—",
         GRN if bb_pos and bb_pos < 0.3 else (RED if bb_pos and bb_pos > 0.7 else AMB),
         bb_pos or 0.5),
        ("Tech Score", f"{a_score:+d}",
         GRN if a_score >= 2 else (RED if a_score <= -2 else AMB),
         max(0.0, min(1.0, (a_score + 8) / 16))),
        ("Macro Net", f"{net_score:+d}",
         GRN if net_score >= 2 else (RED if net_score <= -2 else AMB),
         max(0.0, min(1.0, (net_score + 10) / 20))),
    ]

    for ci, (lbl, val, vcol, pct) in enumerate(ti_items):
        tx = PAD + 10 + ci * cw_ti
        drw.text((tx, y + 9),  lbl, font=F11,  fill=INK3)
        drw.text((tx, y + 24), val, font=F18b, fill=vcol)
        n_d = 10
        fil = max(0, min(n_d, round(pct * n_d)))
        _dots(tx, y + H_TECH - 22, n=n_d, filled=fil, col_on=vcol, col_off=CARD3)
        drw.text((tx, y + H_TECH - 8), f"{int(pct*100)}%", font=F11, fill=INK3)
        if ci < cols - 1:
            drw.line([(tx + cw_ti - 6, y + 12), (tx + cw_ti - 6, y + H_TECH - 12)],
                     fill=DIV, width=1)

    if sma20 and sma50 and price_usd:
        sma_t = f"SMA20 ${sma20:,.0f}  ·  SMA50 ${sma50:,.0f}  ·  Price ${price_usd:,.0f}"
        drw.text((PAD + 12, y + H_TECH - 4), sma_t, font=F11, fill=MUT)

    y += H_TECH + GAP

    # ======================================================== #
    # ⑥ BUYING GUIDE                                           #
    # ======================================================== #
    _sec("BUYING GUIDE & RECOMMENDATION", "💡")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_BUY)], radius=10, fill=PANEL)

    cw3  = (W - 2 * PAD - 20) // 3
    pg1  = PAD + 14

    # Col 1 – Best day
    drw.text((pg1, y + 10), "Best Day to Buy", font=F11, fill=INK3)
    if best_day:
        drw.text((pg1, y + 26), f"📅 {_ordinal(best_day)} of month", font=F18b, fill=GLD)
        if win_label:
            drw.text((pg1, y + 52), f"Window: {win_label}", font=F11, fill=INK2)
        if top3_days:
            drw.text((pg1, y + 66), f"Top 3: {', '.join(_ordinal(d) for d in top3_days)}",
                     font=F11, fill=MUT)
    drw.line([(PAD + cw3 + 6, y + 10), (PAD + cw3 + 6, y + H_BUY - 10)], fill=DIV, width=1)

    # Col 2 – Month low 22K
    pg2 = PAD + cw3 + 20
    drw.text((pg2, y + 10), "Month Low  (22K)", font=F11, fill=INK3)
    if ml_day:
        drw.text((pg2, y + 26), f"📉 {_ordinal(ml_day)}", font=F18b, fill=GRN)
        if ml_price_22k:
            drw.text((pg2, y + 52), f"₹{ml_price_22k:,}/g", font=F14, fill=INK2)
        if ml_trend:
            tc = GRN if ml_trend == "falling" else (RED if ml_trend == "rising" else INK2)
            drw.text((pg2, y + 72), f"Trend: {ml_trend}", font=F11, fill=tc)
    else:
        drw.text((pg2, y + 26), "Calculating…", font=F14, fill=MUT)
    drw.line([(PAD + cw3 * 2 + 10, y + 10), (PAD + cw3 * 2 + 10, y + H_BUY - 10)], fill=DIV, width=1)

    # Col 3 – Recommendation
    pg3 = PAD + cw3 * 2 + 22
    drw.text((pg3, y + 10), "Today's Recommendation", font=F11, fill=INK3)
    if a_rec:
        rc = (a_rec.replace("🟢","").replace("🔴","").replace("🟡","")
             .replace("⚪","").replace("🟠","").strip())
        rcol = GRN if "BUY" in a_rec.upper() else (RED if any(
            w in a_rec.upper() for w in ("AVOID","WAIT","SELL")) else AMB)
        parts = rc.split(" – ")
        drw.text((pg3, y + 26), parts[0][:24], font=F18b, fill=rcol)
        if len(parts) > 1:
            drw.text((pg3, y + 52), parts[1][:32], font=F11, fill=INK2)
    drw.text((pg3, y + 78), f"Signal: {pred_dir}  ({pred_score:+.1f})", font=F11, fill=INK2)

    y += H_BUY + GAP

    # ======================================================== #
    # ⑦ GEOPOLITICAL SENTIMENT                                 #
    # ======================================================== #
    _sec("GEOPOLITICAL SENTIMENT", "🌍")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_GEO)], radius=10, fill=PANEL)

    gc2  = (geo_signal.replace("🔴","").replace("🟠","").replace("🟡","").replace("🟢","").strip())
    gcol = GRN if geo_score < 0 else (RED if geo_score >= 2 else AMB)
    drw.text((PAD + 14, y + 10), gc2[:60], font=F18b, fill=gcol)

    ppx2 = PAD + 14
    ppx2 += _pill(ppx2, y + 38, f"▲ {bull_cnt} bullish", GRN2, fnt=F12, h=24)
    ppx2 += _pill(ppx2, y + 38, f"▼ {bear_cnt} bearish", RED2, fnt=F12, h=24)

    hls = (geo or {}).get("top_headlines", [])
    hly2 = y + 70
    for htitle, hbc, hbrc in hls[:n_hl]:
        hcol2 = GRN2 if hbc > hbrc else (RED2 if hbrc > hbc else MUT)
        drw.text((PAD + 14, hly2), f"• {htitle[:92]}", font=F11, fill=hcol2)
        hly2 += 20

    y += H_GEO + GAP

    # ======================================================== #
    # ⑧ WORLD MACRO SIGNALS                                    #
    # ======================================================== #
    if descs:
        _sec("WORLD MACRO SIGNALS", "🌐")
        row_h   = 36
        n_show  = min(len(descs), 12)
        t_h     = n_show * row_h + 6

        CN, CV, CP = 178, 82, 104
        # header row
        drw.rounded_rectangle([(PAD, y), (W - PAD, y + 24)], radius=4, fill=CARD3)
        for hdr_txt, hx2 in [("Indicator",  PAD + 30),
                              ("Signal bar", PAD + CN),
                              ("Value",      W - PAD - CP - CV + 4),
                              ("Rating",     W - PAD - CP + 10)]:
            drw.text((hx2, y + 5), hdr_txt, font=F11, fill=INK3)
        y += 24

        SIG_MAP = {
            "real_yield":    ("Real Yield",    "tip_val"),
            "dxy":           ("DXY Dollar",    "dxy_val"),
            "yields":        ("10Y Yield",     "yield_now"),
            "yield_curve":   ("Yield Curve",   "yield_curve_spread"),
            "vix":           ("VIX Fear",      "vix_now"),
            "risk_assets":   ("S&P 500 1d",    "sp500_1d"),
            "oil":           ("Oil 5d%",       "oil_5d"),
            "silver_ratio":  ("Gold/Silver",   "gold_silver_ratio"),
            "copper":        ("Copper 5d%",    "copper_5d"),
            "eur_usd":       ("EUR/USD",       "eurusd_val"),
            "etf_flow":      ("GLD ETF 5d",    "gld_5d"),
            "gold_momentum": ("Gold 5d%",      "gold_5d"),
        }

        for ri, (key, _) in enumerate(descs.items()):
            if ri >= n_show: break
            ry     = y + ri * row_h
            row_bg = PANEL if ri % 2 == 0 else CARD
            drw.rectangle([(PAD, ry), (W - PAD, ry + row_h - 2)], fill=row_bg)
            vote   = votes.get(key, 0)
            vc     = _vote_col(vote)
            # dot
            drw.ellipse([(PAD + 8, ry + 12), (PAD + 22, ry + 26)], fill=vc)
            # name
            nm = SIG_MAP.get(key, (key.replace("_", " ").title(), ""))[0]
            drw.text((PAD + 28, ry + 11), nm[:22], font=F13, fill=INK)
            # bar
            bx0 = PAD + CN; bx1 = W - PAD - CP - CV - 8
            norm = max(0.0, min(1.0, (vote + 2) / 4))
            _hbar(bx0, ry + 14, bx1, ry + 22, norm, vc)
            # value
            rk  = SIG_MAP.get(key, ("", ""))[1]
            rv  = (global_signals or {}).get(rk)
            vt2 = ""
            if rv is not None:
                vt2 = f"{rv:.2f}" if isinstance(rv, float) and abs(rv) < 100 else (
                    f"{rv:.0f}" if isinstance(rv, float) else str(rv))
            drw.text((W - PAD - CP - CV + 4, ry + 11), vt2[:10], font=F13, fill=INK2)
            # rating pill
            rl = {2:"BULLISH",1:"MILD ▲",0:"NEUTRAL",-1:"MILD ▼",-2:"BEARISH"}.get(vote, str(vote))
            _pill(W - PAD - CP + 2, ry + 7, rl, vc, fnt=F11, h=22)

        y += t_h + GAP

    # ======================================================== #
    # ⑨ FOOTER                                                 #
    # ======================================================== #
    fy = TOTAL_H - H_FTR
    _h_gradient(drw, 0, fy, W, TOTAL_H, HDR_R, HDR_L, steps=70)
    drw.rectangle([(0, fy), (W, fy + 4)], fill=GLD)
    drw.text((PAD, fy + 18),
             "Data: COMEX/MCX  ·  INR includes 15.5% duty+GST  ·  Not financial advice",
             font=F11, fill=INK2)
    if os.name == "nt":
        ts = now.strftime("Generated %#d %B %Y  %H:%M IST")
    else:
        ts = now.strftime("Generated %-d %B %Y  %H:%M IST")
    drw.text((W - PAD - _tw(ts, F11), fy + 18), ts, font=F11, fill=INK3)
    drw.text((PAD, fy + 36), "✦ premtechiee/automations  |  Gold Notifier Bot",
             font=F11, fill=MUT)

    # ── Save ────────────────────────────────────────────────────────────────
    final_h = min(TOTAL_H, y + H_FTR + 10)
    img = img.crop((0, 0, W, final_h))
    img.save(out_path, format="PNG", optimize=True)
    logger.info("Image saved → %s  (%dx%d)", out_path, W, final_h)
    return out_path
