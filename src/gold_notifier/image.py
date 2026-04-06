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
    grt: dict | None = None,
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

    W   = 1440   # wider canvas for mobile readability (was 1080)
    PAD = 30
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

    F64b  = _fnt(70, True)   # hero price
    F48b  = _fnt(53, True)   # large price / hero fallback
    F30b  = _fnt(34, True)   # section subtitle / card price
    F24b  = _fnt(28, True)   # label bold / card price secondary
    F22b  = _fnt(26, True)   # section header text
    F18b  = _fnt(22, True)   # sub-label bold
    F16b  = _fnt(20, True)   # body bold
    F15   = _fnt(18)          # body text
    F14   = _fnt(17)
    F13   = _fnt(16)
    # Aliases kept for backward compat across all draw calls below
    # (old F11→F15, F12→F16b, F13→F18b, F14→F15, F16b→F22b, F18b→F24b, F22b→F30b, F48b→F64b)
    F11   = F15
    F12   = F16b
    F13   = F18b
    F14   = F15
    F16b  = F22b
    F18b  = F24b
    F22b  = F30b
    F48b  = F64b

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

    grt_22k    = (grt or {}).get("22k")
    grt_24k    = (grt or {}).get("24k")
    grt_src    = (grt or {}).get("source", "GRT Jewellers")
    grt_date   = (grt or {}).get("date", "")
    grt_offers = (grt or {}).get("offers", [])

    n_sig        = len(descs)
    n_hl         = len((geo or {}).get("top_headlines", []))
    n_grt_offers = len(grt_offers)

    # ── Section heights ─────────────────────────────────────────────────────
    # All values scaled ~33% vs the original 1080px design for mobile readability
    H_HDR   = 180
    H_KPI_CARD = 215                              # height of each individual KPI card
    H_KPI   = H_KPI_CARD + (168 if grt_22k else 0)  # +168px GRT sub-row when available
    H_HIST  = 56
    H_CHART = 380
    H_GAUGE = 440
    H_TECH  = 156
    H_SIG   = (n_sig * 56 + 84) if n_sig else 0
    H_BUY   = 174
    H_GEO   = 140 + n_hl * 32
    # GRT section: offers-only strip (prices are now in the KPI sub-row)
    H_GRT   = (n_grt_offers * 26 + 46) if (grt_22k and n_grt_offers) else 0
    H_FTR   = 72
    SH      = 64
    GAP     = 20

    n_secs  = 5 + (1 if H_SIG else 0) + (1 if H_GRT else 0)
    TOTAL_H = (H_HDR + H_KPI + H_HIST + H_CHART + H_GAUGE + H_TECH + H_SIG
               + H_BUY + H_GEO + H_GRT + H_FTR + n_secs * SH + GAP * (n_secs + 5) + 30)

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
        drw.rounded_rectangle([(PAD, y), (W - PAD, y + SH)], radius=10,
                               outline=GLD2, width=1)
        drw.rounded_rectangle([(PAD, y), (PAD + 8, y + SH)], radius=5, fill=GLD)
        txt = f"{icon}  {label}" if icon else label
        drw.text((PAD + 22, y + 16), txt, font=F16b, fill=GLD3)
        drw.rectangle([(PAD, y + SH - 2), (W - PAD, y + SH)], fill=GLD2)
        y += SH + 10

    # Pill badge
    def _pill(px, py, txt, bg, fg=None, fnt=None, h=32, pad=14):
        if fnt is None: fnt = F12
        if fg  is None: fg  = INK if sum(bg) > 400 else (BG if sum(bg) > 200 else INK)
        tw  = _tw(txt, fnt)
        pw  = tw + pad * 2
        drw.rounded_rectangle([(px, py), (px + pw, py + h)], radius=h // 2, fill=bg)
        drw.text((px + pad, py + (h - 18) // 2), txt, font=fnt, fill=fg)
        return pw + 8

    # Horizontal progress bar
    def _hbar(x0, y0, x1, y1, pct, fg, bg=None, radius=3):
        if bg is None: bg = CARD3
        drw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=bg)
        fe = x0 + int(max(0.0, min(1.0, pct)) * (x1 - x0))
        if fe > x0:
            drw.rounded_rectangle([(x0, y0), (fe, y1)], radius=radius, fill=fg)

    # Dot meter (segmented)
    def _dots(x0, y0, n=10, filled=5, col_on=None, col_off=None, d=12, gap=5):
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
        pw   = tw + 20
        _alpha_rect(px, py, px + pw, py + 28, (*col, 38), radius=6)
        drw.text((px + 10, py + 5), txt, font=fnt, fill=col)
        return pw + 8

    # ======================================================== #
    # ① HERO HEADER                                            #
    # ======================================================== #
    _h_gradient(drw, 0, 0, W, H_HDR, HDR_L, HDR_R, steps=100)
    # subtle diagonal shimmer strip
    _alpha_rect(0, 0, W, H_HDR, (255, 255, 255, 12))
    drw.rectangle([(0, H_HDR - 5), (W, H_HDR)], fill=GLD)

    # App name
    drw.text((PAD, 16), "✦ GOLD PRICE DASHBOARD", font=F22b, fill=GLD3)
    # Date / time
    if os.name == "nt":
        dt_str = now.strftime("%#d %B %Y   ·   %H:%M IST")
    else:
        dt_str = now.strftime("%-d %B %Y   ·   %H:%M IST")
    drw.text((PAD, 58), dt_str, font=F14, fill=INK2)
    drw.text((PAD, 90), f"Source: {src_lbl}", font=F13, fill=MUT)

    y = H_HDR + GAP

    # ======================================================== #
    # ② GLOBAL MARKET SIGNALS  (moved here — quick context)   #
    # ======================================================== #
    SIG_MAP_G = {
        "real_yield":    ("Real Bond Yield",      "tip_val"),
        "dxy":           ("US Dollar Strength",   "dxy_val"),
        "yields":        ("Govt Bond Rate (10Y)", "yield_now"),
        "yield_curve":   ("Yield Curve Gap",      "yield_curve_spread"),
        "vix":           ("Market Fear Index",    "vix_now"),
        "risk_assets":   ("US Stocks (1-day)",    "sp500_1d"),
        "oil":           ("Oil Price (5-day)",    "oil_5d"),
        "silver_ratio":  ("Gold/Silver Ratio",    "gold_silver_ratio"),
        "copper":        ("Copper (5-day)",       "copper_5d"),
        "eur_usd":       ("Euro vs Dollar",       "eurusd_val"),
        "etf_flow":      ("Gold ETF Flow (5d)",   "gld_5d"),
        "gold_momentum": ("Gold Momentum (5d)",   "gold_5d"),
    }
    PILL_LBL_G = {2: "Positive", 1: "Slightly+", 0: "Neutral", -1: "Slightly-", -2: "Negative"}

    if descs:
        _sec("GLOBAL MARKET SIGNALS", "🌐")
        g_n_show  = min(len(descs), 12)
        g_row_h   = 46
        g_n_cols  = 2
        g_col_gap = 12
        g_col_w   = (W - 2 * PAD - g_col_gap) // g_n_cols
        g_n_rows  = (g_n_show + g_n_cols - 1) // g_n_cols
        g_t_h     = g_n_rows * g_row_h + 4

        g_sig_items = list(descs.items())[:g_n_show]
        for ri in range(g_n_rows):
            ry = y + ri * g_row_h
            for ci in range(g_n_cols):
                idx = ri * g_n_cols + ci
                if idx >= len(g_sig_items):
                    break
                key, _ = g_sig_items[idx]
                cx     = PAD + ci * (g_col_w + g_col_gap)
                row_bg = PANEL if ri % 2 == 0 else CARD
                drw.rectangle([(cx, ry), (cx + g_col_w, ry + g_row_h - 2)], fill=row_bg)
                vote = votes.get(key, 0)
                vc   = _vote_col(vote)
                drw.rounded_rectangle([(cx + 6, ry + 13), (cx + 21, ry + 27)],
                                      radius=3, fill=vc)
                nm = SIG_MAP_G.get(key, (key.replace("_", " ").title(), ""))[0]
                drw.text((cx + 28, ry + 11), nm[:20], font=F13, fill=INK)
                rk = SIG_MAP_G.get(key, ("", ""))[1]
                rv = (global_signals or {}).get(rk)
                if rv is not None:
                    vt2 = (f"{rv:.2f}" if isinstance(rv, float) and abs(rv) < 100
                           else f"{rv:.0f}" if isinstance(rv, float) else str(rv))
                    drw.text((cx + g_col_w - 210, ry + 11), vt2[:8], font=F13, fill=INK2)
                rl = PILL_LBL_G.get(vote, str(vote))
                _pill(cx + g_col_w - 152, ry + 7, rl, vc, fnt=F11, h=26)

        y += g_t_h + GAP

    # ======================================================== #
    # ③ KPI CARDS  22K | 24K | Silver | USD/INR               #
    # ======================================================== #
    _sec("GOLD & COMMODITY PRICES TODAY", "🏅")
    gap_c   = 16
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
        ("SILVER (999 Pure)",
         f"₹{ag_inr_g:,.1f}" if ag_inr_g else "—", "/g", SIL,
         ag_chg_g,
         f"Gold/Silver Ratio: {gs_ratio:.0f}" if gs_ratio else None,
         None, False),
        ("USD / INR",
         f"₹{usd_inr:.2f}", "", BLU,
         None,
         f"Dollar Index: {dxy_val:.1f}" if dxy_val else None,
         f"Fear Index: {vix_val:.1f}" if vix_val else None,
         False),
    ]

    spark_22 = closings_22k[-7:]   # last 7 of the sorted oldest→newest series
    spark_24 = closings_24k[-7:]

    for idx, (lbl, val, unit, acc, day_chg, sub1, sub2, hero) in enumerate(kpi_data):
        cx0 = PAD + sum(card_ws[:idx]) + idx * gap_c
        cx1 = cx0 + card_ws[idx]
        cy0, cy1 = y, y + H_KPI_CARD
        if hero:
            # Outer golden glow ring (drawn before card so it sits behind)
            _shadow_rect(drw, cx0 - 3, cy0 - 3, cx1 + 3, cy1 + 3,
                         GLD2, radius=14, soff=8, scol=(*GLD2, 120))
        _shadow_rect(drw, cx0, cy0, cx1, cy1, PANEL, radius=12, soff=5, scol=SHD)
        # top accent stripe — gradient
        stripe_h = 14 if hero else 5
        _h_gradient(drw, cx0, cy0, cx1, cy0 + stripe_h, acc, GLD3 if hero else acc, steps=24)
        drw.rounded_rectangle([(cx0, cy0), (cx1, cy0 + stripe_h)],
                               radius=6, outline=acc, width=0)
        if hero:
            # Golden border outline around entire card
            drw.rounded_rectangle([(cx0, cy0), (cx1, cy1)],
                                  radius=12, outline=GLD, width=2)
            # Subtle warm inner glow at top third
            _alpha_rect(cx0 + 2, cy0 + stripe_h, cx1 - 2,
                        cy0 + H_KPI_CARD // 3, (*GLD, 18), radius=0)
            # "⭐ BEST RATE" badge top-right corner
            badge_txt = "⭐ FEATURED"
            btw = _tw(badge_txt, F11)
            drw.rounded_rectangle([(cx1 - btw - 22, cy0 + 4),
                                   (cx1 - 4, cy0 + 26)],
                                  radius=6, fill=GLD2)
            drw.text((cx1 - btw - 12, cy0 + 7), badge_txt, font=F11, fill=BG)

        px = cx0 + 18
        # Label
        drw.text((px, cy0 + 22), lbl, font=F12, fill=acc if hero else INK3)
        # Main price
        vf = F22b if hero else F18b
        drw.text((px, cy0 + 50), val, font=vf, fill=INK)
        if unit:
            drw.text((px + _tw(val, vf) + 5, cy0 + 66), unit, font=F13, fill=INK3)

        # Per-day change badge
        if day_chg is not None:
            _chg_badge(px, cy0 + 108, day_chg, "/g", fnt=F12)
        elif idx == 3:  # USD card no chg, show global price
            if price_usd:
                drw.text((px, cy0 + 108), f"Global Gold ${price_usd:,.1f}/oz", font=F12, fill=INK3)

        # sub1 — percentage or note
        if sub1:
            s1col = GRN if "+" in sub1 else (RED if "-" in sub1 else INK3)
            drw.text((px, cy0 + 146), sub1, font=F13, fill=s1col)

        # sub2
        if sub2:
            drw.text((px, cy0 + 170), sub2, font=F13, fill=MUT)

        # sparkline at bottom right of hero/24K cards
        if idx in (0, 1):
            spark = spark_22 if idx == 0 else spark_24
            if len(spark) >= 2:
                sk_x0 = cx1 - 92
                sk_y0 = cy0 + 108
                sk_x1 = cx1 - 10
                sk_y1 = cy0 + H_KPI_CARD - 10
                _sparkline(drw, sk_x0, sk_y0, sk_x1, sk_y1, spark, GRN, RED, bg=CARD2)

    # ── GRT Jewellers KPI sub-row ──────────────────────────────────────────
    if grt_22k:
        GRT_CARD_H = 155
        grt_gap    = gap_c
        grt_cw     = (W - 2 * PAD - 2 * grt_gap) // 3
        grt_y      = y + H_KPI_CARD + 12

        # thin brand label bar spanning full width
        drw.rounded_rectangle([(PAD, grt_y - 8), (W - PAD, grt_y + 4)],
                               radius=4, fill=CARD3)
        drw.text((PAD + 16, grt_y - 6), "💍  GRT JEWELLERS LIVE RATES",
                 font=F13, fill=GLD3)
        grt_y += 8

        # pre-compute comparison values
        diff_ch = (grt_22k - p22k) if p22k else None
        diff_ib = (grt_22k - ibja["22k"]) if (ibja and ibja.get("22k")) else None

        grt_cards = [
            # (label, price_txt, accent, sub1_txt, sub1_col, sub2_txt)
            ("GRT 22K GOLD",
             f"₹{grt_22k:,}",
             GLD,
             (f"{'▲' if diff_ch > 0 else '▼'} ₹{abs(diff_ch):,}/g vs Chennai "
              f"({'premium' if diff_ch > 0 else 'discount'})") if diff_ch is not None else "",
             RED if (diff_ch or 0) > 0 else GRN,
             grt_date),
            ("GRT 24K (estimated)",
             f"₹{grt_24k:,}" if grt_24k else "—",
             GLD2,
             "Estimated from 22K rate",
             INK3,
             grt_src),
            ("MARKET COMPARISON",
             "22K Price Position",
             AMB,
             (f"{'▲' if diff_ib > 0 else '▼'} ₹{abs(diff_ib):,}/g vs Official Rate "
              f"(incl. making charges)") if diff_ib is not None else "Official rate unavailable",
             AMB if (diff_ib or 0) > 0 else GRN,
             (f"vs Chennai: {'▲' if diff_ch > 0 else '▼'} ₹{abs(diff_ch):,}/g"
              ) if diff_ch is not None else ""),
        ]

        for ci, (g_lbl, g_val, g_acc, g_sub1, g_sub1c, g_sub2) in enumerate(grt_cards):
            gcx0 = PAD + ci * (grt_cw + grt_gap)
            gcx1 = gcx0 + grt_cw
            _shadow_rect(drw, gcx0, grt_y, gcx1, grt_y + GRT_CARD_H,
                         PANEL, radius=10, soff=4, scol=SHD)
            _h_gradient(drw, gcx0, grt_y, gcx1, grt_y + 5, g_acc, GLD3, steps=15)
            gpx = gcx0 + 16
            drw.text((gpx, grt_y + 12), g_lbl, font=F12, fill=g_acc)
            drw.text((gpx, grt_y + 36), g_val, font=F18b, fill=INK)
            drw.text((gpx + _tw(g_val, F18b) + 4, grt_y + 52), "/g",
                     font=F13, fill=INK3)
            if g_sub1:
                drw.text((gpx, grt_y + 84), g_sub1[:52], font=F13, fill=g_sub1c)
            if g_sub2:
                drw.text((gpx, grt_y + 110), g_sub2[:38], font=F13, fill=MUT)
            # price bar on comparison card
            if ci == 2 and p22k and diff_ch is not None:
                bar_pct = min(1.0, max(0.0, 0.5 + diff_ch / max(1, p22k) * 8))
                bar_col = RED if bar_pct > 0.55 else (GRN if bar_pct < 0.45 else AMB)
                drw.text((gpx, grt_y + 128), "Price bar vs Chennai:",
                         font=F11, fill=INK3)
                _hbar(gpx, grt_y + 142, gcx1 - 16, grt_y + 152, bar_pct, bar_col)

    y += H_KPI + GAP

    # ── Per-day change strip (history bar) ─────────────────────────────────
    if closings_22k and len(closings_22k) >= 2:
        strip_h = H_HIST
        drw.rounded_rectangle([(PAD, y), (W - PAD, y + strip_h)], radius=10, fill=PANEL)
        drw.rounded_rectangle([(PAD, y), (PAD + 6, y + strip_h)], radius=4, fill=GLD)
        drw.text((PAD + 18, y + 10), "DAY-BY-DAY PRICE CHANGES (22K)", font=F13, fill=MUT)
        n_show  = min(len(closings_22k), 7)
        cell_w  = (W - 2 * PAD - 26) // n_show
        idxs    = list(range(max(0, len(closings_22k) - n_show), len(closings_22k)))
        for j, ii in enumerate(idxs):
            dc  = daily_chg_22k[ii]
            col = GRN if dc >= 0 else RED
            arr = "▲" if dc >= 0 else "▼"
            dx  = PAD + 26 + j * cell_w
            lbl_d = dates_lbl[ii] if ii < len(dates_lbl) else ""
            drw.text((dx, y + 8), lbl_d, font=F13, fill=INK3)
            drw.text((dx, y + 24), f"{arr}{abs(dc):,.0f}", font=F13, fill=col)
        y += strip_h + GAP

    # ======================================================== #
    # ③ 10-DAY LINE + AREA CHART                               #
    # ======================================================== #
    if len(closings_22k) >= 2:
        _sec("LAST 10 DAYS: GOLD PRICE TREND", "📈")
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

        LP, RP, TP, BP = 82, 20, 26, 42
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
            drw.text((PAD + 2, gy - 9), lbl_str, font=F13, fill=MUT)

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
            drw.ellipse([(px - 8, py2 - 8), (px + 8, py2 + 8)], fill=PANEL)
            # filled dot
            drw.ellipse([(px - 5, py2 - 5), (px + 5, py2 + 5)], fill=dot_col)
            # white centre pin
            drw.ellipse([(px - 2, py2 - 2), (px + 2, py2 + 2)], fill=CARD)

            # per-day change label above each point
            if i > 0:
                dc     = daily_chg_22k[i]
                dc_col = C_UP if dc >= 0 else C_DN
                dc_arr = "▲" if dc >= 0 else "▼"
                dc_txt = f"{dc_arr}{abs(dc):,.0f}"
                tw_dc  = _tw(dc_txt, F13)
                label_y = py2 - 24
                # keep label inside chart top
                if label_y < ay0 + 2:
                    label_y = py2 + 10
                drw.text((px - tw_dc // 2, label_y), dc_txt, font=F13, fill=dc_col)

            # date label below axis (every point)
            if i < len(dates_lbl):
                dl    = dates_lbl[i]
                tw_dl = _tw(dl, F13)
                drw.text((px - tw_dl // 2, ay1 + 6), dl, font=F13, fill=INK3)

        # ── Current price callout tag ─────────────────────────────────────
        lx, ly = _cx(n_pts - 1), _cy(closings_22k[-1])
        pl  = f"₹{closings_22k[-1]:,}"
        pw  = _tw(pl, F13) + 16
        tag_x = max(ax0, lx - pw // 2)
        drw.rounded_rectangle([(tag_x, ly - 26), (tag_x + pw, ly - 8)],
                               radius=5, fill=GLD)
        drw.text((tag_x + 8, ly - 25), pl, font=F13,
                 fill=BG if sum(GLD) > 350 else INK)

        # ── Stats panel ──────────────────────────────────────────────────
        sx0 = split_x + 10
        drw.rounded_rectangle([(sx0, y), (W - PAD, y + ch)], radius=12, fill=PANEL)
        # Header
        _h_gradient(drw, sx0, y, W - PAD, y + 44, GLD2, GLD, steps=30)
        drw.rounded_rectangle([(sx0, y), (W - PAD, y + 44)], radius=10, outline=GLD2, width=0)
        spx = sx0 + 18
        drw.text((spx, y + 12), "WORLD GOLD PRICE", font=F14, fill=BG if sum(GLD) > 350 else INK)

        sy = y + 56
        if price_usd:
            drw.text((spx, sy), f"${price_usd:,.1f}  /oz", font=F18b, fill=INK); sy += 34
        for sl, sv, sc in [
            ("Today's Change", f"₹{abs(chg_22k):,.0f}/g" if chg_22k is not None else "—",
             GRN if (chg_22k or 0) >= 0 else RED),
            ("7-Day Change",  f"{chg_7d:+.2f}%"  if chg_7d  else "—",
             GRN if (chg_7d  or 0) > 0 else RED),
            ("30-Day Change", f"{chg_30d:+.2f}%" if chg_30d else "—",
             GRN if (chg_30d or 0) > 0 else RED),
        ]:
            drw.text((spx, sy), sl, font=F13, fill=INK3); sy += 18
            drw.text((spx, sy), sv, font=F14, fill=sc); sy += 26
        sy += 5
        drw.line([(spx, sy), (W - PAD - 16, sy)], fill=DIV, width=1); sy += 13

        # 22K vs yesterday
        drw.text((spx, sy), "22K vs yesterday", font=F13, fill=INK3); sy += 18
        if len(closings_22k) >= 2:
            d1 = closings_22k[-1] - closings_22k[-2]
            d1c = GRN if d1 >= 0 else RED
            drw.text((spx, sy), f"{'▲' if d1>=0 else '▼'} ₹{abs(d1):,}/g",
                     font=F14, fill=d1c); sy += 28
        drw.line([(spx, sy), (W - PAD - 16, sy)], fill=DIV, width=1); sy += 10

        # Multiples
        if closings_22k:
            cv = closings_22k[-1]
            drw.text((spx, sy), "Bulk Buying Guide", font=F13, fill=INK3); sy += 18
            for g, v in [(8, cv * 8), (10, cv * 10), (12, cv * 12)]:
                drw.text((spx, sy), f"{g}g = ₹{v:,}", font=F13, fill=INK2); sy += 17

        # Trend sparkline
        if len(spark_22) >= 2:
            sy += 10
            drw.text((spx, sy), "10-Day Price Trend", font=F13, fill=INK3); sy += 18
            _sparkline(drw, spx, sy, W - PAD - 18, sy + 42, spark_22, GRN, RED, bg=CARD2)

        y += ch + GAP

    # ======================================================== #
    # ④ SIGNAL GAUGE + 7-DAY FORECAST                          #
    # ======================================================== #
    _sec("BUY / SELL SIGNAL & 7-DAY FORECAST", "⚡")
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
        drw.text((GCX - GR - 40, GCY + 10), "SELL", font=F13, fill=RED)
        drw.text((GCX + GR + 10,  GCY + 10), "BUY",  font=F13, fill=GRN)

        # Glow around hub
        _glow_hub(GCX, GCY, r_out=46, r_in=16, rgba=GLOW)

        # Needle
        nr  = _math.radians(nd)
        nx  = GCX + (GR - 28) * _math.cos(nr)
        ny2 = GCY + (GR - 28) * _math.sin(nr)
        drw.line([(GCX, GCY), (nx, ny2)], fill=SHD, width=10)
        drw.line([(GCX, GCY), (nx, ny2)], fill=GLD2, width=7)
        drw.line([(GCX, GCY), (nx, ny2)], fill=GLD, width=3)
        # Hub
        drw.ellipse([(GCX - 14, GCY - 14), (GCX + 14, GCY + 14)], fill=GLD)
        drw.ellipse([(GCX - 6,  GCY - 6),  (GCX + 6,  GCY + 6)],  fill=INK)

        # Score text
        st = f"Score: {score:+.1f}"
        drw.text((GCX - _tw(st, F15) // 2, GCY + 24), st, font=F15, fill=INK)
        if   score >= 7:   ver, vc = "STRONG BUY",  GRN2
        elif score >= 3:   ver, vc = "BUY",          GRN
        elif score <= -7:  ver, vc = "STRONG SELL",  RED2
        elif score <= -3:  ver, vc = "SELL",          RED
        else:              ver, vc = "NEUTRAL",       AMB
        drw.text((GCX - _tw(ver, F22b) // 2, GCY + 50), ver, font=F22b, fill=vc)

    _gauge(combined)

    # Forecast panel (right half)
    fx0 = W // 2 + 8
    fy0 = ga_top
    fy1 = ga_top + H_GAUGE - GAP
    _shadow_rect(drw, fx0, fy0, W - PAD, fy1, PANEL, radius=10, soff=4, scol=SHD)
    _h_gradient(drw, fx0, fy0, W - PAD, fy0 + 44, GLD2, GLD, steps=30)
    drw.text((fx0 + 18, fy0 + 12), "7-DAY FORECAST", font=F16b,
             fill=BG if sum(GLD) > 350 else INK)

    wry = fy0 + 52
    for hdr, x in [("Day", fx0 + 18), ("Dir", fx0 + 90), ("Expected", fx0 + 162),
                   ("Price Range (low – high)", fx0 + 330)]:
        drw.text((x, wry), hdr, font=F13, fill=GLD if hdr == "Expected" else INK3)
    wry += 24
    drw.line([(fx0 + 10, wry), (W - PAD - 10, wry)], fill=DIV, width=1)
    wry += 8

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

        if wry < fy1 - 96:
            if is_wk:
                _alpha_rect(fx0 + 8, wry - 2, W - PAD - 8, wry + 32, (*CARD2, 180), radius=5)
                drw.text((fx0 + 18, wry + 6), wd, font=F14, fill=INK3)
                drw.text((fx0 + 90, wry + 6), "Weekend", font=F14, fill=MUT)
            else:
                pcol = GRN2 if "UP" in dirn else (RED2 if "DOWN" in dirn else AMB)
                arr3 = "▲" if "UP" in dirn else ("▼" if "DOWN" in dirn else "—")
                drw.text((fx0 + 18, wry + 5), wd, font=F13, fill=INK)
                _pill(fx0 + 78, wry + 2, f"{arr3} {dirn}", pcol, fnt=F13, h=26)
                drw.text((fx0 + 162, wry + 5), f"₹{mid_22:,}", font=F13, fill=GLD)
                drw.text((fx0 + 330, wry + 5), f"₹{lo_22:,} – ₹{hi_22:,}", font=F13, fill=INK2)
            wry += 36

    # Forecast area mini-chart
    if len(fc_mids) >= 2:
        wry += 8
        drw.line([(fx0 + 10, wry), (W - PAD - 10, wry)], fill=DIV, width=1); wry += 8
        drw.text((fx0 + 18, wry), "Forecast confidence band", font=F13, fill=INK3); wry += 18
        fc_x0 = fx0 + 12; fc_x1 = W - PAD - 12
        fc_y0 = wry;       fc_y1 = min(wry + 64, fy1 - 14)
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
        drw.text((fx0 + 18, fy1 - 24), f"Market Outlook: {oc}"[:46], font=F13, fill=INK2)

    y = ga_top + H_GAUGE

    # ======================================================== #
    # ⑤ TECHNICAL INDICATORS — DOT METERS                      #
    # ======================================================== #
    _sec("PRICE HEALTH METERS", "📊")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_TECH)], radius=10, fill=PANEL)
    _h_gradient(drw, PAD + 2, y + 2, W - PAD - 2, y + 32, PANEL, CARD2, steps=40)

    cols  = 5
    cw_ti = (W - 2 * PAD - 26) // cols
    ti_items = [
        ("Momentum", f"{rsi:.1f}" if rsi is not None else "—",
         GRN if rsi and rsi < 45 else (RED if rsi and rsi > 70 else AMB),
         (rsi or 50) / 100 if rsi else 0.5),
        ("Trend Signal", f"{macd_val:+.2f}" if macd_val is not None else "—",
         GRN if macd_cross and macd_cross > 0 else RED,
         max(0.0, min(1.0, 0.5 + (macd_cross or 0) / 20))),
        ("Price Position", f"{bb_pos * 100:.0f}%" if bb_pos is not None else "—",
         GRN if bb_pos and bb_pos < 0.3 else (RED if bb_pos and bb_pos > 0.7 else AMB),
         bb_pos or 0.5),
        ("Tech Rating", f"{a_score:+d}",
         GRN if a_score >= 2 else (RED if a_score <= -2 else AMB),
         max(0.0, min(1.0, (a_score + 8) / 16))),
        ("Overall Score", f"{net_score:+d}",
         GRN if net_score >= 2 else (RED if net_score <= -2 else AMB),
         max(0.0, min(1.0, (net_score + 10) / 20))),
    ]

    for ci, (lbl, val, vcol, pct) in enumerate(ti_items):
        tx = PAD + 13 + ci * cw_ti
        drw.text((tx, y + 12),  lbl, font=F13,  fill=INK3)
        drw.text((tx, y + 32), val, font=F18b, fill=vcol)
        n_d = 10
        fil = max(0, min(n_d, round(pct * n_d)))
        _dots(tx, y + H_TECH - 30, n=n_d, filled=fil, col_on=vcol, col_off=CARD3)
        drw.text((tx, y + H_TECH - 12), f"{int(pct*100)}%", font=F13, fill=INK3)
        if ci < cols - 1:
            drw.line([(tx + cw_ti - 8, y + 16), (tx + cw_ti - 8, y + H_TECH - 16)],
                     fill=DIV, width=1)

    if sma20 and sma50 and price_usd:
        sma_t = f"20-day Avg ${sma20:,.0f}  ·  50-day Avg ${sma50:,.0f}  ·  Now ${price_usd:,.0f}"
        drw.text((PAD + 16, y + H_TECH - 4), sma_t, font=F13, fill=MUT)

    y += H_TECH + GAP

    # ======================================================== #
    # ⑥ BUYING GUIDE                                           #
    # ======================================================== #
    _sec("BUYING GUIDE & RECOMMENDATION", "💡")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_BUY)], radius=10, fill=PANEL)

    cw3  = (W - 2 * PAD - 26) // 3
    pg1  = PAD + 18

    # Col 1 – Best day
    drw.text((pg1, y + 14), "Best Day to Buy", font=F13, fill=INK3)
    if best_day:
        drw.text((pg1, y + 34), f"📅 {_ordinal(best_day)} of month", font=F18b, fill=GLD)
        if win_label:
            drw.text((pg1, y + 70), f"Window: {win_label}", font=F13, fill=INK2)
        if top3_days:
            drw.text((pg1, y + 90), f"Top 3: {', '.join(_ordinal(d) for d in top3_days)}",
                     font=F13, fill=MUT)
    drw.line([(PAD + cw3 + 8, y + 14), (PAD + cw3 + 8, y + H_BUY - 14)], fill=DIV, width=1)

    # Col 2 – Month low 22K
    pg2 = PAD + cw3 + 26
    drw.text((pg2, y + 14), "Cheapest Day This Month (22K)", font=F13, fill=INK3)
    if ml_day:
        drw.text((pg2, y + 34), f"📉 {_ordinal(ml_day)}", font=F18b, fill=GRN)
        if ml_price_22k:
            drw.text((pg2, y + 70), f"₹{ml_price_22k:,}/g", font=F15, fill=INK2)
        if ml_trend:
            tc = GRN if ml_trend == "falling" else (RED if ml_trend == "rising" else INK2)
            drw.text((pg2, y + 96), f"Trend: {ml_trend}", font=F13, fill=tc)
    else:
        drw.text((pg2, y + 34), "Calculating…", font=F15, fill=MUT)
    drw.line([(PAD + cw3 * 2 + 13, y + 14), (PAD + cw3 * 2 + 13, y + H_BUY - 14)], fill=DIV, width=1)

    # Col 3 – Recommendation
    pg3 = PAD + cw3 * 2 + 28
    drw.text((pg3, y + 14), "Today's Recommendation", font=F13, fill=INK3)
    if a_rec:
        rc = (a_rec.replace("🟢","").replace("🔴","").replace("🟡","")
             .replace("⚪","").replace("🟠","").strip())
        rcol = GRN if "BUY" in a_rec.upper() else (RED if any(
            w in a_rec.upper() for w in ("AVOID","WAIT","SELL")) else AMB)
        parts = rc.split(" – ")
        drw.text((pg3, y + 34), parts[0][:24], font=F18b, fill=rcol)
        if len(parts) > 1:
            drw.text((pg3, y + 70), parts[1][:32], font=F13, fill=INK2)
    drw.text((pg3, y + 106), f"Signal Score: {pred_dir}  ({pred_score:+.1f})", font=F13, fill=INK2)

    y += H_BUY + GAP

    # ======================================================== #
    # ⑦ GEOPOLITICAL SENTIMENT                                 #
    # ======================================================== #
    _sec("WORLD NEWS IMPACT ON GOLD", "🌍")
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_GEO)], radius=10, fill=PANEL)

    gc2  = (geo_signal.replace("🔴","").replace("🟠","").replace("🟡","").replace("🟢","").strip())
    gcol = GRN if geo_score < 0 else (RED if geo_score >= 2 else AMB)
    drw.text((PAD + 18, y + 14), gc2[:60], font=F18b, fill=gcol)

    ppx2 = PAD + 18
    ppx2 += _pill(ppx2, y + 52, f"▲ {bull_cnt} bullish", GRN2, fnt=F13, h=30)
    ppx2 += _pill(ppx2, y + 52, f"▼ {bear_cnt} bearish", RED2, fnt=F13, h=30)

    hls = (geo or {}).get("top_headlines", [])
    hly2 = y + 92
    for htitle, hbc, hbrc in hls[:n_hl]:
        hcol2 = GRN2 if hbc > hbrc else (RED2 if hbrc > hbc else MUT)
        drw.text((PAD + 18, hly2), f"• {htitle[:110]}", font=F13, fill=hcol2)
        hly2 += 28

    y += H_GEO + GAP

    # ======================================================== #
    # ⑧ GRT TODAY'S OFFERS  (prices are in KPI sub-row above) #
    # ======================================================== #
    if grt_22k and grt_offers:
        _sec("GRT JEWELLERS — TODAY'S OFFERS", "💍")
        # Compact 2-column pill-row layout — each offer = one tight row
        g_off_cols  = 2
        g_off_col_w = (W - 2 * PAD - 8) // g_off_cols
        g_off_row_h = 28
        g_off_n     = len(grt_offers)
        g_off_rows  = (g_off_n + g_off_cols - 1) // g_off_cols
        g_off_h     = g_off_rows * g_off_row_h + 12

        drw.rounded_rectangle([(PAD, y), (W - PAD, y + g_off_h)], radius=8, fill=PANEL)

        off_section_colours = [AMB, BLU, GRN2, GLD2, SIL]
        off_seen: dict[str, int] = {}
        for oi, off in enumerate(grt_offers):
            sec = off.get("section", "")
            if sec not in off_seen:
                off_seen[sec] = len(off_seen) % len(off_section_colours)
            scol  = off_section_colours[off_seen[sec]]
            oc    = oi % g_off_cols
            or_   = oi // g_off_cols
            ox    = PAD + 4 + oc * g_off_col_w
            oy    = y + 6 + or_ * g_off_row_h

            # tiny colour dot
            drw.ellipse([(ox + 4, oy + 9), (ox + 14, oy + 19)], fill=scol)
            # short section abbreviation in accent color
            abv = (sec[:8] if sec else "Offer").upper()
            drw.text((ox + 20, oy + 5), abv, font=F11, fill=scol)
            abv_w = _tw(abv, F11)
            # offer title (truncated to fit remaining width)
            title = off.get("title", "")
            max_chars = (g_off_col_w - abv_w - 42) // max(1, _tw("W", F11) // 2)
            drw.text((ox + 24 + abv_w, oy + 5), title[:max_chars], font=F11, fill=INK)

        y += g_off_h + GAP

    # ======================================================== #
    # ⑨ FOOTER                                                 #
    # ======================================================== #
    fy = TOTAL_H - H_FTR
    _h_gradient(drw, 0, fy, W, TOTAL_H, HDR_R, HDR_L, steps=70)
    drw.rectangle([(0, fy), (W, fy + 4)], fill=GLD)
    drw.text((PAD, fy + 22),
             "Data: Global Markets (COMEX/MCX)  ·  Price includes import duty + GST  ·  Not investment advice",
             font=F13, fill=INK2)
    if os.name == "nt":
        ts = now.strftime("Generated %#d %B %Y  %H:%M IST")
    else:
        ts = now.strftime("Generated %-d %B %Y  %H:%M IST")
    drw.text((W - PAD - _tw(ts, F13), fy + 22), ts, font=F13, fill=INK3)
    drw.text((PAD, fy + 46), "✦ premtechiee/automations  |  Gold Notifier Bot",
             font=F13, fill=MUT)

    # ── Save ────────────────────────────────────────────────────────────────
    final_h = min(TOTAL_H, y + H_FTR + 10)
    img = img.crop((0, 0, W, final_h))
    img.save(out_path, format="PNG", optimize=True)
    logger.info("Image saved → %s  (%dx%d)", out_path, W, final_h)
    return out_path
