"""
stock_analyzer/charts.py
=========================
PIL-only chart helpers (no matplotlib dependency).

Every public function returns a ``PIL.Image.Image`` that can be:
  • pasted into the main PNG report canvas, or
  • wrapped in ``reportlab.platypus.Image(BytesIO(...))`` for the PDF.
"""

from __future__ import annotations
import io

from PIL import Image, ImageDraw, ImageFont


# ── Palette helpers ────────────────────────────────────────────────────────

_DARK = {
    "bg":     (22, 28, 42),
    "panel":  (28, 35, 52),
    "panel2": (38, 47, 68),
    "grid":   (55, 65, 85),
    "text":   (235, 238, 245),
    "muted":  (150, 160, 180),
    "accent": (90, 170, 255),
    "green":  (70, 210, 140),
    "red":    (255, 95, 110),
    "amber":  (255, 175, 80),
    "violet": (175, 130, 255),
}

_LIGHT = {
    "bg":     (255, 255, 255),
    "panel":  (248, 250, 252),
    "panel2": (236, 241, 248),
    "grid":   (220, 225, 232),
    "text":   (25, 30, 45),
    "muted":  (110, 120, 135),
    "accent": (30, 107, 216),
    "green":  (20, 140, 90),
    "red":    (200, 50, 64),
    "amber":  (230, 140, 30),
    "violet": (140, 90, 220),
}


