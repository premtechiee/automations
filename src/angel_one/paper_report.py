"""
src/angel_one/paper_report.py
==================================
Build a rich performance report for paper-trading sessions.

Pulls everything from `data/paper_trader_state.json` (written by
`auto_trader.TraderState.save`) and computes the standard trading
metrics traders care about: win-rate, profit factor, expectancy,
average win / loss, biggest win / loss, per-symbol and per-bucket
breakdowns, plus an open-positions table.

The report is returned as a plain-text string suitable for `print`
or pushing through WhatsApp / Telegram, and is also written to
`data/paper_reports/YYYY-MM-DD_HHMM.txt` for archival.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .auto_trader import TraderState, _PAPER_STATE_FILE, OpenTrade, _now_ist

_REPORTS_DIR = Path("data") / "paper_reports"


def _trade_dicts(state: TraderState) -> list[dict]:
    """All closed trades — today + history — as plain dicts."""
    rows: list[dict] = []
    for t in state.closed_today:
        rows.append(asdict(t))
    rows.extend(state.history or [])
    return rows


def _stats(trades: Iterable[dict]) -> dict:
    """Compute headline stats for a list of closed trades."""
    trades = list(trades)
    n      = len(trades)
    wins   = [t for t in trades if (t.get("realised_pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("realised_pnl") or 0) < 0]
    flats  = [t for t in trades if (t.get("realised_pnl") or 0) == 0]

    gross_win  = sum(t["realised_pnl"] for t in wins)
    gross_loss = sum(t["realised_pnl"] for t in losses)   # negative
    net_pnl    = gross_win + gross_loss

    avg_win  = (gross_win / len(wins))    if wins   else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    win_rate = (len(wins) / n * 100)      if n      else 0.0

    profit_factor = (gross_win / abs(gross_loss)) if gross_loss else float("inf") if gross_win else 0.0
    expectancy    = (net_pnl / n)                  if n           else 0.0

    biggest_win  = max((t["realised_pnl"] for t in wins),   default=0.0)
    biggest_loss = min((t["realised_pnl"] for t in losses), default=0.0)

    return {
        "trades":        n,
        "wins":          len(wins),
        "losses":        len(losses),
        "flats":         len(flats),
        "win_rate":      win_rate,
        "gross_win":     gross_win,
        "gross_loss":    gross_loss,
        "net_pnl":       net_pnl,
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "profit_factor": profit_factor,
        "expectancy":    expectancy,
        "biggest_win":   biggest_win,
        "biggest_loss":  biggest_loss,
    }


def _by_key(trades: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        groups[str(t.get(key, "?"))].append(t)
    return {k: _stats(v) for k, v in groups.items()}


def _line(ch: str = "─", n: int = 64) -> str:
    return ch * n


def _hdr(title: str) -> str:
    return f"\n{title}\n{_line()}"


def build_report(state: TraderState | None = None,
                 starting_cash: float = 100000.0) -> str:
    """Return a multi-section text report. Pass `state` to override loading."""
    state = state or TraderState.load(_PAPER_STATE_FILE, paper=True)
    closed = _trade_dicts(state)
    s      = _stats(closed)

    cur_cash = starting_cash + state.cumulative_pnl
    pct_ret  = (state.cumulative_pnl / starting_cash * 100) if starting_cash else 0.0

    out: list[str] = []
    out.append(_line("═"))
    out.append(f"  PAPER-TRADING PERFORMANCE REPORT".center(64))
    out.append(f"  generated {_now_ist():%Y-%m-%d %H:%M IST}".center(64))
    out.append(_line("═"))

    # ── Capital ──
    out.append(_hdr("CAPITAL"))
    out.append(f"  Starting cash       : ₹{starting_cash:>14,.2f}")
    out.append(f"  Current equity*     : ₹{cur_cash:>14,.2f}   "
               f"(*excludes open MTM)")
    out.append(f"  Cumulative P&L      : ₹{state.cumulative_pnl:>+14,.2f}   "
               f"({pct_ret:+.2f}%)")
    out.append(f"  Today's realised    : ₹{state.realised_pnl:>+14,.2f}")
    if state.halted:
        out.append(f"  ⚠ HALTED            : {state.halted_reason}")

    # ── Performance ──
    out.append(_hdr("PERFORMANCE  (all closed trades)"))
    if s["trades"] == 0:
        out.append("  No closed trades yet.")
    else:
        out.append(f"  Trades closed       : {s['trades']:>14d}")
        out.append(f"  Wins / Losses       : {s['wins']:>5d} / {s['losses']:<5d}"
                   f"   (flats {s['flats']})")
        out.append(f"  Win rate            : {s['win_rate']:>13.2f}%")
        out.append(f"  Net P&L             : ₹{s['net_pnl']:>+14,.2f}")
        out.append(f"  Gross win / loss    : ₹{s['gross_win']:>+14,.2f}  /  "
                   f"₹{s['gross_loss']:>+,.2f}")
        out.append(f"  Average win         : ₹{s['avg_win']:>+14,.2f}")
        out.append(f"  Average loss        : ₹{s['avg_loss']:>+14,.2f}")
        pf = s["profit_factor"]
        pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"
        out.append(f"  Profit factor       : {pf_str:>14}")
        out.append(f"  Expectancy / trade  : ₹{s['expectancy']:>+14,.2f}")
        out.append(f"  Biggest win         : ₹{s['biggest_win']:>+14,.2f}")
        out.append(f"  Biggest loss        : ₹{s['biggest_loss']:>+14,.2f}")

    # ── By bucket ──
    if closed:
        out.append(_hdr("BY BUCKET"))
        out.append(f"  {'Bucket':<10}{'N':>4}  {'Win%':>6}  {'Net P&L':>14}  {'PF':>6}")
        for bk, st in sorted(_by_key(closed, "bucket").items()):
            pf  = st["profit_factor"]
            pfs = "∞" if pf == float("inf") else f"{pf:.2f}"
            out.append(f"  {bk:<10}{st['trades']:>4}  {st['win_rate']:>5.1f}%  "
                       f"₹{st['net_pnl']:>+12,.2f}  {pfs:>6}")

        # ── By symbol (top 10 by |net P&L|) ──
        out.append(_hdr("BY SYMBOL  (top 10 by |net P&L|)"))
        out.append(f"  {'Symbol':<14}{'N':>4}  {'Win%':>6}  {'Net P&L':>14}  {'PF':>6}")
        sym_stats = _by_key(closed, "symbol")
        ranked = sorted(sym_stats.items(), key=lambda kv: -abs(kv[1]["net_pnl"]))[:10]
        for sym, st in ranked:
            pf  = st["profit_factor"]
            pfs = "∞" if pf == float("inf") else f"{pf:.2f}"
            out.append(f"  {sym:<14}{st['trades']:>4}  {st['win_rate']:>5.1f}%  "
                       f"₹{st['net_pnl']:>+12,.2f}  {pfs:>6}")

        # ── By exit reason ──
        out.append(_hdr("BY EXIT REASON"))
        out.append(f"  {'Status':<12}{'N':>4}  {'Win%':>6}  {'Net P&L':>14}")
        for st_key, st in sorted(_by_key(closed, "status").items()):
            out.append(f"  {st_key:<12}{st['trades']:>4}  {st['win_rate']:>5.1f}%  "
                       f"₹{st['net_pnl']:>+12,.2f}")

    # ── Open positions ──
    out.append(_hdr(f"OPEN POSITIONS  ({len(state.open_trades)})"))
    if not state.open_trades:
        out.append("  (none)")
    else:
        out.append(f"  {'Symbol':<14}{'Bkt':<8}{'Qty':>5}  "
                   f"{'Entry':>9}  {'SL':>9}  {'Target':>9}  Opened")
        for t in state.open_trades:
            out.append(f"  {t.symbol:<14}{t.bucket:<8}{t.qty:>5}  "
                       f"{t.entry_price:>9.2f}  {t.sl:>9.2f}  {t.target:>9.2f}  "
                       f"{t.opened_at[:16]}")
        # Total committed capital
        committed = sum(t.entry_price * t.qty for t in state.open_trades)
        out.append(f"  {'─' * 60}")
        out.append(f"  Capital committed   : ₹{committed:>+14,.2f}")

    # ── Closed today ──
    out.append(_hdr(f"CLOSED TODAY  ({len(state.closed_today)})"))
    if not state.closed_today:
        out.append("  (none)")
    else:
        out.append(f"  {'Symbol':<14}{'Qty':>5}  {'Entry':>9}  {'Exit':>9}  "
                   f"{'P&L':>11}  Status")
        for t in state.closed_today:
            ex = t.exit_price if t.exit_price is not None else 0.0
            out.append(f"  {t.symbol:<14}{t.qty:>5}  {t.entry_price:>9.2f}  "
                       f"{ex:>9.2f}  ₹{t.realised_pnl:>+9,.2f}  {t.status}")

    # ── Recent history ──
    if state.history:
        out.append(_hdr(f"RECENT CLOSED TRADES  (last {min(15, len(state.history))})"))
        out.append(f"  {'Closed':<19}  {'Symbol':<14}{'Qty':>5}  "
                   f"{'P&L':>11}  Status")
        for h in state.history[-15:]:
            out.append(f"  {(h.get('closed_at') or '')[:19]:<19}  "
                       f"{h.get('symbol',''):<14}{h.get('qty',0):>5}  "
                       f"₹{h.get('realised_pnl',0):>+9,.2f}  "
                       f"{h.get('status','')}")

    out.append(_line("═"))
    return "\n".join(out)


def save_report(text: str) -> Path:
    """Write the report to `data/paper_reports/<timestamp>.txt` and mirror a
    copy under `logs/stock_analyzer/<date>/` for the per-run audit trail."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    p = _REPORTS_DIR / f"{_now_ist():%Y-%m-%d_%H%M}.txt"
    p.write_text(text, encoding="utf-8")
    try:
        from lib.logging_setup import archive_artifact
        archive_artifact("angel_one", p, subdir="paper_reports")
    except Exception:
        pass
    return p


