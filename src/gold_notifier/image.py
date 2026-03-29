"""
automations/gold_notifier/image.py
====================================
Pillow-based gold price card image generator.
"""

import logging
import math as _math
import os
from datetime import date, datetime, timedelta

from .config import INDIA_GOLD_DUTY_FACTOR, IMAGE_OUTPUT_PATH

logger = logging.getLogger(__name__)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11<=n<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"


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
    light_mode: bool = False,
    out_path: str = IMAGE_OUTPUT_PATH,
) -> str | None:
    """
    Draw a compact gold price card using Pillow and save it as a PNG.
    Returns the file path on success, None on failure.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not installed — skipping image generation. Run: pip install pillow")
        return None

    # ── Dark palette ──────────────────────────────────────────────────────
    BG = (10, 12, 20); BG2 = (16, 19, 32); CARD = (22, 26, 42)
    CARD2 = (28, 34, 54); CARD3 = (34, 40, 64)
    GOLD = (255, 200, 50); GOLD_DIM = (180, 140, 30)
    WHITE = (232, 235, 242); MUTED = (130, 140, 165)
    GREEN = (55, 195, 105); GREEN_D = (25, 90, 50)
    RED = (255, 65, 65); RED_D = (100, 20, 20)
    ORANGE = (255, 150, 35); YELLOW = (250, 210, 45)
    GREY = (85, 92, 115); DIV = (36, 42, 66)
    TEAL = (30, 150, 140); BLUE = (60, 120, 210)
    SILVER_COL = (192, 200, 215)

    if light_mode:
        BG = (255,255,255); BG2 = (245,246,250); CARD = (232,235,245)
        CARD2 = (218,222,236); CARD3 = (200,206,225)
        WHITE = (18,20,38); MUTED = (75,85,115); GREY = (110,118,145); DIV = (185,190,210)
        GOLD = (180,130,0); GOLD_DIM = (140,100,0)
        GREEN = (25,145,65); GREEN_D = (180,230,200)
        RED = (200,30,30); RED_D = (245,185,185)
        ORANGE = (200,100,0); YELLOW = (160,120,0)
        TEAL = (10,120,110); BLUE = (30,90,180)

    W = 960; PAD = 22; HALF = W // 2
    now_str = datetime.now().strftime("%d %b %Y  •  %I:%M %p")

    def fnt(size, bold=False):
        candidates = ["C:/Windows/Fonts/segoeui.ttf","C:/Windows/Fonts/arial.ttf",
                      "C:/Windows/Fonts/DejaVuSans.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        bold_cands = ["C:/Windows/Fonts/segoeuib.ttf","C:/Windows/Fonts/arialbd.ttf",
                      "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        for p in (bold_cands + candidates if bold else candidates):
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    F_TITLE = fnt(30, bold=True); F_H1 = fnt(22, bold=True)
    F_H2 = fnt(17, bold=True); F_REG = fnt(14); F_SM = fnt(13); F_XSM = fnt(12)

    def th(f): return f.size + 5

    def dc(direction):
        return GREEN if direction == "UP" else (RED if direction == "DOWN" else YELLOW)

    def vc(v):
        return GREEN if v > 0 else (RED if v < 0 else GREY)

    def hline(d, y, x0=PAD, x1=W-PAD, col=DIV, width=1):
        d.line([(x0, y+4), (x1, y+4)], fill=col, width=width)
        return y + 12

    def sec_hdr(d, y, title, x0=PAD, x1=W-PAD, icon_col=GOLD):
        bar_h = 32
        d.rectangle([(x0, y), (x1, y+bar_h)], fill=CARD2)
        d.rectangle([(x0, y+bar_h-4), (x1, y+bar_h)], fill=icon_col)
        d.text((x0+10, y+7), title, font=F_H2, fill=icon_col)
        return y + bar_h + 6

    def badge(d, x, y, txt, bg, fg=None, f=None):
        if fg is None: fg = BG
        if f is None:  f  = F_XSM
        bb = d.textbbox((0,0), txt, font=f)
        tw, bh = bb[2]-bb[0], bb[3]-bb[1]
        px, py = 7, 3
        d.rounded_rectangle([(x,y),(x+tw+px*2,y+bh+py*2)], radius=5, fill=bg)
        d.text((x+px, y+py), txt, font=f, fill=fg)
        return int(x + tw + px*2 + 6)

    def hbar(d, x, y, w, h, pct, fg, bg=None):
        if bg is None: bg = CARD2
        d.rectangle([(x,y),(x+w,y+h)], fill=bg)
        filled = max(2, int(w * max(0.0, min(1.0, pct))))
        d.rectangle([(x,y),(x+filled,y+h)], fill=fg)
        d.rectangle([(x+filled-1,y),(x+filled+1,y+h)], fill=WHITE)

    def gauge(d, cx, cy, r, score):
        val = max(0.02, min(0.98, (score+10)/20.0))
        bb  = [(cx-r,cy-r),(cx+r,cy+r)]
        d.arc(bb, start=150, end=30, fill=(50,55,80), width=10)
        for zs,ze,zc in [(150,210,RED_D),(210,270,(80,70,20)),(270,30,GREEN_D)]:
            d.arc(bb, start=zs, end=ze, fill=zc, width=8)
        col_end = int(150 + 240*val) % 360
        col = RED if val < 0.35 else (YELLOW if val < 0.65 else GREEN)
        d.arc(bb, start=150, end=col_end, fill=col, width=10)
        needle_pillow = 150 + 240*val
        ang = _math.radians(-needle_pillow)
        nr  = r - 16
        nx  = cx + int(nr * _math.cos(ang)); ny = cy - int(nr * _math.sin(ang))
        d.line([(cx,cy),(nx,ny)], fill=WHITE, width=3)
        d.ellipse([(cx-5,cy-5),(cx+5,cy+5)], fill=WHITE)
        lbl = f"{score:+.1f}"
        lb = d.textbbox((0,0), lbl, font=F_XSM); lw = lb[2]-lb[0]
        d.text((cx-lw//2, cy+8), lbl, font=F_XSM, fill=WHITE)

    # ── Extract data ───────────────────────────────────────────────────────
    usd_inr    = data["usd_inr_rate"]  if data else 84.0
    ibja       = data.get("ibja")      if data else None
    gr_chennai = data.get("gr_chennai") if data else None
    if gr_chennai:
        p24k, p22k, src = gr_chennai["24k"], gr_chennai["22k"], f"Chennai ({gr_chennai['date']})"
    elif ibja:
        p24k, p22k, src = ibja["24k"], ibja["22k"], f"IBJA {ibja['date']}"
    elif data:
        p24k = round(data["price_inr_per_g"] * INDIA_GOLD_DUTY_FACTOR)
        p22k = round(p24k * 22 / 24); src = "Live market estimate"
    else:
        p24k = p22k = 0; src = "N/A"

    chg_val   = round(data["change_inr_g"]) if data and data.get("change_inr_g") is not None else None
    chg_7d    = analysis.get("chg_7d")  if analysis else None
    chg_30d   = analysis.get("chg_30d") if analysis else None
    hist_rows = (history or [])[:10]
    wk_rows   = (weekly_prediction or [])[:7]
    votes     = (global_signals or {}).get("votes", {})

    _hdr_deep  = BG2   if not light_mode else (210,215,230)
    _hdr_strip = CARD2 if not light_mode else (190,196,218)

    H    = max(2200, 72+170+200+160+250+260+320+350+60+PAD*12)
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    y    = 0

    # ── Header ────────────────────────────────────────────────────────────
    draw.rectangle([(0,0),(W,68)], fill=_hdr_deep)
    draw.rectangle([(0,0),(W,4)],  fill=GOLD)
    draw.rectangle([(0,64),(W,68)],fill=_hdr_strip)
    draw.text((PAD,12), "🥇  Gold Price Update", font=F_TITLE, fill=GOLD)
    draw.text((PAD,46), now_str, font=F_SM, fill=MUTED)
    badge(draw, W-PAD-130, 44, f"USD/INR ₹{usd_inr:.2f}", bg=CARD3, fg=MUTED)
    draw.text((PAD, 12), f"Source: {src}", font=F_XSM, fill=GREY)
    y = 72

    # ── Live price cards ──────────────────────────────────────────────────
    y = sec_hdr(draw, y, "LIVE GOLD PRICE", icon_col=GOLD)
    card_w = (W - PAD*3) // 2; card_h = 88; card_y = y + 4
    for ci, (carat, price) in enumerate([("24 Carat", p24k), ("22 Carat", p22k)]):
        cx0 = PAD + ci*(card_w+PAD)
        draw.rectangle([(cx0,card_y),(cx0+card_w,card_y+card_h)], fill=CARD)
        draw.rectangle([(cx0,card_y),(cx0+card_w,card_y+card_h//2)], fill=CARD2)
        accent = GOLD if ci == 0 else GOLD_DIM
        draw.rectangle([(cx0,card_y),(cx0+card_w,card_y+3)], fill=accent)
        draw.text((cx0+12, card_y+8), carat, font=F_SM, fill=MUTED)
        draw.text((cx0+12, card_y+26), f"₹{price:,}", font=F_H1, fill=WHITE)
        draw.text((cx0+12, card_y+54), f"/gram", font=F_XSM, fill=MUTED)
        draw.text((cx0+80, card_y+54), f"8g = ₹{price*8:,}", font=F_XSM, fill=MUTED)
        if chg_val is not None and ci == 0:
            chg_col = GREEN if chg_val > 0 else (RED if chg_val < 0 else GREY)
            sign    = "▲+" if chg_val > 0 else ("▼" if chg_val < 0 else "─")
            draw.text((cx0+card_w-110, card_y+30), f"{sign}₹{abs(chg_val):,}", font=F_SM, fill=chg_col)
            draw.text((cx0+card_w-110, card_y+48), "vs yesterday", font=F_XSM, fill=MUTED)
    y = card_y + card_h + 8

    # ── Silver card ────────────────────────────────────────────────────────
    sc_y = y
    draw.rectangle([(PAD,sc_y),(W-PAD,sc_y+48)], fill=CARD)
    draw.rectangle([(PAD,sc_y),(W-PAD,sc_y+24)], fill=CARD2)
    draw.rectangle([(PAD,sc_y),(PAD+3,sc_y+48)], fill=SILVER_COL)
    if silver:
        ag_inr_g = silver["price_inr_g"]; ag_inr_kg = silver["price_inr_kg"]
        ag_usd = silver["price_usd"]; ag_chg = silver.get("change_inr_g")
        gs_ratio = silver.get("gs_ratio"); src_tag = silver.get("source","")
        draw.text((PAD+10,sc_y+6),  "Silver (999 fine)", font=F_SM,  fill=SILVER_COL)
        draw.text((PAD+10,sc_y+26), f"₹{ag_inr_g:,.2f} /gram",       font=F_H2, fill=WHITE)
        draw.text((PAD+240,sc_y+30),f"₹{ag_inr_kg:,}/kg",             font=F_XSM, fill=MUTED)
        src_lbl = f"${ag_usd:.2f}/oz  ({src_tag})"
        src_bb  = draw.textbbox((0,0), src_lbl, font=F_XSM)
        draw.text((W-PAD-(src_bb[2]-src_bb[0])-4, sc_y+6), src_lbl, font=F_XSM, fill=MUTED)
        if ag_chg is not None:
            s_col  = GREEN if ag_chg > 0 else (RED if ag_chg < 0 else GREY)
            s_sign = "▲+" if ag_chg > 0 else ("▼" if ag_chg < 0 else "─")
            draw.text((PAD+380,sc_y+30), f"{s_sign}₹{abs(ag_chg):.2f}/g today", font=F_XSM, fill=s_col)
        if gs_ratio:
            if   gs_ratio > 90: rc,rt = RED,        f"G/S {gs_ratio} — gold overvalued"
            elif gs_ratio < 65: rc,rt = GREEN,      f"G/S {gs_ratio} — gold undervalued"
            else:               rc,rt = SILVER_COL, f"G/S ratio: {gs_ratio}"
            badge(draw, W-PAD-210, sc_y+26, rt, bg=CARD3, fg=rc)
    else:
        draw.text((PAD+10,sc_y+6),  "Silver (999 fine)", font=F_SM, fill=SILVER_COL)
        draw.text((PAD+10,sc_y+26), "Price data unavailable", font=F_REG, fill=GREY)
    y = sc_y + 54

    # ── Change pills + sparkline ──────────────────────────────────────────
    px_b = PAD
    if chg_7d is not None:
        c7 = float(chg_7d)
        px_b = badge(draw, px_b, y, f"7d: {'+' if c7>=0 else ''}{c7:.1f}%",
                     bg=(GREEN if c7>=0 else RED), fg=BG)
    if chg_30d is not None:
        c30 = float(chg_30d)
        px_b = badge(draw, px_b, y, f"30d: {'+' if c30>=0 else ''}{c30:.1f}%",
                     bg=(GREEN if c30>=0 else RED), fg=BG)
    if hist_rows:
        sp_x0,sp_y0 = W-PAD-160, y; sp_w,sp_h = 160, 22
        sp_prices   = [r["22k"] for r in reversed(hist_rows)]
        sp_min = min(sp_prices)-100; sp_max = max(sp_prices)+100; sp_rng = max(1,sp_max-sp_min)
        sp_pts = [
            (sp_x0 + int(i*sp_w/max(1,len(sp_prices)-1)),
             sp_y0 + sp_h - int(sp_h*(p-sp_min)/sp_rng))
            for i,p in enumerate(sp_prices)
        ]
        if len(sp_pts) >= 2:
            draw.line(sp_pts, fill=GOLD_DIM, width=2)
        for pt in sp_pts:
            draw.ellipse([(pt[0]-2,pt[1]-2),(pt[0]+2,pt[1]+2)], fill=GOLD)
        draw.text((sp_x0,sp_y0+sp_h+2), "22K trend (10d)", font=F_XSM, fill=GREY)
    y += 18

    # ── Strong buy alert ──────────────────────────────────────────────────
    if (p24k < 12_500) and (chg_30d is not None) and (float(chg_30d) <= -5.0):
        _c30 = float(chg_30d); _p30 = round(p24k/(1+_c30/100))
        draw.rectangle([(PAD,y),(W-PAD,y+52)], fill=(110,15,15))
        draw.rectangle([(PAD,y),(PAD+3,y+52)], fill=RED)
        draw.text((PAD+10,y+5),  f"🚨  RARE BUY OPPORTUNITY  —  24K ₹{p24k:,}/g  (BELOW ₹12,500!)", font=F_H2, fill=(255,240,60))
        draw.text((PAD+10,y+30), f"Price is {abs(_c30):.1f}% cheaper than 30 days ago (was ₹{_p30:,}/g)  —  Strong case to BUY", font=F_XSM, fill=(255,200,200))
        y += 58
    y = hline(draw, y)

    # ── Gauge + today's outlook ───────────────────────────────────────────
    row_b_y = y
    y = sec_hdr(draw, y, "PREDICTION SIGNAL GAUGE", x1=HALF-4, icon_col=TEAL)
    tech_score = (analysis["score"] if analysis else 0.0) + (geo["geo_score"] if geo else 0.0)
    pred_score = float(prediction.get("score", 0.0)) if prediction else 0.0
    combined   = round(tech_score + pred_score*0.3, 1)
    gauge_cx   = HALF//2; gauge_cy = y+44; gauge_r = 48
    gauge(draw, gauge_cx, gauge_cy, gauge_r, combined)
    draw.text((PAD, gauge_cy+gauge_r+4), "SELL", font=F_XSM, fill=RED)
    draw.text((gauge_cx-14, gauge_cy+gauge_r+4), "HOLD", font=F_XSM, fill=YELLOW)
    draw.text((HALF-PAD-28, gauge_cy+gauge_r+4), "BUY", font=F_XSM, fill=GREEN)
    if prediction:
        sig = prediction.get("signal_votes",{}); ups = sum(1 for v in sig.values() if v>0); downs = sum(1 for v in sig.values() if v<0)
        sv_y = gauge_cy+gauge_r+20
        draw.text((PAD, sv_y), f"UP signals: {ups}  /  DOWN: {downs}", font=F_XSM, fill=WHITE)
        hbar(draw, PAD, sv_y+16, HALF-PAD*2, 8, ups/max(1,ups+downs), GREEN, bg=(60,20,20))
        row_b_gauge_end = sv_y+30
    else:
        row_b_gauge_end = gauge_cy+gauge_r+20

    # Right: today's outlook
    ry = row_b_y; ry = sec_hdr(draw, ry, "TODAY'S OUTLOOK", x0=HALF+4, x1=W-PAD, icon_col=TEAL)
    rx = HALF+14
    if prediction:
        d_val = prediction["direction"]; conf = prediction["confidence"]
        arr   = "▲" if d_val=="UP" else ("▼" if d_val=="DOWN" else "→")
        pcol  = dc(d_val)
        d_eng = {"UP":"Going UP","DOWN":"Going DOWN","FLAT":"Stable"}.get(d_val, d_val)
        c_eng = {"High":"Very confident","Moderate":"Fairly confident","Low":"Not sure","Uncertain":"Unclear"}.get(conf, str(conf or ""))
        draw.text((rx,ry), f"{arr}  {d_eng}", font=F_H1, fill=pcol); ry += th(F_H1)+4
        badge(draw, rx, ry, f" {c_eng} ", bg=pcol, fg=BG, f=F_SM); ry += th(F_SM)+8
        hbar(draw, rx, ry, W-rx-PAD, 10, (pred_score+10)/20.0, pcol); ry += 16
        draw.text((rx,ry), f"Score: {pred_score:+.1f}", font=F_XSM, fill=MUTED); ry += th(F_XSM)+4
        all_r = prediction.get("reasons_up",[]) + prediction.get("reasons_down",[])
        if all_r:
            draw.text((rx,ry), f"Why: {str(all_r[0])[:60]}", font=F_XSM, fill=(175,180,210))
            ry += th(F_XSM)+4
    if analysis:
        score2 = analysis["score"]+(geo["geo_score"] if geo else 0)
        if   score2 >= 5: at,ac = "✔ Good time to buy", GREEN
        elif score2 >= 2: at,ac = "✔ Okay to buy",      YELLOW
        elif score2 >= 0: at,ac = "~ Wait for dip",     MUTED
        else:             at,ac = "✖ Price is high",     RED
        draw.text((rx,ry), at, font=F_REG, fill=ac); ry += th(F_REG)+2
        sup = round(analysis["bb_low_usd"]  *usd_inr/31.1035)
        rec = round(analysis["recovery_usd"]*usd_inr/31.1035)
        draw.text((rx,ry), f"Support ₹{sup:,}/g  →  Target ₹{rec:,}/g", font=F_XSM, fill=MUTED)
        ry += th(F_XSM)+2

    y = max(row_b_gauge_end, ry)+4; y = hline(draw, y)

    # ── 10-day candlestick + 7-day forecast (side by side) ────────────────
    row_d_y = y
    y  = sec_hdr(draw, y,  "LAST 10 DAYS  — Candlestick  (22K /g)", x1=HALF-4, icon_col=GOLD)
    ry = row_d_y
    ry = sec_hdr(draw, ry, "7-DAY PRICE FORECAST  (22K /g)", x0=HALF+4, x1=W-PAD)

    cs_chart_end_y = y
    if hist_rows:
        prices_22k = [r["22k"] for r in hist_rows]
        p_min_h = min(prices_22k)-300; p_max_h = max(prices_22k)+300; p_rng_h = max(1,p_max_h-p_min_h)
        cs_h = 90; cs_bot = y+cs_h; cs_area = HALF-PAD-4; bw_c = cs_area//max(1,len(hist_rows))
        for gi in range(4):
            gp=p_min_h+int(p_rng_h*gi/3); gy=cs_bot-int(cs_h*gi/3)
            draw.line([(PAD,gy),(HALF-4,gy)], fill=DIV, width=1)
            draw.text((PAD,gy-11), f"₹{gp:,}", font=F_XSM, fill=GREY)
        close_pts = []
        for i,row in enumerate(reversed(hist_rows)):
            bx_c=PAD+i*bw_c; price=row["22k"]; cx_c=bx_c+bw_c//2
            body_h=max(4,int(cs_h*(price-p_min_h)/p_rng_h)); by_c=cs_bot-body_h
            col_c=GREEN if row["chg"]>=0 else RED; body_pad=max(1,bw_c//5)
            draw.rectangle([(bx_c+body_pad,by_c),(bx_c+bw_c-body_pad,cs_bot)], fill=col_c)
            draw.line([(cx_c,by_c-max(3,body_h//6)),(cx_c,cs_bot+2)], fill=col_c, width=1)
            draw.text((bx_c,by_c-15), f"₹{price:,}", font=F_XSM, fill=col_c)
            close_pts.append((cx_c,by_c))
        if len(close_pts)>=2: draw.line(close_pts, fill=GOLD_DIM, width=2)
        for pt in close_pts: draw.ellipse([(pt[0]-3,pt[1]-3),(pt[0]+3,pt[1]+3)], fill=GOLD)
        cy = cs_bot+6
        for i,row in enumerate(reversed(hist_rows)):
            bx_c=PAD+i*bw_c; parts=str(row["date"]).split()
            draw.text((bx_c+2,cy),    parts[0] if parts else "", font=F_XSM, fill=MUTED)
            draw.text((bx_c+2,cy+12), parts[1] if len(parts)>1 else "", font=F_XSM, fill=GREY)
        cy += 28
        tc = sum(r["chg"] for r in hist_rows); tc22 = round(tc*22/24)
        chg_col_s = GREEN if tc22>0 else (RED if tc22<0 else GREY)
        draw.text((PAD,cy), f"Net: {'+' if tc22>=0 else ''}₹{tc22:,}/g  Lo:₹{min(prices_22k):,}  Hi:₹{max(prices_22k):,}", font=F_XSM, fill=chg_col_s)
        cs_chart_end_y = cy+th(F_XSM)+4
    else:
        draw.text((PAD,y), "No history available", font=F_SM, fill=MUTED)
        cs_chart_end_y = y+th(F_SM)

    fc_chart_end_y = ry
    if wk_rows:
        trade_rows = [r for r in wk_rows if not r["is_weekend"]]
        fc_min  = min(r["low_22k"]  for r in trade_rows)-300 if trade_rows else p22k-500
        fc_max  = max(r["high_22k"] for r in trade_rows)+300 if trade_rows else p22k+500
        fc_rng  = max(1,fc_max-fc_min); fc_chart_h=90; fc_ch_bot=ry+fc_chart_h
        fc_col_w = (W-PAD-(HALF+4))//max(1,len(wk_rows))
        for gi in range(5):
            gp=fc_min+int(fc_rng*gi/4); gy=fc_ch_bot-int(fc_chart_h*gi/4)
            draw.line([(HALF+4,gy),(W-PAD,gy)], fill=DIV, width=1)
            draw.text((HALF+6,gy-11), f"₹{gp:,}", font=F_XSM, fill=GREY)
        hi_pts=[]; lo_pts=[]; mid_pts=[]
        for i,row in enumerate(wk_rows):
            cx_i=HALF+4+i*fc_col_w+fc_col_w//2
            if not row["is_weekend"]:
                lo_pct=(row["low_22k"]-fc_min)/fc_rng; hi_pct=(row["high_22k"]-fc_min)/fc_rng; mid_pct=(row["mid_22k"]-fc_min)/fc_rng
                lo_pts.append((cx_i,fc_ch_bot-int(fc_chart_h*lo_pct)))
                hi_pts.append((cx_i,fc_ch_bot-int(fc_chart_h*hi_pct)))
                mid_pts.append((cx_i,fc_ch_bot-int(fc_chart_h*mid_pct)))
        net_dir   = "UP" if sum(1 for r in trade_rows if r["direction"]=="UP") > len(trade_rows)//2 else "DOWN"
        band_fill = GREEN_D if net_dir=="UP" else RED_D
        line_col  = GREEN   if net_dir=="UP" else RED
        if len(hi_pts)>=2: draw.polygon(hi_pts+list(reversed(lo_pts)), fill=band_fill)
        if len(mid_pts)>=2: draw.line(mid_pts, fill=line_col, width=2)
        mid_idx = 0
        for i,row in enumerate(wk_rows):
            cx_i=HALF+4+i*fc_col_w+fc_col_w//2
            bc=dc(row["direction"]) if not row["is_weekend"] else GREY
            if not row["is_weekend"] and mid_idx < len(mid_pts):
                mx,my=mid_pts[mid_idx]
                draw.ellipse([(mx-7,my-7),(mx+7,my+7)], fill=band_fill)
                draw.ellipse([(mx-4,my-4),(mx+4,my+4)], fill=bc)
                draw.text((mx-22,my-22), f"₹{row['mid_22k']:,}", font=F_XSM, fill=bc)
                mid_idx += 1
            else:
                draw.line([(cx_i-5,fc_ch_bot-8),(cx_i+5,fc_ch_bot-18)], fill=GREY, width=2)
                draw.line([(cx_i-5,fc_ch_bot-18),(cx_i+5,fc_ch_bot-8)], fill=GREY, width=2)
            lc=GREY if row["is_weekend"] else WHITE
            draw.text((HALF+4+i*fc_col_w+2,fc_ch_bot+4),  row["date"].strftime("%a"),    font=F_XSM, fill=lc)
            draw.text((HALF+4+i*fc_col_w+2,fc_ch_bot+18), row["date"].strftime("%d %b"), font=F_XSM, fill=MUTED)
            if not row["is_weekend"]:
                arr="▲" if row["direction"]=="UP" else ("▼" if row["direction"]=="DOWN" else "→")
                draw.text((HALF+4+i*fc_col_w+2,fc_ch_bot+32), arr, font=F_XSM, fill=bc)
        fy=fc_ch_bot+48; draw.text((HALF+6,fy), "Band = uncertainty range  •  Estimates only", font=F_XSM, fill=GREY)
        fc_chart_end_y=fy+th(F_XSM)+4
    else:
        draw.text((HALF+6,ry), "Forecast unavailable", font=F_SM, fill=MUTED)
        fc_chart_end_y=ry+th(F_SM)+4

    y = max(fc_chart_end_y, cs_chart_end_y)+4; y = hline(draw, y)

    # ── Best day to buy + historical guide (side by side) ─────────────────
    row_c_y = y
    y  = sec_hdr(draw, y,  "BEST DAY TO BUY THIS MONTH", x1=HALF-4, icon_col=TEAL)
    ry = row_c_y
    ry = sec_hdr(draw, ry, "HISTORICAL BUY GUIDE", x0=HALF+4, x1=W-PAD, icon_col=TEAL)
    rx = HALF+14

    if monthly_low_pred:
        import calendar as _cal
        mlp=monthly_low_pred; pd_=mlp["predicted_date"]; conf_tag=mlp["confidence"]
        conf_col=GREEN if conf_tag=="High" else (YELLOW if conf_tag=="Moderate" else ORANGE)
        draw.text((PAD,y), "Predicted cheapest day:", font=F_SM, fill=MUTED); y+=th(F_SM)+2
        draw.rectangle([(PAD,y),(HALF-12,y+50)], fill=CARD2)
        draw.rectangle([(PAD,y),(PAD+4,y+50)], fill=conf_col)
        draw.text((PAD+10,y+4), f"{_ordinal(mlp['predicted_day'])} {pd_.strftime('%B')}", font=F_H1, fill=WHITE)
        draw.text((PAD+10,y+32), mlp["predicted_weekday"], font=F_XSM, fill=MUTED)
        badge(draw, HALF-130, y+16, conf_tag, bg=conf_col, fg=BG); y+=56
        today_dt=date.today(); month_end_v=_cal.monthrange(today_dt.year,today_dt.month)[1]
        rem_days=[today_dt+timedelta(days=d+1) for d in range(month_end_v-today_dt.day)]
        if rem_days:
            cell_w=min(28,(HALF-PAD*2)//max(1,len(rem_days))); cell_h=22
            for di,day_d in enumerate(rem_days):
                dx=PAD+di*cell_w
                is_predicted=(day_d.day==mlp["predicted_day"])
                is_runnerup=any(c["day"]==day_d.day for c in mlp.get("top3",[])[1:3])
                is_wknd=day_d.weekday()>=5
                if is_predicted: cell_c=conf_col; txt_c=BG
                elif is_runnerup: cell_c=CARD3;   txt_c=conf_col
                else: cell_c=CARD if not is_wknd else BG; txt_c=GREY if is_wknd else MUTED
                draw.rectangle([(dx,y),(dx+cell_w-1,y+cell_h)], fill=cell_c)
                day_s=str(day_d.day); bb=draw.textbbox((0,0),day_s,font=F_XSM); tw=bb[2]-bb[0]
                draw.text((dx+(cell_w-tw)//2,y+4), day_s, font=F_XSM, fill=txt_c)
            y+=cell_h+4
            draw.text((PAD,y), f"▓ = predicted  ░ = runner-up  {_ordinal(mlp['predicted_day'])} highlighted", font=F_XSM, fill=GREY)
            y+=th(F_XSM)+2
        draw.text((PAD,y), f"22K: ₹{mlp['low_22k']:,} – ₹{mlp['high_22k']:,} /g", font=F_SM, fill=WHITE); y+=th(F_SM)+2
        hbar(draw, PAD, y, HALF-PAD*2, 8, 0.5, GOLD); y+=12
        draw.text((PAD,y), f"24K: ₹{mlp['low_inr']:,} – ₹{mlp['high_inr']:,} /g", font=F_XSM, fill=MUTED); y+=th(F_XSM)+4
        if mlp.get("hist_aligns"):
            badge(draw, PAD, y, "✅ Matches historical cheapest-day pattern", bg=GREEN_D, fg=GREEN); y+=22
    else:
        draw.text((PAD,y), "No prediction available", font=F_SM, fill=MUTED); y+=th(F_SM)
    row_c_left_end = y

    if payment:
        lo_price=payment.get("current_month_low_price"); lo_date=payment.get("current_month_low_date")
        if lo_date and (lo_price or payment.get("current_month_low_inr22k")):
            lo_inr22=payment.get("current_month_low_inr22k") or round((lo_price/31.1035)*usd_inr*INDIA_GOLD_DUTY_FACTOR*22/24)
            days_ago=(date.today()-lo_date).days
            d_lbl="today" if days_ago==0 else f"{_ordinal(lo_date.day)} {lo_date.strftime('%b')} ({days_ago}d)"
            draw.text((rx,ry), f"Month low so far: ₹{lo_inr22:,}/g (22K)", font=F_SM, fill=WHITE); ry+=th(F_SM)+1
            draw.text((rx,ry), f"Occurred: {d_lbl}", font=F_XSM, fill=MUTED); ry+=th(F_XSM)+2
            trend=payment.get("current_month_trend","")
            t_col=GREEN if trend=="falling" else (RED if trend=="rising" else GREY)
            t_txt={"falling":"↓ Falling — consider buying soon","rising":"↑ Rising — low likely passed","flat":"→ Flat — stable"}.get(trend,"")
            if t_txt: draw.text((rx,ry), t_txt, font=F_SM, fill=t_col); ry+=th(F_SM)+4
        bd=payment.get("best_date_this_month")
        if bd:
            days_left=(bd-date.today()).days if bd>=date.today() else -1
            if days_left>=0: when="Today!" if days_left==0 else f"{_ordinal(bd.day)} {bd.strftime('%B')} ({days_left}d away)"
            else:
                nd=payment.get("best_date_next_month")
                when=nd.strftime(f"{_ordinal(nd.day)} %B %Y") if nd else "next month"
            draw.text((rx,ry), f"Historically cheapest: {_ordinal(payment['best_day'])} each month", font=F_SM, fill=WHITE); ry+=th(F_SM)+1
            draw.text((rx,ry), f"Next: {when}", font=F_XSM, fill=GOLD); ry+=th(F_XSM)+4
        mn=payment.get("scheme_month_names",{}); top3s=payment.get("scheme_top3_starts") or []
        best_sn=payment.get("scheme_best_start_name","")
        draw.text((rx,ry), "Best month to start gold scheme:", font=F_XSM, fill=MUTED); ry+=th(F_XSM)+2
        pm=rx
        for m,p2 in top3s[:3]:
            pm=badge(draw,pm,ry,f"{mn.get(m,'?')} {'✓' if p2<=0 else '+'+str(p2)+'%'}",
                     bg=(GREEN if p2<=0 else (YELLOW if p2<=1.5 else ORANGE)),fg=BG)
        ry+=24
        cur_extra=next((p2 for m,p2 in top3s if m==date.today().month),None)
        if cur_extra is not None:
            cur_m=mn.get(date.today().month,"This month")
            if   cur_extra<=0.5: nt,nc=f"✔  {cur_m} — great time to start!",GREEN
            elif cur_extra<=2.0: nt,nc=f"~  {cur_m}: okay (+{cur_extra}% vs ideal)",YELLOW
            else:                nt,nc=f"✖  {cur_m}: costly (+{cur_extra}%) — prefer {best_sn}",ORANGE
            draw.text((rx,ry), nt, font=F_XSM, fill=nc); ry+=th(F_XSM)+2
    else:
        draw.text((rx,ry), "No data", font=F_SM, fill=MUTED); ry+=th(F_SM)

    y = max(row_c_left_end, ry)+6; y = hline(draw, y)

    # ── World market signals ──────────────────────────────────────────────
    y = sec_hdr(draw, y, "WORLD MARKET SIGNALS", icon_col=BLUE)
    mkt_items = [
        ("real_yield","Real Yields","↓ Good  ↑ Bad"),("dxy","US Dollar","↓ Good  ↑ Bad"),
        ("yields","Interest Rates","↓ Good  ↑ Bad"),("yield_curve","Yield Curve","Inverted = Fear"),
        ("vix","Market Fear","↑ Good  ↓ Bad"),("risk_assets","Stock Markets","↓ Good  ↑ Bad"),
        ("oil","Oil Prices","↑ Inflationary"),("copper","Copper (Economy)","↓ Fear = Gold UP"),
        ("etf_flow","GLD ETF Flow","↑ Inst. Buying"),("gold_momentum","Gold Momentum","5-day trend"),
    ]
    bar_label_w=145; bar_w=W-PAD*2-bar_label_w-95
    for key,label,hint in mkt_items:
        v=votes.get(key,0); col=vc(v); pct=0.8 if v>0 else (0.2 if v<0 else 0.5)
        draw.rectangle([(PAD,y),(W-PAD,y+28)], fill=CARD)
        draw.rectangle([(PAD,y),(PAD+3,y+28)], fill=col)
        draw.text((PAD+8,y+7), label, font=F_XSM, fill=WHITE)
        bx0=PAD+bar_label_w; hbar(draw,bx0,y+9,bar_w,10,pct,col)
        impact_txt="GOOD ▲" if v>0 else ("BAD ▼" if v<0 else "NEUTRAL →")
        badge(draw, W-PAD-90, y+6, impact_txt, bg=col, fg=BG)
        draw.text((bx0,y+22), hint, font=F_XSM, fill=GREY); y+=32

    if global_signals:
        net=global_signals.get("net_score",0); raw_=global_signals.get("global_outlook","")
        nkey=raw_[:2]
        net_map={"🟢":("Bullish for Gold",GREEN),"🟡":("Slightly Bullish",YELLOW),
                 "⚪":("Mixed / Neutral",GREY),"🟠":("Slightly Bearish",ORANGE),"🔴":("Bearish for Gold",RED)}
        ntxt,ncol=net_map.get(nkey,(raw_ or "Unknown",GREY))
        draw.text((PAD,y+2), "Overall →", font=F_SM, fill=MUTED)
        ex=badge(draw,PAD+80,y,f" {ntxt} ",bg=ncol,fg=BG,f=F_SM)
        hbar(draw,ex+4,y+4,W-ex-PAD-10,10,(float(net)+5)/10.0,ncol); y+=22
    y += 6

    # ── Footer ─────────────────────────────────────────────────────────────
    y += 6
    draw.rectangle([(0,y),(W,y+30)], fill=_hdr_deep)
    draw.rectangle([(0,y),(W,y+2)],  fill=GOLD_DIM)
    draw.text((PAD,y+8), "⚠️ For personal reference only — not financial advice.", font=F_XSM, fill=GREY)
    draw.text((W-PAD-250,y+8), "Gold Price Notifier  •  Auto-generated", font=F_XSM, fill=GREY)
    y += 32

    final_h = min(y+14, H)
    img     = img.crop((0, 0, W, final_h))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    logger.info(f"Price image saved → {out_path}  ({W}×{final_h}px)")
    return out_path