def _pal(theme: str) -> dict:
    return _DARK if theme == "dark" else _LIGHT


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    # Mobile-readable scaling: charts internally use 10–18 pt; multiply so
    # labels stay legible when the PNG is downsampled by chat clients.
    size = max(11, int(round(size * 1.55)))
    for name in (
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, fnt) -> int:
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=fnt)
        return r - l
    except Exception:
        return len(text) * (fnt.size // 2)


# ── Public: save chart to PNG bytes (for PDF embedding) ────────────────────

def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Chart 1: Expected profit bars (top picks, colour = direction) ──────────

def chart_expected_profit(
    picks: list[dict],
    title: str,
    width: int = 1150,
    height: int = 340,
    theme: str = "dark",
) -> Image.Image:
    """Horizontal bar chart — expected profit % per top pick; bar colour by
    prediction direction (UP/DOWN/SIDEWAYS), grey when no predict."""
    pal = _pal(theme)
    img = Image.new("RGB", (width, height), pal["panel"])
    d = ImageDraw.Draw(img)

    f_title = _font(18, True)
    f_lbl   = _font(13)
    f_val   = _font(13, True)
    f_small = _font(11)

    d.text((18, 12), title, font=f_title, fill=pal["accent"])

    if not picks:
        d.text((18, 60), "No picks available.", font=f_lbl, fill=pal["muted"])
        return img

    # Normalise rows
    rows = []
    for p in picks[:10]:
        lv = p.get("levels") or {}
        pr = (p.get("predict") or {})
        rows.append({
            "sym":  p["symbol"].replace(".NS", ""),
            "pct":  float(lv.get("expected_profit_pct") or 0.0),
            "dir":  pr.get("direction", ""),
            "conf": int(pr.get("confidence") or 0),
            "hold": int(lv.get("est_hold_days") or 0),
        })

    if not rows:
        return img

    max_abs = max((abs(r["pct"]) for r in rows), default=5.0) or 5.0
    # Layout
    chart_x0 = 110
    chart_x1 = width - 140
    chart_y0 = 50
    chart_y1 = height - 24
    row_gap  = 2
    avail    = chart_y1 - chart_y0
    bar_h    = max(12, (avail - row_gap * (len(rows) - 1)) // len(rows))

    # Zero axis
    zx = chart_x0 + (chart_x1 - chart_x0) // 2
    d.line([(zx, chart_y0 - 4), (zx, chart_y1 + 4)],
           fill=pal["grid"], width=1)

    # Gridlines at ±25%, ±50%, ±75%, ±100% of max_abs
    for frac in (0.25, 0.5, 0.75, 1.0):
        for sign in (-1, +1):
            gx = zx + int(sign * frac * (chart_x1 - chart_x0) / 2)
            d.line([(gx, chart_y0), (gx, chart_y1)],
                   fill=pal["grid"], width=1)
            if sign > 0 and frac == 1.0:
                d.text((gx - 18, chart_y1 + 4), f"+{max_abs:.1f}%",
                       font=f_small, fill=pal["muted"])
            if sign < 0 and frac == 1.0:
                d.text((gx - 18, chart_y1 + 4), f"-{max_abs:.1f}%",
                       font=f_small, fill=pal["muted"])

    dir_colour = {"UP": pal["green"], "DOWN": pal["red"],
                  "SIDEWAYS": pal["amber"]}

    y = chart_y0
    for r in rows:
        bar_w = int(abs(r["pct"]) / max_abs * (chart_x1 - chart_x0) / 2)
        c     = dir_colour.get(r["dir"], pal["muted"])
        if r["pct"] >= 0:
            d.rectangle([(zx, y), (zx + bar_w, y + bar_h)], fill=c)
        else:
            d.rectangle([(zx - bar_w, y), (zx, y + bar_h)], fill=c)

        # Symbol label
        d.text((10, y + bar_h // 2 - 7), r["sym"], font=f_val, fill=pal["text"])
        # Value + confidence
        val_txt = f"{r['pct']:+.2f}%"
        if r["conf"]:
            val_txt += f"   ({r['dir']} {r['conf']}%)"
        if r["hold"]:
            val_txt += f"   hold {r['hold']}d"
        val_x = (zx + bar_w + 8) if r["pct"] >= 0 else (zx - bar_w - 8 - _text_w(d, val_txt, f_lbl))
        d.text((val_x, y + bar_h // 2 - 8), val_txt, font=f_lbl, fill=pal["text"])
        y += bar_h + row_gap

    return img


# ── Chart 2: Risk-vs-Reward scatter ────────────────────────────────────────

def chart_risk_reward(
    buckets: dict,
    width: int = 560,
    height: int = 340,
    theme: str = "dark",
) -> Image.Image:
    """Scatter of risk% (X) vs expected profit% (Y) for top picks.
    Mobile-friendly redesign: shaded R:R zones, leader-line labels,
    big legend, quadrant guides. Bubble size ∝ bucket score."""
    pal = _pal(theme)
    img = Image.new("RGB", (width, height), pal["panel"])
    d = ImageDraw.Draw(img)

    f_title = _font(17, True)
    f_sub   = _font(11)
    f_lbl   = _font(12, True)
    f_small = _font(11)
    f_axis  = _font(11, True)

    # Header band
    d.rectangle([(0, 0), (width, 38)], fill=pal["panel2"])
    d.text((16, 8),  "🎯 Risk vs Expected Profit", font=f_title, fill=pal["accent"])
    d.text((16, 26), "Bigger bubble = higher conviction · Above grey line = R:R > 1:1",
            font=f_sub, fill=pal["muted"])

    bucket_colour = {
        "intraday": pal["accent"],
        "swing":    pal["green"],
        "holding":  pal["violet"],
        "sell":     pal["red"],
    }
    bucket_label = {
        "intraday": "Same-Day",
        "swing":    "Swing",
        "holding":  "Hold",
        "sell":     "Sell",
    }

    rows = []
    for key in ("intraday", "swing", "holding", "sell"):
        for p in (buckets.get(key) or [])[:6]:
            lv = p.get("levels") or {}
            rp = float(lv.get("risk_pct") or 0.0)
            ep = float(lv.get("expected_profit_pct") or 0.0)
            if rp == 0 and ep == 0:
                continue
            rows.append({
                "sym":    p["symbol"].replace(".NS", ""),
                "risk":   rp,
                "profit": ep,
                "score":  float(p.get("bucket_score") or 50),
                "bucket": key,
            })

    # Plot area — leave generous padding for axis labels & legend at bottom
    pad_l, pad_r = 70, 22
    pad_t, pad_b = 56, 78
    x0, y0 = pad_l, pad_t
    x1, y1 = width - pad_r, height - pad_b
    plot_w = x1 - x0
    plot_h = y1 - y0

    if not rows:
        d.rectangle([(x0, y0), (x1, y1)], outline=pal["grid"], width=1)
        d.text((x0 + 14, y0 + 14), "No picks with computed levels.",
                font=f_lbl, fill=pal["muted"])
        return img

    # Axis ranges with a bit of headroom
    raw_max_risk   = max((r["risk"]   for r in rows), default=5)
    raw_max_profit = max((r["profit"] for r in rows), default=10)
    max_risk   = max(raw_max_risk   * 1.15, 4.0)
    max_profit = max(raw_max_profit * 1.15, 6.0)

    def to_xy(risk: float, profit: float) -> tuple[int, int]:
        cx = x0 + int(min(risk,   max_risk)   / max_risk   * plot_w)
        cy = y1 - int(min(profit, max_profit) / max_profit * plot_h)
        return cx, cy

    # ── Shaded R:R zones (semi-transparent feel via solid fill on panel) ──
    zone_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    zd = ImageDraw.Draw(zone_layer)

    # Polygon clip helper: fill region {risk <= max_risk, 0 <= profit <= max_profit}
    # bounded by a slope line profit = k * risk (k = R:R multiple)
    def shade_above(k: float, rgba: tuple[int, int, int, int]) -> None:
        # Region above profit = k*risk inside the plot box
        pts = [(x0, y1)]  # origin
        # walk along the line until it exits the box
        if k * max_risk <= max_profit:
            # exits through right edge at (max_risk, k*max_risk)
            pts.append(to_xy(max_risk, k * max_risk))
            pts.append((x1, y0))                  # top-right
            pts.append((x0, y0))                  # top-left
        else:
            # exits through top edge at (max_profit/k, max_profit)
            pts.append(to_xy(max_profit / k, max_profit))
            pts.append((x0, y0))                  # top-left
        zd.polygon(pts, fill=rgba)

    # Best zone (R:R ≥ 3) — strong green
    shade_above(3.0, (70, 215, 145, 55))
    # Good zone (R:R ≥ 2) — softer green
    shade_above(2.0, (70, 215, 145, 35))
    # Acceptable zone (R:R ≥ 1) — neutral
    shade_above(1.0, (160, 175, 200, 22))

    img.paste(Image.alpha_composite(img.convert("RGBA"), zone_layer).convert("RGB"))
    d = ImageDraw.Draw(img)

    # ── Plot frame & gridlines ────────────────────────────────────────────
    d.rectangle([(x0, y0), (x1, y1)], outline=pal["grid"], width=1)
    n_grid = 4
    for i in range(1, n_grid + 1):
        gx = x0 + int(i / n_grid * plot_w)
        gy = y1 - int(i / n_grid * plot_h)
        d.line([(gx, y0), (gx, y1)], fill=pal["grid"], width=1)
        d.line([(x0, gy), (x1, gy)], fill=pal["grid"], width=1)
        d.text((gx - 14, y1 + 6), f"{i / n_grid * max_risk:.1f}%",
                font=f_small, fill=pal["muted"])
        d.text((x0 - 56, gy - 6), f"{i / n_grid * max_profit:.1f}%",
                font=f_small, fill=pal["muted"])
    d.text((x0 - 56, y1 - 6), "0%", font=f_small, fill=pal["muted"])
    d.text((x0 - 6,  y1 + 6), "0%", font=f_small, fill=pal["muted"])

    # Axis titles
    d.text((x0 + plot_w // 2 - 50, y1 + 28),
            "Risk  (Stop-Loss distance %)", font=f_axis, fill=pal["text"])
    d.text((6, y0 - 22), "↑ Reward (Expected Profit %)",
            font=f_axis, fill=pal["text"])

    # ── Reference R:R lines: 1:1, 2:1, 3:1 ────────────────────────────────
    for k, lbl, col in [
        (1.0, "R:R 1:1", pal["muted"]),
        (2.0, "R:R 2:1", pal["green"]),
        (3.0, "R:R 3:1", pal["green"]),
    ]:
        if k * max_risk <= max_profit:
            ex, ey = to_xy(max_risk, k * max_risk)
        else:
            ex, ey = to_xy(max_profit / k, max_profit)
        d.line([(x0, y1), (ex, ey)], fill=col, width=1)
        # label near the end of the line
        d.text((ex - 50, ey + 2), lbl, font=f_small, fill=col)

    # ── Plot points with leader lines to avoid overlap ────────────────────
    # Sort by score so small bubbles are drawn first (large on top)
    rows.sort(key=lambda r: r["score"])

    placed: list[tuple[int, int, int, int]] = []  # bounding boxes of labels

    def _label_collides(box: tuple[int, int, int, int]) -> bool:
        for b in placed:
            if not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]):
                return True
        return False

    # Try a sequence of offset directions for label placement
    offsets = [
        (12,  -8),  (12,  8),  (-12, -8), (-12, 8),
        (16, -22), (16, 18), (-16, -22), (-16, 18),
        (24, -36), (-24, -36),
    ]

    for r in rows:
        cx, cy = to_xy(r["risk"], r["profit"])
        rad = 5 + int(min(r["score"], 100) / 18)
        c   = bucket_colour.get(r["bucket"], pal["text"])

        # bubble: filled with bucket colour + thick outline + soft halo
        d.ellipse([(cx - rad - 2, cy - rad - 2), (cx + rad + 2, cy + rad + 2)],
                   outline=pal["panel"], width=2)
        d.ellipse([(cx - rad, cy - rad), (cx + rad, cy + rad)],
                   fill=c, outline=pal["text"], width=1)

        # find a non-overlapping label slot
        sym = r["sym"]
        try:
            tw = int(d.textlength(sym, font=f_lbl))
        except Exception:
            tw = 8 * len(sym)
        th = 14
        chosen = offsets[0]
        for ox, oy in offsets:
            lx = cx + ox + (0 if ox > 0 else -tw)
            ly = cy + oy
            box = (lx - 2, ly - 2, lx + tw + 2, ly + th + 2)
            if (x0 <= box[0] and box[2] <= x1
                    and y0 <= box[1] and box[3] <= y1
                    and not _label_collides(box)):
                chosen = (ox, oy)
                placed.append(box)
                break
        else:
            # fall back: still use first offset
            ox, oy = chosen
            lx = cx + ox + (0 if ox > 0 else -tw)
            ly = cy + oy
            placed.append((lx - 2, ly - 2, lx + tw + 2, ly + th + 2))

        ox, oy = chosen
        lx = cx + ox + (0 if ox > 0 else -tw)
        ly = cy + oy

        # leader line from bubble edge to label
        d.line([(cx, cy), (lx + (tw // 2 if ox < 0 else 0), ly + th // 2)],
                fill=pal["muted"], width=1)
        # label background pill for legibility
        d.rounded_rectangle([(lx - 4, ly - 2), (lx + tw + 4, ly + th + 2)],
                             radius=5, fill=pal["panel2"], outline=pal["grid"])
        d.text((lx, ly), sym, font=f_lbl, fill=pal["text"])

    # ── Legend (horizontal, bottom of card) ───────────────────────────────
    legend_y = height - 28
    legend_x = 16
    for key in ("intraday", "swing", "holding", "sell"):
        col = bucket_colour[key]
        lab = bucket_label[key]
        d.ellipse([(legend_x, legend_y), (legend_x + 14, legend_y + 14)],
                   fill=col, outline=pal["text"])
        d.text((legend_x + 20, legend_y - 1), lab, font=f_lbl, fill=pal["text"])
        try:
            advance = int(d.textlength(lab, font=f_lbl))
        except Exception:
            advance = 9 * len(lab)
        legend_x += 38 + advance

    return img


# ── Chart 3: Sector heatmap (1-day & 1-month avg per sector) ───────────────

def chart_sector_heatmap(
    enriched: list[dict],
    width: int = 560,
    height: int = 340,
    theme: str = "dark",
) -> Image.Image:
    pal = _pal(theme)
    img = Image.new("RGB", (width, height), pal["panel"])
    d = ImageDraw.Draw(img)

    f_title = _font(16, True)
    f_lbl   = _font(11)

    d.text((14, 10), "Sector Performance (avg % change)",
           font=f_title, fill=pal["accent"])

    # Aggregate
    agg: dict[str, dict[str, list[float]]] = {}
    for e in enriched or []:
        sec = (e.get("sector") or "Unknown")[:18]
        t = e.get("tech") or {}
        if "chg_1d_pct" not in t:
            continue
        agg.setdefault(sec, {"d": [], "m": []})
        agg[sec]["d"].append(float(t.get("chg_1d_pct") or 0))
        agg[sec]["m"].append(float(t.get("chg_1m_pct") or 0))

    if not agg:
        d.text((16, 56), "No sector data.", font=f_lbl, fill=pal["muted"])
        return img

    sectors = sorted(
        agg.items(),
        key=lambda kv: sum(kv[1]["m"]) / len(kv[1]["m"]),
        reverse=True,
    )[:10]

    all_vals = [v for sec, s in sectors for v in s["d"] + s["m"]]
    max_abs  = max((abs(v) for v in all_vals), default=3.0) or 3.0

    # Layout: two columns of bars per sector (1D, 1M)
    x0 = 140
    x1 = width - 20
    y0 = 44
    y1 = height - 16
    row_h = (y1 - y0) // len(sectors)
    bar_h = max(6, row_h // 3)
    centre = x0 + (x1 - x0) // 2

    # zero line
    d.line([(centre, y0), (centre, y1)], fill=pal["grid"], width=1)

    for i, (sec, stats) in enumerate(sectors):
        avg_d = sum(stats["d"]) / len(stats["d"])
        avg_m = sum(stats["m"]) / len(stats["m"])
        ry = y0 + i * row_h + 2
        d.text((8, ry + row_h // 2 - 10), sec, font=f_lbl, fill=pal["text"])

        for j, (val, bar_w_mult) in enumerate([(avg_d, 1.0), (avg_m, 1.0)]):
            bar_w = int(abs(val) / max_abs * (x1 - x0) / 2 * bar_w_mult)
            by    = ry + j * (bar_h + 2)
            c     = pal["green"] if val >= 0 else pal["red"]
            if val >= 0:
                d.rectangle([(centre, by), (centre + bar_w, by + bar_h)], fill=c)
            else:
                d.rectangle([(centre - bar_w, by), (centre, by + bar_h)], fill=c)
            tag = "1D" if j == 0 else "1M"
            d.text((x0 - 26, by - 1), tag, font=_font(9), fill=pal["muted"])
            val_txt = f"{val:+.2f}%"
            vx = centre + bar_w + 4 if val >= 0 else centre - bar_w - 4 - _text_w(d, val_txt, f_lbl)
            d.text((vx, by - 1), val_txt, font=_font(10), fill=pal["muted"])

    return img


# ── Chart 4: Macro bars (global markets % change) ──────────────────────────

def chart_macro(
    macro: dict | None,
    width: int = 1150,
    height: int = 180,
    theme: str = "dark",
) -> Image.Image:
    pal = _pal(theme)
    img = Image.new("RGB", (width, height), pal["panel"])
    d = ImageDraw.Draw(img)

    f_title = _font(16, True)
    f_lbl   = _font(12, True)
    f_small = _font(11)

    d.text((14, 10), "Global Markets — Overnight Change (%)",
           font=f_title, fill=pal["accent"])

    snap = (macro or {}).get("snapshot") or {}
    order = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DJI", "Dow"),
             ("VIX", "VIX (Fear)"), ("OIL", "Crude"), ("DXY", "USD"),
             ("GOLD", "Gold"), ("NIFTY", "Nifty 50")]
    items = [(lbl, snap[k]["chg_pct"]) for k, lbl in order
             if snap.get(k) and snap[k].get("chg_pct") is not None]

    if not items:
        d.text((16, 56), "No macro data.", font=f_small, fill=pal["muted"])
        return img

    max_abs = max((abs(v) for _, v in items), default=1.5) or 1.5
    # Layout (columns)
    n = len(items)
    gap    = 14
    col_w  = (width - (n + 1) * gap) // n
    y_mid  = 118
    top    = 48
    bot    = 160

    for i, (lbl, v) in enumerate(items):
        cx = gap + i * (col_w + gap) + col_w // 2
        # VIX up = risk-on negative signal; still colour by raw sign
        colour = pal["green"] if v >= 0 else pal["red"]
        if lbl.startswith("VIX"):
            colour = pal["red"] if v >= 0 else pal["green"]
        bar_len = int(abs(v) / max_abs * 52)
        if v >= 0:
            d.rectangle([(cx - col_w // 3, y_mid - bar_len),
                         (cx + col_w // 3, y_mid)], fill=colour)
        else:
            d.rectangle([(cx - col_w // 3, y_mid),
                         (cx + col_w // 3, y_mid + bar_len)], fill=colour)

        d.line([(cx - col_w // 2, y_mid), (cx + col_w // 2, y_mid)],
               fill=pal["grid"], width=1)
        d.text((cx - _text_w(d, lbl, f_lbl) // 2, bot - 2),
               lbl, font=f_lbl, fill=pal["text"])
        val_txt = f"{v:+.2f}%"
        d.text((cx - _text_w(d, val_txt, f_small) // 2, top - 2),
               val_txt, font=f_small, fill=colour)

    return img


# ── Chart 5: Breadth donut (advancers vs decliners) ────────────────────────

def chart_breadth(
    enriched: list[dict],
    width: int = 560,
    height: int = 210,
    theme: str = "dark",
) -> Image.Image:
    pal = _pal(theme)
    img = Image.new("RGB", (width, height), pal["panel"])
    d = ImageDraw.Draw(img)

    f_title = _font(16, True)
    f_big   = _font(28, True)
    f_lbl   = _font(12)
    f_small = _font(11)

    d.text((14, 10), "Market Breadth",
           font=f_title, fill=pal["accent"])

    adv = dec = flat = 0
    big_up = big_dn = 0
    trending_up = 0
    rsi_list: list[float] = []
    for e in enriched or []:
        t = e.get("tech") or {}
        v = t.get("chg_1d_pct")
        if v is None:
            continue
        if v > 0.2:
            adv += 1
        elif v < -0.2:
            dec += 1
        else:
            flat += 1
        if v >= 2.0:
            big_up += 1
        elif v <= -2.0:
            big_dn += 1
        if t.get("trend_up"):
            trending_up += 1
        rsi_list.append(float(t.get("rsi14") or 50))

    total = adv + dec + flat
    if not total:
        d.text((16, 56), "No breadth data.", font=f_lbl, fill=pal["muted"])
        return img

    # Donut
    cx, cy, r = 100, 115, 62
    # Draw slices using pieslice with hollow centre
    start = -90
    for n, colour in [(adv, pal["green"]), (flat, pal["muted"]), (dec, pal["red"])]:
        if n <= 0:
            continue
        end = start + n / total * 360
        d.pieslice([(cx - r, cy - r), (cx + r, cy + r)], start=start,
                   end=end, fill=colour)
        start = end
    # Hollow
    d.ellipse([(cx - r + 18, cy - r + 18), (cx + r - 18, cy + r - 18)],
              fill=pal["panel"])
    # Centre label
    label = f"{adv}/{total}"
    d.text((cx - _text_w(d, label, f_big) // 2, cy - 18),
           label, font=f_big, fill=pal["text"])
    d.text((cx - _text_w(d, "Up", f_small) // 2, cy + 14),
           "Up", font=f_small, fill=pal["muted"])

    # Legend
    legend_items = [
        ("Advancing",  pal["green"], adv),
        ("Unchanged",  pal["muted"], flat),
        ("Declining",  pal["red"],   dec),
    ]
    ly = 56
    for label_txt, colour, val in legend_items:
        d.rectangle([(180, ly), (192, ly + 10)], fill=colour)
        d.text((198, ly - 2),
               f"{label_txt}  {val}  ({val / total * 100:.0f}%)",
               font=f_lbl, fill=pal["text"])
        ly += 20

    # Stats panel (right side)
    rsi_med = sorted(rsi_list)[len(rsi_list) // 2] if rsi_list else 50
    trend_pct = trending_up / total * 100 if total else 0
    stats = [
        ("Stocks analysed",      f"{total}"),
        ("Trending up (>50/200 EMA)", f"{trending_up} ({trend_pct:.0f}%)"),
        ("Strong gainers (≥ +2%)",   f"{big_up}"),
        ("Strong losers (≤ -2%)",    f"{big_dn}"),
        ("Median RSI(14)",            f"{rsi_med:.0f}"),
    ]
    sx = 370
    sy = 50
    for k, v in stats:
        d.text((sx, sy), k, font=f_small, fill=pal["muted"])
        d.text((sx + 170, sy), v, font=f_lbl, fill=pal["text"])
        sy += 24

    return img


# ── Chart 6: Confidence distribution bar ───────────────────────────────────

def chart_confidence_hist(
    buckets: dict,
    width: int = 560,
    height: int = 200,
    theme: str = "dark",
) -> Image.Image:
    pal = _pal(theme)
    img = Image.new("RGB", (width, height), pal["panel"])
    d = ImageDraw.Draw(img)

    f_title = _font(16, True)
    f_small = _font(11)

    d.text((14, 10), "Prediction Confidence Distribution",
           font=f_title, fill=pal["accent"])

    confs: list[int] = []
    for key in ("intraday", "swing", "holding"):
        for p in (buckets.get(key) or []):
            pr = p.get("predict") or {}
            if pr.get("confidence") is not None:
                confs.append(int(pr["confidence"]))

    if not confs:
        d.text((16, 56), "No predictions.", font=f_small, fill=pal["muted"])
        return img

    # Buckets: 0–49, 50–59, 60–69, 70–79, 80–100
    bins   = [(0, 50, "<50%"), (50, 60, "50–59"), (60, 70, "60–69"),
              (70, 80, "70–79"), (80, 101, "80+")]
    counts = []
    for lo, hi, _ in bins:
        counts.append(sum(1 for c in confs if lo <= c < hi))

    max_c = max(counts) or 1
    x0, y0 = 40, 44
    x1, y1 = width - 20, height - 24
    bar_gap = 14
    bar_w = (x1 - x0 - bar_gap * (len(bins) - 1)) // len(bins)

    colour_for = {"<50%": pal["red"], "50–59": pal["amber"],
                  "60–69": pal["accent"], "70–79": pal["green"],
                  "80+": pal["violet"]}

    for i, ((lo, hi, lbl), cnt) in enumerate(zip(bins, counts)):
        bx = x0 + i * (bar_w + bar_gap)
        bh = int(cnt / max_c * (y1 - y0 - 12))
        by = y1 - bh
        d.rectangle([(bx, by), (bx + bar_w, y1)], fill=colour_for[lbl])
        d.text((bx + bar_w // 2 - 6, y1 + 4), lbl,
               font=f_small, fill=pal["muted"])
        d.text((bx + bar_w // 2 - 4, by - 14), str(cnt),
               font=_font(12, True), fill=pal["text"])

    return img