# ── Image rendering ─────────────────────────────────────────────────────────
# Compact PNG dashboard built with PIL — used by the WhatsApp/Telegram
# notifier to deliver the paper-trading summary as a picture instead of a
# wall of monospaced text (which renders poorly on mobile).

# Modern dark palette
_BG          = (17, 24, 39)        # slate-900
_PANEL       = (31, 41, 55)        # slate-800
_PANEL_ALT   = (24, 33, 47)
_BORDER      = (55, 65, 81)        # slate-700
_TEXT        = (243, 244, 246)     # gray-100
_MUTED       = (156, 163, 175)     # gray-400
_ACCENT      = (251, 191, 36)      # amber-400
_GREEN       = (34, 197, 94)       # green-500
_RED         = (239, 68, 68)       # red-500
_BLUE        = (96, 165, 250)      # blue-400


def _load_font(size: int, bold: bool = False, mono: bool = False):
    from PIL import ImageFont
    candidates: list[str] = []
    if mono:
        candidates += [
            "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
            "consola.ttf", "cour.ttf",
        ]
    else:
        candidates += [
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "arialbd.ttf" if bold else "arial.ttf",
            "seguisb.ttf" if bold else "segoeui.ttf",
        ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _money(v: float, signed: bool = False) -> str:
    sign = "+" if signed and v > 0 else ("-" if v < 0 else ("+" if signed else ""))
    return f"{sign}₹{abs(v):,.0f}"


def _pnl_color(v: float) -> tuple:
    if v > 0:
        return _GREEN
    if v < 0:
        return _RED
    return _MUTED


def render_report_image(
    state: TraderState | None = None,
    starting_cash: float = 100000.0,
    out_path: Path | str | None = None,
    max_open_rows: int = 8,
    max_closed_rows: int = 8,
    max_history_rows: int = 6,
) -> Path:
    """Render a compact PNG dashboard of the paper-trading state.

    Returns the path to the saved image.
    """
    from PIL import Image, ImageDraw

    state  = state or TraderState.load(_PAPER_STATE_FILE, paper=True)
    closed = _trade_dicts(state)
    s      = _stats(closed)

    cur_equity = starting_cash + state.cumulative_pnl
    pct_ret    = (state.cumulative_pnl / starting_cash * 100) if starting_cash else 0.0

    # Fonts
    f_title  = _load_font(28, bold=True)
    f_sub    = _load_font(14)
    f_h      = _load_font(15, bold=True)
    f_kpi_l  = _load_font(11)
    f_kpi_v  = _load_font(20, bold=True)
    f_lbl    = _load_font(12)
    f_val    = _load_font(13, bold=True)
    f_th     = _load_font(11, bold=True, mono=True)
    f_td     = _load_font(11, mono=True)
    f_foot   = _load_font(10)

    W   = 760
    pad = 20

    # ── Compute dynamic height ──
    n_open    = min(len(state.open_trades),  max_open_rows)
    n_closed  = min(len(state.closed_today), max_closed_rows)
    n_hist    = min(len(state.history or []), max_history_rows) if not n_closed else 0
    bk_stats  = _by_key(closed, "bucket") if closed else {}

    H = pad
    H += 70                                      # header
    H += 88                                      # capital strip
    H += 100                                     # KPI grid
    if bk_stats:
        H += 36 + 24 * len(bk_stats) + 12        # by-bucket
    H += 36 + (24 * max(1, n_open)) + 12         # open positions
    if n_closed:
        H += 36 + 24 * n_closed + 12             # closed today
    elif n_hist:
        H += 36 + 24 * n_hist + 12               # recent history
    H += 28                                      # footer
    H += pad

    img  = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)

    # ── Header ──
    draw.rectangle([(0, 0), (W, 70)], fill=_PANEL)
    draw.rectangle([(0, 70), (W, 73)], fill=_ACCENT)
    draw.text((pad, 14), "PAPER TRADING REPORT", fill=_TEXT, font=f_title)
    draw.text((pad, 48), f"Generated  {_now_ist():%a %d %b %Y · %H:%M IST}",
              fill=_MUTED, font=f_sub)
    if state.halted:
        tag = " HALTED "
        tw  = int(draw.textlength(tag, font=f_h))
        draw.rounded_rectangle([(W - pad - tw - 16, 22), (W - pad, 50)],
                                radius=6, fill=_RED)
        draw.text((W - pad - tw - 8, 28), tag, fill=_TEXT, font=f_h)

    y = 70 + pad

    # ── Capital strip (3 columns) ──
    strip_h = 78
    draw.rounded_rectangle([(pad, y), (W - pad, y + strip_h)],
                            radius=10, fill=_PANEL, outline=_BORDER, width=1)
    col_w = (W - 2 * pad) / 3
    cols = [
        ("STARTING CASH",   _money(starting_cash),                _TEXT),
        ("CURRENT EQUITY",  _money(cur_equity),                   _TEXT),
        ("CUMULATIVE P&L",  f"{_money(state.cumulative_pnl, signed=True)}  ({pct_ret:+.2f}%)",
                                                                  _pnl_color(state.cumulative_pnl)),
    ]
    for i, (lbl, val, col) in enumerate(cols):
        cx = pad + int(col_w * i) + 16
        draw.text((cx, y + 12), lbl, fill=_MUTED, font=f_kpi_l)
        draw.text((cx, y + 32), val, fill=col,    font=f_kpi_v)
    # Today's realised in small text under cumulative
    draw.text((pad + int(col_w * 2) + 16, y + 60),
              f"Today: {_money(state.realised_pnl, signed=True)}",
              fill=_pnl_color(state.realised_pnl), font=f_lbl)
    y += strip_h + 14

    # ── KPI grid (4 boxes) ──
    if s["trades"]:
        pf = s["profit_factor"]
        pf_str = "∞" if pf == float("inf") else f"{pf:.2f}"
        kpis = [
            ("TRADES",        f"{s['trades']}",                 _TEXT),
            ("WIN RATE",      f"{s['win_rate']:.1f}%",          _GREEN if s['win_rate'] >= 50 else _RED),
            ("NET P&L",       _money(s['net_pnl'], signed=True), _pnl_color(s['net_pnl'])),
            ("PROFIT FACTOR", pf_str,                            _GREEN if pf >= 1 else _RED),
        ]
        sub = [
            f"{s['wins']}W / {s['losses']}L / {s['flats']}F",
            f"avg win {_money(s['avg_win'])}  loss {_money(s['avg_loss'])}",
            f"best {_money(s['biggest_win'], signed=True)}  worst {_money(s['biggest_loss'], signed=True)}",
            f"expectancy {_money(s['expectancy'], signed=True)}/trade",
        ]
    else:
        kpis = [
            ("TRADES",        "0",   _MUTED),
            ("WIN RATE",      "—",   _MUTED),
            ("NET P&L",       "₹0",  _MUTED),
            ("PROFIT FACTOR", "—",   _MUTED),
        ]
        sub = ["no closed trades yet", "", "", ""]

    box_h = 92
    gap   = 10
    box_w = (W - 2 * pad - 3 * gap) / 4
    for i, ((lbl, val, col), s_line) in enumerate(zip(kpis, sub)):
        x0 = pad + int((box_w + gap) * i)
        x1 = int(x0 + box_w)
        draw.rounded_rectangle([(x0, y), (x1, y + box_h)],
                                radius=10, fill=_PANEL_ALT, outline=_BORDER, width=1)
        draw.text((x0 + 12, y + 10), lbl, fill=_MUTED, font=f_kpi_l)
        draw.text((x0 + 12, y + 28), val, fill=col,    font=f_kpi_v)
        draw.text((x0 + 12, y + 64), s_line, fill=_MUTED, font=f_kpi_l)
    y += box_h + 14

    # ── Helpers for table sections ──
    def _section_header(title: str, count: int | None = None) -> int:
        nonlocal y
        label = title if count is None else f"{title}  ({count})"
        draw.text((pad, y), label, fill=_ACCENT, font=f_h)
        draw.line([(pad, y + 22), (W - pad, y + 22)], fill=_BORDER, width=1)
        y += 30
        return y

    def _row(cells: list[tuple[str, int, tuple, str]]) -> None:
        """cells = [(text, x, color, align)]  align in {'l','r'}."""
        nonlocal y
        for text, x, col, align in cells:
            if align == "r":
                tw = int(draw.textlength(text, font=f_td))
                draw.text((x - tw, y), text, fill=col, font=f_td)
            else:
                draw.text((x, y), text, fill=col, font=f_td)
        y += 22

    # ── By bucket (compact) ──
    if bk_stats:
        _section_header("BY BUCKET")
        # Header row
        cols_x = [pad + 8, pad + 110, pad + 200, pad + 320, pad + 440]
        for txt, cx in zip(["Bucket", "N", "Win%", "Net P&L", "PF"], cols_x):
            draw.text((cx, y), txt, fill=_MUTED, font=f_th)
        y += 20
        for bk, st in sorted(bk_stats.items()):
            pf  = st["profit_factor"]
            pfs = "∞" if pf == float("inf") else f"{pf:.2f}"
            _row([
                (bk,                        cols_x[0], _TEXT,                  "l"),
                (str(st["trades"]),         cols_x[1], _TEXT,                  "l"),
                (f"{st['win_rate']:.1f}%",  cols_x[2], _TEXT,                  "l"),
                (_money(st["net_pnl"], signed=True), cols_x[3], _pnl_color(st["net_pnl"]), "l"),
                (pfs,                       cols_x[4], _TEXT,                  "l"),
            ])
        y += 6

    # ── Open positions ──
    _section_header("OPEN POSITIONS", len(state.open_trades))
    if not state.open_trades:
        draw.text((pad + 8, y), "(none)", fill=_MUTED, font=f_td)
        y += 22
    else:
        cols_x = [pad + 8, pad + 130, pad + 200, pad + 290, pad + 380, pad + 470, pad + 560]
        hdrs   = ["Symbol", "Bkt", "Qty", "Entry", "SL", "Target", "Opened"]
        for txt, cx in zip(hdrs, cols_x):
            draw.text((cx, y), txt, fill=_MUTED, font=f_th)
        y += 20
        for t in state.open_trades[:max_open_rows]:
            _row([
                (t.symbol[:14],             cols_x[0], _TEXT,  "l"),
                (t.bucket[:6],              cols_x[1], _MUTED, "l"),
                (str(t.qty),                cols_x[2], _TEXT,  "l"),
                (f"{t.entry_price:.2f}",    cols_x[3], _TEXT,  "l"),
                (f"{t.sl:.2f}",             cols_x[4], _RED,   "l"),
                (f"{t.target:.2f}",         cols_x[5], _GREEN, "l"),
                ((t.opened_at or "")[5:16], cols_x[6], _MUTED, "l"),
            ])
        if len(state.open_trades) > max_open_rows:
            draw.text((pad + 8, y), f"… +{len(state.open_trades) - max_open_rows} more",
                      fill=_MUTED, font=f_td)
            y += 22
    y += 6

    # ── Closed today (or recent history if nothing closed today) ──
    if n_closed:
        _section_header("CLOSED TODAY", len(state.closed_today))
        cols_x = [pad + 8, pad + 130, pad + 200, pad + 290, pad + 380, pad + 490]
        hdrs   = ["Symbol", "Qty", "Entry", "Exit", "P&L", "Status"]
        for txt, cx in zip(hdrs, cols_x):
            draw.text((cx, y), txt, fill=_MUTED, font=f_th)
        y += 20
        for t in state.closed_today[:max_closed_rows]:
            ex = t.exit_price if t.exit_price is not None else 0.0
            _row([
                (t.symbol[:14],             cols_x[0], _TEXT, "l"),
                (str(t.qty),                cols_x[1], _TEXT, "l"),
                (f"{t.entry_price:.2f}",    cols_x[2], _TEXT, "l"),
                (f"{ex:.2f}",               cols_x[3], _TEXT, "l"),
                (_money(t.realised_pnl, signed=True), cols_x[4], _pnl_color(t.realised_pnl), "l"),
                (t.status,                  cols_x[5], _MUTED, "l"),
            ])
    elif n_hist:
        _section_header("RECENT TRADES", min(len(state.history), max_history_rows))
        cols_x = [pad + 8, pad + 170, pad + 290, pad + 360, pad + 470]
        hdrs   = ["Closed", "Symbol", "Qty", "P&L", "Status"]
        for txt, cx in zip(hdrs, cols_x):
            draw.text((cx, y), txt, fill=_MUTED, font=f_th)
        y += 20
        for h in (state.history or [])[-max_history_rows:]:
            pnl = float(h.get("realised_pnl", 0))
            _row([
                ((h.get("closed_at") or "")[:16], cols_x[0], _MUTED, "l"),
                (str(h.get("symbol",""))[:14],    cols_x[1], _TEXT,  "l"),
                (str(h.get("qty", 0)),            cols_x[2], _TEXT,  "l"),
                (_money(pnl, signed=True),        cols_x[3], _pnl_color(pnl), "l"),
                (str(h.get("status","")),         cols_x[4], _MUTED, "l"),
            ])

    # ── Footer ──
    draw.text((pad, H - pad - 14),
              "Paper trading • virtual capital • not real orders",
              fill=_MUTED, font=f_foot)

    # ── Save ──
    if out_path is None:
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _REPORTS_DIR / f"{_now_ist():%Y-%m-%d_%H%M}.png"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)

    try:
        from lib.logging_setup import archive_artifact
        archive_artifact("angel_one", out_path, subdir="paper_reports")
    except Exception:
        pass
    return out_path
