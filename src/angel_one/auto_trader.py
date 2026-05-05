"""
src/angel_one/auto_trader.py
==================================
Auto-trading engine. Consumes the stock-analyzer pipeline's picks
(`data/stock_reports/`) and routes BUY / SL / TGT decisions through
Angel One — live or paper.

What it does
------------
1. Loads the most-recent saved report (today's intraday/swing picks).
2. Polls live LTPs through Angel One.
3. For each pick, decides whether to BUY (entry triggered), SL-EXIT
   (stop-loss hit), or TARGET-EXIT (target hit).
4. Sizes each position using `available_cash * MAX_PCT_PER_TRADE`.
5. Places the order through `lib.angelone.place_order()` (gated by
   `ANGEL_TRADING_ENABLED=1` — without it everything stays as dry-runs).
6. Persists order state to `data/auto_trader_state.json` so the same
   pick is not re-ordered on every tick.
7. Optionally pushes WhatsApp/Telegram alerts on fill / reject / exit.

Safety rails (all configurable via env vars)
--------------------------------------------
  AUTO_TRADE_MAX_POSITIONS         max simultaneous open trades   (default 5)
  AUTO_TRADE_MAX_DAILY_LOSS_INR    halt trading if today's pnl <= -N (default 5000)
  AUTO_TRADE_MAX_PCT_PER_TRADE     fraction of cash per trade     (default 0.10)
  AUTO_TRADE_MIN_QTY               minimum shares per order       (default 1)
  AUTO_TRADE_BUCKETS               which buckets to trade         (default "intraday,swing")
  AUTO_TRADE_DRY_RUN               1 → never transmit even if ANGEL_TRADING_ENABLED=1
  AUTO_TRADE_NOTIFY_CHANNEL        whatsapp | telegram | none     (default none)

Usage
-----
    # one-shot tick (for testing / cron-driven mode)
    python scripts/angel_one.py auto-trade --once

    # foreground loop (poll every 60s during market hours)
    python scripts/angel_one.py auto-trade
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, time as dtime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Indian Standard Time (UTC + 5:30). Used everywhere a wall-clock decision
# is made so the auto-trader behaves identically on a Windows dev box,
# a Linux server, and a UTC-timezoned GitHub Actions runner.
_IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(_IST)

# Lazy imports so this module remains importable without Angel creds.
def _angel():
    from lib import angelone
    return angelone


_STATE_FILE       = Path("data") / "auto_trader_state.json"
_PAPER_STATE_FILE = Path("data") / "paper_trader_state.json"
_REPORTS_DIR  = Path("data") / "stock_reports"
_REPORTS_IDX  = _REPORTS_DIR / "_index.json"

# Indian market hours (IST)
_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class TraderConfig:
    max_positions:        int   = 6
    max_daily_loss_inr:   float = 5000.0
    max_pct_per_trade:    float = 0.15        # hard cap on notional per trade
    max_risk_pct_per_trade: float = 0.005     # risk-per-trade as fraction of equity (0.5%)
    entry_band_pct:       float = 0.010       # |LTP-entry|/entry must be <= this to fill
    trail_activate_pct:   float = 0.012       # arm trailing stop once price > entry by this %
    trail_distance_pct:   float = 0.008       # trail SL this far below the running peak
    cost_pct_round_trip:  float = 0.0015      # brokerage + STT + slippage proxy (round-trip)
    min_qty:              int   = 1
    buckets:              tuple = ("intraday", "swing")
    dry_run:              bool  = True
    notify_channel:       str   = "none"
    poll_interval_sec:    int   = 60
    paper:                bool  = False    # paper-trading mode (separate state file, never transmits)
    paper_starting_cash:  float = 100000.0 # virtual ₹ to size positions in paper mode

    @classmethod
    def from_env(cls, paper: bool = False) -> "TraderConfig":
        def _i(k, d): return int(os.environ.get(k, str(d)))
        def _f(k, d): return float(os.environ.get(k, str(d)))
        bk = os.environ.get("AUTO_TRADE_BUCKETS", "intraday,swing")
        buckets = tuple(b.strip() for b in bk.split(",") if b.strip())
        # Dry-run default is TRUE unless user opts in to live trading.
        # Paper mode forces dry_run=True regardless of env vars.
        ang_live = os.environ.get("ANGEL_TRADING_ENABLED") == "1"
        dry      = (os.environ.get("AUTO_TRADE_DRY_RUN", "1") == "1") or not ang_live
        if paper:
            dry = True
        return cls(
            max_positions          = _i("AUTO_TRADE_MAX_POSITIONS",        6),
            max_daily_loss_inr     = _f("AUTO_TRADE_MAX_DAILY_LOSS_INR",   5000),
            max_pct_per_trade      = _f("AUTO_TRADE_MAX_PCT_PER_TRADE",    0.15),
            max_risk_pct_per_trade = _f("AUTO_TRADE_MAX_RISK_PCT_PER_TRADE", 0.005),
            entry_band_pct         = _f("AUTO_TRADE_ENTRY_BAND_PCT",       0.010),
            trail_activate_pct     = _f("AUTO_TRADE_TRAIL_ACTIVATE_PCT",   0.012),
            trail_distance_pct     = _f("AUTO_TRADE_TRAIL_DISTANCE_PCT",   0.008),
            cost_pct_round_trip    = _f("AUTO_TRADE_COST_PCT",             0.0015),
            min_qty                = _i("AUTO_TRADE_MIN_QTY",              1),
            buckets                = buckets,
            dry_run                = dry,
            notify_channel         = os.environ.get("AUTO_TRADE_NOTIFY_CHANNEL", "none").lower(),
            poll_interval_sec      = _i("AUTO_TRADE_POLL_SEC",             60),
            paper                  = paper,
            paper_starting_cash    = _f("PAPER_STARTING_CASH",             100000),
        )

    @property
    def state_file(self) -> Path:
        return _PAPER_STATE_FILE if self.paper else _STATE_FILE


# ── State ────────────────────────────────────────────────────────────────────

@dataclass
class OpenTrade:
    symbol:      str
    bucket:      str
    side:        str            # "BUY" (long) — shorting not supported yet
    qty:         int
    entry_price: float
    sl:          float
    target:      float
    order_id:    str | None = None
    opened_at:   str        = ""
    status:      str        = "OPEN"     # OPEN | CLOSED_SL | CLOSED_TGT | CLOSED_EOD
    closed_at:   str | None = None
    exit_price:  float | None = None
    realised_pnl: float = 0.0
    # Trailing-stop bookkeeping (defaults preserve backward-compat with
    # state files written before these fields existed)
    peak_price:    float = 0.0    # running peak LTP since entry
    initial_sl:    float = 0.0    # SL at entry; trailing only ratchets above this
    trail_active:  bool  = False  # True once trail_activate_pct profit reached


@dataclass
class TraderState:
    date:         str               = ""
    open_trades:  list[OpenTrade]   = field(default_factory=list)
    closed_today: list[OpenTrade]   = field(default_factory=list)
    realised_pnl: float             = 0.0
    halted:       bool              = False
    halted_reason: str              = ""
    # Paper-trading: cumulative stats across all sessions
    cumulative_pnl:  float          = 0.0
    cumulative_wins: int            = 0
    cumulative_losses: int          = 0
    history:      list              = field(default_factory=list)  # appended closed trades

    @classmethod
    def load(cls, path: Path = _STATE_FILE, paper: bool = False) -> "TraderState":
        if not path.exists():
            return cls(date=_today())
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            st = cls(
                date         = raw.get("date", _today()),
                open_trades  = [OpenTrade(**t) for t in raw.get("open_trades", [])],
                closed_today = [OpenTrade(**t) for t in raw.get("closed_today", [])],
                realised_pnl = float(raw.get("realised_pnl", 0)),
                halted       = bool(raw.get("halted", False)),
                halted_reason= raw.get("halted_reason", ""),
                cumulative_pnl    = float(raw.get("cumulative_pnl", 0)),
                cumulative_wins   = int(raw.get("cumulative_wins", 0)),
                cumulative_losses = int(raw.get("cumulative_losses", 0)),
                history           = raw.get("history", []),
            )
            # Reset between trading days. For paper mode, archive the day to
            # `history` and reset open/realised but KEEP cumulative stats so
            # we can see overall P&L over weeks/months of paper trading.
            if st.date != _today():
                if paper:
                    for t in st.closed_today:
                        st.history.append(asdict(t))
                    st.history = st.history[-500:]
                    logger.info(f"paper-trader: new day, archived {len(st.closed_today)} "
                                f"trades (cumulative ₹{st.cumulative_pnl:+,.0f})")
                else:
                    logger.info(f"auto-trader: new day ({_today()}), resetting state")
                # Reset day-scoped fields, keep cumulative
                st.date         = _today()
                st.realised_pnl = 0.0
                st.halted       = False
                st.halted_reason = ""
                st.closed_today = []
                # Open trades carry over (swing positions are multi-day)
            return st
        except Exception as exc:
            logger.warning(f"trader state corrupted ({exc}) — starting fresh")
            return cls(date=_today())

    def save(self, path: Path = _STATE_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date":              self.date,
            "open_trades":       [asdict(t) for t in self.open_trades],
            "closed_today":      [asdict(t) for t in self.closed_today],
            "realised_pnl":      self.realised_pnl,
            "halted":            self.halted,
            "halted_reason":     self.halted_reason,
            "cumulative_pnl":    self.cumulative_pnl,
            "cumulative_wins":   self.cumulative_wins,
            "cumulative_losses": self.cumulative_losses,
            "history":           self.history,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _today() -> str:
    return _now_ist().strftime("%Y-%m-%d")


# ── Picks loader ─────────────────────────────────────────────────────────────

def _load_latest_picks() -> dict[str, list[dict]] | None:
    """Returns the `buckets` dict from the most recent saved report."""
    if not _REPORTS_IDX.exists():
        logger.warning("auto-trader: no report index found — run the analyzer first")
        return None
    try:
        idx = json.loads(_REPORTS_IDX.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not idx:
        return None
    latest = _REPORTS_DIR / idx[-1]
    if not latest.exists():
        return None
    try:
        rep = json.loads(latest.read_text(encoding="utf-8"))
        return rep.get("buckets") or {}
    except Exception as exc:
        logger.warning(f"auto-trader: cannot parse {latest}: {exc}")
        return None


# ── Notifications ────────────────────────────────────────────────────────────

def _notify(channel: str, msg: str, image_path: str | Path | None = None) -> dict:
    """Push `msg` to the configured channel.

    If `image_path` is given, the image is sent and `msg` is used as the
    caption. Falls back to plain text if the image upload fails.

    Returns a delivery summary: ``{"channel", "image_sent", "text_sent",
    "recipients", "image_failed", "text_failed"}`` so callers can log a
    truthful outcome instead of assuming success.
    """
    summary = {
        "channel":      (channel or "none").lower(),
        "image_sent":   0,
        "text_sent":    0,
        "image_failed": 0,
        "text_failed":  0,
        "recipients":   0,
    }
    channel = summary["channel"]
    if channel == "none":
        return summary
    img = str(image_path) if image_path and Path(image_path).exists() else None
    try:
        if channel == "telegram":
            from src.angel_one.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
            from lib.telegram import send_message as tg, send_photo as tg_photo
            summary["recipients"] = 1
            if img:
                if tg_photo(TELEGRAM_CHAT_ID, img, msg, TELEGRAM_BOT_TOKEN):
                    summary["image_sent"] = 1
                    return summary
                summary["image_failed"] = 1
                logger.warning("telegram photo failed — falling back to text")
            if tg(TELEGRAM_CHAT_ID, msg, TELEGRAM_BOT_TOKEN):
                summary["text_sent"] = 1
            else:
                summary["text_failed"] = 1
        elif channel == "whatsapp":
            from src.angel_one.config import (
                PHONE_NUMBERS, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL
            )
            from lib.whatsapp import send_message as wa, send_image as wa_img
            for p in PHONE_NUMBERS:
                if not p:
                    continue
                summary["recipients"] += 1
                sent = False
                if img:
                    sent = bool(wa_img(p, img, msg, GREEN_API_INSTANCE,
                                       GREEN_API_TOKEN, GREEN_API_URL))
                    if sent:
                        summary["image_sent"] += 1
                    else:
                        summary["image_failed"] += 1
                        logger.warning(f"whatsapp image failed for {p} — falling back to text")
                if not sent:
                    if wa(p, msg, GREEN_API_INSTANCE, GREEN_API_TOKEN, GREEN_API_URL):
                        summary["text_sent"] += 1
                    else:
                        summary["text_failed"] += 1
    except Exception as exc:
        logger.warning(f"auto-trader notify failed: {exc}")
    return summary


# ── Sizing ───────────────────────────────────────────────────────────────────

def _calc_qty(price: float, sl: float, available_cash: float,
              total_equity: float, cfg: TraderConfig) -> int:
    """Risk-based position sizing.

    Quantity is the **smaller** of:
      • risk-budget qty:  ``equity * max_risk_pct / stop_distance``
      • notional cap qty: ``available_cash * max_pct_per_trade / price``

    This equalises rupee-risk per trade (so tight-SL names get bigger size,
    wide-SL names get smaller) while still capping the notional exposure.
    Falls back to the old notional-only sizing if SL is missing/invalid.
    """
    if price <= 0 or available_cash <= 0:
        return 0
    qty_cap = int((available_cash * cfg.max_pct_per_trade) // price)
    stop_dist = price - sl if sl and sl > 0 else 0.0
    if stop_dist <= 0:
        # No usable stop → fall back to notional cap only
        return max(0, qty_cap)
    risk_budget = max(total_equity, available_cash) * cfg.max_risk_pct_per_trade
    qty_risk    = int(risk_budget // stop_dist)
    return max(0, min(qty_risk, qty_cap))


# ── Decision logic ───────────────────────────────────────────────────────────

@dataclass
class Action:
    kind:   str              # "OPEN" | "CLOSE_SL" | "CLOSE_TGT"
    pick:   dict | None      = None
    trade:  OpenTrade | None = None
    qty:    int              = 0
    price:  float            = 0.0
    bucket: str              = ""
    reason: str              = ""


def _decide(picks: dict[str, list[dict]],
             state: TraderState,
             ltps: dict[str, dict],
             funds: dict,
             cfg: TraderConfig,
             at_eod: bool = False) -> list[Action]:
    actions: list[Action] = []

    # 1. Exit checks on every open trade (SL / target / EOD).
    # Also runs the trailing-stop ratchet so SL only ever moves up (never
    # down) once price has run sufficiently in our favour.
    open_syms = {t.symbol for t in state.open_trades}
    for t in state.open_trades:
        live = ltps.get(t.symbol) or {}
        ltp  = float(live.get("ltp") or 0)
        if ltp <= 0:
            # No live price — can only force-close at EOD using last known
            # entry price as a fallback so the trade doesn't leak forever.
            if at_eod and t.bucket == "intraday":
                actions.append(Action("CLOSE_EOD", trade=t, qty=t.qty,
                                       price=t.entry_price,
                                       reason="EOD close (no LTP, flat)"))
            continue
        if t.side == "BUY":
            # ── Trailing stop ─────────────────────────────────────────
            # Track running peak; once unrealised gain crosses the
            # activation threshold, ratchet SL up to (peak * (1-trail_dist)).
            # SL never moves down — this only protects profit, never widens risk.
            if not t.initial_sl:
                t.initial_sl = t.sl
            t.peak_price = max(t.peak_price or t.entry_price, ltp)
            gain_pct = (t.peak_price - t.entry_price) / t.entry_price if t.entry_price else 0.0
            if gain_pct >= cfg.trail_activate_pct:
                t.trail_active = True
            if t.trail_active:
                trailed = t.peak_price * (1.0 - cfg.trail_distance_pct)
                if trailed > t.sl:
                    t.sl = round(trailed, 2)

            if ltp <= t.sl:
                reason = (f"trailing-SL hit @ {ltp:.2f} (peak {t.peak_price:.2f})"
                          if t.trail_active else f"SL hit @ {ltp:.2f}")
                actions.append(Action("CLOSE_SL", trade=t, qty=t.qty,
                                       price=ltp, reason=reason))
            elif ltp >= t.target:
                actions.append(Action("CLOSE_TGT", trade=t, qty=t.qty,
                                       price=ltp, reason=f"target @ {ltp:.2f}"))
            elif at_eod and t.bucket == "intraday":
                actions.append(Action("CLOSE_EOD", trade=t, qty=t.qty,
                                       price=ltp,
                                       reason=f"EOD square-off @ {ltp:.2f}"))

    # 2. New-entry checks. Skip if halted, full, this symbol already open,
    #    or we're in the EOD pass / outside market hours.
    if state.halted:
        return actions
    if at_eod:
        return actions
    if not is_market_open():
        # Don't open new positions pre-market or post-close — LTPs may be
        # stale (e.g. last close from previous session) and would mis-fire.
        return actions
    if len(state.open_trades) >= cfg.max_positions:
        return actions
    cash = float(funds.get("available_cash") or 0)
    slots_left = cfg.max_positions - len(state.open_trades)

    for bucket in cfg.buckets:
        if slots_left <= 0:
            break
        for pk in (picks.get(bucket) or []):
            if slots_left <= 0:
                break
            sym = pk.get("symbol")
            if not sym or sym in open_syms:
                continue
            lv  = pk.get("levels") or {}
            entry  = float(lv.get("entry")  or 0)
            sl     = float(lv.get("sl")     or 0)
            target = float(lv.get("target") or 0)
            if entry <= 0 or sl <= 0 or target <= 0:
                continue
            live = ltps.get(sym) or {}
            ltp  = float(live.get("ltp") or 0)
            if ltp <= 0:
                continue
            # Long entry trigger: live price within entry_band_pct of the
            # planned entry, AND above SL (so risk:reward is still intact).
            within = abs(ltp - entry) / entry <= cfg.entry_band_pct
            if not within or ltp <= sl:
                continue
            # Equity used for risk-budget: cash + open MTM (paper) or just cash (live).
            equity_for_risk = cash
            if cfg.paper:
                equity_for_risk = cfg.paper_starting_cash + state.cumulative_pnl
            qty = _calc_qty(ltp, sl, cash, equity_for_risk, cfg)
            if qty < cfg.min_qty:
                continue
            actions.append(Action("OPEN", pick=pk, qty=qty, price=ltp,
                                   bucket=bucket,
                                   reason=f"entry @ {ltp:.2f} (SL {sl:.2f}, "
                                          f"tgt {target:.2f})"))
            slots_left -= 1
            cash      -= qty * ltp     # local reservation for the same tick

    return actions


# ── Order placement wrapper ─────────────────────────────────────────────────

def _place(action: Action, cfg: TraderConfig) -> dict:
    a   = _angel()
    if action.kind == "OPEN":
        return a.place_order(
            symbol=action.pick["symbol"], side="BUY", qty=action.qty,
            order_type="MARKET", product="INTRADAY",
            dry_run=cfg.dry_run,
        )
    if action.kind in ("CLOSE_SL", "CLOSE_TGT", "CLOSE_EOD"):
        return a.place_order(
            symbol=action.trade.symbol, side="SELL", qty=action.qty,
            order_type="MARKET", product="INTRADAY",
            dry_run=cfg.dry_run,
        )
    return {"ok": False, "message": f"unknown action {action.kind}"}


# ── Apply action to state ───────────────────────────────────────────────────

def _apply(action: Action, result: dict, state: TraderState,
            cfg: TraderConfig) -> str:
    """Update state in-place and return a human-readable message."""
    now = _now_ist().strftime("%Y-%m-%d %H:%M:%S")
    tag = "DRY" if cfg.dry_run else "LIVE"
    if not result.get("ok"):
        return f"[FAIL] [{tag}] {action.kind} {action.reason} -> {result.get('message')}"

    oid = result.get("order_id")

    if action.kind == "OPEN":
        pk = action.pick
        lv = pk.get("levels") or {}
        sl_open = float(lv.get("sl") or 0)
        t = OpenTrade(
            symbol      = pk["symbol"],
            bucket      = action.bucket,
            side        = "BUY",
            qty         = action.qty,
            entry_price = action.price,
            sl          = sl_open,
            target      = float(lv.get("target") or 0),
            order_id    = oid,
            opened_at   = now,
            peak_price  = action.price,
            initial_sl  = sl_open,
            trail_active= False,
        )
        state.open_trades.append(t)
        return (f"[OPEN] [{tag}] {t.symbol} qty={t.qty} @ Rs {action.price:.2f} "
                f"SL Rs {t.sl:.2f} TGT Rs {t.target:.2f} (order={oid})")

    if action.kind in ("CLOSE_SL", "CLOSE_TGT", "CLOSE_EOD"):
        t = action.trade
        gross = (action.price - t.entry_price) * t.qty
        # Round-trip transaction cost proxy: brokerage + STT + slippage.
        # Modelled as a flat % of the average notional so it scales naturally.
        avg_notional = ((action.price + t.entry_price) / 2.0) * t.qty
        cost = avg_notional * cfg.cost_pct_round_trip
        pnl  = gross - cost
        t.status       = ("CLOSED_SL"  if action.kind == "CLOSE_SL"  else
                          "CLOSED_TGT" if action.kind == "CLOSE_TGT" else
                          "CLOSED_EOD")
        t.closed_at    = now
        t.exit_price   = action.price
        t.realised_pnl = round(pnl, 2)
        state.open_trades = [x for x in state.open_trades if x is not t]
        state.closed_today.append(t)
        state.realised_pnl = round(state.realised_pnl + pnl, 2)
        state.cumulative_pnl = round(state.cumulative_pnl + pnl, 2)
        if pnl >= 0:
            state.cumulative_wins += 1
        else:
            state.cumulative_losses += 1
        if (state.realised_pnl <= -abs(cfg.max_daily_loss_inr)) and not state.halted:
            state.halted        = True
            state.halted_reason = (f"daily loss limit hit "
                                   f"(Rs {state.realised_pnl:,.0f})")
        tag_close = ("[SL]"  if action.kind == "CLOSE_SL"  else
                     "[TGT]" if action.kind == "CLOSE_TGT" else
                     "[EOD]")
        return (f"{tag_close} [{tag}] CLOSE {t.symbol} qty={t.qty} @ Rs {action.price:.2f} "
                f"P&L Rs {pnl:+,.0f} (gross Rs {gross:+,.0f}, cost Rs {cost:.0f}; {action.reason})")

    return f"? {action}"


# ── Main entry points ───────────────────────────────────────────────────────

def is_market_open() -> bool:
    # Local-test override: ``AUTO_TRADE_FORCE_MARKET_OPEN=1`` bypasses the
    # 09:15–15:30 IST window so you can exercise entry logic outside hours.
    # Never set this in CI — LTPs will be stale and trades will mis-fire.
    if os.environ.get("AUTO_TRADE_FORCE_MARKET_OPEN") == "1":
        return True
    # Always evaluate against IST — Indian markets run 09:15–15:30 IST
    # regardless of the runner's local timezone (e.g. UTC on GitHub Actions).
    now_ist = _now_ist()
    t = now_ist.time()
    if t < _MARKET_OPEN or t > _MARKET_CLOSE:
        return False
    # Skip weekends. Indian markets are closed Sat/Sun.
    if now_ist.weekday() >= 5:
        return False
    return True


def tick(cfg: TraderConfig | None = None, at_eod: bool = False) -> dict:
    """One iteration of the trading loop. Safe to call from cron.

    When ``at_eod`` is True, all open *intraday* positions are squared off at
    the current LTP (or last entry price if LTP unavailable) and no new
    entries are taken — use this for the 15:30/15:45 IST EOD job.
    """
    cfg = cfg or TraderConfig.from_env()
    state = TraderState.load(cfg.state_file, paper=cfg.paper)

    # If already halted today, just report and bail.
    if state.halted:
        logger.warning(f"trader halted: {state.halted_reason}")
        return {"ok": False, "halted": True, "reason": state.halted_reason}

    a = _angel()
    if not a.is_available():
        return {"ok": False, "message": "Angel One not authenticated"}

    picks = _load_latest_picks()
    if not picks:
        return {"ok": False, "message": "no picks available"}

    # Paper mode uses a fixed virtual cash balance instead of broker funds.
    if cfg.paper:
        spent = sum(t.entry_price * t.qty for t in state.open_trades)
        funds = {"available_cash": max(0.0, cfg.paper_starting_cash
                                            + state.cumulative_pnl - spent)}
    else:
        funds = a.fetch_funds() or {}

    # Collect every symbol we care about (open trades + new candidates)
    needed: set[str] = {t.symbol for t in state.open_trades}
    for bk in cfg.buckets:
        for pk in (picks.get(bk) or []):
            if pk.get("symbol"):
                needed.add(pk["symbol"])
    ltps: dict[str, dict] = {}
    for s in needed:
        live = a.fetch_ltp(s)
        if live:
            ltps[s] = live

    actions = _decide(picks, state, ltps, funds, cfg, at_eod=at_eod)
    msgs: list[str] = []
    for act in actions:
        result = _place(act, cfg)
        msg = _apply(act, result, state, cfg)
        msgs.append(msg)
        logger.info(msg)
        _notify(cfg.notify_channel, msg)

    state.save(cfg.state_file)
    return {
        "ok":              True,
        "actions":         len(actions),
        "open_trades":     len(state.open_trades),
        "closed_today":    len(state.closed_today),
        "realised_pnl":    state.realised_pnl,
        "cumulative_pnl":  state.cumulative_pnl,
        "halted":          state.halted,
        "messages":        msgs,
    }


def run_loop(cfg: TraderConfig | None = None) -> None:
    """Foreground loop. Polls until market closes."""
    cfg = cfg or TraderConfig.from_env()
    logger.info(f"auto-trader loop starting (poll {cfg.poll_interval_sec}s, "
                f"dry_run={cfg.dry_run}, channel={cfg.notify_channel})")
    while True:
        if not is_market_open():
            logger.info("market closed — auto-trader idle, sleeping 5 min")
            time.sleep(300)
            continue
        try:
            res = tick(cfg)
            if res.get("actions"):
                logger.info(f"tick: {res}")
        except Exception as exc:
            logger.exception(f"auto-trader tick failed: {exc}")
        time.sleep(cfg.poll_interval_sec)
