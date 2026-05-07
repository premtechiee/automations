"""Filesystem layout for the automations repo.

The backend reads/serves files from these paths. They are all resolved relative
to the repository root (the parent of the ``server/`` package), so the API
works regardless of the process cwd.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
LOGS_DIR = REPO_ROOT / "logs"

STOCK_REPORTS_DIR = DATA_DIR / "stock_reports"
STOCK_REPORTS_INDEX = STOCK_REPORTS_DIR / "_index.json"
PAPER_REPORTS_DIR = DATA_DIR / "paper_reports"
PAPER_REPORTS_LAST = PAPER_REPORTS_DIR / "_last_run.txt"
PAPER_STATE = DATA_DIR / "paper_trader_state.json"
LIVE_STATE = DATA_DIR / "auto_trader_state.json"
GOLD_MODEL = DATA_DIR / "gold_prediction_model.json"

LOGS_STOCK_DIR = LOGS_DIR / "stock_analyzer"
LOGS_GOLD_DIR = LOGS_DIR / "gold_notifier"
LOGS_ANGEL_DIR = LOGS_DIR / "angel_one"
