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

    pred_dir = (prediction or {}).get("direction")
    if not pred_dir or pred_dir == "FLAT":
        # Never display FLAT — fall back to the sign of the latest day's
        # change so the call always reads as a directional lean.
        try:
            _last_chg = next((r.get("chg", 0) for r in (history or []) if r.get("trading")), 0)
        except Exception:
            _last_chg = 0
        pred_dir = "UP" if _last_chg >= 0 else "DOWN"
    pred_score = float((prediction or {}).get("score", 0))
    geo_s      = float(geo_score)
    combined   = round(a_score + geo_s + pred_score * 0.3, 1)

    hist_rows = (history or [])[:10]
    wk_all    = (weekly_prediction or [])[:7]

    # Pre-compute forecast arrays (used by both the new prediction chart
    # section ③b and the legacy mini-chart inside section ③'s right panel).
    fc_mids: list[int]  = []
    fc_los:  list[int]  = []
    fc_his:  list[int]  = []
    fc_dirs: list[str]  = []
    fc_dlbl: list[str]  = []
    for _row in wk_all:
        if _row.get("is_weekend"):
            continue
        _mid = _row.get("mid_22k") or round((_row.get("mid_inr", 0) or 0) * 22 / 24)
        _lo  = _row.get("low_22k")  or round((_row.get("low_inr",  _mid) or _mid) * 22 / 24)
        _hi  = _row.get("high_22k") or round((_row.get("high_inr", _mid) or _mid) * 22 / 24)
        if not _mid:
            continue
        fc_mids.append(int(_mid))
        fc_los.append(int(_lo))
        fc_his.append(int(_hi))
        fc_dir_raw = str(_row.get("direction", "")).upper()
        if fc_dir_raw not in ("UP", "DOWN"):
            # Force a directional lean even for legacy/weekend rows so the
            # forecast chart never renders a neutral marker.
            fc_dir_raw = "UP" if _mid >= (fc_mids[-1] if fc_mids else _mid) else "DOWN"
        fc_dirs.append(fc_dir_raw)
        _wd = str(_row.get("weekday", ""))[:3]
        _dt = _row.get("date")
        if hasattr(_dt, "strftime"):
            fc_dlbl.append(_dt.strftime("%d %b").lstrip("0"))
        else:
            fc_dlbl.append(_wd or str(_dt or ""))

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

    hist_sorted  = sorted(hist_rows, key=_parse_hist_date, reverse=True)[:30]
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
    # Day-by-day changes are now drawn directly inside the combined chart
    # (last 7 historic dots get a ▲/▼ ₹X label) — no separate strip.
    H_HIST  = 0
    # Combined chart spans the full width and now includes the indicator
    # strip rendered as an overlay near the top of the chart, above the
    # price line (no separate row underneath).
    H_CHART = 0
    H_PRED       = 460 if (len(closings_22k) >= 2 and len(fc_mids) >= 2) else (
                   400 if len(closings_22k) >= 2 else 0)
    H_PRED_INFO  = 0
    H_GAUGE = 440
    H_TECH  = 380
    H_SIG   = (n_sig * 56 + 84) if n_sig else 0
    H_BUY   = 174
    H_GEO   = 140 + n_hl * 32
    # GRT section: offers-only strip (prices are now in the KPI sub-row)
    H_GRT   = (n_grt_offers * 26 + 46) if (grt_22k and n_grt_offers) else 0
    H_FTR   = 72
    SH      = 64
    GAP     = 20

    n_secs  = 5 + (1 if H_SIG else 0) + (1 if H_GRT else 0) + (1 if H_PRED else 0)
    TOTAL_H = (H_HDR + H_KPI + H_HIST + H_CHART + H_PRED + H_PRED_INFO + H_GAUGE + H_TECH + H_SIG
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

    # ── (Removed) Per-day change strip — day-by-day ▲/▼ values are now
    # annotated directly on the last 7 historic dots inside the combined
    # chart in section ③, so this standalone bar is no longer needed.

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

    for row in wk_all[:7]:
        is_wk   = row.get("is_weekend", False)
        wd      = str(row.get("weekday", ""))[:3]
        dirn    = str(row.get("direction", "")).upper()
        mid_22  = row.get("mid_22k") or round((row.get("mid_inr", 0) or 0) * 22 / 24)
        lo_22   = row.get("low_22k") or round((row.get("low_inr",  mid_22) or mid_22) * 22 / 24)
        hi_22   = row.get("high_22k") or round((row.get("high_inr", mid_22) or mid_22) * 22 / 24)

        # Force a directional lean — never render "FLAT" or unknown text.
        if dirn not in ("UP", "DOWN"):
            ref = closings_22k[-1] if closings_22k else mid_22
            dirn = "UP" if (mid_22 or 0) >= ref else "DOWN"

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

    y = ga_top + H_GAUGE + GAP

    # ======================================================== #
    # ③ COMBINED CHART — Last 30 days actual + 7-day forecast   #
    # ======================================================== #
    if H_PRED and len(closings_22k) >= 2:
        has_forecast = len(fc_mids) >= 2
        if has_forecast:
            _sec("LAST 30 DAYS + 7-DAY PRICE FORECAST (22K /g)", "📈")
        else:
            _sec("LAST 30 DAYS — GOLD PRICE TREND (22K /g)", "📈")

        ph = H_PRED - 8
        # Full width — no right sidebar; summary moves to a strip below.
        chart_x1 = W - PAD

        # Background panel
        drw.rounded_rectangle([(PAD, y), (chart_x1, y + ph)], radius=12, fill=PANEL)
        _v_gradient(drw, PAD + 2, y + 2, chart_x1 - 2, y + ph - 2, PANEL, CARD2, steps=40)

        n_h = len(closings_22k)
        n_f = len(fc_mids) if has_forecast else 0
        n_total = n_h + n_f

        all_vals = list(closings_22k)
        if has_forecast:
            all_vals += fc_los + fc_his + fc_mids
        pmin, pmax = min(all_vals), max(all_vals)
        pad_pct = 0.10
        plo = pmin - (pmax - pmin) * pad_pct
        phi = pmax + (pmax - pmin) * pad_pct
        prng = max(phi - plo, 1)

        # Top inset is enlarged so the indicator cards can overlay above
        # the price line without colliding with it. Bottom needs room for
        # rotated date labels — compute from the longest label so they
        # never get clipped.
        _all_lbls = [str(s) for s in (dates_lbl + (fc_dlbl if has_forecast else [])) if s]
        _max_lbl_w = max((_tw(s, F13) for s in _all_lbls), default=40)
        # rotated tile height ≈ text width + small padding; reserve gap above + below
        BP = max(80, _max_lbl_w + 32)
        LP, RP, TP = 92, 32, 130
        px0 = PAD + LP; px1 = chart_x1 - RP
        py0 = y + TP;   py1 = y + ph - BP

        def _px(i): return int(px0 + i * (px1 - px0) / max(1, n_total - 1))
        def _py(v): return int(py1 - (v - plo) / prng * (py1 - py0))

        # Y-axis grid + price labels (horizontal)
        for gp in [0.0, 0.25, 0.5, 0.75, 1.0]:
            gy = int(py1 - gp * (py1 - py0))
            pv = plo + gp * prng
            drw.line([(px0, gy), (px1, gy)], fill=DIV, width=1)
            drw.text((PAD + 6, gy - 9), f"₹{pv:,.0f}", font=F13, fill=MUT)

        # ── Vertical day guides — only every 5th day so the chart isn't
        # buried under 37 dotted lines.
        for i in range(n_total):
            if i % 5 != 0 and i != n_total - 1 and i != n_h - 1:
                continue
            gx = _px(i)
            for yy in range(py0, py1, 6):
                drw.line([(gx, yy), (gx, yy + 2)], fill=DIV, width=1)

        # ── Historic side: gradient area fill
        hist_xs = [_px(i) for i in range(n_h)]
        hist_ys = [_py(c) for c in closings_22k]
        area_pts = [(hist_xs[0], py1)] + list(zip(hist_xs, hist_ys)) + \
                   [(hist_xs[-1], py1)]
        _alpha_poly(area_pts, (C_UP[0], C_UP[1], C_UP[2], 55))
        top_wash = [(hist_xs[0], int(py0 + (py1 - py0) * 0.4))] + \
                   list(zip(hist_xs, hist_ys)) + \
                   [(hist_xs[-1], int(py0 + (py1 - py0) * 0.4))]
        _alpha_poly(top_wash, (C_UP[0], C_UP[1], C_UP[2], 25))

        # TODAY divider + label (only when forecast is shown)
        if has_forecast:
            today_x = (_px(n_h - 1) + _px(n_h)) // 2
            for yy in range(py0, py1, 6):
                drw.line([(today_x, yy), (today_x, yy + 3)], fill=GLD2, width=1)
            _today_lbl = "TODAY"
            tw_t = _tw(_today_lbl, F13)
            # Position below the chart on the date-label band so it doesn't
            # collide with the indicator overlay strip near the top.
            drw.text((today_x - tw_t // 2, py1 + 6), _today_lbl, font=F13, fill=GLD)

            # Confidence band (forecast low–high), anchored to last historic point
            band_top = [(_px(n_h - 1), _py(closings_22k[-1]))] + \
                       [(_px(n_h + i), _py(fc_his[i])) for i in range(n_f)]
            band_bot = [(_px(n_h - 1), _py(closings_22k[-1]))] + \
                       [(_px(n_h + i), _py(fc_los[i])) for i in range(n_f)]
            _alpha_poly(band_top + list(reversed(band_bot)),
                        (GLD[0], GLD[1], GLD[2], 55))

        # Historic actual line + dots
        hist_pts = list(zip(hist_xs, hist_ys))
        if len(hist_pts) >= 2:
            drw.line(hist_pts, fill=BLU, width=3)
        for i, (xp, yp) in enumerate(hist_pts):
            is_up = closings_22k[i] >= closings_22k[i - 1] if i > 0 else True
            dot_col = C_UP if is_up else C_DN
            # Smaller dots for 30-day density
            drw.ellipse([(xp - 5, yp - 5), (xp + 5, yp + 5)], fill=PANEL)
            drw.ellipse([(xp - 4, yp - 4), (xp + 4, yp + 4)], fill=dot_col)
            drw.ellipse([(xp - 1, yp - 1), (xp + 1, yp + 1)], fill=CARD)

        # Inline day-by-day change labels for the last 7 historic dots.
        # Replaces the separate per-day strip — the ▲/▼ pill sits just
        # above (or below) each dot so day-over-day changes are visible
        # without leaving the chart.
        try:
            n_tag = min(7, len(hist_pts))
            for k in range(len(hist_pts) - n_tag, len(hist_pts)):
                if k <= 0:
                    continue
                dc = daily_chg_22k[k] if k < len(daily_chg_22k) else 0
                if dc == 0:
                    continue
                xp, yp = hist_pts[k]
                col = C_UP if dc >= 0 else C_DN
                arr = "▲" if dc >= 0 else "▼"
                txt = f"{arr}{abs(dc):,.0f}"
                tw_t = _tw(txt, F11)
                pw   = tw_t + 8
                ph_t = 14
                # Default above the dot; flip below if it would clip the
                # top indicator strip area.
                lx0 = xp - pw // 2
                ly0 = yp - ph_t - 8
                if ly0 < py0 + 70:  # leave room for in-chart indicator cards
                    ly0 = yp + 10
                lx1 = lx0 + pw
                _alpha_rect(lx0, ly0, lx1, ly0 + ph_t,
                            (PANEL[0], PANEL[1], PANEL[2], 220), radius=3)
                drw.text((lx0 + 4, ly0 - 1), txt, font=F11, fill=col)
        except Exception:
            pass

        # Forecast dashed line + markers + collision-aware price labels
        if has_forecast:
            fc_pts = [(_px(n_h - 1), _py(closings_22k[-1]))] + \
                     [(_px(n_h + i), _py(fc_mids[i])) for i in range(n_f)]
            for i in range(len(fc_pts) - 1):
                x1a, y1a = fc_pts[i]
                x2a, y2a = fc_pts[i + 1]
                steps = max(4, int(((x2a - x1a) ** 2 + (y2a - y1a) ** 2) ** 0.5 / 8))
                for s in range(steps):
                    if s % 2 == 0:
                        sx1 = int(x1a + (x2a - x1a) * s / steps)
                        sy1 = int(y1a + (y2a - y1a) * s / steps)
                        sx2 = int(x1a + (x2a - x1a) * (s + 1) / steps)
                        sy2 = int(y1a + (y2a - y1a) * (s + 1) / steps)
                        drw.line([(sx1, sy1), (sx2, sy2)], fill=GLD, width=3)

            fc_marker_pts = []
            for i in range(n_f):
                xp, yp = _px(n_h + i), _py(fc_mids[i])
                d = fc_dirs[i]
                dc = C_UP if "UP" in d else (C_DN if "DOWN" in d else AMB)
                drw.ellipse([(xp - 6, yp - 6), (xp + 6, yp + 6)], fill=PANEL)
                drw.ellipse([(xp - 4, yp - 4), (xp + 4, yp + 4)], fill=dc)
                drw.ellipse([(xp - 1, yp - 1), (xp + 1, yp + 1)], fill=CARD)
                fc_marker_pts.append((xp, yp, dc))

            # Forecast price labels — only highlight 3 milestones (first,
            # mid, last) instead of one label per point, to keep the chart
            # uncluttered.
            milestones = {0, n_f // 2, n_f - 1}
            for i, (xp, yp, dc) in enumerate(fc_marker_pts):
                if i not in milestones:
                    continue
                lbl  = f"₹{fc_mids[i]:,}"
                tw_l = _tw(lbl, F13)
                pad_x, pad_y = 6, 3
                pill_w = tw_l + 2 * pad_x
                pill_h = 18
                place_above = (i == n_f - 1)
                ly = yp - 22 if place_above else yp + 12
                if ly < py0 + 2:
                    ly = yp + 12
                if ly + pill_h > py1 - 2:
                    ly = yp - 22
                lx0 = xp - pill_w // 2
                lx1 = lx0 + pill_w
                _alpha_rect(lx0, ly, lx1, ly + pill_h,
                            (PANEL[0], PANEL[1], PANEL[2], 230), radius=4)
                drw.rounded_rectangle([(lx0, ly), (lx1, ly + pill_h)],
                                       radius=4, outline=dc, width=1)
                drw.text((lx0 + pad_x, ly + pad_y), lbl, font=F13, fill=dc)

        # X-axis day labels — render rotated 90° to fit dense timelines.
        # On a 30+7 day chart the per-column spacing is only ~20 px, so we
        # show every 2nd historic date + every forecast date to avoid the
        # rotated tiles overlapping each other.
        def _draw_rot_label(cx: int, top_y: int, text: str, color):
            # Measure the actual text bbox so descenders ("p" in Apr/Sep,
            # "g" in Aug) are NEVER clipped during rotation.
            try:
                tx0, ty0, tx1, ty1 = F13.getbbox(text)
            except Exception:
                tx0, ty0 = 0, 0
                tx1, ty1 = _tw(text, F13), 18
            text_w = tx1 - tx0
            text_h = ty1 - ty0
            pad_x, pad_y = 4, 4
            tile_w = text_w + pad_x * 2
            tile_h = text_h + pad_y * 2
            tile = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((pad_x - tx0, pad_y - ty0),
                                      text, font=F13, fill=color)
            tile = tile.rotate(90, expand=True, resample=Image.BICUBIC)
            img.paste(tile, (cx - tile.width // 2, top_y), tile)

        for i in range(n_h):
            # Always keep the first and last historic dates; thin the rest
            keep = (i == 0) or (i == n_h - 1) or (i % 2 == 0)
            if not keep:
                continue
            if i < len(dates_lbl):
                dl = dates_lbl[i]
                if dl:
                    _draw_rot_label(_px(i), py1 + 22, dl, INK3)
        if has_forecast:
            for i in range(n_f):
                dl = fc_dlbl[i] if i < len(fc_dlbl) else ""
                if not dl:
                    continue
                _draw_rot_label(_px(n_h + i), py1 + 22, dl, GLD2)

        # Current price callout — placed beside the boundary dot
        cur_x, cur_y = _px(n_h - 1), _py(closings_22k[-1])
        cur_lbl = f"₹{closings_22k[-1]:,}"
        cw = _tw(cur_lbl, F13) + 14
        pill_x0 = cur_x - cw - 8
        if pill_x0 < px0:
            pill_x0 = cur_x + 12
        pill_y0 = cur_y - 26
        if pill_y0 < py0 + 2:
            pill_y0 = cur_y + 10
        drw.rounded_rectangle([(pill_x0, pill_y0),
                                (pill_x0 + cw, pill_y0 + 18)], radius=5, fill=BLU)
        drw.text((pill_x0 + 7, pill_y0 + 1), cur_lbl,
                 font=F13, fill=BG if sum(BLU) > 350 else (255, 255, 255))

        # ── In-chart indicator strip (inside the same panel) ──────────────
        # Renders directly below the date axis, still inside the chart card.
        if has_forecast:
            d_today = pred_dir  # guaranteed UP or DOWN — see top of build_image
            try:
                c_today = float((prediction or {}).get("confidence", 0) or 0)
            except (TypeError, ValueError):
                c_today = 0.0
            d_col = GRN if "UP" in d_today else (RED if "DOWN" in d_today else AMB)
            d_arr = "▲" if "UP" in d_today else ("▼" if "DOWN" in d_today else "—")
            move_pct = (fc_mids[-1] - closings_22k[-1]) / max(1, closings_22k[-1]) * 100
            mv_col = GRN if move_pct >= 0 else RED
            band_pct = (fc_his[-1] - fc_los[-1]) / max(1, fc_mids[-1]) * 100
            cv = closings_22k[-1]
            cards = [
                ("Today's call",
                 f"{d_arr} {d_today}",
                 f"Confidence {c_today:.0f}%" if c_today else "—",
                 d_col),
                ("Expected 7-day move",
                 f"{'+' if move_pct >= 0 else ''}{move_pct:.2f}%",
                 f"₹{cv:,} → ₹{fc_mids[-1]:,}",
                 mv_col),
                ("Day-7 range",
                 f"₹{fc_los[-1]:,} – ₹{fc_his[-1]:,}",
                 f"±{band_pct/2:.1f}% band",
                 GLD),
                ("Bulk buying (22K)",
                 f"10g = ₹{cv * 10:,}",
                 f"8g ₹{cv*8:,}  ·  12g ₹{cv*12:,}",
                 INK),
            ]
        else:
            cv = closings_22k[-1]
            chg22 = chg_22k or 0
            cards = [
                ("Today's price",
                 f"₹{cv:,}/g",
                 ("▲ " if chg22 >= 0 else "▼ ") + f"₹{abs(chg22):,.0f}/g",
                 GRN if chg22 >= 0 else RED),
                ("7-day change",
                 f"{chg_7d:+.2f}%" if chg_7d else "—",
                 "vs week ago",
                 GRN if (chg_7d or 0) >= 0 else RED),
                ("30-day change",
                 f"{chg_30d:+.2f}%" if chg_30d else "—",
                 "vs month ago",
                 GRN if (chg_30d or 0) >= 0 else RED),
                ("Bulk buying (22K)",
                 f"10g = ₹{cv * 10:,}",
                 f"8g ₹{cv*8:,}  ·  12g ₹{cv*12:,}",
                 INK),
            ]

        # Strip is OVERLAID at the very top of the chart, above the price
        # line, so the indicators sit visually inside the graph itself.
        n_cards = len(cards)
        gap_c   = 10
        strip_h   = 64
        strip_top = y + 14                # just under the section banner edge
        avail_w = (chart_x1 - PAD) - 2 * 16 - (n_cards - 1) * gap_c
        ccw     = avail_w // n_cards
        for ci, (lbl, big, sub, col) in enumerate(cards):
            cx0 = PAD + 16 + ci * (ccw + gap_c)
            cx1 = cx0 + ccw
            # Translucent backdrop so the chart bg shows through faintly
            _alpha_rect(cx0, strip_top, cx1, strip_top + strip_h,
                        (CARD2[0], CARD2[1], CARD2[2], 215), radius=8)
            drw.rounded_rectangle([(cx0, strip_top), (cx1, strip_top + strip_h)],
                                   radius=8, outline=DIV, width=1)
            drw.rounded_rectangle([(cx0, strip_top), (cx0 + 4, strip_top + strip_h)],
                                   radius=2, fill=col)
            drw.text((cx0 + 12, strip_top + 6),  lbl, font=F13, fill=INK3)
            drw.text((cx0 + 12, strip_top + 24), big, font=F18b, fill=col)
            drw.text((cx0 + 12, strip_top + 46), sub, font=F13, fill=INK2)

        y += ph + GAP

    # ──────────────────────────────────────────────────────────────────────
    # ③c (legacy) Compact info strip — merged into ③ above. Disabled.
    # ──────────────────────────────────────────────────────────────────────
    if False and H_PRED_INFO and len(closings_22k) >= 2:
        has_forecast = len(fc_mids) >= 2
        sh = H_PRED_INFO - 8

        if has_forecast:
            d_today = (prediction or {}).get("direction", "FLAT")
            try:
                c_today = float((prediction or {}).get("confidence", 0) or 0)
            except (TypeError, ValueError):
                c_today = 0.0
            d_col = GRN if "UP" in d_today else (RED if "DOWN" in d_today else AMB)
            d_arr = "▲" if "UP" in d_today else ("▼" if "DOWN" in d_today else "—")

            move_pct = (fc_mids[-1] - closings_22k[-1]) / max(1, closings_22k[-1]) * 100
            mv_col = GRN if move_pct >= 0 else RED
            band_pct = (fc_his[-1] - fc_los[-1]) / max(1, fc_mids[-1]) * 100

            cv = closings_22k[-1]
            cards = [
                ("Today's call",
                 f"{d_arr} {d_today}",
                 f"Confidence {c_today:.0f}%" if c_today else "—",
                 d_col),
                ("Expected 7-day move",
                 f"{'+' if move_pct >= 0 else ''}{move_pct:.2f}%",
                 f"₹{cv:,} → ₹{fc_mids[-1]:,}",
                 mv_col),
                ("Day-7 range",
                 f"₹{fc_los[-1]:,} – ₹{fc_his[-1]:,}",
                 f"±{band_pct/2:.1f}% band",
                 GLD),
                ("Bulk buying (22K)",
                 f"10g = ₹{cv * 10:,}",
                 f"8g ₹{cv*8:,}  ·  12g ₹{cv*12:,}",
                 INK),
            ]
        else:
            cv = closings_22k[-1]
            chg22 = chg_22k or 0
            cards = [
                ("Today's price",
                 f"₹{cv:,}/g",
                 ("▲ " if chg22 >= 0 else "▼ ") + f"₹{abs(chg22):,.0f}/g",
                 GRN if chg22 >= 0 else RED),
                ("7-day change",
                 f"{chg_7d:+.2f}%" if chg_7d else "—",
                 "vs week ago",
                 GRN if (chg_7d or 0) >= 0 else RED),
                ("30-day change",
                 f"{chg_30d:+.2f}%" if chg_30d else "—",
                 "vs month ago",
                 GRN if (chg_30d or 0) >= 0 else RED),
                ("Bulk buying (22K)",
                 f"10g = ₹{cv * 10:,}",
                 f"8g ₹{cv*8:,}  ·  12g ₹{cv*12:,}",
                 INK),
            ]

        n_cards = len(cards)
        gap_c   = 12
        cw      = (W - 2 * PAD - (n_cards - 1) * gap_c) // n_cards
        for ci, (lbl, big, sub, col) in enumerate(cards):
            cx0 = PAD + ci * (cw + gap_c)
            cx1 = cx0 + cw
            drw.rounded_rectangle([(cx0, y), (cx1, y + sh)], radius=10, fill=PANEL)
            drw.rounded_rectangle([(cx0, y), (cx0 + 5, y + sh)], radius=3, fill=col)
            drw.text((cx0 + 14, y + 12), lbl, font=F13, fill=INK3)
            drw.text((cx0 + 14, y + 32), big, font=F18b, fill=col)
            drw.text((cx0 + 14, y + 64), sub, font=F13, fill=INK2)

        y += sh + GAP

    # ======================================================== #
    # ⑤ FULL GOLD PRICE HISTORY (5-year, 22K /g)               #
    # ======================================================== #
    _sec("FULL GOLD PRICE HISTORY — 5 YEARS (22K /g)", "📈")
    # Modern card: subtle gradient backdrop + soft inner border
    _shadow_rect(drw, PAD, y, W - PAD, y + H_TECH, PANEL,
                 radius=14, soff=4, scol=SHD)
    _v_gradient(drw, PAD + 2, y + 2, W - PAD - 2, y + H_TECH - 2,
                CARD2, PANEL, steps=60)
    drw.rounded_rectangle([(PAD, y), (W - PAD, y + H_TECH)],
                          radius=14, outline=DIV, width=1)

    # Try to fetch up to 5 years of COMEX gold history; convert to 22K INR /g.
    long_series: list[tuple] = []   # (date, price_22k)
    try:
        import yfinance as _yf
        _h = _yf.Ticker("GC=F").history(period="5y")
        if _h is not None and len(_h) >= 30:
            for _dt, _row in _h.iterrows():
                _usd = float(_row["Close"])
                _inr_24k = _usd * usd_inr / 31.1035 * INDIA_GOLD_DUTY_FACTOR
                _inr_22k = _inr_24k * 22 / 24
                long_series.append((_dt.date(), round(_inr_22k)))
    except Exception as _exc:
        logger.warning(f"Long history fetch failed, using 30d series: {_exc}")

    # Fallback: reuse the 30-day 22K closings already computed
    if len(long_series) < 30 and closings_22k:
        from datetime import date as _date, timedelta as _td
        _today = _date.today()
        long_series = [(_today - _td(days=len(closings_22k) - i - 1), v)
                       for i, v in enumerate(closings_22k)]

    if len(long_series) >= 2:
        from datetime import date as _date2, timedelta as _td2

        # ── KPI strip (Now / 1Y / 3Y / 5Y / ATH) ────────────────────────
        vals_all = [v for _, v in long_series]
        dates_all = [d for d, _ in long_series]
        cur_v = vals_all[-1]
        cur_d = dates_all[-1]

        def _val_n_days_ago(days: int):
            target = cur_d - _td2(days=days)
            for i, d in enumerate(dates_all):
                if d >= target:
                    return vals_all[i]
            return vals_all[0]

        v1y = _val_n_days_ago(365)
        v3y = _val_n_days_ago(365 * 3)
        v5y = vals_all[0]
        ath_idx = vals_all.index(max(vals_all))
        atl_idx = vals_all.index(min(vals_all))
        ath_v, ath_d = vals_all[ath_idx], dates_all[ath_idx]

        def _pct(a, b):
            return (a - b) / max(1, b) * 100

        kpis = [
            ("Now (22K /g)",  f"₹{cur_v:,}",
             cur_d.strftime("%d %b %Y"), GLD),
            ("1-Year change", f"{_pct(cur_v, v1y):+.1f}%",
             f"₹{v1y:,} → ₹{cur_v:,}",
             GRN if cur_v >= v1y else RED),
            ("3-Year change", f"{_pct(cur_v, v3y):+.1f}%",
             f"₹{v3y:,} → ₹{cur_v:,}",
             GRN if cur_v >= v3y else RED),
            ("5-Year change", f"{_pct(cur_v, v5y):+.1f}%",
             f"₹{v5y:,} → ₹{cur_v:,}",
             GRN if cur_v >= v5y else RED),
            ("All-time high", f"₹{ath_v:,}",
             ath_d.strftime("%d %b %Y"), AMB),
        ]
        n_k    = len(kpis)
        gap_k  = 10
        kpi_h  = 64
        kpi_x0 = PAD + 16
        kpi_x1 = W - PAD - 16
        kpi_y0 = y + 12
        avail  = (kpi_x1 - kpi_x0) - (n_k - 1) * gap_k
        kw     = avail // n_k
        for ki, (lbl, big, sub, col) in enumerate(kpis):
            kx0 = kpi_x0 + ki * (kw + gap_k)
            kx1 = kx0 + kw
            _alpha_rect(kx0, kpi_y0, kx1, kpi_y0 + kpi_h,
                        (CARD2[0], CARD2[1], CARD2[2], 220), radius=10)
            drw.rounded_rectangle([(kx0, kpi_y0), (kx1, kpi_y0 + kpi_h)],
                                  radius=10, outline=DIV, width=1)
            drw.rounded_rectangle([(kx0, kpi_y0), (kx0 + 4, kpi_y0 + kpi_h)],
                                  radius=2, fill=col)
            drw.text((kx0 + 14, kpi_y0 + 6),  lbl, font=F11,  fill=INK3)
            drw.text((kx0 + 14, kpi_y0 + 22), big, font=F18b, fill=col)
            drw.text((kx0 + 14, kpi_y0 + 46), sub, font=F11,  fill=INK2)

        # ── Plot area (below KPI strip, above year axis) ────────────────
        LP, RP, TP, BP = 78, 28, 12 + kpi_h + 18, 56
        ax0, ay0 = PAD + LP, y + TP
        ax1, ay1 = W - PAD - RP, y + H_TECH - BP

        vals = vals_all
        vmin, vmax = min(vals), max(vals)
        # Pad range a bit so line never hugs the edges
        pad = (vmax - vmin) * 0.06 if vmax > vmin else 1
        plo = vmin - pad
        phi = vmax + pad
        prng = max(phi - plo, 1)
        n = len(long_series)

        def _xp(i): return int(ax0 + (ax1 - ax0) * i / max(1, n - 1))
        def _yp(v): return int(ay1 - (ay1 - ay0) * (v - plo) / prng)

        # Y-axis: 5 dotted gridlines + price labels
        for k in range(5):
            yk = ay0 + (ay1 - ay0) * k // 4
            for xx in range(ax0, ax1, 6):
                drw.line([(xx, yk), (xx + 2, yk)], fill=DIV, width=1)
            v_g = phi - prng * k / 4
            drw.text((PAD + 8, yk - 7), f"₹{int(v_g):,}", font=F11, fill=MUT)

        # Year boundaries — pill labels + dotted vertical guides
        last_year = None
        year_xs   = []
        for i, (d, _) in enumerate(long_series):
            if d.year != last_year:
                last_year = d.year
                year_xs.append((i, d.year))
        for i_yr, yr in year_xs:
            xk = _xp(i_yr)
            for yy in range(ay0, ay1, 6):
                drw.line([(xk, yy), (xk, yy + 2)], fill=DIV, width=1)
            yl = str(yr)
            tw_y = _tw(yl, F11)
            ly0 = ay1 + 8
            lx0 = max(ax0, xk - tw_y // 2 - 6)
            lx1 = min(ax1, lx0 + tw_y + 12)
            _alpha_rect(lx0, ly0, lx1, ly0 + 18,
                        (CARD2[0], CARD2[1], CARD2[2], 220), radius=4)
            drw.text((lx0 + 6, ly0 + 2), yl, font=F11, fill=INK2)

        # ── Multi-stop gradient area fill below the price line ─────────
        try:
            line_pts = [(_xp(i), _yp(v)) for i, (_, v) in enumerate(long_series)]
            # Build 3 stacked bands of decreasing opacity for a smooth wash
            for alpha in (90, 55, 28):
                poly = [(line_pts[0][0], ay1)] + line_pts + [(line_pts[-1][0], ay1)]
                _alpha_poly(poly, (GLD[0], GLD[1], GLD[2], alpha))
        except Exception:
            line_pts = [(_xp(i), _yp(v)) for i, (_, v) in enumerate(long_series)]

        # 200-day MA first (so 50-day MA sits on top), thinner & dim
        if n >= 200:
            ma2_pts = []
            for i in range(199, n):
                avg2 = sum(vals[i - 199:i + 1]) / 200
                ma2_pts.append((_xp(i), _yp(avg2)))
            if len(ma2_pts) >= 2:
                drw.line(ma2_pts, fill=AMB, width=2)

        if n >= 50:
            ma_pts = []
            for i in range(49, n):
                avg = sum(vals[i - 49:i + 1]) / 50
                ma_pts.append((_xp(i), _yp(avg)))
            if len(ma_pts) >= 2:
                drw.line(ma_pts, fill=BLU, width=2)

        # Main price line — slightly thicker with a subtle outer glow
        if len(line_pts) >= 2:
            try:
                _alpha_lines = line_pts
                # Soft outer glow: draw same line with translucent gold
                # (PIL doesn't blur lines; emulate by widening a faint stroke).
                glow_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(glow_overlay).line(
                    _alpha_lines, fill=(GLD[0], GLD[1], GLD[2], 70), width=7)
                img.paste(glow_overlay, (0, 0), glow_overlay)
            except Exception:
                pass
            drw.line(line_pts, fill=GLD, width=3)

        # 5-year high / low markers with dotted guideline down to axis
        for i_m, label, col in [(ath_idx, f"5Y HIGH ₹{vals[ath_idx]:,}", GRN),
                                (atl_idx, f"5Y LOW ₹{vals[atl_idx]:,}",   RED)]:
            xm, ym = _xp(i_m), _yp(vals[i_m])
            for yy in range(ym, ay1, 5):
                drw.line([(xm, yy), (xm, yy + 2)], fill=col, width=1)
            drw.ellipse([(xm - 7, ym - 7), (xm + 7, ym + 7)], fill=PANEL)
            drw.ellipse([(xm - 5, ym - 5), (xm + 5, ym + 5)], fill=col)
            drw.ellipse([(xm - 2, ym - 2), (xm + 2, ym + 2)], fill=CARD)
            tw_l = _tw(label, F11)
            place_above = ym - 26 >= ay0 + 2
            ly = ym - 24 if place_above else ym + 10
            lx = max(ax0, min(ax1 - tw_l - 12, xm - tw_l // 2 - 6))
            _alpha_rect(lx, ly, lx + tw_l + 12, ly + 18,
                        (PANEL[0], PANEL[1], PANEL[2], 235), radius=5)
            drw.rounded_rectangle([(lx, ly), (lx + tw_l + 12, ly + 18)],
                                  radius=5, outline=col, width=1)
            drw.text((lx + 6, ly + 2), label, font=F11, fill=col)

        # Current price pill at the right edge
        cx, cy = _xp(n - 1), _yp(vals[-1])
        cur_lbl = f"NOW ₹{vals[-1]:,}"
        cw = _tw(cur_lbl, F13) + 16
        drw.ellipse([(cx - 7, cy - 7), (cx + 7, cy + 7)], fill=PANEL)
        drw.ellipse([(cx - 5, cy - 5), (cx + 5, cy + 5)], fill=BLU)
        px0_p = max(ax0, cx - cw - 8)
        py0_p = max(ay0 + 2, cy - 28)
        drw.rounded_rectangle([(px0_p, py0_p), (px0_p + cw, py0_p + 20)],
                              radius=6, fill=BLU)
        drw.text((px0_p + 8, py0_p + 2), cur_lbl, font=F13,
                 fill=BG if sum(BLU) > 350 else (255, 255, 255))

        # Footer summary band
        first_v = vals[0]
        chg_pct = (vals[-1] - first_v) / max(1, first_v) * 100
        chg_col = GRN if chg_pct >= 0 else RED
        chg_arr = "▲" if chg_pct >= 0 else "▼"
        summary = (f"{n} trading days  ·  "
                   f"Range ₹{vmin:,} – ₹{vmax:,}  ·  "
                   f"5Y change {chg_arr} {abs(chg_pct):.1f}%")
        drw.text((PAD + 16, y + H_TECH - 24), summary, font=F13, fill=chg_col)

        # Mini-legend (right side of footer)
        leg_x = ax1 - 240
        leg_y = y + H_TECH - 26
        drw.line([(leg_x, leg_y + 8), (leg_x + 22, leg_y + 8)], fill=GLD, width=3)
        drw.text((leg_x + 28, leg_y + 2), "Price", font=F11, fill=INK3)
        drw.line([(leg_x + 80, leg_y + 8), (leg_x + 102, leg_y + 8)], fill=BLU, width=2)
        drw.text((leg_x + 108, leg_y + 2), "50d MA", font=F11, fill=INK3)
        drw.line([(leg_x + 160, leg_y + 8), (leg_x + 182, leg_y + 8)], fill=AMB, width=2)
        drw.text((leg_x + 188, leg_y + 2), "200d MA", font=F11, fill=INK3)
    else:
        drw.text((PAD + 18, y + 18), "Insufficient history available.", font=F13, fill=MUT)

    y += H_TECH + GAP

    # ============================================================ #
    # ⑥ BUYING GUIDE  +  ⑧ GRT TODAY'S OFFERS  (collage, 2-column) #
    # ============================================================ #
    has_grt_offers = bool(grt_22k and grt_offers)

    # Left side: 3 KPI cards in a horizontal strip
    L_KPI_H     = 156                     # height of each KPI tile
    L_MIN_H     = L_KPI_H + 24            # tile + top/bot pad
    # Right side: GRT offers as a 2-column small-card grid
    R_HEADER_H   = 34
    R_FOOT_PAD   = 12
    R_CARD_H     = 72
    R_CARD_GAP   = 8
    R_CARD_COLS  = 2
    R_CARD_ROWS  = ((len(grt_offers) + R_CARD_COLS - 1) // R_CARD_COLS
                    if has_grt_offers else 0)
    R_NEED_H     = (R_HEADER_H
                    + R_CARD_ROWS * (R_CARD_H + R_CARD_GAP)
                    - (R_CARD_GAP if R_CARD_ROWS else 0)
                    + R_FOOT_PAD * 2
                    if has_grt_offers else 0)
    H_COLLAGE    = max(L_MIN_H, R_NEED_H) if has_grt_offers else L_MIN_H

    if has_grt_offers:
        _sec("BUYING GUIDE & TODAY'S OFFERS", "💡")
    else:
        _sec("BUYING GUIDE & RECOMMENDATION", "💡")

    # 60 / 40 split for breathing room (left has 3 KPI tiles)
    LCW = int((W - 2 * PAD - 14) * 0.60) if has_grt_offers else (W - 2 * PAD)
    lx0 = PAD
    lx1 = lx0 + LCW
    rx0 = lx1 + 14
    rx1 = W - PAD

    # ── LEFT: Buying Guide as 3 KPI cards ────────────────────────────────
    drw.rounded_rectangle([(lx0, y), (lx1, y + H_COLLAGE)], radius=10, fill=PANEL)
    _v_gradient(drw, lx0 + 2, y + 2, lx1 - 2, y + H_COLLAGE - 2,
                PANEL, CARD2, steps=40)
    drw.rounded_rectangle([(lx0, y), (lx1, y + H_COLLAGE)],
                          radius=10, outline=DIV, width=1)

    # 3 tiles side-by-side
    L_INNER_PAD = 12
    L_GAP       = 10
    tile_w      = (LCW - 2 * L_INNER_PAD - 2 * L_GAP) // 3
    tile_y0     = y + (H_COLLAGE - L_KPI_H) // 2
    tile_y1     = tile_y0 + L_KPI_H

    def _draw_kpi_tile(col_idx: int, accent, label: str,
                       big_val: str, big_col,
                       sub1: str = "", sub2: str = ""):
        tx0 = lx0 + L_INNER_PAD + col_idx * (tile_w + L_GAP)
        tx1 = tx0 + tile_w
        # Tile body — subtle vertical gradient
        drw.rounded_rectangle([(tx0, tile_y0), (tx1, tile_y1)],
                              radius=10, fill=CARD2)
        _v_gradient(drw, tx0 + 1, tile_y0 + 1, tx1 - 1, tile_y1 - 1,
                    CARD2, PANEL, steps=24)
        drw.rounded_rectangle([(tx0, tile_y0), (tx1, tile_y1)],
                              radius=10, outline=DIV, width=1)
        # Top accent bar
        _h_gradient(drw, tx0, tile_y0, tx1, tile_y0 + 4, accent, accent, steps=2)
        drw.rounded_rectangle([(tx0, tile_y0), (tx1, tile_y0 + 4)],
                              radius=2, fill=accent)
        # Label
        drw.text((tx0 + 12, tile_y0 + 12), label[:30], font=F13, fill=INK3)
        # Big value (auto-shrunk to fit width)
        bv = big_val[:32]
        bv_font = F22b
        if _tw(bv, bv_font) > tile_w - 24:
            bv_font = F18b
        if _tw(bv, bv_font) > tile_w - 24:
            bv = bv[:18] + "…"
        drw.text((tx0 + 12, tile_y0 + 40), bv, font=bv_font, fill=big_col)
        # Sub-lines
        if sub1:
            drw.text((tx0 + 12, tile_y0 + 86), sub1[:48], font=F13, fill=INK2)
        if sub2:
            drw.text((tx0 + 12, tile_y0 + 112), sub2[:50], font=F11, fill=MUT)

    # Tile 1 — Best Day to Buy
    bd_sub1 = f"Window: {win_label}" if win_label else ""
    bd_sub2 = (f"Top 3: {', '.join(_ordinal(d) for d in top3_days)}"
               if top3_days else "")
    _draw_kpi_tile(
        0, GLD, "Best Day to Buy",
        f"📅 {_ordinal(best_day)}" if best_day else "—",
        GLD, bd_sub1, bd_sub2,
    )

    # Tile 2 — Cheapest Day This Month (22K)
    if ml_day:
        m2_sub1 = f"₹{ml_price_22k:,}/g" if ml_price_22k else ""
        m2_sub2 = f"Trend: {ml_trend}" if ml_trend else ""
        _draw_kpi_tile(
            1, GRN, "Cheapest This Month",
            f"📉 {_ordinal(ml_day)}", GRN, m2_sub1, m2_sub2,
        )
    else:
        _draw_kpi_tile(1, GRN, "Cheapest This Month",
                       "Calculating…", MUT, "", "")

    # Tile 3 — Today's Recommendation
    if a_rec:
        rc = (a_rec.replace("🟢","").replace("🔴","").replace("🟡","")
              .replace("⚪","").replace("🟠","").strip())
        rcol = GRN if "BUY" in a_rec.upper() else (
               RED if any(w in a_rec.upper() for w in ("AVOID","WAIT","SELL")) else AMB)
        parts = rc.split(" – ")
        head = parts[0]
        sub  = parts[1] if len(parts) > 1 else ""
    else:
        head, sub, rcol = "—", "", AMB
    _draw_kpi_tile(
        2, rcol, "Today's Recommendation",
        head, rcol, sub,
        f"Signal: {pred_dir}  ({pred_score:+.1f})",
    )

    # ── RIGHT: GRT offers as a 2-column small-card grid ──────────────────
    if has_grt_offers:
        drw.rounded_rectangle([(rx0, y), (rx1, y + H_COLLAGE)], radius=10, fill=PANEL)
        _v_gradient(drw, rx0 + 2, y + R_HEADER_H, rx1 - 2, y + H_COLLAGE - 2,
                    PANEL, CARD2, steps=40)
        drw.rounded_rectangle([(rx0, y), (rx1, y + H_COLLAGE)],
                              radius=10, outline=DIV, width=1)

        # Header strip
        _h_gradient(drw, rx0, y, rx1, y + R_HEADER_H, GLD2, GLD, steps=28)
        ttl     = "GRT JEWELLERS — TODAY'S OFFERS"
        ttl_col = BG if sum(GLD) > 380 else INK
        drw.text((rx0 + 14, y + 9), ttl, font=F14, fill=ttl_col)

        off_section_colours = [AMB, BLU, GRN2, GLD2, SIL]
        off_seen: dict[str, int] = {}

        grid_x0 = rx0 + R_FOOT_PAD
        grid_x1 = rx1 - R_FOOT_PAD
        grid_y0 = y + R_HEADER_H + R_FOOT_PAD
        card_w  = (grid_x1 - grid_x0 - R_CARD_GAP * (R_CARD_COLS - 1)) // R_CARD_COLS

        for oi, off in enumerate(grt_offers):
            row = oi // R_CARD_COLS
            col = oi %  R_CARD_COLS
            cx0 = grid_x0 + col * (card_w + R_CARD_GAP)
            cy0 = grid_y0 + row * (R_CARD_H + R_CARD_GAP)
            cx1 = cx0 + card_w
            cy1 = cy0 + R_CARD_H
            if cy1 > y + H_COLLAGE - 4:
                break

            sec = off.get("section", "")
            if sec not in off_seen:
                off_seen[sec] = len(off_seen) % len(off_section_colours)
            scol = off_section_colours[off_seen[sec]]

            # Card body + soft gradient
            drw.rounded_rectangle([(cx0, cy0), (cx1, cy1)], radius=8, fill=CARD2)
            _v_gradient(drw, cx0 + 1, cy0 + 1, cx1 - 1, cy1 - 1,
                        CARD2, PANEL, steps=18)
            drw.rounded_rectangle([(cx0, cy0), (cx1, cy1)],
                                  radius=8, outline=DIV, width=1)
            # Top accent bar (section colour)
            drw.rounded_rectangle([(cx0, cy0), (cx1, cy0 + 4)],
                                  radius=2, fill=scol)

            # Section abbreviation
            abv = (sec[:14] if sec else "Offer").upper()
            drw.text((cx0 + 10, cy0 + 10), abv, font=F11, fill=scol)

            # Title — wrap to 2 lines if needed
            title   = off.get("title", "")
            avail_w = card_w - 20
            # crude word-wrap
            words   = title.split()
            line1, line2, cur = "", "", ""
            for w in words:
                trial = (cur + " " + w).strip()
                if _tw(trial, F13) <= avail_w:
                    cur = trial
                else:
                    if not line1:
                        line1 = cur
                        cur   = w
                    else:
                        line2 = cur
                        cur   = w
                        break
            if not line1:
                line1 = cur
                cur   = ""
            if not line2:
                line2 = cur
            # truncate line2 with ellipsis if more text remains
            remaining = title[len((line1 + " " + line2).strip()):].strip()
            if remaining and line2:
                while line2 and _tw(line2 + " …", F13) > avail_w:
                    line2 = line2[:-1]
                line2 = (line2 + " …").strip()
            drw.text((cx0 + 10, cy0 + 30), line1, font=F13, fill=INK)
            if line2:
                drw.text((cx0 + 10, cy0 + 50), line2, font=F13, fill=INK2)

    y += H_COLLAGE + GAP

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

    # (Section ⑧ GRT offers is rendered above as part of the collage.)

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
